import os
import sys
import uuid
import subprocess
import threading
import queue
import asyncio

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

app = FastAPI(title="Mapperatorinator API")

class Job:
    def __init__(self, cmd: list[str], work_dir: str):
        self.id = uuid.uuid4().hex
        self.work_dir = work_dir
        os.makedirs(work_dir, exist_ok=True)
        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1,
        )
        self.queue: queue.Queue[str | None] = queue.Queue()
        self.output_file: str | None = None
        self.thread = threading.Thread(target=self._collect_output, daemon=True)
        self.thread.start()

    def _collect_output(self) -> None:
        assert self.process.stdout is not None
        for line in iter(self.process.stdout.readline, ""):
            self.queue.put(line)
            if "Generated .osz saved to" in line:
                self.output_file = line.strip().split(" to ")[-1]
        self.process.stdout.close()
        self.process.wait()
        self.queue.put(None)

jobs: dict[str, Job] = {}

class InferRequest(BaseModel):
    audio_path: str
    beatmap_path: str | None = None
    model: str = "v30"
    export_osz: bool = True

@app.post("/api/infer")
def start_inference(req: InferRequest):
    work_dir = os.path.abspath(os.path.join("outputs", uuid.uuid4().hex))
    cmd = [
        sys.executable,
        "inference.py",
        "-cn",
        req.model,
        f"audio_path={req.audio_path}",
        f"output_path={work_dir}",
    ]
    if req.beatmap_path:
        cmd.append(f"beatmap_path={req.beatmap_path}")
    cmd.append("export_osz=true" if req.export_osz else "export_osz=false")

    job = Job(cmd, work_dir)
    jobs[job.id] = job
    return {"job_id": job.id}

@app.get("/api/progress/{job_id}")
async def progress(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")

    async def event_generator():
        while True:
            line = await asyncio.to_thread(job.queue.get)
            if line is None:
                break
            yield {"data": line}

    return EventSourceResponse(event_generator())

@app.get("/api/download/{job_id}")
def download(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    if job.output_file and os.path.exists(job.output_file):
        return FileResponse(job.output_file, filename=os.path.basename(job.output_file), media_type="application/octet-stream")
    if job.process.poll() is None:
        raise HTTPException(status_code=409, detail="job not finished")
    raise HTTPException(status_code=404, detail="output not found")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5005)

