import os, uuid, shutil, subprocess, threading, time, json, re
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles\nfrom fastapi.middleware.cors import CORSMiddleware

BASE = Path(__file__).parent
DATA = BASE / "data"
UPLOADS = DATA / "uploads"
OUTPUTS = DATA / "outputs"
for p in (UPLOADS, OUTPUTS): p.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="ClipVault AI")
allowed_origins = [x.strip() for x in os.getenv("ALLOWED_ORIGINS", "*").split(",") if x.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins if allowed_origins != ["*"] else ["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=BASE / "public"), name="static")
JOBS = {}
LOCK = threading.Lock()

def run(cmd):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout)[-1800:])
    return p.stdout

def duration(path):
    out = run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",str(path)])
    return max(0.0, float(out.strip()))

def fetch_source(url, dest):
    # Public, directly accessible streams/VODs only. No DRM/auth bypass.
    run(["yt-dlp","--no-playlist","-f","bv*+ba/b","--merge-output-format","mp4","-o",str(dest),url])
    if not dest.exists():
        candidates = list(dest.parent.glob(dest.stem + ".*"))
        if candidates: return candidates[0]
        raise RuntimeError("Source download did not produce a media file.")
    return dest

def transcribe(path):
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel(os.getenv("WHISPER_MODEL","small"), device="cpu", compute_type="int8")
        segments, _ = model.transcribe(str(path), language="hi", vad_filter=True, word_timestamps=True)
        rows=[]
        for seg in segments:
            words = []
            if seg.words:
                words = [{"start": w.start, "end": w.end, "word": w.word.strip()} for w in seg.words]
            rows.append({"start":seg.start,"end":seg.end,"text":seg.text.strip(),"words":words})
        return rows
    except ImportError:
        return []
    except Exception:
        return []

def make_srt(segments, start, end, out):
    def stamp(sec):
        ms=int(max(0,sec)*1000); h=ms//3600000; m=(ms%3600000)//60000; s=(ms%60000)//1000; milli=ms%1000
        return f"{h:02}:{m:02}:{s:02},{milli:03}"
    lines=[]; idx=1
    for seg in segments:
        if seg["end"] < start or seg["start"] > end: continue
        a=max(0,seg["start"]-start); b=max(a+0.2,seg["end"]-start)
        lines += [str(idx),f"{stamp(a)} --> {stamp(b)}",seg["text"],""]; idx+=1
    out.write_text("\\n".join(lines), encoding="utf-8")
    return idx > 1

def candidates(path, length, clip_len=35):
    # Lightweight fallback: evenly sample the source. Production upgrade: audio/video semantic ranking.
    if length <= clip_len: return [(0, length)]
    count=min(8, max(3, int(length // 420)+1))
    step=(length-clip_len)/max(1,count-1)
    return [(i*step, min(length, i*step+clip_len)) for i in range(count)]

def process(job_id, source, source_name):
    try:
        with LOCK: JOBS[job_id]["status"]="processing"; JOBS[job_id]["progress"]=8
        total=duration(source)
        if total < 3: raise RuntimeError("Video is too short.")
        with LOCK: JOBS[job_id]["duration"]=round(total,1); JOBS[job_id]["progress"]=20
        segments=transcribe(source)
        picks=candidates(source,total)
        results=[]
        for n,(start,end) in enumerate(picks,1):
            out=OUTPUTS/f"{job_id}_{n:02}.mp4"
            srt=OUTPUTS/f"{job_id}_{n:02}.srt"
            has_subs=make_srt(segments,start,end,srt) if segments else False
            vf="scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"
            if has_subs:
                # Escape path for ffmpeg subtitles filter.
                subpath=str(srt.resolve()).replace("\\\\","/").replace(":","\\\\:")
                vf += f",subtitles='{subpath}':force_style='FontName=Arial,FontSize=17,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=3,Shadow=1,Alignment=2,MarginV=130'"
            run(["ffmpeg","-y","-ss",str(start),"-i",str(source),"-t",str(end-start),"-vf",vf,"-c:v","libx264","-preset","veryfast","-crf","23","-c:a","aac","-b:a","128k","-movflags","+faststart",str(out)])
            results.append({"name":out.name,"url":f"/media/{out.name}","start":round(start,1),"end":round(end,1),"captioned":has_subs})
            with LOCK: JOBS[job_id]["progress"]=20+int(75*n/len(picks)); JOBS[job_id]["clips"]=results
        with LOCK: JOBS[job_id]["status"]="completed"; JOBS[job_id]["progress"]=100
    except Exception as e:
        with LOCK: JOBS[job_id]["status"]="failed"; JOBS[job_id]["error"]=str(e)

@app.get("/", response_class=HTMLResponse)
def home():
    return (BASE/"public/index.html").read_text(encoding="utf-8")

@app.post("/api/jobs")
async def create_job(background: BackgroundTasks, url: Optional[str]=Form(None), file: Optional[UploadFile]=File(None)):
    if not url and not file: raise HTTPException(400,"Add a video URL or upload a video file.")
    jid=uuid.uuid4().hex[:10]
    if file:
        ext=Path(file.filename or "video.mp4").suffix or ".mp4"
        source=UPLOADS/f"{jid}{ext}"
        with source.open("wb") as f: shutil.copyfileobj(file.file,f)
        source_name=file.filename or source.name
        background.add_task(process,jid,source,source_name)
    else:
        source=UPLOADS/f"{jid}.mp4"
        def fetch_then_process():
            try:
                fetched=fetch_source(url,source)
                process(jid,fetched,url)
            except Exception as e:
                with LOCK: JOBS[jid]["status"]="failed"; JOBS[jid]["error"]=str(e)
        background.add_task(fetch_then_process)
    with LOCK: JOBS[jid]={"id":jid,"status":"queued","progress":0,"clips":[],"source":file.filename if file else url}
    return {"id":jid,"status":"queued"}

@app.get("/api/jobs/{job_id}")
def job_status(job_id):
    with LOCK: job=JOBS.get(job_id)
    if not job: raise HTTPException(404,"Job not found")
    return job

@app.get("/media/{filename}")
def media(filename):
    path=OUTPUTS/Path(filename).name
    if not path.exists(): raise HTTPException(404)
    return FileResponse(path, media_type="video/mp4", filename=path.name)

