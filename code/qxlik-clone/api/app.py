# -*- coding: utf-8 -*-
"""qxlik-clone 后端 API
- SQLite 独立数据库 /opt/qxlik-api/data/qxlik.db（专用，不与任何现有系统共享）
- 统一响应 {code, message, data:{total,pageNum,pageSize,list}}
- Bearer token 认证（内存 sessions 表），登录/登出/改密
- 8 个模块列表接口（与 js/data/*.json demo 数据同构）
"""
import os
import re
import json
import time
import sqlite3
import secrets
import hashlib
import base64
from contextlib import contextmanager
from datetime import datetime

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
DB_PATH = os.path.join(DATA_DIR, 'qxlik.db')

app = FastAPI(title='qxlik-clone API', version='1.0.0')


@app.exception_handler(HTTPException)
def http_exception_handler(request, exc):
    """统一 401 等错误响应为 {code, message, data} 契约"""
    return JSONResponse({'code': exc.status_code, 'message': str(exc.detail), 'data': None},
                        status_code=exc.status_code)


# ---------------------------------------------------------------- DB 工具
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def db():
    conn = get_conn()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def q(sql, params=(), one=False, conn=None):
    """便捷查询"""
    own = conn is None
    if own:
        conn = get_conn()
    try:
        cur = conn.execute(sql, params)
        rows = cur.fetchall()
        if one:
            return dict(rows[0]) if rows else None
        return [dict(r) for r in rows]
    finally:
        if own:
            conn.close()


def ex(sql, params=(), conn=None):
    """便捷写"""
    own = conn is None
    if own:
        conn = get_conn()
    try:
        cur = conn.execute(sql, params)
        if own:
            conn.commit()
        return cur.lastrowid
    finally:
        if own:
            conn.close()


# ---------------------------------------------------------------- 密码哈希
def hash_password(pwd: str) -> str:
    salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac('sha256', pwd.encode(), salt.encode(), 100000).hex()
    return f'pbkdf2${salt}${h}'


def verify_password(pwd: str, stored: str) -> bool:
    try:
        _, salt, h = stored.split('$')
        calc = hashlib.pbkdf2_hmac('sha256', pwd.encode(), salt.encode(), 100000).hex()
        return secrets.compare_digest(calc, h)
    except Exception:
        return False


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# ---------------------------------------------------------------- 建表
SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT UNIQUE NOT NULL,
  password TEXT NOT NULL,
  nickname TEXT DEFAULT '',
  tel TEXT DEFAULT '',
  email TEXT DEFAULT '',
  role TEXT DEFAULT 'admin',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
  token_hash TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL,
  expires_at REAL NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS device (
  id INTEGER PRIMARY KEY,
  deviceId TEXT, deviceName TEXT, roleName TEXT, wifiName TEXT, location TEXT,
  status INTEGER DEFAULT 1, online INTEGER DEFAULT 1,
  productType TEXT, deviceType TEXT, version TEXT,
  lastActiveTime TEXT, createTime TEXT
);
CREATE TABLE IF NOT EXISTS firmware (
  id INTEGER PRIMARY KEY,
  version TEXT, chipType TEXT, fileSize TEXT, status INTEGER DEFAULT 1,
  forceUpdate INTEGER DEFAULT 0, changelog TEXT, lastOnlineTime TEXT, createTime TEXT
);
CREATE TABLE IF NOT EXISTS memory_chat (
  id INTEGER PRIMARY KEY,
  time TEXT, deviceName TEXT, sender TEXT, tools TEXT, content TEXT, audio INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS memory_long (
  id INTEGER PRIMARY KEY,
  time TEXT, content TEXT, source TEXT, importance TEXT
);
CREATE TABLE IF NOT EXISTS memory_summary (
  id INTEGER PRIMARY KEY,
  time TEXT, deviceName TEXT, summary TEXT
);
CREATE TABLE IF NOT EXISTS voiceprint (
  id INTEGER PRIMARY KEY,
  speakerId TEXT, name TEXT, description TEXT, status INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS agent (
  id INTEGER PRIMARY KEY,
  agentName TEXT, agentId TEXT, platform TEXT, description TEXT,
  isDefault INTEGER DEFAULT 0, publishTime TEXT
);
"""


def seed_from_json():
    """从 api/seed/*.json 灌入初始 demo 数据（幂等：表非空则跳过）"""
    seed_dir = os.path.join(BASE_DIR, 'seed')
    if not os.path.isdir(seed_dir):
        return
    tables = ['device', 'firmware', 'memory_chat', 'memory_long', 'memory_summary', 'voiceprint', 'agent']
    with db() as conn:
        for t in tables:
            if q(f'SELECT COUNT(*) c FROM {t}', one=True, conn=conn)['c'] > 0:
                continue
            path = os.path.join(seed_dir, t + '.json')
            if not os.path.isfile(path):
                continue
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
            rows = data.get('data', {}).get('list', [])
            cols_map = {
                'device': ['deviceId', 'deviceName', 'roleName', 'wifiName', 'location', 'status', 'online',
                           'productType', 'deviceType', 'version', 'lastActiveTime', 'createTime'],
                'firmware': ['version', 'chipType', 'fileSize', 'status', 'forceUpdate', 'changelog',
                             'lastOnlineTime', 'createTime'],
                'memory_chat': ['time', 'deviceName', 'sender', 'tools', 'content', 'audio'],
                'memory_long': ['time', 'content', 'source', 'importance'],
                'memory_summary': ['time', 'deviceName', 'summary'],
                'voiceprint': ['speakerId', 'name', 'description', 'status'],
                'agent': ['agentName', 'agentId', 'platform', 'description', 'isDefault', 'publishTime'],
            }
            cols = cols_map[t]
            for r in rows:
                vals = [json.dumps(r.get(c)) if isinstance(r.get(c), list) else r.get(c) for c in cols]
                ex(f'INSERT INTO {t} ({",".join(cols)}) VALUES ({",".join(["?"] * len(cols))})', vals, conn=conn)


def ensure_admin():
    with db() as conn:
        row = q('SELECT id FROM users LIMIT 1', one=True, conn=conn)
        if row:
            return
        ex('INSERT INTO users (username, password, nickname, role, created_at) VALUES (?,?,?,?,?)',
           ('admin', hash_password('admin123'), '小智', 'admin', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
           conn=conn)

@app.on_event('startup')
def startup():
    os.makedirs(DATA_DIR, exist_ok=True)
    with db() as conn:
        for stmt in SCHEMA.split(';'):
            stmt = stmt.strip()
            if stmt:
                conn.execute(stmt)
        # 轻量迁移：旧库补 tel/email 列
        cols = [r['name'] for r in q('PRAGMA table_info(users)', conn=conn)]
        for col in ('tel', 'email'):
            if col not in cols:
                conn.execute(f'ALTER TABLE users ADD COLUMN {col} TEXT DEFAULT \'\'')
    ensure_admin()
    seed_from_json()


# ---------------------------------------------------------------- 响应工具
def ok(data=None, code=200, message='success'):
    return JSONResponse({'code': code, 'message': message, 'data': data})


def fail(code, message, status=200):
    return JSONResponse({'code': code, 'message': message, 'data': None}, status_code=status)


# ---------------------------------------------------------------- 认证
SESSION_TTL = 7 * 24 * 3600  # 7 天


def get_user(request: Request):
    auth = request.headers.get('authorization', '')
    if not auth.startswith('Bearer '):
        return None
    token = auth[7:].strip()
    if not token:
        return None
    row = q('SELECT s.*, u.username, u.nickname, u.role FROM sessions s '
            'JOIN users u ON u.id = s.user_id WHERE s.token_hash = ?',
            (hash_token(token),), one=True)
    if not row:
        return None
    if row['expires_at'] < time.time():
        ex('DELETE FROM sessions WHERE token_hash = ?', (hash_token(token),))
        return None
    return dict(row)


def require_user(request: Request):
    user = get_user(request)
    if not user:
        raise HTTPException(status_code=401, detail='未登录或会话已过期')
    return user


# ---------------------------------------------------------------- 模型
class LoginBody(BaseModel):
    username: str
    password: str


class ChangePwdBody(BaseModel):
    oldPassword: str
    newPassword: str


# ---------------------------------------------------------------- 认证接口
@app.post('/api/auth/login')
def login(body: LoginBody, request: Request):
    u = body.username.strip()
    if not u or not body.password:
        return fail(400, '用户名和密码不能为空')
    row = q('SELECT * FROM users WHERE username = ?', (u,), one=True)
    if not row or not verify_password(body.password, row['password']):
        return fail(401, '用户名或密码错误')
    token = secrets.token_urlsafe(32)
    now = time.time()
    ex('INSERT INTO sessions (token_hash, user_id, expires_at, created_at) VALUES (?,?,?,?)',
       (hash_token(token), row['id'], now + SESSION_TTL, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    return ok({
        'token': token,
        'user': {'id': row['id'], 'username': row['username'], 'nickname': row['nickname'], 'role': row['role']}
    })


@app.post('/api/auth/logout')
def logout(request: Request):
    user = get_user(request)
    if user:
        auth = request.headers.get('authorization', '')
        token = auth[7:].strip()
        ex('DELETE FROM sessions WHERE token_hash = ?', (hash_token(token),))
    return ok(None, message='已退出登录')


@app.get('/api/auth/me')
def me(user=Depends(require_user)):
    return ok({'id': user['user_id'], 'username': user['username'],
               'nickname': user['nickname'], 'role': user['role']})


@app.post('/api/auth/change-password')
def change_password(body: ChangePwdBody, user=Depends(require_user)):
    row = q('SELECT * FROM users WHERE id = ?', (user['user_id'],), one=True)
    if not row or not verify_password(body.oldPassword, row['password']):
        return fail(400, '原密码错误')
    if len(body.newPassword) < 6:
        return fail(400, '新密码至少 6 位')
    ex('UPDATE users SET password = ? WHERE id = ?', (hash_password(body.newPassword), user['user_id']))
    return ok(None, message='密码已修改')


# ---------------------------------------------------------------- 个人资料
class ProfileBody(BaseModel):
    nickname: str = ''
    tel: str = ''
    email: str = ''
    password: str = ''          # 留空则不修改密码
    confirmPassword: str = ''


@app.get('/api/user/profile')
def get_profile(user=Depends(require_user)):
    row = q('SELECT id, username, nickname, tel, email, role FROM users WHERE id = ?',
            (user['user_id'],), one=True)
    if not row:
        return fail(404, '用户不存在')
    return ok(row)


@app.post('/api/user/profile')
def update_profile(body: ProfileBody, user=Depends(require_user)):
    if body.password:
        if len(body.password) < 6:
            return fail(400, '新密码至少 6 位')
        if body.password != body.confirmPassword:
            return fail(400, '两次输入的密码不一致')
    ex('UPDATE users SET nickname = ?, tel = ?, email = ? WHERE id = ?',
       (body.nickname.strip() or user['username'], body.tel.strip(), body.email.strip(), user['user_id']))
    if body.password:
        ex('UPDATE users SET password = ? WHERE id = ?',
           (hash_password(body.password), user['user_id']))
    return ok(None, message='保存成功')


# ---------------------------------------------------------------- 模块列表接口
def list_page(table, order_by, row_mapper=None, filters=None):
    """标准分页查询。filters: list of (col, value) 等值过滤"""
    where = ''
    params = []
    for col, val in (filters or []):
        where += (' AND ' if where else ' WHERE ') + f'{col} = ?'
        params.append(val)
    total = q(f'SELECT COUNT(*) c FROM {table}{where}', params, one=True)['c']
    rows = q(f'SELECT * FROM {table}{where} ORDER BY {order_by} LIMIT 20', params)
    if row_mapper:
        rows = [row_mapper(r) for r in rows]
    return total, rows


def wrap_page(pageNum, pageSize, total, rows):
    return {'total': total, 'pageNum': pageNum, 'pageSize': pageSize, 'list': rows}


@app.get('/api/device/list')
def device_list(request: Request, _user=Depends(require_user)):
    pageNum = int(request.query_params.get('pageNum', 1))
    pageSize = int(request.query_params.get('pageSize', 10))
    total, rows = list_page('device', 'id DESC')
    return ok(wrap_page(pageNum, pageSize, total, rows))


@app.get('/api/firmware/list')
def firmware_list(request: Request, _user=Depends(require_user)):
    pageNum = int(request.query_params.get('pageNum', 1))
    pageSize = int(request.query_params.get('pageSize', 10))
    total, rows = list_page('firmware', 'id DESC')
    return ok(wrap_page(pageNum, pageSize, total, rows))


@app.get('/api/memory/chat/list')
def memory_chat_list(request: Request, _user=Depends(require_user)):
    pageNum = int(request.query_params.get('pageNum', 1))
    pageSize = int(request.query_params.get('pageSize', 10))
    total, rows = list_page('memory_chat', 'id DESC', row_mapper=lambda r: {
        **r, 'tools': json.loads(r['tools']) if r.get('tools') else [], 'audio': bool(r.get('audio'))})
    return ok(wrap_page(pageNum, pageSize, total, rows))


@app.get('/api/memory/long/list')
def memory_long_list(request: Request, _user=Depends(require_user)):
    pageNum = int(request.query_params.get('pageNum', 1))
    pageSize = int(request.query_params.get('pageSize', 10))
    total, rows = list_page('memory_long', 'id DESC')
    return ok(wrap_page(pageNum, pageSize, total, rows))


@app.get('/api/memory/summary/list')
def memory_summary_list(request: Request, _user=Depends(require_user)):
    pageNum = int(request.query_params.get('pageNum', 1))
    pageSize = int(request.query_params.get('pageSize', 10))
    total, rows = list_page('memory_summary', 'id DESC')
    return ok(wrap_page(pageNum, pageSize, total, rows))


@app.get('/api/voiceprint/list')
def voiceprint_list(request: Request, _user=Depends(require_user)):
    pageNum = int(request.query_params.get('pageNum', 1))
    pageSize = int(request.query_params.get('pageSize', 10))
    total, rows = list_page('voiceprint', 'id DESC')
    return ok(wrap_page(pageNum, pageSize, total, rows))


@app.get('/api/agent/list')
def agent_list(request: Request, _user=Depends(require_user)):
    pageNum = int(request.query_params.get('pageNum', 1))
    pageSize = int(request.query_params.get('pageSize', 10))
    total, rows = list_page('agent', 'id ASC', row_mapper=lambda r: {**r, 'isDefault': bool(r.get('isDefault'))})
    return ok(wrap_page(pageNum, pageSize, total, rows))


@app.get('/api/index/recent')
def index_recent(_user=Depends(require_user)):
    total, rows = list_page('device', 'lastActiveTime DESC')
    recent = rows[:6]
    stats = {
        'chatTotal': 186,
        'deviceTotal': q('SELECT COUNT(*) c FROM device', one=True)['c'],
        'agentTotal': q('SELECT COUNT(*) c FROM agent', one=True)['c'],
    }
    return ok({'total': total, 'pageNum': 1, 'pageSize': 6, 'list': recent, 'stats': stats})


# ---------------------------------------------------------------- 健康检查
@app.get('/api/health')
def health():
    return ok({'status': 'up', 'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'db': DB_PATH})


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=8010)
