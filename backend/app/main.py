from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path
from backend.app.core.config import settings
from backend.app.core.database import init_db
from backend.app.api import patents_router, analyze_router, reports_router

FRONTEND_DIR = Path(__file__).parents[2] / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title=settings.app_title, version=settings.app_version, lifespan=lifespan)

app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(FRONTEND_DIR / "templates"))

app.include_router(patents_router.router)
app.include_router(analyze_router.router)
app.include_router(reports_router.router)


@app.get("/")
def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@app.get("/health")
def health():
    return {"status": "ok", "version": settings.app_version}
