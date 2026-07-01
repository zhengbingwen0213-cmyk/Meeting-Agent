import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from typing import Union

from app.config import get_settings
from app.routes import router


settings = get_settings()
settings.storage_dir.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
meeting_logger = logging.getLogger("meeting-point")
meeting_logger.setLevel(logging.INFO)
backend_log_path = settings.storage_dir / "backend.log"
if not any(getattr(handler, "baseFilename", "") == str(backend_log_path) for handler in meeting_logger.handlers):
    file_handler = logging.FileHandler(backend_log_path, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s - %(message)s"))
    meeting_logger.addHandler(file_handler)

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix=settings.api_prefix)


@app.get("/")
async def root() -> dict[str, Union[str, int]]:
    return {
        "name": settings.app_name,
        "status": "ok",
        "port": settings.app_port,
    }


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
