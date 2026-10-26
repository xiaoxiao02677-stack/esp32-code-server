# -*- coding: utf-8 -*-
"""qxlik-clone 后端 API（全模块 CRUD + yuhe 主站桥）
- SQLite 独立数据库 data/qxlik.db（专用，不与任何现有系统共享）
- 统一响应 {code, message, data:{total,pageNum,pageSize,list}}
- Bearer token 认证，登录/登出/改密/个人资料
- 17 个业务模块通用 CRUD：列表(真分页+关键字搜索)/新增/编辑/删除
- 首页仪表盘：最近设备 + 真实统计（聊天记录数/设备数/智能体数）
- yuhe 主站桥：本地账号 ↔ 主站账号绑定，SM2 登录代理 + 双服务器(A先C后)转发
"""
import os
import io
import json
import time
import uuid as uuidlib
import sqlite3
import secrets
import hashlib
from contextlib import contextmanager
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
DB_PATH = os.path.join(DATA_DIR, 'qxlik.db')

app = FastAPI(title='qxlik-clone API', version='2.0.0')


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
  lastActiveTime TEXT, createTime TEXT,
  orderNo TEXT DEFAULT '', source TEXT DEFAULT 'manual'
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
CREATE TABLE IF NOT EXISTS biz_user (
  id INTEGER PRIMARY KEY,
  name TEXT, avatar TEXT, email TEXT, tel TEXT,
  deviceCount INTEGER DEFAULT 0, onlineCount INTEGER DEFAULT 0, messageCount INTEGER DEFAULT 0,
  status INTEGER DEFAULT 1, accountType TEXT, roleName TEXT,
  lastLoginTime TEXT, lastLoginIp TEXT
);
CREATE TABLE IF NOT EXISTS reminder (
  id INTEGER PRIMARY KEY,
  content TEXT, time TEXT, repeatType TEXT, status INTEGER DEFAULT 0, deviceName TEXT
);
CREATE TABLE IF NOT EXISTS music (
  id INTEGER PRIMARY KEY,
  name TEXT, category TEXT, url TEXT, sort INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS knowledge (
  id INTEGER PRIMARY KEY,
  name TEXT, status INTEGER DEFAULT 1, docCount INTEGER DEFAULT 0,
  chunkCount INTEGER DEFAULT 0, createTime TEXT
);
CREATE TABLE IF NOT EXISTS template (
  id INTEGER PRIMARY KEY,
  name TEXT, category TEXT, content TEXT, isDefault INTEGER DEFAULT 0, createTime TEXT
);
CREATE TABLE IF NOT EXISTS auth_role (
  id INTEGER PRIMARY KEY,
  title TEXT, permission TEXT, type TEXT, route TEXT, component TEXT,
  icon TEXT, sort INTEGER DEFAULT 0, visible INTEGER DEFAULT 1, status INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS config_model (
  id INTEGER PRIMARY KEY,
  category TEXT, name TEXT, modelType TEXT, description TEXT,
  isDefault INTEGER DEFAULT 0, createTime TEXT
);
CREATE TABLE IF NOT EXISTS config_oss (
  id INTEGER PRIMARY KEY,
  category TEXT, name TEXT, description TEXT, isDefault INTEGER DEFAULT 0, createTime TEXT
);
CREATE TABLE IF NOT EXISTS config_stt (
  id INTEGER PRIMARY KEY,
  category TEXT, name TEXT, description TEXT, isDefault INTEGER DEFAULT 0, createTime TEXT
);
CREATE TABLE IF NOT EXISTS config_tts (
  id INTEGER PRIMARY KEY,
  category TEXT, name TEXT, description TEXT, createTime TEXT
);
CREATE TABLE IF NOT EXISTS yuhe_link (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  qx_user_id INTEGER NOT NULL,
  yuhe_username TEXT NOT NULL,
  yuhe_password_enc TEXT NOT NULL,
  server_tag TEXT NOT NULL DEFAULT '',
  yuhe_token TEXT DEFAULT '',
  token_expire_at INTEGER DEFAULT 0,
  active INTEGER DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(qx_user_id)
);
"""

# ---------------------------------------------------------------- 模块注册表
# route → 表配置。cols: 允许写入的列（白名单，防注入）；
# search: keyword 模糊搜索的列；ints/bools: 入库类型转换；json_cols: 存 JSON 字符串
MODULES = {
    'device': {
        'table': 'device', 'order': 'id DESC',
        'cols': ['deviceId', 'deviceName', 'roleName', 'wifiName', 'location', 'status', 'online',
                 'productType', 'deviceType', 'version', 'lastActiveTime', 'createTime',
                 'orderNo', 'source'],
        'search': ['deviceId', 'deviceName', 'roleName', 'wifiName', 'location', 'productType', 'deviceType', 'orderNo'],
        'ints': ['status', 'online'], 'bools': ['online'],
    },
    'firmware': {
        'table': 'firmware', 'order': 'id DESC',
        'cols': ['version', 'chipType', 'fileSize', 'status', 'forceUpdate', 'changelog',
                 'lastOnlineTime', 'createTime'],
        'search': ['version', 'chipType', 'changelog'],
        'ints': ['status', 'forceUpdate'], 'bools': ['forceUpdate'],
    },
    'memory/chat': {
        'table': 'memory_chat', 'order': 'id DESC',
        'cols': ['time', 'deviceName', 'sender', 'tools', 'content', 'audio'],
        'search': ['time', 'deviceName', 'sender', 'content'],
        'ints': ['audio'], 'bools': ['audio'], 'json_cols': ['tools'],
    },
    'memory/long': {
        'table': 'memory_long', 'order': 'id DESC',
        'cols': ['time', 'content', 'source', 'importance'],
        'search': ['time', 'content', 'source', 'importance'],
        'ints': [], 'bools': [],
    },
    'memory/summary': {
        'table': 'memory_summary', 'order': 'id DESC',
        'cols': ['time', 'deviceName', 'summary'],
        'search': ['time', 'deviceName', 'summary'],
        'ints': [], 'bools': [],
    },
    'voiceprint': {
        'table': 'voiceprint', 'order': 'id DESC',
        'cols': ['speakerId', 'name', 'description', 'status'],
        'search': ['speakerId', 'name', 'description'],
        'ints': ['status'], 'bools': [],
    },
    'agent': {
        'table': 'agent', 'order': 'id ASC',
        'cols': ['agentName', 'agentId', 'platform', 'description', 'isDefault', 'publishTime'],
        'search': ['agentName', 'agentId', 'platform', 'description'],
        'ints': ['isDefault'], 'bools': ['isDefault'],
    },
    'user': {
        'table': 'biz_user', 'order': 'id DESC',
        'cols': ['name', 'avatar', 'email', 'tel', 'deviceCount', 'onlineCount', 'messageCount',
                 'status', 'accountType', 'roleName', 'lastLoginTime', 'lastLoginIp'],
        'search': ['name', 'email', 'tel', 'roleName', 'accountType', 'lastLoginIp'],
        'ints': ['deviceCount', 'onlineCount', 'messageCount', 'status'], 'bools': [],
    },
    'reminder': {
        'table': 'reminder', 'order': 'id DESC',
        'cols': ['content', 'time', 'repeatType', 'status', 'deviceName'],
        'search': ['content', 'time', 'repeatType', 'deviceName'],
        'ints': ['status'], 'bools': [],
    },
    'music': {
        'table': 'music', 'order': 'sort ASC, id DESC',
        'cols': ['name', 'category', 'url', 'sort'],
        'search': ['name', 'category', 'url'],
        'ints': ['sort'], 'bools': [],
    },
    'knowledge': {
        'table': 'knowledge', 'order': 'id DESC',
        'cols': ['name', 'status', 'docCount', 'chunkCount', 'createTime'],
        'search': ['name'],
        'ints': ['status', 'docCount', 'chunkCount'], 'bools': [],
    },
    'template': {
        'table': 'template', 'order': 'id DESC',
        'cols': ['name', 'category', 'content', 'isDefault', 'createTime'],
        'search': ['name', 'category', 'content'],
        'ints': ['isDefault'], 'bools': ['isDefault'],
    },
    'auth-role': {
        'table': 'auth_role', 'order': 'sort ASC, id ASC',
        'cols': ['title', 'permission', 'type', 'route', 'component', 'icon', 'sort', 'visible', 'status'],
        'search': ['title', 'permission', 'type', 'route', 'component'],
        'ints': ['sort', 'visible', 'status'], 'bools': ['visible'],
    },
    'config/model': {
        'table': 'config_model', 'order': 'id ASC',
        'cols': ['category', 'name', 'modelType', 'description', 'isDefault', 'createTime'],
        'search': ['category', 'name', 'modelType', 'description'],
        'ints': ['isDefault'], 'bools': ['isDefault'],
    },
    'config/oss': {
        'table': 'config_oss', 'order': 'id ASC',
        'cols': ['category', 'name', 'description', 'isDefault', 'createTime'],
        'search': ['category', 'name', 'description'],
        'ints': ['isDefault'], 'bools': ['isDefault'],
    },
    'config/stt': {
        'table': 'config_stt', 'order': 'id ASC',
        'cols': ['category', 'name', 'description', 'isDefault', 'createTime'],
        'search': ['category', 'name', 'description'],
        'ints': ['isDefault'], 'bools': ['isDefault'],
    },
    'config/tts': {
        'table': 'config_tts', 'order': 'id ASC',
        'cols': ['category', 'name', 'description', 'createTime'],
        'search': ['category', 'name', 'description'],
        'ints': [], 'bools': [],
    },
}

# 种子文件名（api/seed/ 下）与表名的映射
SEED_FILES = {
    'device': 'device', 'firmware': 'firmware', 'memory_chat': 'memory_chat',
    'memory_long': 'memory_long', 'memory_summary': 'memory_summary',
    'voiceprint': 'voiceprint', 'agent': 'agent',
    'biz_user': 'user', 'reminder': 'reminder', 'music': 'music',
    'knowledge': 'knowledge', 'template': 'template', 'auth_role': 'auth_role',
    'config_model': 'config_model', 'config_oss': 'config_oss',
    'config_stt': 'config_stt', 'config_tts': 'config_tts',
}


def _now():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def seed_from_json():
    """从 api/seed/*.json 灌入初始数据（幂等：表非空则跳过）"""
    seed_dir = os.path.join(BASE_DIR, 'seed')
    if not os.path.isdir(seed_dir):
        return
    with db() as conn:
        for table, fname in SEED_FILES.items():
            try:
                if q(f'SELECT COUNT(*) c FROM {table}', one=True, conn=conn)['c'] > 0:
                    continue
                path = os.path.join(seed_dir, fname + '.json')
                if not os.path.isfile(path):
                    continue
                with open(path, encoding='utf-8') as f:
                    data = json.load(f)
                rows = data.get('data', {}).get('list', [])
                if not rows:
                    continue
                # 按表实际列过滤（seed 可能带表没有的字段）
                tcols = [r['name'] for r in q(f'PRAGMA table_info({table})', conn=conn)]
                cols = [k for k in rows[0].keys() if k != 'id' and k in tcols]
                for r in rows:
                    vals = []
                    for c in cols:
                        v = r.get(c)
                        if isinstance(v, list):
                            v = json.dumps(v, ensure_ascii=False)
                        vals.append(v)
                    ex(f'INSERT INTO {table} ({",".join(cols)}) VALUES ({",".join(["?"] * len(cols))})',
                       vals, conn=conn)
            except Exception as e:
                print(f'[seed] {table}: {e}')


def ensure_admin():
    with db() as conn:
        row = q('SELECT id FROM users LIMIT 1', one=True, conn=conn)
        if row:
            return
        ex('INSERT INTO users (username, password, nickname, role, created_at) VALUES (?,?,?,?,?)',
           ('admin', hash_password('admin123'), '小智', 'admin', _now()), conn=conn)


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
        # 轻量迁移：device 表补电商联动列
        dcols = [r['name'] for r in q('PRAGMA table_info(device)', conn=conn)]
        for col, ddl in (('orderNo', "TEXT DEFAULT ''"), ('source', "TEXT DEFAULT 'manual'")):
            if col not in dcols:
                conn.execute(f'ALTER TABLE device ADD COLUMN {col} {ddl}')
        # 同步日志表
        conn.execute(SYNC_LOG_TABLE)
        # 首次生成同步令牌
        if not _sync_token():
            with open(SYNC_TOKEN_FILE, 'w', encoding='utf-8') as f:
                f.write(secrets.token_hex(48))
            os.chmod(SYNC_TOKEN_FILE, 0o600)
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
    """直连主站登录：账号密码必须是主站账号且属于 proxys 角色组。
    主站登录成功 → /user/info 查 roles → 无 proxys 拒绝 → 有则建本地影子用户 +
    yuhe_link 绑定 + 站点会话（本地不再有独立账号体系）。"""
    u = body.username.strip()
    if not u or not body.password:
        return fail(400, '用户名和密码不能为空')

    # 主站登录（A 先 C 后），成功即持有主站 token
    last_err = None
    for tag in [s['tag'] for s in YUHE_SERVERS]:
        try:
            yuhe_token, expire = _yuhe_login(tag, u, body.password)
        except HTTPException as e:
            last_err = e.detail
            continue
        break
    else:
        return fail(502, f'主站登录失败: {last_err or "两台主站均不可达"}')

    # 查主站身份与角色
    base = _yuhe_base(tag)
    try:
        st, _, txt = _do_http('GET', f'{base}/yuhe/user/info', headers={
            'Authorization': f'Bearer {yuhe_token}', 'Accept': 'application/json'}, timeout=15)
        info = (json.loads(txt).get('data') or {}) if st == 200 else {}
    except Exception:
        info = {}
    roles = info.get('roles') or []
    if PROXYS_ROLE not in roles:
        return fail(403, '该账号不属于 proxys 组，无权访问本站。请先在主站申请加入 proxys 角色组。')

    # 本地影子用户（username 为主站用户名；首次登录自动创建）
    row = q('SELECT * FROM users WHERE username = ?', (u,), one=True)
    if not row:
        ex('INSERT INTO users (username, password, nickname, role, created_at) VALUES (?,?,?,?,?)',
           (u, '(yuhe-sso)', u, 'admin', _now()))
        row = q('SELECT * FROM users WHERE username = ?', (u,), one=True)
    elif row['password'] == '(yuhe-sso)' and row['role'] != 'admin':
        ex("UPDATE users SET role='admin' WHERE id = ?", (row['id'],))
        row = q('SELECT * FROM users WHERE username = ?', (u,), one=True)

    # 自动绑定主站（登录即绑定，免再走绑定弹窗）
    _link_save(row['id'], u, _enc_password(body.password), tag,
               yuhe_token, int(time.time()) + int(expire))

    # 站点会话
    token = secrets.token_urlsafe(32)
    now = time.time()
    ex('INSERT INTO sessions (token_hash, user_id, expires_at, created_at) VALUES (?,?,?,?)',
       (hash_token(token), row['id'], now + SESSION_TTL, _now()))
    return ok({
        'token': token,
        'user': {'id': row['id'], 'username': row['username'],
                 'nickname': row['nickname'], 'role': 'admin'}
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
    password: str = ''
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


# ---------------------------------------------------------------- 通用 CRUD 引擎
def _prep(m, col, v):
    """入库前类型转换"""
    if col in m.get('json_cols', []):
        if isinstance(v, list):
            return json.dumps(v, ensure_ascii=False)
        if isinstance(v, str) and v.strip():
            # 逗号分隔字符串 → JSON 数组
            return json.dumps([t.strip() for t in v.split(',') if t.strip()], ensure_ascii=False)
        return None
    if col in m['bools']:
        return 1 if v in (True, 1, '1', 'true', 'True', '是') else 0
    if col in m['ints']:
        try:
            return int(v)
        except (TypeError, ValueError):
            return 0
    if v is None:
        return None
    return str(v)


def _post(m, row):
    """出库后类型还原（前端契约：bool 为真布尔，json 列为数组）"""
    for c in m['ints']:
        if c in row and row[c] is not None and c not in m['bools']:
            try:
                row[c] = int(row[c])
            except (TypeError, ValueError):
                pass
    for c in m.get('bools', []):
        if c in row:
            row[c] = bool(row[c])
    for c in m.get('json_cols', []):
        if c in row and row[c]:
            try:
                row[c] = json.loads(row[c])
            except (TypeError, ValueError):
                row[c] = []
    return row


def make_list(route):
    m = MODULES[route]

    def _list(request: Request, _user=Depends(require_user)):
        try:
            pageNum = max(1, int(request.query_params.get('pageNum', 1)))
        except ValueError:
            pageNum = 1
        try:
            pageSize = min(100, max(1, int(request.query_params.get('pageSize', 10))))
        except ValueError:
            pageSize = 10
        keyword = (request.query_params.get('keyword') or '').strip()
        where, params = '', []
        if keyword:
            kw = f'%{keyword}%'
            like = ' OR '.join(f'{c} LIKE ?' for c in m['search'])
            where = ' WHERE ' + like
            params = [kw] * len(m['search'])
        total = q(f'SELECT COUNT(*) c FROM {m["table"]}{where}', params, one=True)['c']
        rows = q(f'SELECT * FROM {m["table"]}{where} ORDER BY {m["order"]} LIMIT ? OFFSET ?',
                 params + [pageSize, (pageNum - 1) * pageSize])
        rows = [_post(m, r) for r in rows]
        return ok({'total': total, 'pageNum': pageNum, 'pageSize': pageSize, 'list': rows})

    return _list


def make_create(route):
    m = MODULES[route]

    def _create(body: dict, _user=Depends(require_user)):
        if not isinstance(body, dict):
            return fail(400, '请求体必须是 JSON 对象')
        cols, vals = [], []
        for c in m['cols']:
            if c in body:
                cols.append(c)
                vals.append(_prep(m, c, body[c]))
        if not cols:
            return fail(400, '无有效字段')
        # 时间类列缺省自动补当前时间
        for tc in ('createTime', 'publishTime', 'lastActiveTime', 'time', 'lastLoginTime'):
            if tc in m['cols'] and tc not in cols:
                cols.append(tc)
                vals.append(_now())
        try:
            new_id = ex(f'INSERT INTO {m["table"]} ({",".join(cols)}) VALUES ({",".join(["?"] * len(cols))})', vals)
        except sqlite3.IntegrityError as e:
            return fail(400, f'写入失败: {e}')
        row = q(f'SELECT * FROM {m["table"]} WHERE id = ?', (new_id,), one=True)
        return ok(_post(m, row) if row else {'id': new_id}, message='创建成功')

    return _create


def make_update(route):
    m = MODULES[route]

    def _update(body: dict, _user=Depends(require_user)):
        if not isinstance(body, dict) or not body.get('id'):
            return fail(400, '缺少 id')
        rid = body['id']
        row = q(f'SELECT id FROM {m["table"]} WHERE id = ?', (rid,), one=True)
        if not row:
            return fail(404, '记录不存在')
        cols, vals = [], []
        for c in m['cols']:
            if c in body:
                cols.append(c)
                vals.append(_prep(m, c, body[c]))
        if not cols:
            return fail(400, '无有效字段')
        vals.append(rid)
        ex(f'UPDATE {m["table"]} SET {",".join(c + " = ?" for c in cols)} WHERE id = ?', vals)
        row = q(f'SELECT * FROM {m["table"]} WHERE id = ?', (rid,), one=True)
        return ok(_post(m, row) if row else None, message='更新成功')

    return _update


def make_delete(route):
    m = MODULES[route]

    def _delete(body: dict, _user=Depends(require_user)):
        if not isinstance(body, dict) or not body.get('id'):
            return fail(400, '缺少 id')
        rid = body['id']
        row = q(f'SELECT id FROM {m["table"]} WHERE id = ?', (rid,), one=True)
        if not row:
            return fail(404, '记录不存在')
        ex(f'DELETE FROM {m["table"]} WHERE id = ?', (rid,))
        return ok(None, message='删除成功')

    return _delete


for _route in MODULES:
    app.add_api_route(f'/api/{_route}/list', make_list(_route), methods=['GET'])
    app.add_api_route(f'/api/{_route}/create', make_create(_route), methods=['POST'])
    app.add_api_route(f'/api/{_route}/update', make_update(_route), methods=['POST'])
    app.add_api_route(f'/api/{_route}/delete', make_delete(_route), methods=['POST'])


# ---------------------------------------------------------------- 首页仪表盘
@app.get('/api/index/recent')
def index_recent(_user=Depends(require_user)):
    rows = q('SELECT * FROM device ORDER BY lastActiveTime DESC LIMIT 6')
    total = q('SELECT COUNT(*) c FROM device', one=True)['c']
    stats = {
        'chatTotal': q('SELECT COUNT(*) c FROM memory_chat', one=True)['c'],
        'deviceTotal': total,
        'agentTotal': q('SELECT COUNT(*) c FROM agent', one=True)['c'],
    }
    return ok({'total': total, 'pageNum': 1, 'pageSize': 6, 'list': rows, 'stats': stats})


# ---------------------------------------------------------------- 健康检查
@app.get('/api/health')
def health():
    return ok({'status': 'up', 'time': _now(), 'db': DB_PATH})


# ---------------------------------------------------------------- 电商联动（yuhe.pro WooCommerce → qxlik 设备管理）
SYNC_TOKEN_FILE = os.path.join(DATA_DIR, 'sync_token')
SYNC_LOG_TABLE = """
CREATE TABLE IF NOT EXISTS sync_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event TEXT, order_no TEXT, payload TEXT, result TEXT, created_at TEXT
);
"""


def _sync_token():
    try:
        with open(SYNC_TOKEN_FILE, encoding='utf-8') as f:
            return f.read().strip()
    except OSError:
        return ''


def verify_sync(request: Request):
    """内部同步鉴权：X-Sync-Token 与 data/sync_token 一致"""
    tok = request.headers.get('x-sync-token', '')
    expect = _sync_token()
    if not expect or not secrets.compare_digest(tok, expect):
        raise HTTPException(status_code=401, detail='同步令牌无效')


def _log_sync(event, order_no, payload, result):
    try:
        ex('INSERT INTO sync_log (event, order_no, payload, result, created_at) VALUES (?,?,?,?,?)',
           (event, order_no, json.dumps(payload, ensure_ascii=False)[:2000], result[:500], _now()))
    except Exception:
        pass


def _rand_device_id():
    import random
    mac = [random.randint(0x10, 0xEE) for _ in range(6)]
    return ':'.join(f'{b:02X}' for b in mac)


class OrderSyncBody(BaseModel):
    orderNo: str
    customerName: str = ''
    customerPhone: str = ''
    productName: str = ''
    productSku: str = ''
    quantity: int = 1
    status: str = 'paid'      # paid=已支付(登记/恢复) cancelled/refunded=取消/退款(停用)


@app.post('/api/sync/order')
def sync_order(body: OrderSyncBody, request: Request, _g=Depends(verify_sync)):
    """WooCommerce 订单 → 设备登记/停用（幂等）"""
    if not body.orderNo.strip():
        return fail(400, 'orderNo 不能为空')
    order_no = body.orderNo.strip()

    if body.status in ('cancelled', 'refunded'):
        # 取消/退款 → 关联设备全部停用
        rows = q('SELECT id, deviceId, status FROM device WHERE orderNo = ?', (order_no,))
        for r in rows:
            ex('UPDATE device SET status = 0, online = 0 WHERE id = ?', (r['id'],))
        _log_sync('order_cancel', order_no, body.model_dump(), f'disabled {len(rows)} devices')
        return ok({'orderNo': order_no, 'action': 'disabled', 'affected': len(rows)},
                  message='订单已取消，关联设备已停用')

    # paid / processing / completed → 登记（按订单号 upsert：已有行复用，不足补建）
    qty = max(1, min(99, body.quantity or 1))
    existing = q('SELECT id, deviceId, status FROM device WHERE orderNo = ? ORDER BY id', (order_no,))

    updated, created = 0, 0
    for i in range(qty):
        if i < len(existing):
            # payload 有值才覆盖，避免重放（重试队列）时用空值洗掉已有信息
            ex('UPDATE device SET status = 1, online = 0, '
               'productType = CASE WHEN ? != \'\' THEN ? ELSE productType END, '
               'deviceName = CASE WHEN ? != \'\' THEN ? ELSE deviceName END WHERE id = ?',
               (body.productName or '', body.productName or '',
                _device_name(body, i + 1) if (body.customerName or body.customerPhone or body.productName) else '',
                _device_name(body, i + 1) if (body.customerName or body.customerPhone or body.productName) else '',
                existing[i]['id']))
            updated += 1
        else:
            ex('INSERT INTO device (deviceId, deviceName, roleName, location, status, online, '
               'productType, deviceType, version, lastActiveTime, createTime, orderNo, source) '
               'VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
               (_rand_device_id(), _device_name(body, i + 1), '默认角色', '待收货', 1, 0,
                body.productName or '', body.productSku or 'AI-DEVICE', '待烧录',
                _now(), _now(), order_no, 'shop'))
            created += 1
    _log_sync('order_paid', order_no, body.model_dump(), f'updated {updated}, created {created}')
    return ok({'orderNo': order_no, 'action': 'upserted', 'updated': updated, 'created': created},
              message='设备登记成功')


def _device_name(body, seq):
    base = body.productName or '屿禾AI设备'
    who = body.customerName or body.customerPhone or '客户'
    return f'{who}的{base}' + (f' #{seq}' if body.quantity > 1 else '')


@app.get('/api/sync/log')
def sync_log(request: Request, _user=Depends(require_user)):
    """同步日志（后台管理员可查，普通 Bearer 认证）"""
    rows = q('SELECT id, event, order_no, result, created_at FROM sync_log ORDER BY id DESC LIMIT 100')
    return ok(rows)


# ================================================================
# yuhe 主站桥（qxlik 本地账号 ↔ yuhe 主站账号绑定）
#
# 链路：浏览器 → 8080 /api/yuhe/*（本后端）→ 主站 Java（A 先 C 后）
#   1. /api/yuhe/servers   服务器列表（A=生产 sandyun.top:8001，C=yuhe.pro）
#   2. /api/yuhe/link      绑定主站账号（后端 OCR 验证码 → SM2 登录 → Fernet 存密码）
#   3. /api/yuhe/me        绑定状态
#   4. /api/yuhe/unlink    解绑（并下线主站 token）
#   5. /api/yuhe/proxy     通用代理 {server, method, path, body}：带 token 转发，
#                          401 自动重登录（OCR）重试一次；A 不可达自动换 C
#
# 密码存储：Fernet 对称加密（密钥 data/yuhe_secret.key，0600）。
# SM2 加密：gmssl 库 C1C2C3 输出 → 重排为 C1C3C2（主站 BC 库 SM2Engine.Mode.C1C3C2）。
# ================================================================

import ssl as _ssl
import urllib.request
import urllib.error

# 主站服务器清单（A 先 C 后）
YUHE_SERVERS = [
    {'tag': 'A', 'name': '主站（生产）', 'base': 'https://sandyun.top:8001'},
    {'tag': 'C', 'name': '主站（备用）', 'base': 'https://yuhe.pro'},
]
# 登录本站所需的主站角色组（sys_role.role_code）；无此角色的主站账号拒绝登录
PROXYS_ROLE = 'proxys'

# ---- Fernet 密钥管理（可逆加密主站密码，供 401 自动重登录） ----
YUHE_SECRET_FILE = os.path.join(DATA_DIR, 'yuhe_secret.key')
_fernet = None
try:
    from cryptography.fernet import Fernet
    if not os.path.exists(YUHE_SECRET_FILE):
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(YUHE_SECRET_FILE, 'wb') as f:
            f.write(Fernet.generate_key())
        os.chmod(YUHE_SECRET_FILE, 0o600)
    with open(YUHE_SECRET_FILE, 'rb') as f:
        _fernet = Fernet(f.read())
except Exception:
    _fernet = None


def _enc_password(plain: str) -> str:
    if not _fernet:
        raise HTTPException(status_code=500, detail='后端加密模块不可用（cryptography 未安装）')
    return _fernet.encrypt(plain.encode('utf-8')).decode('ascii')


def _dec_password(enc: str) -> str:
    if not _fernet:
        raise HTTPException(status_code=500, detail='后端加密模块不可用（cryptography 未安装）')
    return _fernet.decrypt(enc.encode('ascii')).decode('utf-8')


# ---- SM2 加密（gmssl mode=1 = C1C3C2，与主站 BC 库同模式） ----
def _sm2_encrypt_c1c3c2(plain: str, pubkey_hex: str) -> str:
    """与主站前端 '04' + sm2.doEncrypt(captcha+password, pubKey, 1) 完全等价。
    gmssl CryptSM2(mode=1).encrypt 输出 C1(64B)||C3(32B)||C2(n) 且无 04 前缀，
    主站 BC SM2Utils.decrypt 自动补 04，故返回 '04' + hex。
    注意：gmssl __init__ 的 public_key.lstrip("04") 会误伤 X 坐标以 0/4 开头的
    密钥，构造后直接覆写 public_key 规避。"""
    from gmssl import sm2 as _gm
    pk = (pubkey_hex or '').strip().lower()
    if len(pk) == 130 and pk.startswith('04'):
        pk = pk[2:]
    if len(pk) != 128:
        raise RuntimeError('SM2 公钥格式异常（期望 128/130 位 hex）')
    crypt = _gm.CryptSM2(public_key='11' * 64, private_key='', mode=1)
    crypt.public_key = pk  # 覆写规避开头的 lstrip bug
    cipher = crypt.encrypt(plain.encode('utf-8'))
    if not cipher or len(cipher) < 97:
        raise RuntimeError('SM2 加密失败')
    return '04' + cipher.hex()


# ---- OCR 验证码识别（主站 SpecCaptcha 5 位字母数字） ----
_ocr_instance = None


def _ocr_captcha(img_bytes: bytes):
    global _ocr_instance
    try:
        if _ocr_instance is None:
            import ddddocr
            _ocr_instance = ddddocr.DdddOcr(show_ad=False)
        return (_ocr_instance.classification(img_bytes) or '').strip()
    except Exception:
        return None


# ---- HTTP（自签证书跳过校验：A 站 sandyun.top:8001 为自签） ----
_ssl_ctx = _ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = _ssl.CERT_NONE


def _do_http(method: str, url: str, headers=None, body=None, timeout=12, as_bytes=False):
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(url, data=data, method=method)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_ctx) as resp:
            raw = resp.read()
            return resp.status, dict(resp.headers), (raw if as_bytes else raw.decode('utf-8', 'replace'))
    except urllib.error.HTTPError as e:
        raw = e.read()
        return e.code, dict(e.headers), (raw if as_bytes else raw.decode('utf-8', 'replace'))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f'主站网络请求失败: {e}')


def _yuhe_base(server_tag: str) -> str:
    for s in YUHE_SERVERS:
        if s['tag'] == server_tag:
            return s['base']
    raise HTTPException(status_code=400, detail=f'未知服务器: {server_tag}')


# ---- yuhe_link 存取 ----
def _link_get(qx_user_id: int):
    return q('SELECT * FROM yuhe_link WHERE qx_user_id = ?', (qx_user_id,), one=True)


def _link_save(qx_user_id: int, username: str, password_enc: str, server_tag: str,
               token: str = '', token_expire_at: int = 0):
    now = _now()
    if _link_get(qx_user_id):
        ex('UPDATE yuhe_link SET yuhe_username=?, yuhe_password_enc=?, server_tag=?, '
           'yuhe_token=?, token_expire_at=?, active=1, updated_at=? WHERE qx_user_id=?',
           (username, password_enc, server_tag, token, token_expire_at, now, qx_user_id))
    else:
        ex('INSERT INTO yuhe_link (qx_user_id, yuhe_username, yuhe_password_enc, server_tag, '
           'yuhe_token, token_expire_at, active, created_at, updated_at) VALUES (?,?,?,?,?,?,1,?,?)',
           (qx_user_id, username, password_enc, server_tag, token, token_expire_at, now, now))


# ---- 主站登录（复刻 console-v2 authApi.login 契约） ----
def _yuhe_login(server_tag: str, username: str, password: str):
    """pub-config 取公钥 → 拉验证码图 OCR → SM2(captcha+password) → POST /user/login。
    成功返回 (token, expire_seconds)。"""
    base = _yuhe_base(server_tag)

    st, _, txt = _do_http('GET', f'{base}/yuhe/user/pub-config', timeout=15)
    if st != 200:
        raise HTTPException(status_code=502, detail=f'获取主站公钥失败 (HTTP {st})')
    try:
        pubkey = (json.loads(txt).get('data') or {}).get('sm2PublicKey', '')
    except Exception:
        pubkey = ''
    if not pubkey:
        raise HTTPException(status_code=502, detail='主站未返回 SM2 公钥')

    cap_uuid = uuidlib.uuid4().hex
    st, _, img = _do_http('GET', f'{base}/yuhe/user/captcha?uuid={cap_uuid}', timeout=10, as_bytes=True)
    if st != 200 or not img or len(img) < 100:
        raise HTTPException(status_code=502, detail='获取主站验证码失败')
    code = _ocr_captcha(img)
    if not code or len(code) != 5:
        raise HTTPException(status_code=502, detail='验证码识别失败，请稍后重试')

    encrypted = _sm2_encrypt_c1c3c2(code + password, pubkey)

    st, _, txt = _do_http('POST', f'{base}/yuhe/user/login', headers={
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'User-Agent': 'Mozilla/5.0 (qxlik-bridge)',
        'Origin': base,
        'Referer': f'{base}/',
    }, body={'username': username, 'password': encrypted, 'captchaId': cap_uuid}, timeout=20)
    try:
        j = json.loads(txt)
    except Exception:
        j = {}
    if st == 200 and j.get('code') == 0:
        d = j.get('data') or {}
        token = d.get('token', '')
        expire = d.get('expire', 86400)
        if not token:
            raise HTTPException(status_code=502, detail='主站登录响应缺少 token')
        return token, int(expire)
    msg = (j.get('msg') or j.get('message') or f'HTTP {st}')
    raise HTTPException(status_code=502, detail=f'主站登录失败: {msg}')


# ---- 代理核心 ----
class _NeedsRelogin(Exception):
    pass


def _yuhe_proxy_once(server_tag: str, token: str, method: str, path: str, body=None):
    """单次转发。path 形如 /agent/list（不含 /yuhe 前缀）。401 抛 _NeedsRelogin。"""
    base = _yuhe_base(server_tag)
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {token}',
        'User-Agent': 'Mozilla/5.0 (qxlik-bridge)',
        'Origin': base,
        'Referer': f'{base}/',
    }
    if body is not None:
        headers['Content-Type'] = 'application/json'
    st, hdrs, txt = _do_http(method, f'{base}/yuhe{path}', headers=headers, body=body, timeout=25)
    if st == 401:
        raise _NeedsRelogin()
    return st, hdrs, txt


# ---- 请求体模型 ----
class YuheLinkBody(BaseModel):
    serverTag: str = ''
    username: str
    password: str


class YuheProxyBody(BaseModel):
    server: str = ''
    method: str = 'GET'
    path: str
    # 前端 GET 请求恒发 "body": null；pydantic v2 中 dict=None 显式传 null 会 422，必须 Optional
    body: Optional[dict] = None


@app.get('/api/yuhe/servers')
def yuhe_servers(_user=Depends(require_user)):
    return ok(YUHE_SERVERS)


@app.get('/api/yuhe/me')
def yuhe_me(_user=Depends(require_user)):
    user = _user
    link = _link_get(user['user_id'])
    if not link or not link['active']:
        return ok({'linked': False})
    exp = link['token_expire_at'] or 0
    return ok({
        'linked': True,
        'username': link['yuhe_username'],
        'serverTag': link['server_tag'],
        'hasToken': bool(link['yuhe_token']),
        'tokenExpireAt': exp,
        'tokenAlive': bool(link['yuhe_token']) and (exp > time.time() + 60),
    })


@app.post('/api/yuhe/link')
def yuhe_link_bind(body: YuheLinkBody, _user=Depends(require_user)):
    """绑定主站账号：用户名+密码 → 双服务器 A先C后 登录 → Fernet 存密码 + token"""
    user = _user
    username = body.username.strip()
    if not username or not body.password:
        return fail(400, '主站用户名和密码不能为空')

    prefer = (body.serverTag or '').strip().upper()
    order = [s['tag'] for s in YUHE_SERVERS]
    if prefer in order:
        order.remove(prefer)
        order.insert(0, prefer)

    last_err = None
    for tag in order:
        try:
            token, expire = _yuhe_login(tag, username, body.password)
            _link_save(user['user_id'], username, _enc_password(body.password), tag,
                       token, int(time.time()) + expire)
            return ok({'serverTag': tag, 'username': username}, message='主站账号绑定成功')
        except HTTPException as e:
            last_err = str(e.detail)
        except Exception as e:
            last_err = str(e)
    return fail(502, f'两台主站均登录失败（最后错误: {last_err}）')


@app.post('/api/yuhe/unlink')
def yuhe_unlink(_user=Depends(require_user)):
    user = _user
    link = _link_get(user['user_id'])
    if link and link['active']:
        if link['yuhe_token']:
            try:
                _do_http('POST', f"{_yuhe_base(link['server_tag'])}/yuhe/user/logout",
                         headers={'Authorization': f"Bearer {link['yuhe_token']}",
                                  'User-Agent': 'Mozilla/5.0 (qxlik-bridge)'}, timeout=6)
            except Exception:
                pass
        ex("UPDATE yuhe_link SET active=0, yuhe_token='', token_expire_at=0, updated_at=? "
           'WHERE qx_user_id=?', (_now(), user['user_id']))
    return ok(None, message='已解绑')


def _relay_response(st, hdrs, txt):
    """主站响应 → qxlik 契约 {code,message,data}。JSON 原样包进 data.body；
    二进制 base64 进 data.binary。主站业务错（code!=0）也透传给前端处理。"""
    ctype = ''
    for k in ('Content-Type', 'content-type', 'Content-type'):
        if k in (hdrs or {}):
            ctype = hdrs[k]
            break
    if ctype.startswith('application/json') or ctype.startswith('text/'):
        try:
            parsed = json.loads(txt)
            return JSONResponse({'code': 200, 'message': 'success',
                                 'data': {'status': st, 'body': parsed, 'contentType': ctype}})
        except Exception:
            return JSONResponse({'code': 200, 'message': 'success',
                                 'data': {'status': st, 'rawBody': txt, 'contentType': ctype}})
    raw = txt if isinstance(txt, bytes) else str(txt).encode('utf-8')
    return JSONResponse({'code': 200, 'message': 'success',
                         'data': {'status': st, 'binary': base64.b64encode(raw).decode(),
                                  'contentType': ctype}})


@app.post('/api/yuhe/proxy')
def yuhe_proxy(body: YuheProxyBody, _user=Depends(require_user)):
    """通用代理：{server?, method, path, body?}。
    - server 留空 → 用绑定服务器的 tag
    - 401 → 用库中密码自动重登录后重试一次；重登录也失败 → 401 要求重新绑定
    - 502（网络层）→ 换另一台服务器重试一次
    - token 剩余 <5min → 主动重登录再转发（createToken 复用未过期 token 并顺延 24h）"""
    user = _user
    link = _link_get(user['user_id'])
    if not link or not link['active']:
        return fail(401, '尚未绑定主站账号')
    if not body.path.startswith('/'):
        return fail(400, 'path 必须以 / 开头')
    server_tag = (body.server or link['server_tag'] or 'A')
    method = (body.method or 'GET').upper()
    if method not in ('GET', 'POST', 'PUT', 'DELETE'):
        return fail(400, f'不支持的 method: {method}')

    # token 临近过期 → 主动续期（重登录即续期）
    if link['yuhe_token'] and 0 < (link['token_expire_at'] or 0) < time.time() + 300:
        try:
            token, expire = _yuhe_login(server_tag, link['yuhe_username'],
                                        _dec_password(link['yuhe_password_enc']))
            _link_save(user['user_id'], link['yuhe_username'], link['yuhe_password_enc'],
                       server_tag, token, int(time.time()) + expire)
            link = _link_get(user['user_id'])
        except Exception:
            pass  # 续期失败不阻断，带旧 token 继续（可能仍有效）

    other_tag = None
    for s in YUHE_SERVERS:
        if s['tag'] != server_tag:
            other_tag = s['tag']
            break

    attempted_relogin = False
    attempted_failover = False
    for _attempt in range(3):
        try:
            st, hdrs, txt = _yuhe_proxy_once(server_tag, link['yuhe_token'], method, body.path, body.body)
            return _relay_response(st, hdrs, txt)
        except _NeedsRelogin:
            if attempted_relogin:
                return fail(401, '主站会话已失效且自动重登录仍失败，请重新绑定主站账号')
            attempted_relogin = True
            try:
                token, expire = _yuhe_login(server_tag, link['yuhe_username'],
                                            _dec_password(link['yuhe_password_enc']))
                _link_save(user['user_id'], link['yuhe_username'], link['yuhe_password_enc'],
                           server_tag, token, int(time.time()) + expire)
                link = _link_get(user['user_id'])
            except HTTPException as e:
                return fail(401, f'主站会话过期，自动重登录失败: {e.detail}，请重新绑定主站账号')
        except HTTPException as e:
            # 网络层失败 → 换台服务器再试；其余错误直接返回
            if e.status_code == 502 and not attempted_failover and other_tag:
                attempted_failover = True
                server_tag = other_tag
                continue
            return fail(e.status_code, str(e.detail))
    return fail(502, '主站请求失败')


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=8010)

# ---------------------------------------------------------------- yuhe 音频播放桥
@app.get('/api/yuhe/play/{audio_uuid}')
def yuhe_play_audio(audio_uuid: str, _user=Depends(require_user)):
    """声音克隆试听桥：uuid 是主站 POST /voiceClone/audio/{id} 换取的一次性播放标识。
    GET /voiceClone/play/{uuid} 主站返回音频二进制（一次性，读后即焚）。
    浏览器 window.open 直接命中本端点 → 流式返回音频字节。"""
    from fastapi.responses import Response as _Resp
    link = _link_get(_user['user_id'])
    if not link or not link['active'] or not link['yuhe_token']:
        return fail(401, '尚未绑定主站账号')
    server_tag = link['server_tag'] or 'A'
    base = _yuhe_base(server_tag)
    st, hdrs, raw = _do_http('GET', f'{base}/yuhe/voiceClone/play/{audio_uuid}',
                             headers={'Authorization': f'Bearer {link["yuhe_token"]}',
                                      'User-Agent': 'Mozilla/5.0 (qxlik-bridge)'},
                             timeout=30, as_bytes=True)
    if st != 200:
        return fail(502, f'音频获取失败（主站 HTTP {st}）')
    ctype = 'audio/mpeg'
    for k in ('Content-Type', 'content-type'):
        if k in (hdrs or {}) and hdrs[k]:
            ctype = hdrs[k]
            break
    return _Resp(content=raw, media_type=ctype,
                 headers={'Content-Disposition': 'inline; filename="voice.mp3"',
                          'Cache-Control': 'no-store'})
