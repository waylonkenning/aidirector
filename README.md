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

## 🚀 Quick Start (One-Click Launch)

This project includes a smart startup script that automatically handles all Python virtual environments, `pip` dependencies, and `npm` Node modules for you on its first run.

**To install and run the application:**
Simply double-click the `Launch AIDirector.command` file in the project directory. 

*Alternatively, you can run it from the terminal:*
```bash
./Launch\ AIDirector.command
```

*Note: On the very first run, it may take 2-3 minutes to download all necessary dependencies. Once complete, it will automatically spin up the FastAPI background process and launch the Next.js UI.*

Finally, open your browser to `http://localhost:3000`. 

## Initial Configuration
1. Click the **Settings (⚙️)** tab in the sidebar.
2. Enter the absolute path where you want the SQLite database to live (e.g., `/Users/yourname/Desktop/Video_Archive.db`).
3. Add the absolute folders mapping to your raw video files under **Target Scan Directories**.
4. Enter your Gemini API key (this is passed to the LLM agent that handles natural language searches—your actual video transcription and tagging is all done 100% locally).
5. Click **Scan Directory & Process Videos** to start building your database!

> **Note on First Run:** The exact first time you click "Scan", the backend will automatically pull the MLX versions of Whisper and LLaVA from HuggingFace. This initial download can take several minutes and occupy 5-10GB of disk space.

*Built by Waylon Kenning.*
