# 🎥 Master Video Archive System (M4 Mac Mini)

This document outlines the architecture and operation of the on-device video brain built for the **X9 Pro** drive.

---

## 🆘 RECOVERY & RESUMING
If the Terminal window closes, the Mac restarts, or processing stops, use these commands:

### 1. Check if it's currently running
```bash
ps -ef | grep -E "director_engine.py" | grep -v grep
```

### 2. Manual Relaunch (if stopped)
If the above command returns nothing, restart the backend engine inside your Python environment:
```bash
cd backend
python3 -m uvicorn main:app --port 8000
```
*Note: Background processing for new videos can also be triggered directly from the UI through the backend API.*

---

## 🚀 System Overview
Your **M4 Mac Mini** is transforming an archive of **21,646 videos** into a searchable, auto-editable library. It uses a unified local pipeline to process narrative and visual data simultaneously.

---

## ⚙️ Unified "Director Engine"
Previously two separate systems, the logic is now combined into a single robust daemon: `director_engine.py`. Before this daemon can process files, they must be ingested into the system.

### 📁 Ingesting New Libraries
To point the engine at a new folder or hard drive (e.g., an Apple Photos export folder):
```bash
python3 director_engine.py --scan-folder "/path/to/my/videos"
```
*This command safely crawls the folder, extracts EXIF creation timestamps via `ffprobe`, and inserts the paths into the database, repairing any malformed duplicates along the way.*

### 🧠 Intelligence Layers
1.  **The Narrative Layer (Audio):**
    *   **Engine:** `mlx-whisper` (**Small Model** - `whisper-small-mlx`).
    *   **Configuration:** Forced **English** detection to prevent hallucinations in noisy clips.
    *   **Rescue Mode:** Automatic re-processing with `whisper-large-v3` if noise-induced loops are detected.
2.  **The Visual Layer (Vision):**
    *   **Engine:** `mlx-vlm` (`nanoLLaVA-1.5-8bit`).
    *   **Function:** Extracts keyframes and "watches" them to generate descriptive tags.
    *   **B-Roll Filter:** Identifies cinematic atmosphere (landscapes, objects, transit) where speech is low.

---

## 🎬 The "Director AI" Vision
The engine builds the foundation for automated video editing:
-   **Phase 1 (Global Indexer):** Thematic Grouping and Smart Search (Complete/Ongoing).
-   **Phase 2 (Auto-Editor Agent):** Surgical segment-level analysis for frame-accurate cutting (Live).
-   **Phase 3 (Editorial Storyboard):** Automatic generation of movie-script style summaries with A-Roll/B-Roll classification.

## 🧹 Archive Maintenance
To keep the library clean, the system provides specialized tools in the **Settings (⚙️)** panel:

1.  **Smart Duplicate Detection**:
    *   **Logic:** Identifies clips with near-identical durations (±0.1s) created within a **5-minute window**. 
    *   **Function:** Automatically suggests a "Keeper" based on filename quality (camera originals vs downloads).
2.  **Live Photo Cleanup**:
    *   **Logic:** Identifies clips shorter than **3 seconds**.
    *   **Function:** Marks them as `livephoto` status, removing them from the Studio search and archive stats.

---

## 🏗 Storage & Logs
-   **Database:** `Video_Archive.db` (SQLite + FTS5 Search).
-   **Unified Log:** Terminal output from the FastAPI backend and Next.js frontend.
-   **Editorial Storyboards:** Generated visually in the AI Studio and saved as `STORY_PLAN_[date].md`.
-   **Compiled Videos:** Saved to `VLOG_BUILD` before final output.

---

## 🔍 How to Search
The entire archive is now searchable via the local **AI Studio Next.js Interface**. Navigate to `http://localhost:3000` to visually search by keyword, filter by date using the heatmap Calendar, or generate video rough cuts.

---

## 📋 Technical Specs
-   **Hardware:** Apple M4 Mac Mini (Neural Engine & GPU Optimized).
-   **Process:** ~4-5 seconds per video for full multi-modal indexing.
-   **Resumability:** The script can be stopped and restarted anytime; it automatically skips finished files.

---
**Last Updated:** Saturday, Feb 28, 2026 - 02:50 PM
