import os
import subprocess
import sys
import re
import argparse

# This dictionary should ideally be loaded from the database, but we'll use it as a fallback
# for the Shanghai demo, or let the script find paths.
# We'll rely on the AI Director to provide absolute paths in the plan.

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMP_DIR = os.path.join(BASE_DIR, "VLOG_BUILD")
os.makedirs(TEMP_DIR, exist_ok=True)

def run_ffmpeg(cmd):
    # Print the command being run
    print(f"Running: {' '.join(cmd)}", flush=True)
    
    # We use Popen instead of run so we get real-time lines printed to stdout
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1 # Line buffered
    )
    
    for line in iter(process.stdout.readline, ''):
        print(line, end='', flush=True)
        
    process.stdout.close()
    return_code = process.wait()
    
    if return_code != 0:
        print(f"\nError: FFmpeg exited with code {return_code}", flush=True)
        sys.exit(return_code)

def get_clip_duration(path: str) -> float:
    """Return the duration of a media file in seconds using ffprobe."""
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
             '-of', 'default=noprint_wrappers=1:nokey=1', path],
            capture_output=True, text=True
        )
        return float(result.stdout.strip())
    except Exception:
        return float('inf')  # Unknown — don't clamp


def generate_black_clip(output_path: str, duration: float = 0.5):
    """Deprecated: Fades are now applied directly to transitions."""
    pass


def process_scene(scene):
    scene_id = scene['id']
    arolls = scene['aroll']
    overlays = scene['overlays']
    
    # 1. Trim A-Rolls
    aroll_files = []
    for j, aroll in enumerate(arolls):
        seg_id = f"{scene_id}_{j}"
        output_path = os.path.join(TEMP_DIR, f"{seg_id}_aroll.mp4")
        duration = float(aroll["end"]) - float(aroll["start"])
        
        # Accurate Output Seeking Trim A-Roll + Normalize to 720p 29.97fps 48kHz
        trim_cmd = [
            'ffmpeg', '-i', aroll["path"], '-ss', aroll["start"], '-t', str(duration),
            '-vf', 'scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,format=yuv420p',
            '-r', '30000/1001',
            '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '23', 
            '-c:a', 'aac', '-ar', '48000', '-ac', '2', '-y', output_path
        ]
        run_ffmpeg(trim_cmd)
        aroll_files.append(output_path)
        
    if not aroll_files:
        print(f"Warning: Scene {scene_id} has no valid A-roll segments. Skipping scene.", flush=True)
        return None
        
    # 2. Concat A-Rolls for the scene
    list_path = os.path.join(TEMP_DIR, f"{scene_id}_aroll_list.txt")
    with open(list_path, "w") as f:
        for a in aroll_files:
            f.write(f"file '{os.path.basename(a)}'\n")
            
    scene_aroll_concat = os.path.join(TEMP_DIR, f"{scene_id}_aroll_concat.mp4")
    concat_cmd = [
        'ffmpeg', '-f', 'concat', '-safe', '0', '-i', list_path,
        '-c', 'copy', '-y', scene_aroll_concat
    ]
    run_ffmpeg(concat_cmd)
    
    if not overlays:
        return scene_aroll_concat
        
    # 3. Apply Complex Filter for Overlays
    current_input = scene_aroll_concat
    for i, overlay in enumerate(overlays):
        broll_path = overlay['path']
        broll_trim_start = float(overlay['trim_start'])
        broll_trim_end = float(overlay['trim_end'])
        overlay_at = float(overlay['at'])

        # Clamp trim to actual clip duration so out-of-range LLM values don't produce empty files.
        clip_dur = get_clip_duration(broll_path)
        if broll_trim_start >= clip_dur:
            print(f"[WARN] B-roll trim start {broll_trim_start}s exceeds clip duration {clip_dur:.1f}s for {broll_path} — skipping overlay", flush=True)
            continue
        broll_trim_end = min(broll_trim_end, clip_dur)
        broll_duration = broll_trim_end - broll_trim_start
        if broll_duration <= 0:
            print(f"[WARN] B-roll duration <= 0 after clamping for {broll_path} — skipping overlay", flush=True)
            continue

        next_output = os.path.join(TEMP_DIR, f"{scene_id}_ovl_{i}.mp4")
        
        # 1) Pre-trim the B-roll to guarantee frame-accuracy and prevent empty video streams
        broll_temp = os.path.join(TEMP_DIR, f"{scene_id}_broll_trim_{i}.mp4")
        pretrim_cmd = [
            'ffmpeg', '-i', broll_path, '-ss', str(broll_trim_start), '-t', str(broll_duration),
            '-vf', 'scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,format=yuv420p',
            '-r', '30000/1001',
            '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '23', 
            '-c:a', 'aac', '-ar', '48000', '-ac', '2', '-y', broll_temp
        ]
        run_ffmpeg(pretrim_cmd)

        # Guard: if the pretrim produced an empty file (e.g. seek beyond eof), skip overlay.
        if not os.path.exists(broll_temp) or os.path.getsize(broll_temp) < 1024:
            print(f"[WARN] Pre-trimmed B-roll is empty for {broll_path} — skipping overlay", flush=True)
            continue
        
        # 2) Use filter_complex to overlay the already-trimmed broll
        # Note: B-roll audio is omitted by default, allowing A-roll audio to pass through.
        filter_str = f"[1:v]scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,setpts=PTS-STARTPTS+{overlay_at}/TB [ov]; [0:v][ov] overlay=eof_action=pass:enable='between(t,{overlay_at},{overlay_at + broll_duration})'"
        
        cmd = [
            'ffmpeg', '-i', current_input, '-i', broll_temp,
            '-filter_complex', filter_str, 
            '-r', '30000/1001',
            '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '23', 
            '-c:a', 'aac', '-ar', '48000', '-ac', '2', '-y', next_output
        ]
        run_ffmpeg(cmd)
        current_input = next_output
        
    return current_input

def parse_plan(plan_path):
    scenes = []
    current_scene = None
    current_mode = None
    
    def to_sec(val):
        if not val: return "0"
        if ':' in val:
            parts = val.split(':')
            if len(parts) == 2: return str(float(parts[0])*60 + float(parts[1]))
            if len(parts) == 3: return str(float(parts[0])*3600 + float(parts[1])*60 + float(parts[2]))
        return val.replace(':', '.')
    
    # Helper to extract absolute path from the thumbnail markdown
    def extract_path(line):
        # Use a greedy match for the URL so that filenames with parentheses
        # (e.g. "1080p(4).mov") don't truncate the path at the first ")".
        # The markdown format is: ![alt](url) — we want everything inside the
        # LAST pair of parens, so we match up to the final closing paren.
        match = re.search(r'!\[.*?\]\((.+)\)', line)
        if match:
            url = match.group(1)
            # Find the path= parameter (stop at &)
            path_match = re.search(r'path=([^&]+)', url)
            if path_match:
                import urllib.parse
                return urllib.parse.unquote(path_match.group(1))
        return None

    with open(plan_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line: continue
            
            if line.startswith("## **SCENE"):
                if current_scene: scenes.append(current_scene)
                # Sanitize Scene ID: Take everything after SCENE X:
                parts = line.split(":")
                raw_id = parts[1].strip().lower().replace(" ", "_") if len(parts) > 1 else line.replace("#", "").strip().lower().replace(" ", "_").replace("*", "")
                clean_id = re.sub(r'[^a-zA-Z0-9_]', '', raw_id)
                current_scene = {"id": clean_id, "aroll": [], "overlays": []}
            elif line.startswith("*   **A-ROLL:**"):
                current_mode = 'A'
            elif line.startswith("*   **B-ROLL OVERLAYS:**"):
                current_mode = 'B'
            elif current_mode == 'A' and re.search(r'^[\*\-\s]*Segment', line, re.IGNORECASE):
                match = re.search(r'\[([\d\.:]+)\s*-\s*([\d\.:]+)\]', line)
                if match and current_scene is not None:
                    path = extract_path(line)
                    if path:
                        current_scene["aroll"].append({
                            "path": path,
                            "start": to_sec(match.group(1)),
                            "end": to_sec(match.group(2))
                        })
            elif current_mode == 'B' and line.startswith("*   `"):
                # Matches format: `*   `/Path.MOV` | Trim: [start - end] | Overlay @ time ![thumbnail](...)`
                trim_match = re.search(r'Trim:\s*\[([\d\.:]+)\s*-\s*([\d\.:]+)\]', line)
                overlay_match = re.search(r'Overlay\s*@\s*([\d\.:]+)', line)
                path = extract_path(line)
                
                if path and overlay_match and current_scene is not None:
                    try:
                        overlay_time = to_sec(overlay_match.group(1))
                            
                        t_start = "0"
                        t_end = "10" # Default 10s if trim format goes wrong
                        if trim_match:
                            t_start = to_sec(trim_match.group(1))
                            t_end = to_sec(trim_match.group(2))
                            
                        current_scene["overlays"].append({
                            "path": path,
                            "trim_start": t_start,
                            "trim_end": t_end,
                            "at": str(overlay_time)
                        })
                    except ValueError:
                        pass
                        
    if current_scene: scenes.append(current_scene)
    return scenes

def main():
    parser = argparse.ArgumentParser(description='Build a vlog from a story plan.')
    parser.add_argument('plan_path', help='Path to the story plan markdown file')
    parser.add_argument('--dip-transitions', nargs='*', type=int, default=[], metavar='N',
                        help='Scene gap indices (0-based) that get a dip to black (e.g. 0 2)')
    parser.add_argument('--fade-to-black', action='store_true',
                        help='Apply a 1-second fade to black at the end of the final video')
    parser.add_argument('--scene-titles', nargs='*', default=[],
                        help='Scene titles in "index:title" format (e.g. "0:Intro" "1:Walking")')
    parser.add_argument('--lower-thirds', nargs='*', type=int, default=[],
                        help='Indices of scenes that should have lower thirds titles displayed')
    args = parser.parse_args()

    plan_path = args.plan_path
    dip_set = set(args.dip_transitions or [])
    fade_to_black = args.fade_to_black
    
    # Parse scene titles: {"0": "Title", ...}
    scene_titles_map = {}
    for st in args.scene_titles:
        if ':' in st:
            idx_str, title = st.split(':', 1)
            scene_titles_map[int(idx_str)] = title
            
    lower_thirds_set = set(args.lower_thirds or [])

    # Clear the temporary build directory before starting
    print(f"Cleaning temporary build directory: {TEMP_DIR}")
    for filename in os.listdir(TEMP_DIR):
        file_path = os.path.join(TEMP_DIR, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
        except Exception as e:
            print(f'Failed to delete {file_path}. Reason: {e}')

    scenes = parse_plan(plan_path)

    build_list = []
    # Identify a font path for macOS (fallback for the demo)
    macos_font = "/System/Library/Fonts/Supplemental/Helvetica.ttc"
    if not os.path.exists(macos_font):
        macos_font = "Helvetica" # Fallback to generic font name

    for i, scene in enumerate(scenes):
        final_scene_file = process_scene(scene)
        if not final_scene_file:
            continue
            
        # Apply Lower Third if requested
        if i in lower_thirds_set and i in scene_titles_map:
            title = scene_titles_map[i].replace("'", "").replace(":", "") # Basic sanitize
            titled_scene_file = final_scene_file.replace(".mp4", "_titled.mp4")
            print(f"Applying lower third to scene {i}: '{title}'", flush=True)
            
            # Create a separate transparent stream for the lower third
            # Duration of 5 seconds: Fade in for 1s, hold for 3s, fade out for 1s.
            # Alpha faded then overlaid onto the main video.
            lt_filter = (
                f"color=c=black@0.6:s=1280x60:d=5:rate=30000/1001,format=rgba [box]; "
                f"[box]drawtext=text='{title}':fontcolor=white:fontsize=36:x=40:y=(h-th)/2:fontfile={macos_font} [lt]; "
                f"[lt]fade=t=in:st=0:d=1:alpha=1,fade=t=out:st=4:d=1:alpha=1 [lt_faded]; "
                f"[0:v][lt_faded]overlay=x=0:y=H-h-40:eof_action=pass:shortest=0"
            )
            
            lt_cmd = [
                'ffmpeg', '-i', final_scene_file,
                '-filter_complex', lt_filter,
                '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '23',
                '-c:a', 'copy', '-y', titled_scene_file
            ]
            run_ffmpeg(lt_cmd)
            final_scene_file = titled_scene_file
            
        build_list.append(final_scene_file)

    if not build_list:
        print("\nError: No valid scenes could be built (likely due to missing A-Roll data).", flush=True)
        sys.exit(1)

    # Apply Fades for Dip-to-Black transitions
    faded_build_list = []
    for i, b in enumerate(build_list):
        need_fade_in = (i > 0 and (i - 1) in dip_set)
        need_fade_out = (i < len(build_list) - 1 and i in dip_set)
        
        if need_fade_in or need_fade_out:
            duration = get_clip_duration(b)
            faded_scene_file = b.replace(".mp4", "_faded.mp4")
            v_filters = []
            a_filters = []
            
            if need_fade_in:
                v_filters.append("fade=t=in:st=0:d=0.5")
                a_filters.append("afade=t=in:st=0:d=0.5")
            if need_fade_out:
                fade_out_start = max(0.0, duration - 0.5)
                v_filters.append(f"fade=t=out:st={fade_out_start:.3f}:d=0.5")
                a_filters.append(f"afade=t=out:st={fade_out_start:.3f}:d=0.5")
            
            print(f"Applying dip-to-black fades to scene {i}...", flush=True)
            fade_cmd = [
                'ffmpeg', '-i', b,
                '-vf', ",".join(v_filters),
                '-af', ",".join(a_filters),
                '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '23',
                '-c:a', 'aac', '-ar', '48000', '-ac', '2', '-y', faded_scene_file
            ]
            run_ffmpeg(fade_cmd)
            faded_build_list.append(faded_scene_file)
        else:
            faded_build_list.append(b)

    # FINAL CONCAT
    final_list_path = os.path.join(TEMP_DIR, "final_list.txt")
    with open(final_list_path, "w") as f:
        for b in faded_build_list:
            f.write(f"file '{os.path.basename(b)}'\n")

    output_dir = os.path.join(BASE_DIR, "VLOG_OUTPUT")
    os.makedirs(output_dir, exist_ok=True)
    final_output = os.path.join(output_dir, f"VLOG_BUILD_{os.path.basename(plan_path).replace('.md', '')}.mp4")
    concat_cmd = [
        'ffmpeg', '-f', 'concat', '-safe', '0', '-i', final_list_path,
        '-c', 'copy', '-y', final_output
    ]
    run_ffmpeg(concat_cmd)

    # FADE TO BLACK — re-encode final output with 1s fade at the end
    if fade_to_black:
        duration = get_clip_duration(final_output)
        fade_start = max(0.0, duration - 1.0)
        faded_output = final_output.replace('.mp4', '_fading.mp4')
        print(f"Applying fade to black (start={fade_start:.2f}s)...", flush=True)
        fade_cmd = [
            'ffmpeg', '-i', final_output,
            '-vf', f'fade=t=out:st={fade_start:.3f}:d=1',
            '-af', f'afade=t=out:st={fade_start:.3f}:d=1',
            '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '23',
            '-c:a', 'aac', '-ar', '48000', '-ac', '2', '-y', faded_output
        ]
        run_ffmpeg(fade_cmd)
        os.replace(faded_output, final_output)

    # Cleanup (Disabled for debugging)
    # import shutil
    # shutil.rmtree(TEMP_DIR, ignore_errors=True)
    print(f"\nSUCCESS: Created {final_output}")

if __name__ == "__main__":
    main()
