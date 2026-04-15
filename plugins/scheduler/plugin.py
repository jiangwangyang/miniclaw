import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime

import httpx
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

CHAT_URL = "http://localhost:11223/chat"
DATA_DIR = "data"
TASKS_DB_FILE = "data/tasks.db"
scheduler: AsyncIOScheduler
async_client: httpx.AsyncClient
router: APIRouter = APIRouter(prefix="/task")


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
    response = await async_client.post(f"{CHAT_URL}?id={task_id}&message={content}")
    response.raise_for_status()
    async for _ in response.aiter_lines():
        pass


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


@router.get("/list")
async def list_tasks():
    jobs = scheduler.get_jobs()
    result = [job_to_dict(job) for job in jobs]
    return JSONResponse(content={"success": True, "data": result, "total": len(result)})


@router.post("")
async def save_task(task: TaskEntity):
    task_id = str(uuid.uuid4())
    scheduler.add_job(execute_task, "cron", id=task_id, name=task.name, args=[task_id, task.name, task.content], year=task.year, month=task.month, day=task.day, week=task.week, day_of_week=task.day_of_week, hour=task.hour, minute=task.minute, second=task.second)
    job = scheduler.get_job(task_id)
    return JSONResponse(content={
        "success": True,
        "message": f"Task {task_id} created",
        "data": job_to_dict(job)
    })


@router.delete("/{task_id}")
async def delete_task_by_id(task_id: str):
    job = scheduler.get_job(task_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    scheduler.remove_job(task_id)
    return JSONResponse(content={"success": True, "message": f"Task {task_id} deleted"})


@router.post("/{task_id}/enable")
async def enable_task_by_id(task_id: str):
    job = scheduler.get_job(task_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    scheduler.resume_job(task_id)
    return JSONResponse(content={"success": True, "message": f"Task {task_id} enabled"})


@router.post("/{task_id}/disable")
async def disable_task_by_id(task_id: str):
    job = scheduler.get_job(task_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    scheduler.pause_job(task_id)
    return JSONResponse(content={"success": True, "message": f"Task {task_id} disabled"})


@router.post("/{task_id}/run")
async def run_task_now(task_id: str):
    job = scheduler.get_job(task_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    scheduler.modify_job(job.id, next_run_time=datetime.now())
    return JSONResponse(content={"success": True, "message": f"Task {task_id} execution started"})


@asynccontextmanager
async def lifespan(app: FastAPI, **kwargs):
    global scheduler, async_client
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
    scheduler = AsyncIOScheduler(jobstores={"default": SQLAlchemyJobStore(url=f"sqlite:///{TASKS_DB_FILE}")})
    async_client = httpx.AsyncClient()
    if not scheduler.running:
        scheduler.start()
    app.include_router(router)
    logging.info("Scheduler plugin started, scheduler running")
    yield
    if scheduler.running:
        scheduler.shutdown()
    logging.info("Scheduler plugin stopped")
