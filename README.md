# AI Director

A fully localized, serverless video ingestion pipeline and conversational AI engine optimized explicitly for Apple Silicon (M-series Macs). 

AI Director allows you to dump entire SD cards or massive folders of raw video clips (`.mp4`, `.mov`, `.avi`, `.mkv`, etc.) onto a drive. The engine will autonomously scan them, generate proxy thumbnails, transcribe all dialogue locally using MLX Whisper, and generate semantic visual tags using a local Vision Language Model (MLX LLaVA). 

You can then search, filter, and chat with your entire video archive via a beautiful Next.js frontend, or ask the AI to generate JSON timelines to automatically import into Premiere Pro/DaVinci Resolve!

## System Requirements

This project is explicitly tailored for high-performance execution on Mac hardware using Apple's MLX framework.
- **Hardware:** Apple Silicon (M1, M2, M3, M4)
- **OS:** macOS 13.3+ minimum
- **External Dependencies:** `ffmpeg` and `ffprobe` must be installed on your system.
    ```bash
    brew install ffmpeg
    ```

## Installation

### 1. Database & Python Backend
First, set up your Python environment and install the required MLX engines.

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Next.js Frontend
In a separate terminal window, initialize the React user interface.

```bash
cd frontend_app
npm install
```

## Running the Application

You will need to run both the FastAPI backend and the Next.js frontend simultaneously.

**Terminal 1 (Backend):**
```bash
cd backend
source venv/bin/activate
python3 -m uvicorn main:app --port 8000 --reload
```

**Terminal 2 (Frontend):**
```bash
cd frontend_app
npm run dev
```

Finally, open your browser to `http://localhost:3000`. 

## Initial Configuration
1. Click the **Settings (⚙️)** tab in the sidebar.
2. Enter the absolute path where you want the SQLite database to live (e.g., `/Users/yourname/Desktop/Video_Archive.db`).
3. Add the absolute folders mapping to your raw video files under **Target Scan Directories**.
4. Enter your Gemini API key (this is passed to the LLM agent that handles natural language searches—your actual video transcription and tagging is all done 100% locally).
5. Click **Scan Directory & Process Videos** to start building your database!

> **Note on First Run:** The exact first time you click "Scan", the backend will automatically pull the MLX versions of Whisper and LLaVA from HuggingFace. This initial download can take several minutes and occupy 5-10GB of disk space.

*Built by Waylon Kenning.*
