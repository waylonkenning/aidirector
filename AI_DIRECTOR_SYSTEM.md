# 🎬 AI Director System: Automated Video Editing Pipeline

This document explains how the **AI Director** transforms thousands of raw clips into finished videos. The system follows a **"Search -> Select -> Stitch"** philosophy.

---

## 🛠 1. The Multi-Modal Brain (`director_engine.py`)
The system starts by indexing every video file on the X9 Pro drive. It doesn't just look at file names; it understands content.

### **Indexing Layers:**
- **Narrative (Audio):** `mlx-whisper` extracts every word spoken.
- **Visual (Vision):** `mlx-vlm` (NanoLLaVA) analyzes keyframes to generate descriptive tags (e.g., "crowded street," "close-up of food").
- **Metadata:** Extracts GPS, creation date, and camera specs.

---

## 🎭 2. The Editorial Storyboard (`auto_editor.py`)
When you select a topic or date, the AI assumes the role of an **Editor**. It classifies clips into two roles:

### **A-ROLL (The Narrative)**
- **Criteria:** High speech density, face detected, steady camera.
- **Function:** Tells the story, provides the "talking head" or primary action.

### **B-ROLL (The Context)**
- **Criteria:** Low speech, high visual interest, cinematic movement (pans/tilts).
- **Function:** Covers jump cuts, provides atmosphere, and visually reinforces the narrative.

---

## ✂️ 3. Narrative Logic for B-Roll Overlays
The AI doesn't drop B-roll randomly. It follows three editorial rules:

1.  **Semantic Match:** If the narrator says "dumplings," the AI searches visual tags for "dumplings" or "food stall" and overlays it within 1 second of the mention.
2.  **Atmospheric Context:** Intro and Outro segments are overlaid with wide shots of the location (e.g., "Shanghai skyline") to establish the setting.
3.  **Jump Cut Coverage:** When the narrator's head "jumps" due to a cut in speech, a 2-3 second B-roll clip is used to mask the transition.

---

## 🚀 4. The AI Studio Interface (`page.tsx`)
To generate a video, open your browser and navigate to the local Next.js frontend at `http://localhost:3000`.

### **Repeatable Workflow:**
1.  **Search & Filter:** Enter a keyword (e.g., "dumplings") or select a date on the Calendar heatmap.
2.  **Clean Archive:** Use the **Hide Selected (🚫)** button or individual **Hide (✕)** buttons on clip cards to mark redundant or unwanted files as duplicates.
3.  **Transcribe:** Select specific clips and click **"🎙️ Transcribe Clips (x)"** to use the heavy `whisper-large-v3-mlx` model only on what you need.
4.  **Generate Plan:** Click **"🎬 Generate Story Plan"**. The UI will animate as Gemini analyzes the clips and drafts a chronological narrative.
5.  **Review Plan:** The generated plan appears in the interactive NLE Viewer.
6.  **Build Video:** Click **"🎞️ Build my video"**. You can toggle **"Fade to black at end"**, **"Lower thirds on all"**, or individual **"Dip to black"** transitions between scenes.

---

## 📋 Data Flow Architecture
`Raw Footage` -> `Director Engine (DB)` -> `Auto-Editor (MD/JSON Plan)` -> `FFmpeg (Final MP4)`

**Last Updated:** Saturday, Feb 28, 2026 - 02:45 PM
