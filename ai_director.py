import os
import sqlite3
import argparse
import sys
import re
import subprocess
import mlx_whisper
import urllib.parse
import json

def _load_config():
    settings_path = os.path.join(os.path.dirname(__file__), "backend", "settings.json")
    if os.path.exists(settings_path):
        with open(settings_path, "r") as f:
            return json.load(f)
    return {}

config = _load_config()
DB_PATH = config.get("dbPath", os.path.join(os.path.dirname(__file__), "Video_Archive.db"))

WHISPER_MODEL = "mlx-community/whisper-small-mlx"
VISION_MODEL = "mlx-community/nanoLLaVA-1.5-8bit"

def get_clips_by_date(date_str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, path, filename, duration_sec, transcription, visual_tags, created FROM videos WHERE date(created) = ? ORDER BY filename ASC", (date_str,))
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_clips_by_query(query):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, path, filename, duration_sec, transcription, visual_tags, created FROM videos 
        WHERE id IN (SELECT video_id FROM video_search WHERE transcription MATCH ?)
        OR visual_tags LIKE ?
        ORDER BY created ASC
    ''', (query, f"%{query}%"))
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_db_stats():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM videos')
    total = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM videos WHERE transcription IS NOT NULL AND transcription != ""')
    transcribed = cursor.fetchone()[0]
    
    # Get grouped timeline counts for calendar UI dots
    cursor.execute('SELECT date(created), COUNT(id) FROM videos GROUP BY date(created)')
    timeline_rows = cursor.fetchall()
    
    conn.close()
    
    timeline = [{"date": r[0], "count": r[1]} for r in timeline_rows if r[0]]
    
    return {
        "total_clips": total,
        "transcribed_clips": transcribed,
        "timeline": timeline
    }

def _isolate_vision_batch(video_path, segments_meta):
    """
    segments_meta = [{"idx": 0, "time": "1.234"}, {"idx": 1, "time": "4.567"}]
    Loads the MLX VLM once, extracts all frames, processes them, and returns a dict mapping idx -> description.
    """
    if not segments_meta:
        return {}
        
    import tempfile
    import json
    
    # 1. Pre-extract all frames via ffmpeg so we don't interleave ffmpeg calls with MLX inference
    frames_to_process = []
    for meta in segments_meta:
        frame_path = os.path.join(tempfile.gettempdir(), f"batch_vlm_{os.path.basename(video_path)}_{meta['idx']}.jpg")
        subprocess.run(['ffmpeg', '-ss', meta['time'], '-i', video_path, '-vframes', '1', '-q:v', '2', '-update', '1', frame_path, '-y', '-loglevel', 'error'], capture_output=True)
        if os.path.exists(frame_path):
            frames_to_process.append({"idx": meta["idx"], "path": frame_path})
            
    if not frames_to_process:
        return {meta["idx"]: "Visual data unavailable" for meta in segments_meta}
        
    code = f"""
import sys
import json
import os
import re

try:
    from mlx_vlm import load, generate
    
    model_path = "{VISION_MODEL}"
    # Load model ONCE
    model, processor = load(model_path)
    
    frames = {json.dumps(frames_to_process)}
    prompt = "Describe exactly what is in this video frame in one short sentence."
    
    results = {{}}
    
    for f in frames:
        idx = f["idx"]
        path = f["path"]
        
        try:
            output = generate(model, processor, path, prompt, verbose=False, max_tokens=30)
            
            content = "Visual analysis failed"
            if "assistant" in output.lower():
                parts = re.split(r"assistant", output, flags=re.IGNORECASE)
                if len(parts) > 1:
                    content = parts[1].split("==========")[0].strip()
            else:
                content = output.strip()
                
            content = content.replace("mx.metal.get_peak_memory is deprecated and will be removed in a future version. Use mx.get_peak_memory instead.", "").strip()
            results[str(idx)] = content
        except Exception as e:
            results[str(idx)] = "Visual analysis failed"
            
    print("START_JSON_PAYLOAD")
    print(json.dumps(results))
    print("END_JSON_PAYLOAD")
    
except Exception as e:
    sys.exit(1)
"""
    try:
        proc = subprocess.run(['python3', '-c', code], capture_output=True, text=True, check=True)
        stdout = proc.stdout
        
        # Cleanup temp frames immediately
        for f in frames_to_process:
            if os.path.exists(f["path"]):
                os.remove(f["path"])
                
        if "START_JSON_PAYLOAD" in stdout and "END_JSON_PAYLOAD" in stdout:
            json_str = stdout.split("START_JSON_PAYLOAD")[1].split("END_JSON_PAYLOAD")[0].strip()
            return json.loads(json_str)
            
        return {}
    except Exception as e:
        print("Subprocess vision batch failed:", e)
        # Cleanup temp frames on failure
        for f in frames_to_process:
            if os.path.exists(f["path"]):
                os.remove(f["path"])
        return {}

def _isolate_whisper(path, repo):
    """
    Because FastAPI/Uvicorn multithreading often crashes MLX C++ bindings with EXC_BAD_ACCESS (Segfaults),
    we must completely isolate the Whisper transcription into a separate python process.
    """
    code = """
import mlx_whisper
import json
import sys

try:
    path = sys.argv[1]
    repo = sys.argv[2]
    result = mlx_whisper.transcribe(path, path_or_hf_repo=repo, language='en')
    out = {
        'text': result.get('text', '').strip(),
        'segments': result.get('segments', [])
    }
    print("START_JSON_PAYLOAD")
    print(json.dumps(out))
    print("END_JSON_PAYLOAD")
except Exception as e:
    sys.exit(1)
"""
    try:
        proc = subprocess.run(['python3', '-c', code, path, repo], capture_output=True, text=True, check=True)
        stdout = proc.stdout
        if "START_JSON_PAYLOAD" in stdout and "END_JSON_PAYLOAD" in stdout:
            json_str = stdout.split("START_JSON_PAYLOAD")[1].split("END_JSON_PAYLOAD")[0].strip()
            return json.loads(json_str)
        return {'text': '', 'segments': []}
    except Exception as e:
        print("Subprocess whisper failed:", e)
        return {'text': '', 'segments': []}

def merge_segments_by_sentence(segments: list) -> list:
    """
    Whisper splits on silences, not sentence boundaries, so a segment can end
    mid-sentence (e.g. "...Catherine's") with the next picking up the tail
    ("bottom cheek. Anyways...").

    This function:
    1. Merges consecutive segments where the previous ends without sentence-
       ending punctuation (., ?, !).
    2. Re-splits the merged text into individual sentences.
    3. Distributes timestamps proportionally by word count.

    Returns a new list of segments with clean sentence-aligned boundaries.
    """
    if not segments:
        return []

    # --- Step 1: merge across sentence-straddling boundaries ---
    merged = []
    current = dict(segments[0])  # shallow copy
    current['text'] = current['text'].strip()

    for seg in segments[1:]:
        text = seg['text'].strip()
        if not text:
            continue
        prev_text = current['text']
        # Does the previous segment end without terminal punctuation?
        if prev_text and not re.search(r'[.?!]\s*$', prev_text):
            # Merge: extend the current block to cover this segment too
            current['end'] = seg['end']
            current['text'] = prev_text + ' ' + text
        else:
            merged.append(current)
            current = {'start': seg['start'], 'end': seg['end'], 'text': text,
                       'visual': seg.get('visual', '')}
    merged.append(current)

    # --- Step 2: re-split each block at sentence boundaries ---
    result = []
    for block in merged:
        # Split on sentence-ending punctuation followed by whitespace
        sentences = re.split(r'(?<=[.?!])\s+', block['text'].strip())
        sentences = [s.strip() for s in sentences if s.strip()]

        if len(sentences) <= 1:
            block['text'] = sentences[0] if sentences else block['text']
            result.append(block)
            continue

        # Distribute timestamps proportionally by word count
        total_words = sum(len(s.split()) for s in sentences)
        duration = block['end'] - block['start']
        t = block['start']
        for sent in sentences:
            words = len(sent.split())
            seg_dur = duration * (words / total_words) if total_words else 0
            result.append({
                'start': round(t, 2),
                'end': round(t + seg_dur, 2),
                'text': sent,
                'visual': block.get('visual', '')
            })
            t += seg_dur

    return result

def get_or_create_segments(vid_id, path):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT start_time, end_time, text, visual_description FROM video_segments WHERE video_id = ?", (vid_id,))
    existing = cursor.fetchall()
    
    if existing:
        conn.close()
        return [{"start": r[0], "end": r[1], "text": r[2], "visual": r[3]} for r in existing]
    
    print(f"  [Deep Analysis] Processing segments for: {os.path.basename(path)}")
    try:
        result = _isolate_whisper(path, WHISPER_MODEL)
        segments = result.get('segments', [])
        
        processed_segments = []
        segments_meta = []
        valid_segments = []
        
        for i, seg in enumerate(segments):
            start, end, text = seg['start'], seg['end'], seg['text'].strip()
            if not text or (end - start) < 0.5: continue
            
            mid_point = (start + end) / 2
            segments_meta.append({"idx": i, "time": f"{mid_point:.3f}"})
            valid_segments.append({"start": start, "end": end, "text": text, "idx": i})
            
        # Batch process all vision in one go
        vision_results = _isolate_vision_batch(path, segments_meta)
        
        for seg in valid_segments:
            idx = seg["idx"]
            visual = vision_results.get(str(idx), "Visual data unavailable")
            processed_segments.append({"start": seg["start"], "end": seg["end"], "text": seg["text"], "visual": visual})

        # Merge across sentence-straddling boundaries before storing
        # Visual description: use the one from the first sub-segment of each merged block
        clean_segments = merge_segments_by_sentence(processed_segments)

        for seg in clean_segments:
            cursor.execute(
                "INSERT INTO video_segments (video_id, start_time, end_time, text, visual_description) VALUES (?, ?, ?, ?, ?)",
                (vid_id, seg["start"], seg["end"], seg["text"], seg.get("visual", ""))
            )
        
        conn.commit()
        conn.close()
        return clean_segments
    except Exception as e:
        print(f"  Error analyzing segments: {e}")
        conn.close()
        return []

def upgrade_transcription_stream(clips):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    total = len(clips)
    for i, c in enumerate(clips):
        vid_id, path, filename, dur, old_trans, tags, created_at = c
        
        yield f"Processing {i+1} of {total}: {filename}...\n"
        
        if not os.path.exists(path):
            yield f"File missing: {path}\n"
            continue
            
        try:
            # Enforce the high quality model for upgrade in isolated process
            result = _isolate_whisper(path, "mlx-community/whisper-large-v3-mlx")
            text = result.get('text', '').strip()
            
            # Hallucination check based on known phrases and length
            word_count = len(text.split())
            hallucinated_phrases = ["subtitles", "amara.org", "thanks for watching", "music", "♪", "transcript", "thank you"]
            
            # 1. Short and contains a known hallucination phrase
            is_halluc_phrase = word_count < 30 and any(phrase in text.lower() for phrase in hallucinated_phrases)
            
            # 2. Impossible Speech Rate (e.g. 100 words in 3 seconds)
            # Normal conversational English is ~2.5 words per second. Even auctioneers max out around 4-5.
            # If whisper outputs > 6 words per second, it's almost certainly hallucinating a repeating loop.
            is_impossible_rate = False
            try:
                dur_float = float(dur)
                if dur_float > 0 and (word_count / dur_float) > 6:
                    is_impossible_rate = True
            except:
                pass
                
            # 3. Repeating phrases (Whisper loop glitch)
            # A simple heuristic: if a chunk of 10 words appears 3+ times, it's a loop.
            is_repeating_loop = False
            if word_count > 20:
                words = text.lower().split()
                # Check for 8-word sequence repetitions
                if len(words) >= 16:
                    for j in range(len(words) - 8):
                        seq = " ".join(words[j:j+8])
                        if text.lower().count(seq) > 2:
                            is_repeating_loop = True
                            break
            
            is_hallucination = is_halluc_phrase or is_impossible_rate or is_repeating_loop
            
            if word_count < 3 or is_hallucination:
                text = ""
                yield f"  Audio: B-ROLL (No speech detected or completely hallucinated)\n"
            else:
                yield f"  Audio: Transcribed ({len(text.split())} words)\n"
                
            # Update database
            cursor.execute('UPDATE videos SET transcription = ? WHERE id = ?', (text, vid_id))
            if text:
                cursor.execute("INSERT OR REPLACE INTO video_search (video_id, transcription) VALUES (?, ?)", (vid_id, text))
            else:
                cursor.execute("DELETE FROM video_search WHERE video_id = ?", (vid_id,))
                
            # Clear old segments so they regenerate next time a plan is made
            cursor.execute("DELETE FROM video_segments WHERE video_id = ?", (vid_id,))
            
            conn.commit()
            
        except Exception as e:
            yield f"  Audio Error on {filename}: {str(e)}\n"
            
    conn.close()
    yield "DONE\n"

def extract_keywords(text):
    if not text: return []
    stop_words = {'the', 'and', 'a', 'to', 'of', 'in', 'is', 'it', 'its', 'we', 'have', 'has', 'had', 'just', 'at', 'this', 'that', 'with', 'but', 'for', 'are', 'was'}
    words = re.findall(r'\w+', text.lower())
    return [w for w in words if len(w) > 3 and w not in stop_words]

def find_best_broll(keywords, broll_pool):
    if not broll_pool: return None, "No B-roll available."
    if not keywords: return broll_pool.pop(0), "Sequential fallback."
    
    best_match = None
    max_score = -1
    best_rationale = ""
    
    for i, b in enumerate(broll_pool):
        vid_id, path, name, dur, trans, tags, created_at = b
        score = 0
        matches = []
        for kw in keywords:
            if tags and kw in tags.lower(): score += 2; matches.append(kw)
            if trans and kw in trans.lower(): score += 1; matches.append(kw)
        
        if score > max_score:
            max_score = score
            best_match = i
            best_rationale = f"Semantic Match: Visuals contain keywords ({', '.join(set(matches))})." if matches else "Atmospheric Context"
                
    if best_match is not None:
        return broll_pool.pop(best_match), best_rationale
    return broll_pool.pop(0), "Sequential fallback."

def generate_story_plan(clips, title):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    output_dir = os.path.join(base_dir, "VLOG_OUTPUT")
    os.makedirs(output_dir, exist_ok=True)
    plan_path = os.path.join(output_dir, f"STORY_PLAN_{title}.md")
    aroll_pool = []
    broll_pool = []
    
    for c in clips:
        # clips: (id, path, filename, duration_sec, transcription, visual_tags, created)
        word_count = len(c[4].split()) if c[4] else 0
        if word_count > 12: aroll_pool.append(c)
        else: broll_pool.append(c)
            
    with open(plan_path, 'w') as f:
        f.write(f"# ✂️ RAW FOOTAGE CUTTING PLAN: {title}\n")
        f.write(f"Generated by AI Director System\n\n")
        
        # DEBUG DUMP FOR USER
        rough_cut_report = f"# 🎬 Director AI: Rough Cut Analysis - {title}\n\n"
        for c in clips:
            vid_id, path, name, dur, trans, tags, created_at = c
            segments = get_or_create_segments(vid_id, path)
            if not segments: continue
                
            rough_cut_report += f"## 🎞 File: {name}\n"
            rough_cut_report += f"Recorded: {created_at}\n"
            rough_cut_report += f"Path: {path}\n"
            rough_cut_report += f"Duration: {dur:.1f}s\n"
            for seg in segments:
                mid_time = (seg['start'] + seg['end']) / 2
                rough_cut_report += f"**[{seg['start']:05.2f}s - {seg['end']:05.2f}s]**\n"
                rough_cut_report += f"- Midpoint Thumbnail Timestamp: {mid_time:.3f}\n"
                rough_cut_report += f"- 🗣 **SAYING:** {seg['text']}\n"
                rough_cut_report += f"- 👁 **SEEING:** {seg['visual']}\n\n"
        
        for i, a in enumerate(aroll_pool[:10]):
            vid_id, path, name, dur, trans, tags, created_at = a
            segments = get_or_create_segments(vid_id, path)
            keywords = extract_keywords(trans)
            
            scene_name_clean = re.sub(r'[^a-zA-Z0-9]', '_', name.lower())
            f.write(f"## **SCENE {i+1}: {scene_name_clean}**\n")
            
            # Format A-ROLL
            f.write(f"*   **A-ROLL:** `{name}`\n")
            for j, seg in enumerate(segments):
                mid_time = (seg['start'] + seg['end']) / 2
                f.write(f"    *   Segment {j+1}: [{seg['start']:05.2f} - {seg['end']:05.2f}] ({seg['text']}) ![thumbnail](http://localhost:8000/api/thumbnail?path={urllib.parse.quote(path)}&t={mid_time:.3f})\n")
            
            # Format B-ROLL OVERLAYS
            f.write(f"*   **B-ROLL OVERLAYS:**\n")
            match, rationale = find_best_broll(keywords, broll_pool)
            if match:
                b_vid_id, b_path, b_name, b_dur, b_trans, b_tags, b_created_at = match
                b_mid = b_dur / 2 if b_dur else 1.5
                f.write(f"    *   `{b_name}` | Trim: [{0:.2f}-{min(3.0, b_dur):.2f}] | Overlay @ 05.00 ![thumbnail](http://localhost:8000/api/thumbnail?path={urllib.parse.quote(b_path)}&t={b_mid:.3f})\n")
                f.write(f"        *   **RATIONALE:** *{rationale}* Visuals: {b_tags if b_tags else 'Cinematic scenery'}\n")
            
            f.write("\n---\n\n")
            
    return plan_path

def generate_story_plan_stream(clips, title):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    output_dir = os.path.join(base_dir, "VLOG_OUTPUT")
    os.makedirs(output_dir, exist_ok=True)
    plan_path = os.path.join(output_dir, f"STORY_PLAN_{title}.md")
    import google.generativeai as genai
    
    # 1. Compile the Rough Cut Report from the Database
    rough_cut_report = f"# 🎬 Director AI: Rough Cut Analysis - {title}\n\n"
    
    for c in clips:
        vid_id, path, name, dur, trans, tags, created_at = c
        yield f"data: {{\"chunk\": \"Analyzing video {name}...\"}}\n\n"
        segments = get_or_create_segments(vid_id, path)
        if not segments:
            continue

        rough_cut_report += f"## 🎞 File: {name}\n"
        rough_cut_report += f"Recorded: {created_at}\n"
        rough_cut_report += f"Path: {path}\n"
        rough_cut_report += f"Duration: {dur:.1f}s\n"
        for seg in segments:
            mid_time = (seg['start'] + seg['end']) / 2
            rough_cut_report += f"**[{seg['start']:05.2f}s - {seg['end']:05.2f}s]**\n"
            rough_cut_report += f"- Midpoint Thumbnail Timestamp: {mid_time:.3f}\n"
            rough_cut_report += f"- 🗣 **SAYING:** {seg['text']}\n"
            rough_cut_report += f"- 👁 **SEEING:** {seg['visual']}\n\n"

    # 2. Instruct Gemini
    system_instruction = """
You are an expert documentary video editor and storyteller.
I will provide you with a "Rough Cut Analysis" containing transcribed segments and visuals from various raw video clips.

Your job is to read these clips, understand the narrative or event occurring, and build a compelling "Non-Linear Editor (NLE) Cutting Plan".
You should select the best soundbites to form an A-Roll narrative track (V1), and find matching B-Roll footage to overlay on top (V2) to hide cuts or show what the speaker is talking about.

CRITICAL INSTRUCTION - CHRONOLOGICAL TIMELINE:
You MUST organize the entirely of your Cutting Plan so that the scenes unfold in STRICTLY CHRONOLOGICAL ORDER based on the "Recorded:" timestamp provided for each file in the report. Do not jump back and forth in time. Tell the story from the morning to the evening.

CRITICAL INSTRUCTION - COMPLETE SENTENCES ONLY:
Every segment you include in the plan MUST begin and end on a complete sentence. Never start a segment mid-sentence (i.e. do not start with a lowercase word or a word that clearly continues a thought from before). If a segment's text in the report starts with a sentence fragment, skip that fragment and begin only from the first complete sentence within it. If the entire segment text is a fragment with no complete sentence, omit that segment entirely.

CRITICAL FORMATTING RULES:
You must output YOUR ENTIRE RESPONSE exactly matching this Markdown format structure so my editing software can parse it and render the timeline:

# ✂️ AI Director Cutting Plan: [Title]

## **SCENE 1: [Catchy Scene Title]**
*   **A-ROLL:** `[filename.MOV]`
    *   Segment 1: [00.00 - 05.00] (The exact text being spoken) ![thumbnail](http://localhost:8000/api/thumbnail?path={Absolute_File_Path_From_Report}&t={Midpoint_Thumbnail_Timestamp})
    *   Segment 2: [05.00 - 10.00] (Next spoken text) ![thumbnail](http://localhost:8000/api/thumbnail?path={Absolute_File_Path_From_Report}&t={Midpoint_Thumbnail_Timestamp})
*   **B-ROLL OVERLAYS:**
    *   `[different_filename.MOV]` | Trim: [00.00-03.00] | Overlay @ 05.00 ![thumbnail](http://localhost:8000/api/thumbnail?path={Absolute_File_Path_From_Report}&t={Midpoint_Thumbnail_Timestamp})
        *   **RATIONALE:** *[Brief explanation of why this B-roll fits here]* Visuals: [Description of the B-Roll visual]

CRITICAL TIMESTAMP FORMAT RULES:
- ALL timestamps (A-Roll segments AND B-Roll Trim/Overlay) MUST be in DECIMAL SECONDS (e.g. 12.50, 47.00). NEVER use MM:SS colon notation (e.g. never write 7:00 or 1:30).
- B-Roll Trim start and end MUST NOT exceed the actual duration of that clip as listed in the report. If a clip is 94s long, valid trims are e.g. [0.00-4.00], not [420.00-660.00].

---

You can create as many Scenes as necessary to tell the story.
Always include the `![thumbnail]` markdown image tag exactly as formatted above, injecting the absolute Path and the exact Midpoint Timestamp provided in the report for that segment. DO NOT URL ENCODE the path yourself, just output the raw path string. My frontend will URL encode it.
    """



    yield f"data: {{\"chunk\": \"Drafting story narrative via Gemini...\"}}\n\n"
    import json
    settings_file = os.path.join(base_dir, "backend", "settings.json")
    model_name = "models/gemini-3.1-flash" # Default
    if os.path.exists(settings_file):
        try:
            with open(settings_file, "r") as f:
                settings = json.load(f)
                if "geminiModel" in settings:
                    model_name = settings["geminiModel"]
        except:
            pass
            
    # If the user saved just "gemini-3.1-flash" instead of "models/gemini-3.1-flash" in a previous iteration, fix that
    if not model_name.startswith("models/"):
        model_name = f"models/{model_name}"

    # 3. Stream the generation
    model = genai.GenerativeModel(
        model_name=model_name,
        system_instruction=system_instruction
    )
    
    with open(plan_path, 'w') as f:
        # We don't write headers first here because Gemini generates the whole markdown structure
        response = model.generate_content(rough_cut_report, stream=True)
        for chunk in response:
            text = chunk.text
            f.write(text)
            # Make sure it's valid JSON for the SSE frontend parser
            safe_text = json.dumps({"chunk": text})
            yield f"data: {safe_text}\n\n"
            
    # Final done yield
    safe_done = json.dumps({"chunk": f"DONE:{plan_path}"})
    yield f"data: {safe_done}\n\n"

def main():
    parser = argparse.ArgumentParser(description="AI Director: Automated Video Storytelling")
    parser.add_argument("--date", help="Process all clips from a specific date (YYYY-MM-DD)")
    parser.add_argument("--query", help="Search clips by keyword or theme")
    parser.add_argument("--build", action="store_true", help="Automatically trigger FFmpeg build after planning")
    
    args = parser.parse_args()
    if not args.date and not args.query:
        print("Please provide --date (e.g. 2011-09-17) or --query (e.g. dumplings)")
        sys.exit(1)
        
    title = args.date if args.date else args.query.replace(" ", "_")
    print(f"🎬 AI Director: Performing Deep Rough Cut Analysis for '{title}'...")
    
    clips = get_clips_by_date(args.date) if args.date else get_clips_by_query(args.query)
    if not clips:
        print("No clips found. Ensure Director Engine has indexed these files.")
        sys.exit(0)
        
    print(f"Found {len(clips)} clips. Analyzing segments...")
    plan_path = generate_story_plan(clips, title)
    print(f"✅ Deep Analysis & Story Plan generated: {plan_path}")
    
    if args.build:
        print(f"🚀 Starting FFmpeg Build Engine...")
        base_dir = os.path.dirname(os.path.abspath(__file__))
        build_script = os.path.join(base_dir, "generate_vlog.py")
        os.system(f"python3 {build_script} {plan_path}")

if __name__ == "__main__":
    main()
