#!/usr/bin/env python3
"""
Web Chat - 在线聊天工具
支持：文字聊天、文件传输、图片发送/接收、私聊
"""

import os
import uuid
import datetime
from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit, join_room, leave_room

app = Flask(__name__)
app.config['SECRET_KEY'] = 'webchat-secret-key'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

socketio = SocketIO(app, cors_allowed_origins="*")

# 存储数据
users = {}  # {sid: {'username': xxx, 'room': 'general'}}
rooms = {'general': []}  # {room_name: [messages]}

def get_user_by_name(username):
    for sid, info in users.items():
        if info['username'] == username:
            return sid
    return None

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
    
    ext = os.path.splitext(file.filename)[1]
    filename = f"{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    
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
    user_info = users.pop(request.sid, None)
    if user_info:
        username = user_info['username']
        room = user_info.get('room', 'general')
        
        emit('system_message', {
            'text': f'👋 {username} 离开了聊天',
            'time': datetime.datetime.now().strftime('%H:%M'),
            'room': room
        }, to=room)
        
        emit('user_left', {'username': username, 'room': room}, to=room)
        emit('users_update', {
            'users': [u['username'] for u in users.values() if u.get('room') == room],
            'room': room
        }, to=room)

@socketio.on('join')
def handle_join(data):
    username = data.get('username', f'用户{request.sid[:4]}')
    room = data.get('room', 'general')
    
    users[request.sid] = {'username': username, 'room': room}
    join_room(room)
    
    # 发送欢迎消息
    emit('system_message', {
        'text': f'🎉 欢迎 {username} 加入聊天！',
        'time': datetime.datetime.now().strftime('%H:%M'),
        'room': room
    }, to=room)
    
    # 发送在线用户列表
    room_users = [u['username'] for u in users.values() if u.get('room') == room]
    emit('users_update', {'users': room_users, 'room': room}, to=room)
    
    # 发送历史消息
    if room in rooms:
        for msg in rooms[room][-50:]:
            emit('message', msg)

@socketio.on('leave_room')
def handle_leave_room(data):
    old_room = data.get('room', 'general')
    leave_room(old_room)
    
    if request.sid in users:
        users[request.sid]['room'] = 'general'
    
    # 通知离开
    emit('left_room', {'room': old_room})

@socketio.on('chat_message')
def handle_message(data):
    username = users.get(request.sid, {}).get('username', '未知用户')
    message_type = data.get('type', 'text')
    room = data.get('room', 'general')
    target = data.get('target')  # 私聊目标用户
    
    msg_data = {
        'username': username,
        'type': message_type,
        'time': datetime.datetime.now().strftime('%H:%M'),
        'room': room
    }
    
    if message_type == 'text':
        msg_data['text'] = data.get('text', '')
    elif message_type == 'image':
        msg_data['url'] = data.get('url', '')
    elif message_type == 'file':
        msg_data['url'] = data.get('url', '')
        msg_data['filename'] = data.get('filename', '')
    
    # 私聊
    if target:
        msg_data['is_private'] = True
        target_sid = get_user_by_name(target)
        
        # 发送给目标用户
        if target_sid:
            emit('message', msg_data, to=target_sid)
        
        # 发送给自己
        emit('message', msg_data, to=request.sid)
    else:
        # 群聊
        if room not in rooms:
            rooms[room] = []
        rooms[room].append(msg_data)
        if len(rooms[room]) > 100:
            rooms[room] = rooms[room][-100:]
        
        emit('message', msg_data, to=room)

@socketio.on('typing')
def handle_typing(data):
    username = users.get(request.sid, {}).get('username', '未知用户')
    room = data.get('room', 'general')
    target = data.get('target')
    
    if target:
        target_sid = get_user_by_name(target)
        if target_sid:
            emit('user_typing', {'username': username}, to=target_sid)
    else:
        emit('user_typing', {'username': username}, to=room, include_self=False)

@socketio.on('request_private_chat')
def handle_private_chat(data):
    target = data.get('target')
    username = users.get(request.sid, {}).get('username', '未知用户')
    
    target_sid = get_user_by_name(target)
    if target_sid:
        # 创建私聊房间
        private_room = f"private_{min(request.sid, target_sid)}_{max(request.sid, target_sid)}"
        
        emit('private_chat_started', {
            'room': private_room,
            'target': target,
            'target_username': username
        }, to=target_sid)
        
        emit('private_chat_started', {
            'room': private_room,
            'target': target,
            'target_username': users.get(target_sid, {}).get('username', target)
        }, to=request.sid)

if __name__ == '__main__':
    print("🚀 聊天服务启动: http://localhost:5000")
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
