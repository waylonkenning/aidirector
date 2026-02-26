# AI Director: Open Source Readiness & Roadmap

To successfully open-source the AI Director application and make it accessible, robust, and easy to run for other developers, several hardcoded assumptions tied to your local development environment need to be abstracted.

Here is a recommended roadmap of architectural changes and features required before publishing the repository.

## 1. Environment & Configuration Portability

Currently, the application relies on hardcoded paths that only exist on your machine (e.g., `/Volumes/X9 Pro/...`). 

- [x] **Move SQLite Database into Application Directory:** Change `DB_PATH = "/Volumes/X9 Pro/Video_Archive.db"` to a relative path like `DB_PATH = os.path.join(os.path.dirname(__file__), "Video_Archive.db")`. This ensures new users have a local database initialized upon cloning.
- [x] **Settings UI for Gemini API Key:** The Gemini API key should not be hardcoded or expected as a system environment variable strictly. Add an input field in the frontend Settings page that saves the key to `backend/settings.json`, which the backend then reads to initialize `google.generativeai`.
- [ ] **Configurable Watch/Archive Folders:** Users need a way to specify where their raw video files are stored.
- [x] **Temp Directories:** Replace hardcoded paths like `/tmp/seg_analysis...` with standard Python cross-platform temporary directory modules (`tempfile.gettempdir()`) or a dedicated `temp/` folder in the project root to prevent permission issues on Windows/Linux. *(Solved: Implemented tempfile across backend processing scripts).*

## 2. Robust Video Indexing Pipeline

The script that scans raw video files, generates thumbnails, and inserts metadata into the database needs to ideally be a polished standalone module.

- [x] **Background Indexer Daemon/Cron:** Create a unified `indexer.py` script that can scan user-defined archive directories for new `mp4/mov` files, extract basic metadata (resolution, fps, duration) using `ffprobe`, and register them in the SQLite DB. *(Solved: Built directly into `director_engine.py --scan-folder`)*.
- [x] **Duplicate Prevention:** Ensure the indexer checks file hashes or absolute paths to prevent re-indexing the same video twice. *(Solved: Built with duplicate path cache and string coercion self-healing in `director_engine.py`)*.

## 3. Transcription & Visual Recognition Portability

The project currently heavily relies on Apple Silicon-specific MLX libraries (`mlx-whisper`, `mlx-vlm`). 

- [ ] **Hardware Agnosticism vs. Apple Silicon Focus:** 
  - *Option A (Apple Silicon Only):* Explicitly brand the open-source project as "AI Director for Mac/Apple Silicon". Document that an M1/M2/M3/M4 chip is required.
  - *Option B (Cross-Platform):* Implement a fallback pipeline. Use `torch` or `transformers` for standard CUDA/CPU execution of Whisper and LLaVA if MLX is not available on the host system.
- [ ] **Model Download Handling:** HuggingFace `mlx-community` models download automatically, but you should display a loading/downloading progress bar in the UI during the first run so users don't think the app is frozen while pulling gigabytes of weights.

## 4. Subprocess Isolation & Concurrency 

You successfully solved the MLX `EXC_BAD_ACCESS` segfaults by isolating transcription into a separate process (`subprocess.run(['python3', '-c', code])`). 

- [x] **Standardized Task Queues:** While `subprocess` works, a more robust open-source pattern would be using a lightweight background task queue (like `Celery` + `Redis` or `Huey`/`RQ` with SQLite) to dispatch long-running ML jobs (transcription, visual tagging, FFmpeg renders) without blocking FastAPI endpoints. *(Currently partially solved via isolated subprocesses for MLX)*.
- [x] **WebSockets for Job Status:** Upgrade the UI to show real-time progress bars for transcription and rendering tasks via WebSockets or SSE, rather than just waiting for backend HTTP responses. *(Solved: Server-Sent Events (SSE) implemented across the frontend).*

## 5. Dependency Management & Documentation

- [ ] **`requirements.txt` / `Pipfile`:** A clean Python dependency file must be created containing exact working versions of `fastapi`, `uvicorn`, `mlx-whisper`, `mlx-vlm`, `google-generativeai`, etc.
- [ ] **`package.json` Cleanup:** Ensure the Next.js `frontend_app` has no broken dependencies or references to deleted internal folders.
- [ ] **System Dependencies:** Document that `ffmpeg` and `ffprobe` must be installed on the host machine (`brew install ffmpeg` / `apt-get install ffmpeg`).
- [ ] **Comprehensive `README.md`:** Write a clear getting started guide:
    1. Clone repo
    2. Run `npm install`
    3. Run `pip install -r requirements.txt`
    4. Install `ffmpeg`
    5. Set Gemini API Key in UI Settings.

## 6. Security Warning
- [x] Examine `ai_director.py` and `main.py` for any remaining hardcoded credentials, personal names, or absolute paths containing your username before pushing to a public GitHub repository.
