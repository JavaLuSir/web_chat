#!/usr/bin/env python3
"""
Web Chat - 群聊聊天工具
支持：文字聊天、文件传输、图片发送/接收、群聊、@提及在线用户
"""

import os
import uuid
import datetime
import re
import html
from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit, join_room, leave_room

app = Flask(__name__)
app.config['SECRET_KEY'] = 'webchat-secret-key'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

socketio = SocketIO(app, cors_allowed_origins="*")

# ============ 安全配置 ============

# 允许的文件扩展名
ALLOWED_EXTENSIONS = {
    # 文档
    'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt', 'csv', 'rtf', 'odt',
    # 图片
    'jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'svg', 'ico', 'tif', 'tiff',
    # 压缩包
    'zip', 'rar', '7z', 'tar', 'gz', 'bz2', 'xz',
    # 音频
    'mp3', 'wav', 'ogg', 'flac', 'aac', 'm4a', 'wma',
    # 视频
    'mp4', 'avi', 'mov', 'mkv', 'wmv', 'flv', 'webm', 'm4v',
    # 代码/数据
    'js', 'ts', 'py', 'java', 'c', 'cpp', 'h', 'hpp', 'cs', 'go', 'rs', 
    'php', 'rb', 'swift', 'kt', 'scala', 'html', 'css', 'scss', 'less',
    'json', 'xml', 'yaml', 'yml', 'toml', 'sql', 'sh', 'bash',
    # 其他
    'pem', 'key', 'crt', 'cer', 'log', 'md', 'markdown'
}

# 禁止的文件扩展名（危险）
BLOCKED_EXTENSIONS = {
    'exe', 'sh', 'bat', 'cmd', 'ps1', 'vbs', 'js', 'jar', 'app', 
    'dmg', 'deb', 'rpm', 'msi', 'scr', 'pif', 'com', 'gadget',
    'htm', 'hta', 'jsp', 'asp', 'asa', 'cer', 'phar', 'phtml'
}

# 允许的 MIME 类型前缀
ALLOWED_MIME_PREFIXES = [
    'image/', 'audio/', 'video/', 'application/pdf',
    'application/zip', 'application/x-zip', 'application/x-rar',
    'application/msword', 'application/vnd.ms-',
    'application/vnd.openxmlformats', 'text/'
]

# 存储数据
users = {}  # {sid: {'username': xxx}}
rooms = {'general': []}  # {room_name: [messages]}

def get_user_by_name(username):
    for sid, info in users.items():
        if info['username'] == username:
            return sid
    return None

def get_online_users():
    return [info['username'] for info in users.values()]

# ============ 安全函数 ============

def validate_username(username):
    """验证用户名安全性"""
    if not username:
        return False, "用户名不能为空"
    if len(username) < 2 or len(username) > 20:
        return False, "用户名长度需在2-20字符之间"
    # 只允许字母、数字、下划线、中文
    if not re.match(r'^[a-zA-Z0-9_\u4e00-\u9fff]+$', username):
        return False, "用户名只能包含字母、数字、下划线、中文"
    return True, username

def sanitize_message(text):
    """XSS防护 - 转义HTML特殊字符"""
    if not text:
        return ""
    return html.escape(text).strip()

def validate_filename(filename):
    """验证文件名安全性"""
    if not filename:
        return False, "文件名不能为空"
    
    # 去除路径穿越
    filename = os.path.basename(filename)
    
    # 检查扩展名
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    
    # 禁止危险扩展名
    if ext in BLOCKED_EXTENSIONS:
        return False, f"禁止上传 .{ext} 类型文件"
    
    # 只允许已知扩展名
    if ext and ext not in ALLOWED_EXTENSIONS:
        return False, f"不支持 .{ext} 文件类型"
    
    return True, filename

# ============ 路由 ============

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload/<filename>')
def uploaded_file(filename):
    # 防止路径穿越
    filename = os.path.basename(filename)
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/api/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': '没有文件'}), 400
    
    file = request.files['file']
    filename = file.filename
    
    # 验证文件名
    valid, msg = validate_filename(filename)
    if not valid:
        return jsonify({'error': msg}), 400
    
    # 获取安全扩展名
    ext = os.path.splitext(filename)[1].lower() if '.' in filename else ''
    safe_filename = f"{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], safe_filename)
    
    # 保存文件
    file.save(filepath)
    
    # 检查文件大小
    file_size = os.path.getsize(filepath)
    if file_size > 50 * 1024 * 1024:
        os.remove(filepath)
        return jsonify({'error': '文件大小不能超过50MB'}), 400
    
    # 检查是否是图片
    image_exts = {'jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'svg'}
    is_image = ext.lstrip('.') in image_exts
    
    return jsonify({
        'filename': safe_filename,
        'url': f"/upload/{safe_filename}",
        'is_image': is_image,
        'original_name': filename
    })

@app.route('/api/online_users')
def api_online_users():
    return jsonify({'users': get_online_users()})

@app.route('/api/set_username', methods=['POST'])
def set_username():
    from flask import make_response
    data = request.json
    username = data.get('username', '')
    
    # 验证用户名
    valid, msg = validate_username(username)
    if not valid:
        return jsonify({'error': msg}), 400
    
    # 设置安全的Cookie
    response = make_response(jsonify({'success': True}))
    response.set_cookie(
        'chat_username', 
        username, 
        max_age=86400, 
        httponly=True,
        samesite='Lax'
    )
    return response

# ============ SocketIO 事件 ============

@socketio.on('connect')
def handle_connect():
    print(f"用户连接: {request.sid}")

@socketio.on('disconnect')
def handle_disconnect():
    user_info = users.pop(request.sid, None)
    if user_info:
        username = user_info['username']
        
        msg = f'👋 {username} 离开了群聊'
        rooms['general'].append({
            'type': 'system',
            'text': msg,
            'time': datetime.datetime.now().strftime('%H:%M')
        })
        
        emit('system_message', {
            'text': msg,
            'time': datetime.datetime.now().strftime('%H:%M')
        }, to='general')
        
        emit('user_left', {'username': username}, to='general')
        emit('users_update', {
            'users': get_online_users()
        }, to='general')

@socketio.on('join')
def handle_join(data):
    username = data.get('username', '')
    
    # 验证用户名
    valid, msg = validate_username(username)
    if not valid:
        # 使用默认用户名
        username = f"用户{request.sid[:4]}"
    
    # 检查用户名是否已存在
    existing_sid = get_user_by_name(username)
    if existing_sid and existing_sid != request.sid:
        counter = 1
        while get_user_by_name(f"{username}{counter}"):
            counter += 1
        username = f"{username}{counter}"
    
    users[request.sid] = {'username': username}
    join_room('general')
    
    emit('system_message', {
        'text': f'🎉 欢迎 {username} 加入群聊！',
        'time': datetime.datetime.now().strftime('%H:%M')
    }, to='general')
    
    emit('users_update', {'users': get_online_users()}, to='general')
    
    for msg in rooms['general'][-50:]:
        emit('message', msg)

@socketio.on('chat_message')
def handle_message(data):
    username = users.get(request.sid, {}).get('username', '未知用户')
    message_type = data.get('type', 'text')
    
    msg_data = {
        'username': username,
        'type': message_type,
        'time': datetime.datetime.now().strftime('%H:%M'),
        'mentions': []
    }
    
    if message_type == 'text':
        text = data.get('text', '')
        # XSS防护 - 转义HTML
        text = sanitize_message(text)
        
        # 验证消息长度
        if len(text) > 2000:
            text = text[:2000] + '...(内容过长)'
        
        msg_data['text'] = text
        
        # 解析 @ 提及
        mention_pattern = r'@(\S+)'
        mentions = re.findall(mention_pattern, text)
        msg_data['mentions'] = mentions
            
    elif message_type == 'image':
        # 验证图片URL
        url = data.get('url', '')
        if url.startswith('/upload/'):
            msg_data['url'] = url
        else:
            return  # 无效URL
            
    elif message_type == 'file':
        # 验证文件URL
        url = data.get('url', '')
        if url.startswith('/upload/'):
            msg_data['url'] = url
            msg_data['filename'] = sanitize_message(data.get('filename', '未知文件'))
        else:
            return  # 无效URL
    
    # 群聊：所有人收到消息
    if 'general' not in rooms:
        rooms['general'] = []
    rooms['general'].append(msg_data)
    if len(rooms['general']) > 100:
        rooms['general'] = rooms['general'][-100:]
    
    emit('message', msg_data, to='general')
    
    # @通知
    if message_type == 'text':
        for mentioned_username in mentions:
            mentioned_sid = get_user_by_name(mentioned_username)
            if mentioned_sid and mentioned_sid != request.sid:
                emit('mentioned', {
                    'username': username,
                    'text': text,
                    'time': msg_data['time']
                }, to=mentioned_sid)

@socketio.on('typing')
def handle_typing(data):
    username = users.get(request.sid, {}).get('username', '未知用户')
    emit('user_typing', {'username': username}, to='general', include_self=False)

if __name__ == '__main__':
    print("🚀 群聊服务启动: http://localhost:5000")
    print("🛡️ 安全功能：XSS防护、文件验证、Cookie安全")
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
