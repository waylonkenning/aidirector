import os
import sys
# Triggering uvicorn hot-reload to load ai_director.py changes
import subprocess
import warnings

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
    dbPath: str = None
    watchFolders: list[str] = None

@app.post("/api/settings")
def update_user_settings(req: SettingsUpdate):
    settings = load_settings()
    if req.geminiModel:
        settings["geminiModel"] = req.geminiModel
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
    # Ensure all tables exist before attempting to write segments
    settings = load_settings()
    db_path = settings.get("dbPath", os.path.join(os.path.dirname(__file__), "Video_Archive.db"))
    director_engine.init_db(db_path)

    clips_tuples = []
    for c in req.clips:
        clips_tuples.append((
            c["id"], c["path"], c["filename"], c["duration"], 
            c["transcription"], c["visual_tags"], c.get("created", "")
        ))
        
    def event_generator():
        for chunk in ai_director.upgrade_transcription_stream(clips_tuples):
            data = json.dumps({"chunk": chunk})
            yield f"data: {data}\n\n"
            
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


@app.post("/api/build")
def build_video(req: BuildRequest):
    if not os.path.exists(req.plan_path):
        raise HTTPException(status_code=404, detail="Plan file not found")
        
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    build_script = os.path.join(base_dir, "generate_vlog.py")
    
    def generate_build_logs():
        import subprocess
        process = subprocess.Popen(
            ["python3", build_script, req.plan_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        
        for line in iter(process.stdout.readline, ''):
            if line:
                # Check for the final success token
                if line.startswith("SUCCESS: Created"):
                    final_path = line.replace("SUCCESS: Created", "").strip()
                    yield f"data: {json.dumps({'done': final_path})}\n\n"
                else:
                    yield f"data: {json.dumps({'status': line.strip()})}\n\n"
                    
        process.stdout.close()
        process.wait()

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
