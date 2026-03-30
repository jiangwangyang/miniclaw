import logging
from pathlib import Path

from fastapi import FastAPI, APIRouter
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

STATIC_DIR = Path(__file__).parent / "static"
router = APIRouter(prefix="")


@router.get("/")
@router.get("/index")
@router.get("/index.html")
async def index():
    return RedirectResponse(url="/static/index.html", status_code=302)


async def before_application(app: FastAPI, **kwargs):
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.include_router(router)
    logging.info("Web plugin started")


async def after_application(**kwargs):
    logging.info("Web plugin stopped")


async def before_chat(**kwargs):
    pass


async def after_chat(**kwargs):
    pass


async def before_model(**kwargs):
    pass


async def after_model(**kwargs):
    pass


async def before_tool(**kwargs):
    pass


async def after_tool(**kwargs):
    pass
