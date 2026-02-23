# Web Chat 💬

一个简单的在线聊天 Web 应用，支持文字聊天、文件传输、图片发送/接收。

## 功能特性

- 💬 文字聊天
- 🖼️ 发送/接收图片
- 📎 文件传输
- 👥 在线用户列表
- 🔔 实时消息推送 (WebSocket)

## 环境要求

- Python 3.8+
- pip

## 安装步骤

### 1. 安装依赖

```bash
pip install flask flask-socketio eventlet
```

### 2. 启动服务

```bash
python app.py
```

### 3. 访问

浏览器打开：http://localhost:5000

打开多个浏览器标签页即可测试多人聊天。

## 项目结构

```
web_chat/
├── app.py              # Flask 后端
├── templates/
│   └── index.html      # 前端界面
├── uploads/            # 上传的文件目录 (自动创建)
├── README.md
└── .gitignore
```

## 配置

- 默认端口：5000
- 最大文件上传大小：50MB
- 消息历史保存：最近 100 条

如需修改，编辑 `app.py` 中的配置项：
```python
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 修改上传限制
```
