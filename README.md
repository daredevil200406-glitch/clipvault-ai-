# ClipVault AI (MVP)

A self-hostable web app starter for VOD and live-stream clipping.

## What works in this starter
- Responsive dark dashboard
- Upload a local video or submit a supported public VOD/live URL
- Background job queue and status polling
- FFmpeg-based vertical 9:16 clip rendering
- Optional Hinglish transcription/captions with faster-whisper
- Download generated MP4s

## Important scope
This is an MVP starter, not a production clone of PeakCut. Automatic highlight ranking is currently heuristic (scene changes + audio activity) and should be upgraded with an LLM/multimodal ranking service. Live capture requires a continuously reachable stream URL and server-side FFmpeg/yt-dlp; platform access, creator permission, and platform terms apply. Do not bypass DRM, login walls, or access controls.

## Run locally
Requirements: Python 3.11+, FFmpeg installed and available on PATH.

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
source .venv/bin/activate
pip install -r requirements.txt
uvicorn server:app --reload
```
Open http://127.0.0.1:8000

For transcription/captions:
```bash
pip install faster-whisper
```
The first transcription downloads a model. Set `WHISPER_MODEL=small` (default) or `medium` in your environment. Hindi/Hinglish recognition depends on the model and audio quality.

## Deploy
Deploy the Python app to a VM/container that has FFmpeg installed and persistent disk. For production, move jobs and media to Redis + object storage, add authentication, quotas, malware scanning, and a managed worker. Do not deploy this demo with public uploads enabled without those protections.
