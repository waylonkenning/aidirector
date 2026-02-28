import os
import sys
# Triggering uvicorn hot-reload to load ai_director.py changes
import subprocess
import warnings
from collections import defaultdict

# Suppress annoying deprecation warnings from Python 3.9 / google.generativeai
warnings.filterwarnings("ignore", category=FutureWarning)

import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
genai.configure(api_key=os.environ.get("GEMINI_API_KEY", ""))

# Add parent directory to sys.path so we can import ai_director, etc.
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import json
import ai_director
import generate_vlog
import director_engine

app = FastAPI(title="AI Director App API")

# Allow CORS for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from fastapi.responses import RedirectResponse

@app.get("/")
def redirect_to_frontend():
    # If the user clicks the Uvicorn link by mistake, send them to the frontend app
    return RedirectResponse(url="http://localhost:3000")

class QueryRequest(BaseModel):
    query: str = None
    date: str = None

class PlanRequest(BaseModel):
    title: str
    clips: list

import json

SETTINGS_FILE = os.path.join(os.path.dirname(__file__), "settings.json")

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r") as f:
            return json.load(f)
    return {
        "geminiModel": "models/gemini-3.1-flash",
        "geminiApiKey": os.environ.get("GEMINI_API_KEY", ""),
        "dbPath": os.path.join(os.path.dirname(__file__), "Video_Archive.db"),
        "watchFolders": []
    }

def save_settings(settings):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=4)

@app.get("/api/settings")
def get_user_settings():
    return load_settings()

class SettingsUpdate(BaseModel):
    geminiModel: str = None
    geminiApiKey: str = None
    dbPath: str = None
    watchFolders: list[str] = None

@app.post("/api/settings")
def update_user_settings(req: SettingsUpdate):
    settings = load_settings()
    
    if req.geminiModel:
        settings["geminiModel"] = req.geminiModel
        
    if req.geminiApiKey is not None:
        # Update .env file
        env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
        lines = []
        if os.path.exists(env_path):
            with open(env_path, "r") as f:
                lines = f.readlines()
        
        # Replace or append GEMINI_API_KEY
        key_found = False
        new_lines = []
        for line in lines:
            if line.startswith("GEMINI_API_KEY="):
                new_lines.append(f'GEMINI_API_KEY="{req.geminiApiKey}"\n')
                key_found = True
            else:
                new_lines.append(line)
        
        if not key_found:
            new_lines.append(f'GEMINI_API_KEY="{req.geminiApiKey}"\n')
            
        with open(env_path, "w") as f:
            f.writelines(new_lines)
            
        # Re-configure in running process
        os.environ["GEMINI_API_KEY"] = req.geminiApiKey
        genai.configure(api_key=req.geminiApiKey)
        settings["geminiApiKey"] = req.geminiApiKey

    if req.dbPath:
        settings["dbPath"] = req.dbPath
        
    if req.watchFolders is not None:
        settings["watchFolders"] = req.watchFolders
        
    save_settings(settings)
    
    # Reload globals in ai_director dynamically so we don't need a Uvicorn reboot
    ai_director.DB_PATH = settings.get("dbPath", ai_director.DB_PATH)
    director_engine.DB_PATH = settings.get("dbPath", director_engine.DB_PATH)
    director_engine.TRANSCRIPTS_DIR = os.path.join(os.path.dirname(settings.get("dbPath", director_engine.DB_PATH)), "Transcripts")
    
    return {"status": "success"}

@app.post("/api/database/reset")
def reset_database():
    settings = load_settings()
    db_path = settings.get("dbPath", ai_director.DB_PATH)
    
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
            # Re-initialize empty DB so system doesn't crash
            director_engine.init_db(db_path)
            # Also clear logs for a fresh start
            log_path = os.path.join(os.path.dirname(db_path), "Director_Engine.log")
            if os.path.exists(log_path):
                with open(log_path, "w") as f:
                    f.write("")
            return {"status": "success", "message": "Database reset successfully."}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to reset database: {str(e)}")
    
    return {"status": "error", "message": "Database file not found."}

@app.get("/api/models")
def list_models():
    try:
        models = genai.list_models()
        supported_models = []
        
        excluded_keywords = ["image", "tts", "computer-use", "robotics", "deep-research", "nano", "vision", "customtools"]
        
        for m in models:
            if "generateContent" not in m.supported_generation_methods:
                continue
                
            name = m.name.split("/")[-1]
            
            # Filter out models with excluded keywords
            if any(ex in name for ex in excluded_keywords):
                continue
                
            # Only include models that are clearly 'flash' or 'pro' and are part of the gemini family
            if "gemini" in name and ("flash" in name or "pro" in name):
                supported_models.append({"id": m.name, "name": m.display_name or name})
                
        return supported_models
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/status")
def get_status():
    return {"status": "online", "db_path": ai_director.DB_PATH}

@app.get("/api/insights")
def get_insights():
    stats = ai_director.get_db_stats()
    return {
        "total_clips": stats["total_clips"],
        "transcribed_clips": stats["transcribed_clips"],
        "timeline": stats.get("timeline", [])
    }

@app.post("/api/search")
def search_clips(req: QueryRequest):
    if req.date:
        clips = ai_director.get_clips_by_date(req.date)
    elif req.query:
        clips = ai_director.get_clips_by_query(req.query)
    else:
        raise HTTPException(status_code=400, detail="Must provide query or date")
    
    # clips = (id, path, filename, duration_sec, transcription, visual_tags)
    result = []
    for c in clips:
        result.append({
            "id": c[0],
            "path": c[1],
            "filename": c[2],
            "duration": c[3],
            "transcription": c[4],
            "visual_tags": c[5],
            "created": c[6]
        })
    return {"clips": result}

@app.get("/api/duplicates")
def get_duplicates():
    """
    Returns groups of likely-duplicate videos.
    Duplicates are identified by identical EXIF `created` timestamp AND
    duration within 1 second of each other (handles re-encode size drift).
    """
    import sqlite3 as _sqlite3
    settings = load_settings()
    db_path = settings.get("dbPath", os.path.join(os.path.dirname(__file__), "Video_Archive.db"))
    conn = _sqlite3.connect(db_path, timeout=30)
    cursor = conn.cursor()

    # Find all created timestamps that appear on more than one video
    cursor.execute("""
        SELECT id, path, filename, ROUND(duration_sec, 0) as dur_r, created,
               SUBSTR(transcription, 1, 100) as snippet, status
        FROM videos
        WHERE created IS NOT NULL AND created != ''
        ORDER BY created ASC, dur_r ASC
    """)
    rows = cursor.fetchall()
    conn.close()

    # Sort by duration first, then timestamp
    # We use a buckets of rounded duration (to 1 decimal place)
    duration_buckets = defaultdict(list)
    for vid_id, path, filename, dur_r, created, snippet, status in rows:
        # Using 1 decimal place for duration buckets to handle slight re-encode drift
        dur_key = round(dur_r, 1) if dur_r else 0
        duration_buckets[dur_key].append({
            "id": vid_id,
            "path": path,
            "filename": filename,
            "duration": dur_r,
            "created": created,
            "snippet": snippet or "",
            "status": status,
        })

    from datetime import datetime
    duplicate_groups = []
    
    for dur_key, members in duration_buckets.items():
        if len(members) < 2:
            continue
            
        # Within each duration bucket, sort by timestamp
        members.sort(key=lambda x: x["created"])
        
        # Group by proximity (within 5 minutes)
        current_group = [members[0]]
        for i in range(1, len(members)):
            try:
                t1 = datetime.strptime(current_group[-1]["created"], "%Y-%m-%d %H:%M:%S")
                t2 = datetime.strptime(members[i]["created"], "%Y-%m-%d %H:%M:%S")
                diff = abs((t2 - t1).total_seconds())
                
                if diff <= 300: # 5 minute window
                    current_group.append(members[i])
                else:
                    if len(current_group) >= 2:
                        duplicate_groups.append(current_group)
                    current_group = [members[i]]
            except Exception:
                # If parsing fails, don't group
                if len(current_group) >= 2:
                    duplicate_groups.append(current_group)
                current_group = [members[i]]
                
        if len(current_group) >= 2:
            duplicate_groups.append(current_group)

    # Final pass: sort and pick keeper for each group
    formatted_groups = []
    for members in duplicate_groups:
        def keeper_score(m: dict) -> int:
            name = m["filename"]
            if any(p in name for p in ["CFNetworkDownload", "Snapchat-", "AUTO_AWESOME"]):
                return 0
            if name.startswith(("MAH", "MVI_", "C00", "P100", "MOV_")):
                return 2
            return 1
            
        members_sorted = sorted(members, key=keeper_score, reverse=True)
        members_sorted[0]["suggested_keep"] = True
        formatted_groups.append({
            "key": f"{members_sorted[0]['created']}|{members_sorted[0]['duration']}",
            "clips": members_sorted
        })

    return {"groups": formatted_groups, "total_groups": len(formatted_groups)}


class DeleteRequest(BaseModel):
    id: int

@app.post("/api/video/delete")
def delete_video_from_index(req: DeleteRequest):
    """
    Removes a video from the AI Director index (DB only).
    Does NOT delete the original file from disk.
    """
    import sqlite3 as _sqlite3
    settings = load_settings()
    db_path = settings.get("dbPath", os.path.join(os.path.dirname(__file__), "Video_Archive.db"))
    conn = _sqlite3.connect(db_path, timeout=30)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM video_segments WHERE video_id = ?", (req.id,))
    cursor.execute("DELETE FROM video_search WHERE video_id = ?", (req.id,))
    cursor.execute("DELETE FROM videos WHERE id = ?", (req.id,))
    conn.commit()
    conn.close()
    return {"status": "deleted", "id": req.id}

@app.post("/api/video/hide")
def hide_video_from_index(req: DeleteRequest):
    """
    Marks a video as a duplicate/hidden in the DB.
    It will no longer appear in search results or stats.
    """
    import sqlite3 as _sqlite3
    settings = load_settings()
    db_path = settings.get("dbPath", os.path.join(os.path.dirname(__file__), "Video_Archive.db"))
    conn = _sqlite3.connect(db_path, timeout=30)
    cursor = conn.cursor()
    # Mark as duplicate so it's filtered out of all queries
    cursor.execute("UPDATE videos SET status = 'duplicate' WHERE id = ?", (req.id,))
    # Also remove from FTS index so it doesn't match queries anymore
    cursor.execute("DELETE FROM video_search WHERE video_id = ?", (req.id,))
    conn.commit()
    conn.close()
    return {"status": "hidden", "id": req.id}


@app.post("/api/video/hide_short")
def hide_short_clips():
    """
    Marks all clips shorter than 3 seconds as 'livephoto' in the DB.
    """
    import sqlite3 as _sqlite3
    settings = load_settings()
    db_path = settings.get("dbPath", os.path.join(os.path.dirname(__file__), "Video_Archive.db"))
    conn = _sqlite3.connect(db_path, timeout=30)
    cursor = conn.cursor()
    
    # Update status for clips < 3s that aren't already marked
    cursor.execute("UPDATE videos SET status = 'livephoto' WHERE duration_sec < 3 AND (status IS NULL OR status = 'pending')")
    hidden_count = cursor.rowcount
    
    # Also clean up FTS index for these clips
    cursor.execute("DELETE FROM video_search WHERE video_id IN (SELECT id FROM videos WHERE status = 'livephoto')")
    
    conn.commit()
    conn.close()
    return {"status": "success", "hidden_count": hidden_count}


@app.post("/api/duplicates/hide_all")
def hide_all_duplicates():
    """
    Finds all duplicate groups and hides everything EXCEPT the suggested 'keeper' in each group.
    Returns the number of clips hidden.
    """
    dupes_data = get_duplicates()
    groups = dupes_data.get("groups", [])
    
    import sqlite3 as _sqlite3
    settings = load_settings()
    db_path = settings.get("dbPath", os.path.join(os.path.dirname(__file__), "Video_Archive.db"))
    conn = _sqlite3.connect(db_path, timeout=30)
    cursor = conn.cursor()
    
    hidden_count = 0
    for group in groups:
        for clip in group["clips"]:
            if not clip.get("suggested_keep"):
                # Hide this one
                cursor.execute("UPDATE videos SET status = 'duplicate' WHERE id = ?", (clip["id"],))
                cursor.execute("DELETE FROM video_search WHERE video_id = ?", (clip["id"],))
                hidden_count += 1
                
    conn.commit()
    conn.close()
    return {"status": "success", "hidden_count": hidden_count}

@app.post("/api/plan")
def create_plan(req: PlanRequest):
    # We need clips in the tuple format expected by ai_director
    clips_tuples = []
    for c in req.clips:
        clips_tuples.append((
            c["id"], c["path"], c["filename"], c["duration"], 
            c["transcription"], c["visual_tags"], c.get("created", "")
        ))
    
    plan_path = ai_director.generate_story_plan(clips_tuples, req.title)
    
    # Read the text of the generated plan
    if os.path.exists(plan_path):
        with open(plan_path, "r") as f:
            content = f.read()
        return {"plan_path": plan_path, "content": content}
    raise HTTPException(status_code=500, detail="Plan generation failed")


@app.post("/api/plan/stream")
def create_plan_stream(req: PlanRequest):
    clips_tuples = []
    for c in req.clips:
        clips_tuples.append((
            c["id"], c["path"], c["filename"], c["duration"], 
            c["transcription"], c["visual_tags"], c.get("created", "")
        ))
    
    def event_generator():
        for chunk in ai_director.generate_story_plan_stream(clips_tuples, req.title):
            # ai_director ALREADY formats the chunks as Server-Sent Events (SSE)
            yield chunk
            
    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.post("/api/transcription/upgrade")
def upgrade_transcription(req: PlanRequest):
    """Transcribe a specific list of clips (from Studio search results or individual clip button)."""
    settings = load_settings()
    db_path = settings.get("dbPath", os.path.join(os.path.dirname(__file__), "Video_Archive.db"))
    director_engine.init_db(db_path)

    clips_tuples = [
        (c["id"], c["path"], c["filename"], c["duration"],
         c["transcription"], c["visual_tags"], c.get("created", ""))
        for c in req.clips
    ]

    def event_generator():
        import sqlite3 as _sqlite3
        conn = _sqlite3.connect(db_path, timeout=60.0)
        cursor = conn.cursor()
        total = len(clips_tuples)
        for i, (vid_id, path, filename, dur, *_) in enumerate(clips_tuples):
            progress = json.dumps({"chunk": f"Processing {i+1} of {total}: {filename}...\n"})
            yield f"data: {progress}\n\n"
            try:
                text = director_engine.transcribe_single_video(vid_id, path, filename, dur, conn, cursor)
                label = "B-ROLL (No speech)" if not text else f"Transcribed ({len(text.split())} words)"
                chunk_msg = f"  Audio: {label}\n"
                yield f"data: {json.dumps({'chunk': chunk_msg})}\n\n"
            except Exception as e:
                err_msg = f"  Audio Error on {filename}: {e}\n"
                yield f"data: {json.dumps({'chunk': err_msg})}\n\n"
        conn.close()
        done_msg = "DONE\n"
        yield f"data: {json.dumps({'chunk': done_msg})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/api/engine/transcribe-all")
def transcribe_all_indexed():
    """
    Streams transcription progress for every untranscribed video in the DB.
    Gracefully resumes — already-transcribed videos are skipped automatically.
    Each SSE event: {"done": N, "total": M, "filename": "...", "status": "transcribed|b-roll|error"}
    A final event with done == total signals completion.
    """
    settings = load_settings()
    db_path = settings.get("dbPath", os.path.join(os.path.dirname(__file__), "Video_Archive.db"))
    director_engine.init_db(db_path)

    def event_generator():
        import sqlite3 as _sqlite3
        conn = _sqlite3.connect(db_path, timeout=60.0)
        cursor = conn.cursor()

        # Count total pending (no transcription yet, or status != completed)
        cursor.execute("""
            SELECT id, path, filename, duration_sec FROM videos
            WHERE (transcription IS NULL OR transcription = '') AND duration_sec > 2.0
            ORDER BY id ASC
        """)
        pending = cursor.fetchall()
        total = len(pending)

        cursor.execute("SELECT COUNT(*) FROM videos WHERE transcription IS NOT NULL AND transcription != ''")
        already_done = cursor.fetchone()[0]

        # Emit the initial total so the UI can display "0 / N"
        yield f"data: {json.dumps({'done': already_done, 'total': already_done + total, 'filename': '', 'status': 'start'})}\n\n"

        done = already_done
        for vid_id, path, filename, dur in pending:
            if not os.path.exists(path):
                done += 1
                yield f"data: {json.dumps({'done': done, 'total': already_done + total, 'filename': filename, 'status': 'missing'})}\n\n"
                continue
            try:
                text = director_engine.transcribe_single_video(vid_id, path, filename, dur, conn, cursor)
                done += 1
                status = "transcribed" if text else "b-roll"
                yield f"data: {json.dumps({'done': done, 'total': already_done + total, 'filename': filename, 'status': status})}\n\n"
            except Exception as e:
                done += 1
                yield f"data: {json.dumps({'done': done, 'total': already_done + total, 'filename': filename, 'status': 'error', 'error': str(e)})}\n\n"

        conn.close()
        yield f"data: {json.dumps({'done': done, 'total': already_done + total, 'filename': '', 'status': 'complete'})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")




@app.get("/api/video")
def stream_video(path: str):
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Video file not found")
        
    # Sandbox path access
    allowed_prefixes = ["/Volumes/X9 Pro", "/Volumes/Samsung_T5", os.path.dirname(os.path.dirname(os.path.abspath(__file__)))]
    if not any(path.startswith(prefix) for prefix in allowed_prefixes):
        raise HTTPException(status_code=403, detail="Access denied")
        
    import mimetypes
    
    # Guess the MIME type based on the file extension
    mime_type, _ = mimetypes.guess_type(path)
    if not mime_type:
        mime_type = "application/octet-stream"
        
    # FileResponse handles HTTP Range headers automatically, enabling 
    # scrubbing and thumbnail generation in HTML5 <video> elements
    return FileResponse(path, media_type=mime_type)

@app.get("/api/thumbnail")
def get_thumbnail(path: str, t: float = 0.0):
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Video file not found")
        
    from fastapi.responses import Response
    import hashlib
    
    # Persistent on-disk cache keyed by path+timestamp hash — avoids re-running FFmpeg on every request.
    cache_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".thumbnail_cache")
    os.makedirs(cache_dir, exist_ok=True)
    cache_key = hashlib.md5(f"{path}:{t}".encode()).hexdigest()
    cache_path = os.path.join(cache_dir, f"{cache_key}.jpg")
    
    if os.path.exists(cache_path) and os.path.getsize(cache_path) > 0:
        with open(cache_path, "rb") as f:
            return Response(content=f.read(), media_type="image/jpeg", headers={"Cache-Control": "public, max-age=604800"})
    
    cmd = [
        'ffmpeg', '-ss', str(t), '-i', path,
        '-vframes', '1', '-q:v', '2',
        '-vf', 'scale=640:-1',
        '-f', 'image2pipe', '-vcodec', 'mjpeg', '-'
    ]
    try:
        result = subprocess.run(cmd, capture_output=True)
        img_data = result.stdout

        # FFmpeg may exit non-zero for .MOV files even on success; also fall back
        # to t=0 if the seek position produced no frame (e.g. clip shorter than t).
        if not img_data:
            fallback_cmd = [
                'ffmpeg', '-ss', '0', '-i', path,
                '-vframes', '1', '-q:v', '2',
                '-vf', 'scale=640:-1',
                '-f', 'image2pipe', '-vcodec', 'mjpeg', '-'
            ]
            result = subprocess.run(fallback_cmd, capture_output=True)
            img_data = result.stdout

        if not img_data:
            raise HTTPException(status_code=500, detail="Failed to generate thumbnail")

        with open(cache_path, "wb") as f:
            f.write(img_data)
        return Response(content=img_data, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=604800"})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Thumbnail error: {e}")


@app.get("/api/insights")
def get_insights():
    import sqlite3
    from collections import Counter
    import re

    conn = sqlite3.connect(ai_director.DB_PATH)
    cursor = conn.cursor()
    
    # 1. Timeline: Count videos by date
    cursor.execute("SELECT date(created), COUNT(*) FROM videos GROUP BY date(created) ORDER BY date(created) ASC")
    timeline_rows = cursor.fetchall()
    timeline = [{"date": row[0], "count": row[1]} for row in timeline_rows if row[0]]
    
    # 2. Themes: Extract and count words from transcriptions
    cursor.execute("SELECT transcription FROM videos WHERE transcription IS NOT NULL AND transcription != ''")
    transcription_rows = cursor.fetchall()
    conn.close()
    
    word_counts = Counter()
    
    # Common stop words to filter out
    stop_words = {
        "the", "and", "a", "an", "is", "it", "to", "of", "in", "for", "with", "on", "this", 
        "that", "as", "at", "by", "from", "was", "are", "have", "has", "had", "not", "but", 
        "or", "be", "we", "you", "they", "he", "she", "i", "my", "your", "their", "our",
        "can", "will", "would", "could", "should", "here", "there", "what", "where", "when", 
        "why", "how", "so", "if", "then", "just", "like", "about", "out", "up", "down",
        "some", "any", "all", "very", "much", "many", "these", "those", "them", "which",
        "who", "whom", "whose", "it's", "i'm", "don't", "that's", "we're", "you're", "they're",
        "there's", "here's", "what's", "where's", "when's", "why's", "how's", "been", "doing",
        "going", "really", "got", "get", "see", "look", "think", "know", "well", "now",
        "oh", "yeah", "yes", "no", "ok", "okay", "right", "good", "great", "nice", "lot", "little",
        "bit", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
        "first", "say", "said", "did", "didn't", "does", "doesn't", "wasn't", "weren't",
        "am", "isn't", "aren't", "hey", "hi", "hello", "guys", "today", "want", "let", "let's",
        "make", "made", "take", "took", "put", "come", "came", "go", "went", "way", "day", "time",
        "thing", "things", "something", "anything", "nothing", "everything", "someone", "anyone",
        "everyone", "no one", "somebody", "anybody", "nobody", "everybody", "back", "around",
        "through", "over", "into", "because", "cuz", "cause", "too", "also", "even", "than",
        "more", "most", "such", "only", "same", "tell", "show", "give", "find", "use"
    }
    
    import string
    
    for row in transcription_rows:
        text = row[0]
        # Remove punctuation
        text = text.translate(str.maketrans('', '', string.punctuation))
        words = text.split()
        for word in words:
            word_clean = word.strip()
            word_lower = word_clean.lower()
            if len(word_clean) > 3 and word_lower not in stop_words:
                display_word = word_clean.capitalize()
                word_counts[display_word] += 1
                
    # Get top 30 themes
    top_themes = [{"text": k, "value": v} for k, v in word_counts.most_common(30)]
    
    return {
        "timeline": timeline,
        "themes": top_themes
    }

class BuildRequest(BaseModel):
    plan_path: str
    dip_transitions: list[int] = []
    fade_to_black: bool = False
    scene_titles: dict[int, str] = {}
    lower_thirds: list[int] = []


@app.post("/api/build")
def build_video(req: BuildRequest):
    if not os.path.exists(req.plan_path):
        raise HTTPException(status_code=404, detail="Plan file not found")
        
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    build_script = os.path.join(base_dir, "generate_vlog.py")
    
    def generate_build_logs():
        import subprocess
        cmd = ["python3", build_script, req.plan_path]
        if req.dip_transitions:
            cmd += ["--dip-transitions"] + [str(i) for i in req.dip_transitions]
        if req.fade_to_black:
            cmd += ["--fade-to-black"]
        if req.scene_titles:
            cmd += ["--scene-titles"] + [f"{k}:{v}" for k, v in req.scene_titles.items()]
        if req.lower_thirds:
            cmd += ["--lower-thirds"] + [str(i) for i in req.lower_thirds]
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        
        success_sent = False
        for line in iter(process.stdout.readline, ''):
            if line:
                # Check for the final success token
                if line.startswith("SUCCESS: Created"):
                    final_path = line.replace("SUCCESS: Created", "").strip()
                    yield f"data: {json.dumps({'done': final_path})}\n\n"
                    success_sent = True
                else:
                    yield f"data: {json.dumps({'status': line.strip()})}\n\n"
                    
        process.stdout.close()
        process.wait()
        
        # If the process failed and we never emitted a success, send an error
        # event so the frontend can re-enable the Build button.
        if process.returncode != 0 and not success_sent:
            err_msg = f"FFmpeg exited with code {process.returncode}"
            yield f"data: {json.dumps({'error': err_msg})}\n\n"

    return StreamingResponse(generate_build_logs(), media_type="text/event-stream")

@app.post("/api/engine/start")
def start_engine(background_tasks: BackgroundTasks):
    def run_engine():
        director_engine.run_unified_process()
    background_tasks.add_task(run_engine)
    return {"status": "Director engine started in background"}

class ScanRequest(BaseModel):
    path: str

@app.post("/api/engine/scan")
def scan_directory(req: ScanRequest, background_tasks: BackgroundTasks):
    if not os.path.exists(req.path):
        raise HTTPException(status_code=404, detail=f"Directory not found: {req.path}")
    
    def run_scan():
        try:
            director_engine.scan_folder(req.path)
        except Exception as e:
            import traceback
            error_msg = f"FATAL ERROR IN BACKGROUND SCAN:\n{traceback.format_exc()}"
            print(error_msg)
            
            settings = load_settings()
            db_path = settings.get("dbPath", os.path.join(os.path.dirname(__file__), "Video_Archive.db"))
            log_path = os.path.join(os.path.dirname(db_path), "Director_Engine.log")
            
            with open(log_path, "a") as f:
                f.write(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {error_msg}\n")
                
    background_tasks.add_task(run_scan)
    return {"status": f"Started scan of {req.path} in background"}

@app.get("/api/engine/logs")
def get_engine_logs(limit: int = 15):
    """Return the tail of the Director Engine log file."""
    settings = load_settings()
    db_path = settings.get("dbPath", os.path.join(os.path.dirname(__file__), "Video_Archive.db"))
    log_path = os.path.join(os.path.dirname(db_path), "Director_Engine.log")
    
    # Initialize log file on first run
    if not os.path.exists(log_path):
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, "w") as f:
            f.write("Initializing Director Engine...\n")
            
    try:
        with open(log_path, "r") as f:
            lines = f.readlines()
            # Return the last `limit` lines, stripping the raw newline chars
            tail = [line.strip() for line in lines[-limit:] if line.strip()]
            return {"logs": tail}
    except Exception as e:
        return {"logs": [f"Error reading log: {e}"]}
