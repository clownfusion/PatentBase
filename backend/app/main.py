from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path
from backend.app.core.config import settings
from backend.app.core.database import init_db
from backend.app.api import patents_router, analyze_router, reports_router

app = FastAPI(title=settings.app_title, version=settings.app_version)

FRONTEND_DIR = Path(__file__).parents[2] / "frontend"

app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(FRONTEND_DIR / "templates"))

app.include_router(patents_router.router)
app.include_router(analyze_router.router)
app.include_router(reports_router.router)


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/")
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/health")
def health():
    return {"status": "ok", "version": settings.app_version}
