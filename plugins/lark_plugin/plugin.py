import asyncio
import json
import logging
import os
import queue
import threading
import uuid

import lark_oapi as lark
import requests
from fastapi import FastAPI
from lark_oapi.api.im.v1 import *

CHAT_URL = "http://localhost:11223/chat"
INTERRUPT_URL = "http://localhost:11223/interrupt"
LARK_APP_ID = os.getenv("LARK_APP_ID")
LARK_APP_SECRET = os.getenv("LARK_APP_SECRET")
message_queue = queue.Queue(maxsize=10)


# 用户消息消费者 按序消费飞书消息 将用户消息发送到模型并回复
def message_consumer():
    # 初始化飞书客户端
    client = lark.Client.builder() \
        .app_id(LARK_APP_ID) \
        .app_secret(LARK_APP_SECRET) \
        .log_level(lark.LogLevel.INFO) \
        .build()

    # 发送飞书消息
    def send_feishu_message(receive_id: str, content: str):
        request_body: CreateMessageRequestBody = CreateMessageRequestBody.builder() \
            .receive_id(receive_id) \
            .msg_type("text") \
            .content(json.dumps({"text": content}, ensure_ascii=False)) \
            .uuid(str(uuid.uuid4())) \
            .build()
        request: CreateMessageRequest = CreateMessageRequest.builder() \
            .receive_id_type("open_id") \
            .request_body(request_body) \
            .build()
        response: CreateMessageResponse = client.im.v1.message.create(request)
        if not response.success():
            lark.logger.error(f"client.im.v1.message.create failed, code: {response.code}, msg: {response.msg}, log_id: {response.get_log_id()}, resp: \n{json.dumps(json.loads(response.raw.content), ensure_ascii=False)}")

    # 死循环消费队列飞书消息
    while True:
        try:
            # 获取飞书消息
            feishu_message = message_queue.get(timeout=1)
            open_id = feishu_message.event.sender.sender_id.open_id
            user_content = feishu_message.event.message.content
            # 发送到模型
            response = requests.post(f"{CHAT_URL}?id={open_id}&message={user_content}", stream=True)
            response.raise_for_status()
            # 遍历模型返回
            text = ""
            for line in response.iter_lines():
                line = line.decode("utf-8").strip() if line else ""
                if not line.startswith("data:"):
                    continue
                line = line[5:].strip()
                if line == "[DONE]":
                    break
                data = json.loads(line)
                if not data["role"] == "assistant":
                    continue
                text += data["content"]
                if data["content"] == "" and text:
                    # 发送飞书消息
                    send_feishu_message(open_id, text)
                    text = ""
            # 处理完成
            message_queue.task_done()
        except queue.Empty:
            pass


# 飞书消息监听器 将飞书消息放入队列 确保按序处理
def event_listener():
    def do_p2_im_message_receive_v1(data: lark.im.v1.P2ImMessageReceiveV1) -> None:
        lark.logger.info(lark.JSON.marshal(data))
        open_id = data.event.sender.sender_id.open_id
        response = requests.post(f"{INTERRUPT_URL}?id={open_id}")
        response.raise_for_status()
        message_queue.put(data)

    event_handler = lark.EventDispatcherHandler.builder("", "") \
        .register_p2_im_message_receive_v1(do_p2_im_message_receive_v1) \
        .build()
    # 启动新的事件循环创建监听客户端(因为miniclaw已经占用了事件循环，所以需要创建一个新的)
    lark.ws.client.loop = asyncio.new_event_loop()
    asyncio.set_event_loop(lark.ws.client.loop)
    ws_client = lark.ws.Client(LARK_APP_ID, LARK_APP_SECRET, event_handler=event_handler, log_level=lark.LogLevel.INFO)
    ws_client.start()


async def before_application(app: FastAPI, **kwargs):
    if not LARK_APP_ID or not LARK_APP_SECRET:
        return
    # 启动 消费者线程 消息监听线程
    message_consumer_thread = threading.Thread(target=message_consumer, args=())
    event_listener_thread = threading.Thread(target=event_listener, args=())
    message_consumer_thread.daemon = True
    event_listener_thread.daemon = True
    message_consumer_thread.start()
    event_listener_thread.start()
    logging.info("Feishu plugin started")


async def after_application(app: FastAPI, **kwargs):
    logging.info("Feishu plugin stopped")


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
