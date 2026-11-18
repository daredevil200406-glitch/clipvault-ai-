# Deploy ClipVault AI with Netlify (frontend) + Render (Python API)

Netlify hosts the website files. The Python/FFmpeg video-processing server must run separately; Netlify Functions are not a suitable host for long-running video jobs or FFmpeg processing.

## 1) Deploy the API server to Render
1. Push this project folder to a GitHub repository.
2. In Render, create a **Web Service** from that repository.
3. Set build command: `pip install -r requirements.txt`
4. Set start command: `uvicorn server:app --host 0.0.0.0 --port $PORT`
5. Ensure FFmpeg and ffprobe are installed in the runtime. The included `render.yaml` is a starting configuration; if the selected Render runtime does not include FFmpeg, use a Docker deployment based on `python:3.11-slim` and install `ffmpeg`.
6. Add environment variable `ALLOWED_ORIGINS` with your exact Netlify site URL.
7. Add a persistent disk mounted at `/opt/render/project/src/data` (or configure a suitable persistent media store). Video files on an ephemeral filesystem can disappear after restart/redeploy.

## 2) Configure the frontend
1. Open `public/index.html`.
2. Replace `https://YOUR-BACKEND-SERVICE.onrender.com` in `window.CLIPVAULT_API` with your actual Render service URL.
3. Replace `https://YOUR-SITE.netlify.app` in Render's `ALLOWED_ORIGINS` with your actual Netlify site URL.

## 3) Deploy to Netlify
1. In Netlify, choose **Add new site → Import an existing project** and connect the GitHub repository.
2. Set publish directory to `public`; no build command is needed.
3. Deploy.

## Notes
- The included API is an MVP. It uses in-process background tasks and local files, not a production-grade distributed queue.
- Continuous real-time live clipping, robust highlight detection, user accounts, upload limits, and secure multi-user storage still require further development.
- Do not expose an unauthenticated public upload endpoint to the internet without authentication, rate limits, file-size limits, and storage controls.
