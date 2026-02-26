import os
import json
import subprocess
import re
import tempfile
import mlx_whisper
import sqlite3
from datetime import datetime

# Configuration
WHISPER_MODEL = "mlx-community/whisper-small-mlx"
VISION_MODEL = "mlx-community/nanoLLaVA-1.5-8bit"

def _load_config():
    settings_path = os.path.join(os.path.dirname(__file__), "backend", "settings.json")
    if os.path.exists(settings_path):
        with open(settings_path, "r") as f:
            return json.load(f)
    return {}

config = _load_config()
DB_PATH = config.get("dbPath", os.path.join(os.path.dirname(__file__), "Video_Archive.db"))
EDITS_DIR = os.path.join(os.path.dirname(DB_PATH), "Edits")
os.makedirs(EDITS_DIR, exist_ok=True)

def get_precise_segments(video_path):
    print(f"\n[Audio] Transcribing: {os.path.basename(video_path)}")
    try:
        result = mlx_whisper.transcribe(video_path, path_or_hf_repo=WHISPER_MODEL, language="en")
        return result.get('segments', [])
    except Exception as e:
        print(f"  Transcription Error: {e}")
        return []

def get_vision_for_segment(video_path, start_time, end_time, segment_id):
    clean_id = re.sub(r'[^a-zA-Z0-9]', '_', str(segment_id))
    mid_point = (start_time + end_time) / 2
    frame_path = os.path.join(tempfile.gettempdir(), f"edit_segment_{clean_id}.jpg")
    timestamp_str = f"{mid_point:.3f}"
    
    cmd = ['ffmpeg', '-ss', timestamp_str, '-i', video_path, '-vframes', '1', '-q:v', '2', '-update', '1', frame_path, '-y', '-loglevel', 'error']
    subprocess.run(cmd, capture_output=True)
    
    if not os.path.exists(frame_path):
        return "No visual data"
    
    prompt = "Describe exactly what is in this video frame in one short sentence."
    vlm_cmd = f"python3 -m mlx_vlm.generate --model {VISION_MODEL} --image {frame_path} --prompt '{prompt}' --max-tokens 30"
    result = subprocess.run(vlm_cmd, shell=True, capture_output=True, text=True)
    
    raw = result.stdout
    content = "Visual analysis failed"
    if "assistant" in raw.lower():
        parts = re.split(r"assistant", raw, flags=re.IGNORECASE)
        if len(parts) > 1:
            content = parts[1].split("==========")[0].strip()
        content = content.replace("mx.metal.get_peak_memory is deprecated and will be removed in a future version. Use mx.get_peak_memory instead.", "").strip()
    
    if os.path.exists(frame_path):
        os.remove(frame_path)
    return content

def save_analysis(theme_name, timeline):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = os.path.join(EDITS_DIR, f"{theme_name}_{timestamp}.json")
    md_path = os.path.join(EDITS_DIR, f"{theme_name}_{timestamp}.md")
    
    # Save JSON
    with open(json_path, 'w') as f:
        json.dump(timeline, f, indent=4)
    
    # Save Markdown
    with open(md_path, 'w') as f:
        f.write(f"# 🎬 Director AI: Rough Cut Analysis - {theme_name}\n")
        f.write(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        current_file = ""
        for entry in timeline:
            if entry['file'] != current_file:
                f.write(f"\n## 🎞 File: {entry['file']}\n")
                current_file = entry['file']
            
            f.write(f"**[{entry['start']:05.2f}s - {entry['end']:05.2f}s]**\n")
            f.write(f"- 🗣 **SAYING:** {entry['text']}\n")
            f.write(f"- 👁 **SEEING:** {entry['visual']}\n\n")
            
    print(f"\n[System] Analysis saved to:\n  JSON: {json_path}\n  Markdown: {md_path}")

def run_batch_by_date(target_date):
    print(f"[System] Starting Surgical Analysis for: {target_date}")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT path, filename FROM videos WHERE date(created) = ? ORDER BY filename ASC", (target_date,))
    videos = cursor.fetchall()
    conn.close()
    
    if not videos:
        print("No videos found for this date.")
        return

    master_timeline = []
    for path, filename in videos:
        segments = get_precise_segments(path)
        
        if not segments:
            print(f"  [B-Roll] {filename}")
            visual = get_vision_for_segment(path, 1.0, 2.0, "broll_" + filename)
            master_timeline.append({
                "file": filename, "path": path, "start": 0, "end": 5, "text": "[B-ROLL]", "visual": visual
            })
            continue

        for i, seg in enumerate(segments):
            start, end, text = seg['start'], seg['end'], seg['text'].strip()
            if not text or (end - start) < 0.5: continue
            
            print(f"  [{start:05.2f}s -> {end:05.2f}s] Analyzing visual...")
            visual = get_vision_for_segment(path, start, end, f"{filename}_{i}")
            master_timeline.append({
                "file": filename, "path": path, "start": start, "end": end, "text": text, "visual": visual
            })
            
    save_analysis(f"Shanghai_{target_date.replace('-','_')}", master_timeline)

if __name__ == "__main__":
    import sys
    date_to_process = sys.argv[1] if len(sys.argv) > 1 else "2011-09-17"
    run_batch_by_date(date_to_process)
