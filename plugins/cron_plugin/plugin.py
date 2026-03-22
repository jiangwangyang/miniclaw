import json
import logging
import uuid
from datetime import datetime

import requests
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

CHAT_URL = "http://localhost:11223/chat"
scheduler = AsyncIOScheduler(jobstores={"default": SQLAlchemyJobStore(url=f"sqlite:///tasks.db")})
router = APIRouter(prefix="/task")


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
    job = scheduler.get_job(task_id)
    logging.info(f"Executing task: {json.dumps(job_to_dict(job), ensure_ascii=False)}")
    response = requests.post(f"{CHAT_URL}?id={task_id}&message={content}", stream=True)
    response.raise_for_status()
    for _ in response.iter_lines():
        pass


def job_to_dict(job) -> dict:
    return {
        "id": job.id,
        "name": job.name,
        "content": job.args[2],
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
async def run_task_by_id(task_id: str):
    job = scheduler.get_job(task_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    scheduler.resume_job(task_id)
    return JSONResponse(content={"success": True, "message": f"Task {task_id} enabled"})


@router.post("/{task_id}/disable")
async def run_task_by_id(task_id: str):
    job = scheduler.get_job(task_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    scheduler.pause_job(task_id)
    return JSONResponse(content={"success": True, "message": f"Task {task_id} disabled"})


@router.post("/{task_id}/run")
async def run_task_by_id(task_id: str):
    job = scheduler.get_job(task_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    scheduler.modify_job(job.id, next_run_time=datetime.now())
    return JSONResponse(content={"success": True, "message": f"Task {task_id} execution started"})


async def before_application(app: FastAPI, **kwargs):
    app.include_router(router)
    if not scheduler.running:
        scheduler.start()
    logging.info("Cron plugin started, scheduler running")


async def after_application(app: FastAPI, **kwargs):
    if scheduler.running:
        scheduler.shutdown()
    logging.info("Cron plugin stopped")


async def before_chat(session_id: str, messages: list, user_content: str, **kwargs):
    pass


async def after_chat(session_id: str, messages: list, user_content: str, assistant_content: str, **kwargs):
    pass


async def before_model(session_id: str, messages: list, **kwargs):
    pass


async def after_model(session_id: str, messages: list, **kwargs):
    pass


async def before_tool(session_id: str, messages: list, tool_call: dict, **kwargs):
    pass


async def after_tool(session_id: str, messages: list, tool_call: dict, tool_content: str, **kwargs):
    pass
