# AI Studio Dashboard

This is the Next.js application that provides the visual interface and search tools for the AI Director Engine. The frontend is fully decoupled from the processing scripts but relies heavily on the FastAPI backend for real-time Server-Sent Event (SSE) streaming during long-running tasks.

## Getting Started

To run the local development server:

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the interface.

## Architecture & Integration

- This UI connects directly to `http://localhost:8000` assuming the Python `main.py` FastAPI server is running.
- Complex state management for the NLE (Non-Linear Editor) Viewer is handled in `src/app/studio/page.tsx`.
- Long-running inference processes (Story Plan Generation, Subprocess Transcription, and Vlog Rendering) stream their UI progress bar updates over WebSockets/SSE.

## Settings & Models

You no longer need to pass environment variables directly into Next.js. The AI Studio interface features a unified `⚙️ Settings` modal that manages the Gemini API Key state securely with the backend.
