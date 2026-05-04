import logging
import pathlib
import uuid
from contextlib import asynccontextmanager
from datetime import datetime

import httpx
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, APIRouter, HTTPException
from pydantic import BaseModel

CHAT_URL = "http://localhost:11223/chat"
DB_FILE = str(pathlib.Path.home() / ".miniclaw" / "tasks.db")
pathlib.Path(DB_FILE).parent.mkdir(parents=True, exist_ok=True)
SCHEDULER = AsyncIOScheduler(jobstores={"default": SQLAlchemyJobStore(url=f"sqlite:///{DB_FILE}")})
ASYNC_CLIENT = httpx.AsyncClient()
ROUTER = APIRouter(prefix="/task")


class TaskEntity(BaseModel):
    name: str
    content: str
    year: str
    month: str
    day: str
    week: str
    day_of_week: str
    hour: str
    minute: str
    second: str


async def execute_task(task_id: str, name: str, content: str):
    url = f"{CHAT_URL}/{task_id}"
    body = {
        "message": content,
        "workdir": "/tmp",
        "stream": False
    }
    response = await ASYNC_CLIENT.post(url, json=body)
    response.raise_for_status()


def job_to_dict(job) -> dict:
    return {
        "id": job.id,
        "name": job.name,
        "content": job.args[2] if len(job.args) > 2 else "",
        "year": str(job.trigger.fields[0]),
        "month": str(job.trigger.fields[1]),
        "day": str(job.trigger.fields[2]),
        "week": str(job.trigger.fields[3]),
        "day_of_week": str(job.trigger.fields[4]),
        "hour": str(job.trigger.fields[5]),
        "minute": str(job.trigger.fields[6]),
        "second": str(job.trigger.fields[7]),
        "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
        "enabled": job.next_run_time is not None
    }


@ROUTER.get("/list")
async def list_tasks():
    jobs = SCHEDULER.get_jobs()
    return [job_to_dict(job) for job in jobs]


@ROUTER.post("")
async def save_task(task: TaskEntity):
    task_id = str(uuid.uuid4())
    SCHEDULER.add_job(execute_task, "cron", id=task_id, name=task.name, args=[task_id, task.name, task.content], year=task.year, month=task.month, day=task.day, week=task.week, day_of_week=task.day_of_week, hour=task.hour, minute=task.minute, second=task.second)


@ROUTER.delete("/{task_id}")
async def delete_task_by_id(task_id: str):
    job = SCHEDULER.get_job(task_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    SCHEDULER.remove_job(task_id)


@ROUTER.post("/{task_id}/enable")
async def enable_task_by_id(task_id: str):
    job = SCHEDULER.get_job(task_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    SCHEDULER.resume_job(task_id)


@ROUTER.post("/{task_id}/disable")
async def disable_task_by_id(task_id: str):
    job = SCHEDULER.get_job(task_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    SCHEDULER.pause_job(task_id)


@ROUTER.post("/{task_id}/run")
async def run_task_now(task_id: str):
    job = SCHEDULER.get_job(task_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    SCHEDULER.modify_job(job.id, next_run_time=datetime.now())


@asynccontextmanager
async def lifespan(app: FastAPI, **kwargs):
    if not SCHEDULER.running:
        SCHEDULER.start()
    app.include_router(ROUTER)
    logging.info("Scheduler plugin started, scheduler running")
    yield
    if SCHEDULER.running:
        SCHEDULER.shutdown()
    logging.info("Scheduler plugin stopped")
