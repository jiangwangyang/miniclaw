import logging

from fastapi import FastAPI, APIRouter
from fastapi.responses import HTMLResponse

# HTML 内容字符串
HTML_CONTENT = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MiniClaw Chat</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            height: 100vh;
            display: flex;
            flex-direction: column;
        }
        .header {
            background: rgba(255, 255, 255, 0.1);
            backdrop-filter: blur(10px);
            padding: 15px 20px;
            color: white;
            font-size: 18px;
            font-weight: 600;
            border-bottom: 1px solid rgba(255, 255, 255, 0.2);
        }
        .chat-container {
            flex: 1;
            overflow-y: auto;
            padding: 20px;
            display: flex;
            flex-direction: column;
            gap: 15px;
        }
        .message {
            max-width: 70%;
            padding: 12px 16px;
            border-radius: 18px;
            word-wrap: break-word;
            animation: fadeIn 0.3s ease;
        }
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .user-message {
            align-self: flex-end;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border-bottom-right-radius: 4px;
        }
        .assistant-message {
            align-self: flex-start;
            background: rgba(255, 255, 255, 0.95);
            color: #333;
            border-bottom-left-radius: 4px;
            box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
        }
        .message-time {
            font-size: 11px;
            opacity: 0.7;
            margin-top: 5px;
        }
        .input-container {
            background: rgba(255, 255, 255, 0.95);
            padding: 15px 20px;
            display: flex;
            gap: 10px;
            align-items: center;
            box-shadow: 0 -4px 20px rgba(0, 0, 0, 0.1);
        }
        .message-input {
            flex: 1;
            padding: 12px 18px;
            border: 2px solid #e0e0e0;
            border-radius: 25px;
            font-size: 15px;
            outline: none;
            transition: border-color 0.3s;
        }
        .message-input:focus {
            border-color: #667eea;
        }
        .send-button {
            padding: 12px 24px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 25px;
            font-size: 15px;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
        }
        .send-button:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 20px rgba(102, 126, 234, 0.4);
        }
        .send-button:active {
            transform: translateY(0);
        }
        .send-button:disabled {
            opacity: 0.6;
            cursor: not-allowed;
            transform: none;
        }
        .typing-indicator {
            display: none;
            align-self: flex-start;
            background: rgba(255, 255, 255, 0.95);
            padding: 12px 16px;
            border-radius: 18px;
            border-bottom-left-radius: 4px;
        }
        .typing-indicator span {
            display: inline-block;
            width: 8px;
            height: 8px;
            background: #999;
            border-radius: 50%;
            margin: 0 2px;
            animation: typing 1.4s infinite;
        }
        .typing-indicator span:nth-child(2) { animation-delay: 0.2s; }
        .typing-indicator span:nth-child(3) { animation-delay: 0.4s; }
        @keyframes typing {
            0%, 60%, 100% { transform: translateY(0); }
            30% { transform: translateY(-10px); }
        }
    </style>
</head>
<body>
    <div class="header">🤖 MiniClaw Chat</div>
    
    <div class="chat-container" id="chatContainer">
        <div class="message assistant-message">
            你好！我是 MiniClaw，有什么可以帮助你的吗？
            <div class="message-time">刚刚</div>
        </div>
    </div>
    
    <div class="typing-indicator" id="typingIndicator">
        <span></span><span></span><span></span>
    </div>
    
    <div class="input-container">
        <input type="text" class="message-input" id="messageInput" placeholder="输入消息..." maxlength="2000">
        <button class="send-button" id="sendButton" onclick="sendMessage()">发送</button>
    </div>

    <script>
        const chatContainer = document.getElementById('chatContainer');
        const messageInput = document.getElementById('messageInput');
        const sendButton = document.getElementById('sendButton');
        const typingIndicator = document.getElementById('typingIndicator');
        const sessionId = crypto.randomUUID();
        let isTyping = false;

        // 回车发送
        messageInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }
        });

        // 自动聚焦输入框
        messageInput.focus();

        function getCurrentTime() {
            const now = new Date();
            return now.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
        }

        function addMessage(content, isUser) {
            const messageDiv = document.createElement('div');
            messageDiv.className = `message ${isUser ? 'user-message' : 'assistant-message'}`;
            messageDiv.innerHTML = `
                ${escapeHtml(content)}
                <div class="message-time">${getCurrentTime()}</div>
            `;
            chatContainer.appendChild(messageDiv);
            scrollToBottom();
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        function scrollToBottom() {
            chatContainer.scrollTop = chatContainer.scrollHeight;
        }

        function setTyping(typing) {
            isTyping = typing;
            typingIndicator.style.display = typing ? 'block' : 'none';
            sendButton.disabled = typing;
            if (typing) {
                chatContainer.parentNode.insertBefore(typingIndicator, chatContainer.nextSibling);
                scrollToBottom();
            }
        }

        async function sendMessage() {
            const message = messageInput.value.trim();
            if (!message || isTyping) return;

            // 添加用户消息
            addMessage(message, true);
            messageInput.value = '';

            // 显示输入中
            setTyping(true);

            try {
                const eventSource = new EventSource(`/chat?message=${encodeURIComponent(message)}&id=${sessionId}`);
                let assistantMessage = '';
                let messageDiv = null;

                eventSource.onmessage = (event) => {
                    const line = event.data;

                    // 检查结束标记
                    if (line === '[DONE]') {
                        eventSource.close();
                        return;
                    }

                    try {
                        const data = JSON.parse(line);
                        if (data.choices && data.choices[0].delta) {
                            const delta = data.choices[0].delta;
                            if (delta.content) {
                                if (!messageDiv) {
                                    setTyping(false);
                                    messageDiv = document.createElement('div');
                                    messageDiv.className = 'message assistant-message';
                                    chatContainer.appendChild(messageDiv);
                                }
                                assistantMessage += delta.content;
                                messageDiv.innerHTML = `
                                    ${escapeHtml(assistantMessage)}
                                    <div class="message-time">${getCurrentTime()}</div>
                                `;
                                scrollToBottom();
                            }
                        }
                    } catch (e) {
                        // 忽略非 JSON 行
                    }
                };

                eventSource.onerror = (error) => {
                    eventSource.close();
                    if (!assistantMessage) {
                        setTyping(false);
                        addMessage('抱歉，我没有收到响应。', false);
                    }
                };

                eventSource.onclose = () => {
                    if (!assistantMessage) {
                        setTyping(false);
                    }
                };
            } catch (error) {
                setTyping(false);
                addMessage('抱歉，发生了错误：' + error.message, false);
            }
        }
    </script>
</body>
</html>
"""

# 初始化路由
router = APIRouter(prefix="")


@router.get("/", response_class=HTMLResponse)
@router.get("/index", response_class=HTMLResponse)
@router.get("/index.html", response_class=HTMLResponse)
async def index():
    return HTML_CONTENT


async def start(app: FastAPI, **kwargs):
    app.include_router(router)
    logging.info("挂载web页面")


async def stop(app: FastAPI, **kwargs):
    pass


async def before_chat(messages: list, user_content: str, **kwargs):
    pass


async def after_chat(messages: list, user_content: str, assistant_content: str, **kwargs):
    pass


async def before_model(messages: list, **kwargs):
    pass


async def after_model(messages: list, **kwargs):
    pass


async def before_tool(messages: list, tool_call: dict, **kwargs):
    pass


async def after_tool(messages: list, tool_call: dict, tool_response: str, **kwargs):
    pass
