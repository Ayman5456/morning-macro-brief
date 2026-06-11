from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse

from .job import run_brief_job


app = FastAPI(title="Morning Macro Brief Engine", version="0.2.0")


MEDIA_TYPES = {
    ".aac": "audio/aac",
    ".mp3": "audio/mpeg",
    ".opus": "audio/ogg",
    ".flac": "audio/flac",
    ".wav": "audio/wav",
    ".pcm": "application/octet-stream",
    ".json": "application/json",
}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/brief")
def brief(
    format: Literal["text", "audio", "json"] = Query("text"),
    date: str | None = Query(None),
    timezone: str | None = Query(None),
    region: str = Query("global"),
    brief_type: Literal["morning", "evening"] = Query("morning"),
    sample: bool = Query(False),
    no_agent: bool = Query(False),
):
    try:
        result = run_brief_job(
            mode="audio" if format == "audio" else "text",
            target_date=date,
            timezone=timezone,
            region=region,
            brief_type=brief_type,
            sample_data=sample,
            no_agent=no_agent,
            output_dir=Path("outputs"),
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if format == "audio":
        if not result.audio_path:
            raise HTTPException(status_code=500, detail="Audio output was not created.")
        path = Path(result.audio_path)
        media_type = "application/json" if path.name.endswith(".audio.json") else MEDIA_TYPES.get(path.suffix, "application/octet-stream")
        return FileResponse(result.audio_path, media_type=media_type, filename=path.name)
    if format == "json":
        return JSONResponse(result.model_dump())
    return PlainTextResponse(result.output.markdown)


def main() -> None:
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8421"))
    uvicorn.run("morning_brief.server:app", host=host, port=port)


if __name__ == "__main__":
    main()
