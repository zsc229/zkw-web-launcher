import os
import sys
import json
import time
import datetime
import hashlib
import random
import subprocess
import threading
import re
from flask import Flask, render_template, request, jsonify, Response, session, redirect, url_for
from werkzeug.utils import secure_filename # 新增：用于安全处理文件名

# === 配置 ===
app = Flask(__name__)
app.secret_key = 'zkw_studio_super_secret_key_change_this_in_prod'
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 限制最大上传 500MB

DB_FILE = 'users_data.json'
ADMIN_USER = 'admin'
SECRET_ADMIN_PASSWORD = 'zkw180301'
COST_PER_DAY = 10

# 📂 核心文件存放目录
CORES_FOLDER = 'server_cores'
if not os.path.exists(CORES_FOLDER):
    os.makedirs(CORES_FOLDER)

ALLOWED_EXTENSIONS = {'jar'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# 🎁 兑换码库
GIFT_CODES_DB = {
    "ZKW666": 500,
    "NEWYEAR2024":  10000000000000000000000000000,
    "BILIBILI_FAN": 1000000000000,
    "OPENDAY": 1000000
}

# === 用户管理系统 ===
class UserManager:
    def __init__(self):
        self.users = self.load_db()

    def load_db(self):
        if not os.path.exists(DB_FILE):
            default_data = {
                "admin": {
                    "password_hash": hashlib.sha256(SECRET_ADMIN_PASSWORD.encode()).hexdigest(),
                    "points": 99999999,
                    "expiry": "2099-12-31",
                    "is_admin": True
                },
                "_used_codes": []
            }
            self.save_db(default_data)
            return default_data
        try:
            with open(DB_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if "_used_codes" not in data:
                data["_used_codes"] = []
            return data
        except:
            return {}

    def save_db(self, data):
        self.users = data
        with open(DB_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    def register(self, username, password):
        if username in self.users or username == "_used_codes":
            return False, "用户名已存在"
        if username == ADMIN_USER:
            return False, "禁止注册管理员账号"
        self.users[username] = {
            "password_hash": hashlib.sha256(password.encode()).hexdigest(),
            "points": 200,
            "expiry": datetime.datetime.now().strftime("%Y-%m-%d"),
            "is_admin": False,
            "last_signin": ""
        }
        self.save_db(self.users)
        return True, "注册成功！赠送 200 积分"

    def login(self, username, password):
        if username not in self.users or username == "_used_codes":
            return False, "用户不存在"
        p_hash = hashlib.sha256(password.encode()).hexdigest()
        if self.users[username].get('password_hash') != p_hash:
            return False, "密码错误"
        return True, "登录成功"

    def get_user(self, username):
        return self.users.get(username)

    def signin(self, username):
        user = self.users.get(username)
        if not user or user.get('is_admin'):
            return False, "管理员无需签到"
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        if user.get('last_signin') == today:
            return False, "今日已签到"
        reward = random.randint(100, 500)
        user['points'] += reward
        user['last_signin'] = today
        self.save_db(self.users)
        return True, f"签到成功！获得 {reward} 积分"

    def redeem_code(self, username, code):
        code = code.strip().upper()
        if code not in GIFT_CODES_DB:
            return False, "无效兑换码"
        if code in self.users.get("_used_codes", []):
            return False, "兑换码已使用"
        reward = GIFT_CODES_DB[code]
        self.users[username]['points'] += reward
        self.users["_used_codes"].append(code)
        self.save_db(self.users)
        return True, f"兑换成功！获得 {reward} 积分"

    def renew(self, username, days):
        user = self.users.get(username)
        if user.get('is_admin'):
            return True, "管理员无限时长"
        cost = days * COST_PER_DAY
        if user['points'] < cost:
            return False, f"积分不足 (需要{cost})"
        user['points'] -= cost
        try:
            current = datetime.datetime.strptime(user['expiry'], "%Y-%m-%d")
            if current < datetime.datetime.now():
                current = datetime.datetime.now()
            new_date = current + datetime.timedelta(days=days)
            user['expiry'] = new_date.strftime("%Y-%m-%d")
            self.save_db(self.users)
            return True, f"续费成功，有效期至 {user['expiry']}"
        except:
            return False, "日期格式错误"

    def check_access(self, username):
        user = self.users.get(username)
        if user.get('is_admin'):
            return True, "OK"
        try:
            exp = datetime.datetime.strptime(user['expiry'], "%Y-%m-%d")
            if datetime.datetime.now() > exp:
                return False, "服务已过期"
            return True, "OK"
        except:
            return False, "日期错误"

user_mgr = UserManager()

# === 路由 ===
@app.route('/')
def index():
    if 'username' not in session:
        return redirect(url_for('login_page'))
    return render_template('index.html', username=session['username'])

@app.route('/login_page')
def login_page():
    return render_template('login.html')

@app.route('/register_page')
def register_page():
    return render_template('register.html')

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.json
    ok, msg = user_mgr.login(data['username'], data['password'])
    if ok:
        session['username'] = data['username']
        return jsonify({'success': True, 'msg': msg})
    return jsonify({'success': False, 'msg': msg})

@app.route('/api/register', methods=['POST'])
def api_register():
    data = request.json
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    if not username or not password:
        return jsonify({'success': False, 'msg': '用户名和密码不能为空'})
    ok, msg = user_mgr.register(username, password)
    if ok:
        return jsonify({'success': True, 'msg': msg})
    return jsonify({'success': False, 'msg': msg})

@app.route('/api/logout')
def api_logout():
    session.pop('username', None)
    return redirect(url_for('login_page'))

@app.route('/api/user_info')
def api_user_info():
    if 'username' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    user = user_mgr.get_user(session['username'])
    can_start, msg = user_mgr.check_access(session['username'])
    return jsonify({
        'username': session['username'],
        'points': user['points'],
        'expiry': user['expiry'],
        'is_admin': user.get('is_admin', False),
        'can_start': can_start
    })

@app.route('/api/signin', methods=['POST'])
def api_signin():
    if 'username' not in session:
        return jsonify({'success': False}), 401
    ok, msg = user_mgr.signin(session['username'])
    return jsonify({'success': ok, 'msg': msg})

@app.route('/api/redeem', methods=['POST'])
def api_redeem():
    if 'username' not in session:
        return jsonify({'success': False}), 401
    code = request.json.get('code')
    ok, msg = user_mgr.redeem_code(session['username'], code)
    return jsonify({'success': ok, 'msg': msg})

@app.route('/api/renew', methods=['POST'])
def api_renew():
    if 'username' not in session:
        return jsonify({'success': False}), 401
    days = request.json.get('days', 1)
    ok, msg = user_mgr.renew(session['username'], int(days))
    return jsonify({'success': ok, 'msg': msg})

# 🆕 新增：获取核心文件列表
@app.route('/api/cores', methods=['GET'])
def get_cores():
    files = []
    for f in os.listdir(CORES_FOLDER):
        if f.endswith('.jar'):
            path = os.path.join(CORES_FOLDER, f)
            size = os.path.getsize(path)
            size_mb = round(size / 1024 / 1024, 2)
            files.append({'name': f, 'size': f"{size_mb} MB"})
    return jsonify(files)

# 🆕 新增：上传核心文件
@app.route('/api/upload_core', methods=['POST'])
def upload_core():
    if 'username' not in session:
        return jsonify({'success': False, 'msg': '未登录'}), 401
    
    if 'file' not in request.files:
        return jsonify({'success': False, 'msg': '没有文件部分'})
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'msg': '未选择文件'})
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        # 防止中文文件名乱码问题，可选：保留原名或重命名
        # 这里为了简单直接保存，secure_filename 会过滤掉非安全字符
        # 如果文件名被过滤成空，给个默认名
        if filename == '':
            filename = "uploaded_server.jar"
            
        save_path = os.path.join(CORES_FOLDER, filename)
        file.save(save_path)
        return jsonify({'success': True, 'msg': f'上传成功：{filename}', 'filename': filename})
    
    return jsonify({'success': False, 'msg': '只允许上传 .jar 文件'})

# 🆕 新增：删除核心文件
@app.route('/api/delete_core', methods=['POST'])
def delete_core():
    if 'username' not in session:
        return jsonify({'success': False, 'msg': '未登录'}), 401
    filename = request.json.get('filename')
    if not filename:
        return jsonify({'success': False, 'msg': '文件名无效'})
    
    # 安全检查：防止路径遍历攻击
    if '..' in filename or '/' in filename or '\\' in filename:
        return jsonify({'success': False, 'msg': '非法文件名'})
        
    file_path = os.path.join(CORES_FOLDER, filename)
    if os.path.exists(file_path):
        # 如果正在运行该核心，禁止删除
        global current_core_file
        if is_server_running and current_core_file == filename:
            return jsonify({'success': False, 'msg': '服务器正在运行该核心，无法删除'})
        
        os.remove(file_path)
        return jsonify({'success': True, 'msg': '删除成功'})
    return jsonify({'success': False, 'msg': '文件不存在'})

# === 服务器控制逻辑 ===
server_process = None
server_logs = []
is_server_running = False
current_core_file = None # 记录当前运行的核心文件名
java_path = "java"

@app.route('/api/status')
def get_status():
    global is_server_running, current_core_file
    return jsonify({'running': is_server_running, 'current_core': current_core_file})

@app.route('/api/start', methods=['POST'])
def start_server():
    global server_process, is_server_running, server_logs, current_core_file
    
    if 'username' not in session:
        return jsonify({'success': False, 'msg': '未登录'}), 401
    
    can_start, msg = user_mgr.check_access(session['username'])
    if not can_start:
        return jsonify({'success': False, 'msg': f"禁止启动：{msg}"})
    
    if is_server_running:
        return jsonify({'success': False, 'msg': '服务器已在运行'})
    
    data = request.json
    core_name = data.get('core')
    
    if not core_name:
        return jsonify({'success': False, 'msg': '请选择一个核心文件'})
    
    # 安全检查
    if '..' in core_name or '/' in core_name or '\\' in core_name:
        return jsonify({'success': False, 'msg': '非法核心文件名'})
        
    jar_path = os.path.join(CORES_FOLDER, core_name)
    if not os.path.exists(jar_path):
        return jsonify({'success': False, 'msg': '核心文件不存在'})
    
    current_core_file = core_name
    cmd = f'{java_path} -Xms1G -Xmx2G -jar "{jar_path}" nogui'
    
    try:
        server_process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.PIPE,
            text=True, shell=True, encoding='gbk', errors='replace'
        )
        is_server_running = True
        server_logs = []
        
        def read_output():
            global is_server_running
            try:
                for line in server_process.stdout:
                    server_logs.append(line.strip())
                    if len(server_logs) > 500:
                        server_logs.pop(0)
                is_server_running = False
                current_core_file = None
                server_process.wait()
            except:
                is_server_running = False
                current_core_file = None
        
        threading.Thread(target=read_output, daemon=True).start()
        return jsonify({'success': True, 'msg': f'正在启动：{core_name}'})
    except Exception as e:
        is_server_running = False
        current_core_file = None
        return jsonify({'success': False, 'msg': str(e)})

@app.route('/api/stop', methods=['POST'])
def stop_server():
    global server_process, is_server_running, current_core_file
    if server_process and server_process.poll() is None:
        try:
            server_process.stdin.write("stop\n")
            server_process.stdin.flush()
        except:
            server_process.kill()
        return jsonify({'success': True, 'msg': '停止指令已发送'})
    return jsonify({'success': False, 'msg': '服务器未运行'})

@app.route('/api/command', methods=['POST'])
def send_command():
    global server_process
    if not is_server_running or not server_process:
        return jsonify({'success': False, 'msg': '服务器未运行'})
    cmd = request.json.get('command')
    try:
        server_process.stdin.write(cmd + "\n")
        server_process.stdin.flush()
        return jsonify({'success': True})
    except:
        return jsonify({'success': False, 'msg': '发送失败'})

@app.route('/api/logs')
def stream_logs():
    def generate():
        last_len = 0
        while True:
            if len(server_logs) > last_len:
                new_logs = server_logs[last_len:]
                last_len = len(server_logs)
                yield f"data: {json.dumps(new_logs)}\n\n"
            time.sleep(1)
    return Response(generate(), mimetype='text/event-stream')

if __name__ == '__main__':
    import webbrowser
    url = "http://127.0.0.1:5000"
    threading.Thread(target=lambda: (time.sleep(1.5), webbrowser.open(url)), daemon=True).start()
    print(f"🚀 zkw 工作室 Web 版 (带上传功能) 启动成功！")
    print(f"🌐 访问地址：{url}")
    print(f"📂 核心文件将保存在：{os.path.abspath(CORES_FOLDER)}")
    app.run(debug=True, port=5000)
