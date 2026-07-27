"""Sentry RAG - main FastAPI app.

Environment:
- DATABASE_URL (postgres+asyncpg://)
- NIM_API_KEY
- JWT_SECRET
- ADMIN_EMAIL / ADMIN_PASSWORD (optional; auto-generates if password missing)
"""
import os
import logging
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, APIRouter
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from starlette.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env", override=True)

from database import init_db
import nim_client
from routers.auth_router import router as auth_router
from routers.admin_router import router as admin_router
from routers.chat_router import router as chat_router


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Sentry RAG - initializing database and seeding admin...")
    await init_db()
    logger.info("Sentry RAG - startup complete")
    yield
    logger.info("Sentry RAG - shutdown")
    await nim_client.close_client()


app = FastAPI(title="SENTRY/RAG", lifespan=lifespan)

api_router = APIRouter(prefix="/api")


@api_router.get("/")
async def root():
    return {"service": "sentry-rag", "status": "ok"}


@api_router.get("/health")
async def health():
    return {"status": "ok"}


api_router.include_router(auth_router)
api_router.include_router(admin_router)
api_router.include_router(chat_router)

app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve the React build on Hugging Face Spaces (FRONTEND_BUILD_DIR set in Dockerfile).
_frontend_dir = Path(os.environ.get("FRONTEND_BUILD_DIR", "")).resolve()
if _frontend_dir.is_dir() and (_frontend_dir / "index.html").exists():
    _assets = _frontend_dir / "static"
    if _assets.is_dir():
        app.mount("/static", StaticFiles(directory=str(_assets)), name="static")

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        candidate = _frontend_dir / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_frontend_dir / "index.html")
