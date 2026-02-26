import os
import sqlite3
import subprocess
import datetime
import re
import json
import tempfile
import argparse

def _load_config():
    settings_path = os.path.join(os.path.dirname(__file__), "backend", "settings.json")
    if os.path.exists(settings_path):
        with open(settings_path, "r") as f:
            return json.load(f)
    return {}

config = _load_config()
DB_PATH = config.get("dbPath", os.path.join(os.path.dirname(__file__), "Video_Archive.db"))
TRANSCRIPTS_DIR = config.get("transcriptsPath", os.path.join(os.path.dirname(__file__), "Transcripts"))
os.makedirs(TRANSCRIPTS_DIR, exist_ok=True)

VISION_MODEL = "mlx-community/nanoLLaVA-1.5-8bit"
WHISPER_MODEL = "mlx-community/whisper-small-mlx"
LOG_PATH = os.path.join(os.path.dirname(DB_PATH), "Director_Engine.log")
LOG_MAX_LINES = 1000
_log_call_count = 0

def log(msg):
    global _log_call_count
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
    formatted_msg = f"[{timestamp}] {msg}\n"
    print(msg)
    
    _log_call_count += 1
    if _log_call_count >= 50:
        _log_call_count = 0
        try:
            if os.path.exists(LOG_PATH):
                with open(LOG_PATH, "r") as f:
                    lines = f.readlines()[-LOG_MAX_LINES:]
                lines.append(formatted_msg)
                with open(LOG_PATH, "w") as f:
                    f.writelines(lines)
                return
        except Exception:
            pass
            
    with open(LOG_PATH, "a") as f:
        f.write(formatted_msg)

def init_db(db_path):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=60.0)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS videos(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT UNIQUE,
            filename TEXT,
            duration_sec REAL,
            status TEXT,
            visual_tags TEXT,
            transcription TEXT,
            created TEXT
        )
    ''')
    cursor.execute('CREATE VIRTUAL TABLE IF NOT EXISTS video_search USING fts5(video_id, transcription)')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS video_segments(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id INTEGER,
            start_time REAL,
            end_time REAL,
            text TEXT,
            visual_description TEXT
        )
    ''')
    conn.commit()
    conn.close()

def _isolate_whisper(path):
    """Run mlx_whisper in a child process to avoid EXC_BAD_ACCESS crashes under Uvicorn."""
    code = """
import mlx_whisper, json, sys
try:
    result = mlx_whisper.transcribe(sys.argv[1], path_or_hf_repo=sys.argv[2], language='en')
    print("JSON_START")
    print(json.dumps({'text': result.get('text','').strip(), 'segments': result.get('segments', [])}))
    print("JSON_END")
except Exception:
    sys.exit(1)
"""
    try:
        proc = subprocess.run(["python3", "-c", code, path, WHISPER_MODEL],
                              capture_output=True, text=True, timeout=300)
        out = proc.stdout
        if "JSON_START" in out and "JSON_END" in out:
            return json.loads(out.split("JSON_START")[1].split("JSON_END")[0].strip())
    except Exception as e:
        log(f"  Whisper subprocess error: {e}")
    return {'text': '', 'segments': []}

def run_unified_process():
    init_db(DB_PATH)
    conn = sqlite3.connect(DB_PATH, timeout=60.0)
    cursor = conn.cursor()
    
    log(f"Starting Unified Director Engine (Model: {WHISPER_MODEL})...")

    while True:
        cursor.execute('''
            SELECT id, path, filename, duration_sec, status, visual_tags FROM videos 
            WHERE (status = 'pending' OR visual_tags IS NULL) AND duration_sec > 2.0
            ORDER BY id ASC LIMIT 50
        ''')
        
        tasks = cursor.fetchall()
        if not tasks:
            log("All videos processed.")
            break

        for vid_id, path, filename, dur, status, v_tags in tasks:
            if not os.path.exists(path):
                cursor.execute("UPDATE videos SET status = 'missing' WHERE id = ?", (vid_id,))
                conn.commit()
                continue

            log(f"Processing: {filename}")
            
            # 1. TRANSCRIPTION
            if status != 'completed':
                try:
                    result = _isolate_whisper(path)
                    text = result.get('text', '').strip()
                    
                    # Prevent hallucinated transcripts on silent b-roll
                    # 1. Short and contains a known hallucination phrase
                    word_count = len(text.split())
                    hallucinated_phrases = ["subtitles", "amara.org", "thanks for watching", "music", "♪", "transcript", "thank you"]
                    is_halluc_phrase = word_count < 30 and any(phrase in text.lower() for phrase in hallucinated_phrases)
                    
                    # 2. Impossible Speech Rate (e.g. 100 words in 3 seconds)
                    is_impossible_rate = False
                    if dur > 0 and (word_count / dur) > 6:
                        is_impossible_rate = True
                        
                    # 3. Repeating phrases (Whisper loop glitch)
                    is_repeating_loop = False
                    if word_count > 20:
                        words = text.lower().split()
                        if len(words) >= 16:
                            for j in range(len(words) - 8):
                                seq = " ".join(words[j:j+8])
                                if text.lower().count(seq) > 2:
                                    is_repeating_loop = True
                                    break
                    
                    is_hallucination = is_halluc_phrase or is_impossible_rate or is_repeating_loop
                    
                    # If we have very few words or it matches the hallucination logic
                    if word_count < 3 or is_hallucination:
                        text = ""
                    
                    cursor.execute('UPDATE videos SET transcription = ?, status = "completed" WHERE id = ?', (text, vid_id))
                    
                    if text:
                        cursor.execute("INSERT OR REPLACE INTO video_search (video_id, transcription) VALUES (?, ?)", (vid_id, text))
                        safe_name = "".join([c for c in filename if c.isalnum() or c in (' ', '.', '_')]).rstrip()
                        with open(os.path.join(TRANSCRIPTS_DIR, f"{safe_name}.txt"), "w") as f:
                            f.write(f"Source: {path}\n\n{text}")
                    
                    log(f"  Audio: {'B-ROLL (No speech)' if not text else 'Transcribed'}")
                except Exception as e:
                    log(f"  Audio Error: {str(e)}")

            # 2. VISION (Using proven CLI method via subprocess)
            if v_tags is None:
                try:
                    frame_path = os.path.join(tempfile.gettempdir(), f"director_{vid_id}.jpg")
                    subprocess.run(['ffmpeg', '-ss', '00:00:02', '-i', path, '-vframes', '1', '-q:v', '2', '-update', '1', frame_path, '-y', '-loglevel', 'error'], capture_output=True)
                    
                    if os.path.exists(frame_path):
                        cmd = ["python3", "-m", "mlx_vlm.generate", "--model", VISION_MODEL, "--image", frame_path, "--prompt", "List 5 descriptive tags for this scene.", "--max-tokens", "50"]
                        result = subprocess.run(cmd, capture_output=True, text=True)
                        
                        raw = result.stdout
                        if "assistant" in raw.lower():
                            content = re.split(r"assistant", raw, flags=re.IGNORECASE)[1].split("==========")[0].strip()
                            tags = ", ".join([re.sub(r"^[0-9\. ]+", "", l).strip() for l in content.split('\n') if l.strip()])
                            tags = tags.replace("mx.metal.get_peak_memory is deprecated and will be removed in a future version. Use mx.get_peak_memory instead.", "").strip()
                            
                            cursor.execute("UPDATE videos SET visual_tags = ? WHERE id = ?", (tags, vid_id))
                            log(f"  Vision: {tags[:50]}...")
                        
                        if os.path.exists(frame_path):
                            os.remove(frame_path)
                except Exception as e:
                    log(f"  Vision Error: {str(e)}")

            conn.commit()

    conn.close()

def scan_folder(folder_path):
    init_db(DB_PATH)
    if not os.path.exists(folder_path):
        print(f"Error: Folder '{folder_path}' does not exist.")
        return

    conn = sqlite3.connect(DB_PATH, timeout=60.0)
    cursor = conn.cursor()
    
    # Cache existing paths for O(1) deduplication lookup and self-healing
    cursor.execute("SELECT path, duration_sec, created FROM videos")
    existing_videos = {row[0]: (row[1], row[2]) for row in cursor.fetchall()}

    added_count = 0
    updated_count = 0
    skipped_count = 0

    log(f"Starting Scan of: {folder_path}")

    for root, dirs, files in os.walk(folder_path):
        # Actively prevent traversing into system recycle bins, trash folders, and Spotlight caches
        dirs[:] = [d for d in dirs if not d.upper().startswith('$RECYCLE.BIN') and d not in ('.Trashes', '.Trash', '.Spotlight-V100', '.fseventsd', '.DocumentRevisions-V100')]

        for f in files:
            if not f.lower().endswith(('.mp4', '.mov', '.m4v', '.avi', '.mkv', '.webm', '.wmv', '.flv')) or f.startswith('._'):
                continue
                
            full_path = os.path.join(root, f)
            
            is_update = False
            if full_path in existing_videos:
                old_dur, old_created = existing_videos[full_path]
                
                # Check for malformed old data (e.g. 'hevc' string instead of float, or empty creation dates)
                needs_heal = False
                try:
                    float(old_dur) if old_dur is not None else 0.0
                except ValueError:
                    needs_heal = True
                
                if not old_created or old_created.strip() in ('', 'unknown'):
                    needs_heal = True
                
                if not needs_heal:
                    skipped_count += 1
                    continue
                else:
                    is_update = True
                    
            try:
                # Extract metadata using ffprobe
                cmd = [
                    'ffprobe', '-v', 'quiet', '-print_format', 'json', 
                    '-show_format', '-show_streams', full_path
                ]
                result = subprocess.run(cmd, capture_output=True, text=True)
                probe_data = json.loads(result.stdout)

                duration = float(probe_data.get('format', {}).get('duration', 0))
                
                # Try EXIF creation_time
                creation_time = probe_data.get('format', {}).get('tags', {}).get('creation_time')
                if not creation_time:
                    # Fallback to streams
                    for stream in probe_data.get('streams', []):
                        if 'tags' in stream and 'creation_time' in stream['tags']:
                            creation_time = stream['tags']['creation_time']
                            break
                            
                if creation_time:
                    try:
                        # Parse standard ISO string to python datetime
                        dt = datetime.datetime.fromisoformat(creation_time.replace('Z', '+00:00'))
                        created_str = dt.strftime('%Y-%m-%d %H:%M:%S')
                    except ValueError:
                        # Fallback for absurd Apple EXIF dates (e.g. year 127057)
                        mtime = os.path.getmtime(full_path)
                        created_str = datetime.datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
                else:
                    # Fallback to OS modification time
                    mtime = os.path.getmtime(full_path)
                    created_str = datetime.datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')

                if is_update:
                    cursor.execute('''
                        UPDATE videos SET duration_sec = ?, created = ? 
                        WHERE path = ?
                    ''', (duration, created_str, full_path))
                    updated_count += 1
                    log(f"  Healed: {f} (New Dur: {duration:.1f}s, Date: {created_str})")
                else:
                    cursor.execute('''
                        INSERT INTO videos (path, filename, duration_sec, status, created) 
                        VALUES (?, ?, ?, ?, ?)
                    ''', (full_path, f, duration, 'pending', created_str))
                    added_count += 1
                    log(f"  Ingested: {f} (Dur: {duration:.1f}s, Date: {created_str})")

            except sqlite3.IntegrityError:
                # Path already exists in DB (can happen if cache was stale)
                skipped_count += 1

            except Exception as e:
                log(f"  Error processing {f}: {e}")

    conn.commit()
    conn.close()
    
    log(f"Scan complete. Added: {added_count}, Healed: {updated_count}, Skipped {skipped_count}.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI Director Engine")
    parser.add_argument("--scan-folder", type=str, help="Scan a directory for new videos and ingest them.")
    args = parser.parse_args()

    if args.scan_folder:
        scan_folder(args.scan_folder)
    else:
        run_unified_process()
