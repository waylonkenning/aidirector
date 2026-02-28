# 🎬 Auto-Editor Agent: Precise Timeline Analysis

This agent represents **Phase 2** of the Director AI project. While the "Director Engine" performs global indexing for search, the **Auto-Editor Agent** performs surgical, frame-accurate analysis for automated editing.

---

## 🛠 How it Works
The script (`~/scripts/auto_editor.py`) breaks down a video into a "Master Timeline" by aligning spoken words with specific visual frames.

### 1. Surgical Transcription
Unlike the global indexer, the Auto-Editor extracts **Sentence-Level Segments** using `mlx-whisper` (`small-mlx`).
- **Input:** Raw Video.
- **Output:** Precise `[start_time -> end_time]` timestamps for every spoken phrase.
- **Rescue Mode:** Automatically re-processes clips with `large-v3-turbo` if repetitive hallucinations (e.g., "última" loops) are detected.

### 2. Temporal Visual Alignment
For every audio segment, the agent "looks" at the video to verify what is on screen *while* that specific sentence is being spoken.
- **Process:**
    1. Calculate the midpoint of the audio segment.
    2. Use `ffmpeg` to extract a high-quality frame at that exact millisecond.
    3. Pass the frame to `mlx-vlm` (NanoLLaVA) for a "moment-specific" description.

### 3. Timeline Mapping
The result is a structured JSON timeline that pairs **Narrative (A-Roll)** with **Visual Context (B-Roll Verification)**.

**Example Mapping:**
- `[34.0s -> 37.0s]`
- **Audio:** "In the orange, looks yummy."
- **Visual:** "Close-up of a person holding a slice of orange."
- **Editor Logic:** This segment is "Synced A-Roll" (The visual matches the speech).

---

## 🚀 Integration: The Programmatic Video Builder
The timeline mapping data generated above is consumed by the **Story Plan Generator**. Once the LLM signs off on a chronological sequence of segments, our programmatic FFmpeg builder (`generate_vlog.py`) executes the edit:
1. **Removes "Dead Air":** It slices the exact millisecond `[start-end]` bounds returned by the agent.
2. **Smart Overlays:** It injects exact B-roll overlays defined by the semantic matches.
3. **Format Normalization:** It scales everything to 1920x1080, normalizes frame rates to 30fps, and forces uniform stereo audio layout.
4. **Transition Effects:**
    - **Dip to Black:** A 1-second graphical transition can be enabled per-scene to provide a professional pacing break.
    - **Fade to Black:** A global end-of-video fade can be enabled to smoothly close the narrative.

Using the "🎞️ Build my video" button in the AI Studio Interface triggers this exact build pipeline sequentially.

---
**Last Updated:** Saturday, Feb 28, 2026 - 02:55 PM
