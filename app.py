#!/usr/bin/env python3
"""
Web Chat - 群聊聊天工具
支持：文字聊天、文件传输、图片发送/接收、群聊、@提及在线用户
"""

import os
import uuid
import datetime
import re
from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit, join_room, leave_room

app = Flask(__name__)
app.config['SECRET_KEY'] = 'webchat-secret-key'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

socketio = SocketIO(app, cors_allowed_origins="*")

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

@app.route('/api/online_users')
def api_online_users():
    """获取在线用户列表"""
    return jsonify({'users': get_online_users()})

@app.route('/api/set_username', methods=['POST'])
def set_username():
    """设置用户名到Cookie"""
    from flask import make_response
    data = request.json
    username = data.get('username', '')
    
    if username:
        # 设置Cookie，有效期1天
        response = make_response(jsonify({'success': True}))
        response.set_cookie('chat_username', username, max_age=86400, httponly=False)
        return response
    return jsonify({'success': False}), 400

@socketio.on('connect')
def handle_connect():
    print(f"用户连接: {request.sid}")

@socketio.on('disconnect')
def handle_disconnect():
    user_info = users.pop(request.sid, None)
    if user_info:
        username = user_info['username']
        
        # 群聊通知
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
    username = data.get('username', f'用户{request.sid[:4]}')
    
    # 检查用户名是否已存在（排除自己）
    existing_sid = get_user_by_name(username)
    if existing_sid and existing_sid != request.sid:
        # 用户名已被占用，通知前端
        emit('username_taken', {'original': username})
        # 自动生成新用户名
        counter = 1
        while get_user_by_name(f"{username}{counter}"):
            counter += 1
        username = f"{username}{counter}"
    
    users[request.sid] = {'username': username}
    join_room('general')
    
    # 发送欢迎消息
    emit('system_message', {
        'text': f'🎉 欢迎 {username} 加入群聊！',
        'time': datetime.datetime.now().strftime('%H:%M')
    }, to='general')
    
    # 发送在线用户列表
    emit('users_update', {'users': get_online_users()}, to='general')
    
    # 发送历史消息
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
        'mentions': []  # @提及的用户列表
    }
    
    if message_type == 'text':
        text = data.get('text', '')
        msg_data['text'] = text
        
        # 解析 @ 提及
        mention_pattern = r'@(\S+)'
        mentions = re.findall(mention_pattern, text)
        msg_data['mentions'] = mentions
        
        # 检查是否在回复某条消息
        reply_to = data.get('reply_to')
        if reply_to:
            msg_data['reply_to'] = reply_to
            
    elif message_type == 'image':
        msg_data['url'] = data.get('url', '')
    elif message_type == 'file':
        msg_data['url'] = data.get('url', '')
        msg_data['filename'] = data.get('filename', '')
    
    # 群聊：所有人收到消息
    if 'general' not in rooms:
        rooms['general'] = []
    rooms['general'].append(msg_data)
    if len(rooms['general']) > 100:
        rooms['general'] = rooms['general'][-100:]
    
    emit('message', msg_data, to='general')
    
    # 如果有@提及，单独通知被提及的用户
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

@socketio.on('request_private_chat')
def handle_private_chat(data):
    target = data.get('target')
    username = users.get(request.sid, {}).get('username', '未知用户')
    
    target_sid = get_user_by_name(target)
    if target_sid:
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
    print("🚀 群聊服务启动: http://localhost:5000")
    print("💡 功能：群聊、@提及在线用户、Cookie记住用户名")
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
