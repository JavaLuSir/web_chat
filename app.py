#!/usr/bin/env python3
"""
Web Chat - 在线聊天工具
支持：文字聊天、文件传输、图片发送/接收
"""

import os
import uuid
import datetime
from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit, join_room

app = Flask(__name__)
app.config['SECRET_KEY'] = 'webchat-secret-key'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max

# 确保上传目录存在
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

socketio = SocketIO(app, cors_allowed_origins="*")

# 存储在线用户和消息
users = {}  # {sid: username}
rooms = {'general': []}  # 房间消息历史

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/api/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': '没有文件'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': '未选择文件'}), 400
    
    # 生成唯一文件名
    ext = os.path.splitext(file.filename)[1]
    filename = f"{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    
    # 判断是否是图片
    is_image = ext.lower() in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp']
    
    file_url = f"/upload/{filename}"
    
    return jsonify({
        'filename': filename,
        'url': file_url,
        'is_image': is_image,
        'original_name': file.filename
    })

@socketio.on('connect')
def handle_connect():
    print(f"用户连接: {request.sid}")

@socketio.on('disconnect')
def handle_disconnect():
    username = users.pop(request.sid, None)
    if username:
        emit('system_message', {
            'text': f'👋 {username} 离开了聊天',
            'time': datetime.datetime.now().strftime('%H:%M')
        }, to='general')
        emit('user_left', {'username': username}, to='general')

@socketio.on('join')
def handle_join(data):
    username = data.get('username', f'用户{request.sid[:4]}')
    users[request.sid] = username
    
    join_room('general')
    
    # 发送欢迎消息
    emit('system_message', {
        'text': f'🎉 欢迎 {username} 加入聊天！',
        'time': datetime.datetime.now().strftime('%H:%M')
    }, to='general')
    
    # 发送在线用户列表
    emit('users_update', {'users': list(users.values())}, to='general')
    
    # 发送历史消息
    for msg in rooms['general'][-50:]:
        emit('message', msg)

@socketio.on('chat_message')
def handle_message(data):
    username = users.get(request.sid, '未知用户')
    message_type = data.get('type', 'text')
    
    msg_data = {
        'username': username,
        'type': message_type,
        'time': datetime.datetime.now().strftime('%H:%M'),
        'sid': request.sid
    }
    
    if message_type == 'text':
        msg_data['text'] = data.get('text', '')
    elif message_type == 'image':
        msg_data['url'] = data.get('url', '')
    elif message_type == 'file':
        msg_data['url'] = data.get('url', '')
        msg_data['filename'] = data.get('filename', '')
    
    rooms['general'].append(msg_data)
    # 只保留最近100条消息
    if len(rooms['general']) > 100:
        rooms['general'] = rooms['general'][-100:]
    
    emit('message', msg_data, to='general')

@socketio.on('typing')
def handle_typing(data):
    username = users.get(request.sid, '未知用户')
    emit('user_typing', {'username': username}, to='general', include_self=False)

if __name__ == '__main__':
    print("🚀 聊天服务启动: http://localhost:5000")
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
