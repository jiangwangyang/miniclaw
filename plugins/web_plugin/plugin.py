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
            overflow: hidden;
        }
        /* 侧边栏样式 */
        .sidebar {
            width: 260px;
            background: rgba(0, 0, 0, 0.3);
            backdrop-filter: blur(10px);
            display: flex;
            flex-direction: column;
            border-right: 1px solid rgba(255, 255, 255, 0.1);
        }
        .sidebar-header {
            padding: 20px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);
        }
        .new-chat-btn {
            width: 100%;
            padding: 12px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
        }
        .new-chat-btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 20px rgba(102, 126, 234, 0.4);
        }
        .sidebar-title {
            color: rgba(255, 255, 255, 0.8);
            font-size: 12px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-top: 15px;
            margin-bottom: 10px;
        }
        .session-list {
            flex: 1;
            overflow-y: auto;
            padding: 0 10px 10px;
        }
        .session-item {
            padding: 12px;
            margin-bottom: 5px;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.2s;
            color: rgba(255, 255, 255, 0.9);
            font-size: 14px;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .session-item:hover {
            background: rgba(255, 255, 255, 0.2);
        }
        .session-item.active {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        }
        .session-item-icon {
            font-size: 16px;
        }
        .session-item-text {
            flex: 1;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        /* 主内容区域 */
        .main-content {
            flex: 1;
            display: flex;
            flex-direction: column;
            min-width: 0;
        }
        .header {
            background: rgba(255, 255, 255, 0.1);
            backdrop-filter: blur(10px);
            padding: 15px 20px;
            color: white;
            font-size: 18px;
            font-weight: 600;
            border-bottom: 1px solid rgba(255, 255, 255, 0.2);
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        .header-session-info {
            font-size: 12px;
            opacity: 0.7;
            font-weight: 400;
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
            margin: 0 20px;
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
        .empty-state {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            height: 100%;
            color: rgba(255, 255, 255, 0.7);
            text-align: center;
            padding: 40px;
        }
        .empty-state-icon {
            font-size: 64px;
            margin-bottom: 20px;
        }
        .empty-state-title {
            font-size: 24px;
            font-weight: 600;
            margin-bottom: 10px;
            color: white;
        }
        .empty-state-text {
            font-size: 14px;
            max-width: 300px;
        }
    </style>
</head>
<body>
    <!-- 侧边栏 -->
    <div class="sidebar">
        <div class="sidebar-header">
            <button class="new-chat-btn" onclick="startNewChat()">
                <span>+</span>
                <span>新对话</span>
            </button>
            <div class="sidebar-title">历史记录</div>
        </div>
        <div class="session-list" id="sessionList">
            <!-- 会话列表将在这里动态生成 -->
        </div>
    </div>

    <!-- 主内容区域 -->
    <div class="main-content">
        <div class="header">
            <span>🤖 MiniClaw Chat</span>
            <span class="header-session-info" id="sessionInfo"></span>
        </div>

        <div class="chat-container" id="chatContainer">
            <div class="empty-state" id="emptyState">
                <div class="empty-state-icon">💬</div>
                <div class="empty-state-title">开始新对话</div>
                <div class="empty-state-text">点击左侧"新对话"按钮，或选择一个历史会话开始聊天</div>
            </div>
        </div>

        <div class="typing-indicator" id="typingIndicator">
            <span></span><span></span><span></span>
        </div>

        <div class="input-container">
            <input type="text" class="message-input" id="messageInput" placeholder="输入消息..." maxlength="2000" disabled>
            <button class="send-button" id="sendButton" onclick="sendMessage()" disabled>发送</button>
        </div>
    </div>

    <script>
        const chatContainer = document.getElementById('chatContainer');
        const messageInput = document.getElementById('messageInput');
        const sendButton = document.getElementById('sendButton');
        const typingIndicator = document.getElementById('typingIndicator');
        const sessionList = document.getElementById('sessionList');
        const sessionInfo = document.getElementById('sessionInfo');
        const emptyState = document.getElementById('emptyState');

        let currentSessionId = null;
        let isTyping = false;

        // 页面加载时初始化
        document.addEventListener('DOMContentLoaded', () => {
            loadSessionList();

            // 回车发送
            messageInput.addEventListener('keypress', function(e) {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    sendMessage();
                }
            });
        });

        // 加载会话列表
        async function loadSessionList() {
            try {
                const response = await fetch('/session/list');
                const sessions = await response.json();

                sessionList.innerHTML = '';
                sessions.forEach(session => {
                    const item = document.createElement('div');
                    item.className = 'session-item';
                    item.dataset.id = session.id;
                    item.innerHTML = `
                        <span class="session-item-icon">💬</span>
                        <span class="session-item-text">${escapeHtml(session.title)}</span>
                    `;
                    item.onclick = () => loadSession(session.id);
                    sessionList.appendChild(item);
                });
            } catch (error) {
                console.error('加载会话列表失败:', error);
            }
        }

        // 开始新对话
        function startNewChat() {
            currentSessionId = crypto.randomUUID();
            localStorage.setItem('miniclaw_current_session', currentSessionId);

            // 清空聊天区域
            chatContainer.innerHTML = '';
            chatContainer.appendChild(emptyState);
            emptyState.style.display = 'flex';

            // 启用输入
            enableInput();
            sessionInfo.textContent = '新对话';

            // 刷新列表并高亮当前会话
            loadSessionList().then(() => {
                const items = sessionList.querySelectorAll('.session-item');
                items.forEach(item => item.classList.remove('active'));
            });
        }

        // 加载指定会话
        async function loadSession(sessionId) {
            currentSessionId = sessionId;
            localStorage.setItem('miniclaw_current_session', sessionId);

            try {
                const response = await fetch(`/session/${sessionId}`);
                const data = await response.json();

                // 清空聊天区域
                chatContainer.innerHTML = '';
                emptyState.style.display = 'none';

                // 渲染历史消息
                if (data.messages && data.messages.length > 0) {
                    data.messages.forEach(msg => {
                        if (msg.role === 'user') {
                            addMessage(msg.content, true);
                        } else if (msg.role === 'assistant') {
                            addMessage(msg.content, false);
                        }
                    });
                } else {
                    chatContainer.appendChild(emptyState);
                    emptyState.style.display = 'flex';
                }

                // 启用输入
                enableInput();
                sessionInfo.textContent = `会话: ${sessionId.slice(0, 8)}...`;

                // 更新高亮
                const items = sessionList.querySelectorAll('.session-item');
                items.forEach(item => {
                    item.classList.toggle('active', item.dataset.id === sessionId);
                });
            } catch (error) {
                console.error('加载会话失败:', error);
                addMessage('加载会话失败: ' + error.message, false);
            }
        }

        // 启用输入
        function enableInput() {
            messageInput.disabled = false;
            sendButton.disabled = false;
            messageInput.focus();
        }

        function getCurrentTime() {
            const now = new Date();
            return now.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
        }

        function addMessage(content, isUser) {
            // 隐藏空状态
            emptyState.style.display = 'none';

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
            messageInput.disabled = typing;
        }

        async function sendMessage() {
            const message = messageInput.value.trim();
            if (!message || isTyping || !currentSessionId) return;

            // 添加用户消息
            addMessage(message, true);
            messageInput.value = '';

            // 显示输入中
            setTyping(true);

            try {
                const eventSource = new EventSource(`/chat?message=${encodeURIComponent(message)}&id=${currentSessionId}`);
                let assistantMessage = '';
                let messageDiv = null;

                eventSource.onmessage = (event) => {
                    const line = event.data;

                    // 检查结束标记
                    if (line === '[DONE]') {
                        eventSource.close();
                        setTyping(false);
                        // 刷新会话列表
                        loadSessionList();
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
                    setTyping(false);
                    if (!assistantMessage) {
                        addMessage('抱歉，我没有收到响应。', false);
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


async def before_application(app: FastAPI, **kwargs):
    app.include_router(router)
    logging.info("Web plugin started")


async def after_application(app: FastAPI, **kwargs):
    logging.info("Web plugin stopped")


async def before_chat(id: str, messages: list, user_content: str, **kwargs):
    pass


async def after_chat(id: str, messages: list, user_content: str, assistant_content: str, **kwargs):
    pass


async def before_model(id: str, messages: list, **kwargs):
    pass


async def after_model(id: str, messages: list, **kwargs):
    pass


async def before_tool(id: str, messages: list, tool_call: dict, **kwargs):
    pass


async def after_tool(id: str, messages: list, tool_call: dict, tool_content: str, **kwargs):
    pass
