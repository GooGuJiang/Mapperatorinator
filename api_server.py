import os
import uuid
import threading
import queue
import shutil
import json
import asyncio
import contextlib
import io
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from sse_starlette.sse import EventSourceResponse
import hydra
from omegaconf import OmegaConf

import inference

app = FastAPI(title="Mapperatorinator API")


class _QueueWriter(io.TextIOBase):
    """File-like object that pushes written lines to a queue."""

    def __init__(self, q: queue.Queue[str | None]):
        self.q = q
        self._buf = ""

    def write(self, s: str) -> int:
        self._buf += s
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            self.q.put(line)
        return len(s)

    def flush(self) -> None:
        if self._buf:
            self.q.put(self._buf)
            self._buf = ""


class Job:
    def __init__(self, audio: UploadFile, beatmap: Optional[UploadFile], config: str, overrides: Dict[str, Any]):
        self.id = uuid.uuid4().hex
        self.work_dir = os.path.abspath(os.path.join("outputs", self.id))
        os.makedirs(self.work_dir, exist_ok=True)
        self.queue: queue.Queue[str | None] = queue.Queue()
        self.output_file: Optional[str] = None

        audio_path = os.path.join(self.work_dir, audio.filename)
        with open(audio_path, "wb") as f:
            shutil.copyfileobj(audio.file, f)

        beatmap_path = None
        if beatmap:
            beatmap_path = os.path.join(self.work_dir, beatmap.filename)
            with open(beatmap_path, "wb") as f:
                shutil.copyfileobj(beatmap.file, f)

        self.thread = threading.Thread(
            target=self._run,
            args=(audio_path, beatmap_path, config, overrides),
            daemon=True,
        )
        self.thread.start()

    def _run(self, audio_path: str, beatmap_path: Optional[str], config: str, overrides: Dict[str, Any]) -> None:
        writer = _QueueWriter(self.queue)
        with contextlib.redirect_stdout(writer), contextlib.redirect_stderr(writer):
            try:
                params = dict(overrides)
                params["audio_path"] = audio_path
                params["output_path"] = self.work_dir
                if beatmap_path:
                    params["beatmap_path"] = beatmap_path
                overrides_list = [f"{k}={v}" for k, v in params.items()]
                with hydra.initialize(config_path="configs/inference", version_base="1.1"):
                    cfg = hydra.compose(config_name=config, overrides=overrides_list)
                args = OmegaConf.to_object(cfg)
                _, _, osz = inference.main.__wrapped__(args)
                if osz:
                    self.output_file = osz
            except Exception as e:
                self.queue.put(f"ERROR: {e}")
        self.queue.put(None)


jobs: Dict[str, Job] = {}


@app.post("/api/infer")
async def start_inference(
    audio: UploadFile = File(...),
    beatmap: Optional[UploadFile] = File(None),
    config: str = Form("v30"),
    params: str = Form("{}"),
):
    try:
        overrides = json.loads(params) if params else {}
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"invalid params: {e}")

    job = Job(audio, beatmap, config, overrides)
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
    if job.thread.is_alive():
        raise HTTPException(status_code=409, detail="job not finished")
    raise HTTPException(status_code=404, detail="output not found")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=5005)
