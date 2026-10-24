# API 契约与部署说明

> 2026-10-22 起，本站已接入真实后端（FastAPI + SQLite）。
> 前端加载顺序：`auth.js`（认证通道）→ `static.js`（交互）→ `demo-data.js`（数据渲染）。
> 数据加载策略：**真实 API 优先，本地 demo JSON 兜底**（API 不可用或未登录时）。

## 部署拓扑

```
浏览器 → nginx :8009
           ├── /            → /var/www/link（静态 24 页）
           └── /api/        → 127.0.0.1:8010 uvicorn（systemd: qxlik-api）
                                 └── SQLite /opt/qxlik-api/data/qxlik.db
```

- 后端代码：`/opt/qxlik-api/app.py`（本地镜像 `api/app.py`）
- systemd：`qxlik-api.service`（enable --now，Restart=always）
- 初始账号：**admin / admin123**（首次启动自动创建，可在个人中心改密码）
- 重启服务：`systemctl restart qxlik-api`

## 统一响应包装

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "total": 8,
    "pageNum": 1,
    "pageSize": 10,
    "list": [ /* 行对象数组 */ ]
  }
}
```

- 分页参数：`?pageNum=1&pageSize=10`（当前数据量小，服务端固定返回前 20 条）
- 错误：HTTP 401 时返回 `{"code": 401, "message": "未登录或会话已过期", "data": null}`
- 认证方式：`Authorization: Bearer <token>`（登录接口返回，TTL 7 天）

## 认证接口

| 接口 | 方法 | 说明 |
|---|---|---|
| `/api/auth/login` | POST | `{username, password}` → `{token, user:{id,username,nickname,role}}` |
| `/api/auth/logout` | POST | 注销当前 token |
| `/api/auth/me` | GET | 当前用户信息 |
| `/api/auth/change-password` | POST | `{oldPassword, newPassword}` |
| `/api/user/profile` | GET | 个人资料（nickname/tel/email） |
| `/api/user/profile` | POST | 保存个人资料；`password`+`confirmPassword` 留空则不改密码 |
| `/api/health` | GET | 健康检查（免认证） |

密码哈希：PBKDF2-SHA256 10 万轮 + 随机盐；token 以 SHA256 哈希存 sessions 表。

## 业务模块接口（8 个，均需 Bearer token）

| 模块 | API | 页面 | 行数 | 关键字段 |
|---|---|---|---|---|
| 设备管理 | GET /api/device/list | device.html | 8 | deviceId(MAC)/deviceName/roleName/wifiName/location/status/online/productType/deviceType/version/lastActiveTime/createTime |
| 首页仪表盘 | GET /api/index/recent | index.html | 6 | deviceName/roleName/online/lastActiveTime + `stats:{chatTotal,deviceTotal,agentTotal}` 统计卡片联动 |
| 固件管理 | GET /api/firmware/list | firmware.html | 7 | version/chipType/fileSize/status(1=已发布 2=内测中 3=已归档)/forceUpdate/changelog/lastOnlineTime |
| 记忆-聊天记录 | GET /api/memory/chat/list | memory-chat.html | 8 | time/deviceName/sender(user\|agent)/tools(string[])/content/audio(bool)；首列为行展开图标 |
| 记忆-长期记忆 | GET /api/memory/long/list | memory-long.html | 6 | time/content/source/importance(high\|medium\|low) |
| 记忆-对话摘要 | GET /api/memory/summary/list | memory-summary.html | 6 | time/deviceName/summary |
| 声纹管理 | GET /api/voiceprint/list | voiceprint.html | 5 | speakerId/name/description/status |
| 智能体管理 | GET /api/agent/list | config-agent.html | 6 | agentName/agentId/platform/description/isDefault(bool)/publishTime；首两列为固定列 |

数据来源：`/opt/qxlik-api/seed/*.json`（首次启动幂等灌入，表非空跳过）。

## 前端认证流（js/auth.js）

1. **页面守卫**：`/pages/*` 业务页无 token → `location.replace('../login.html')`
2. **401 统一处理**：`QXAuth.api()` 收到 HTTP 401 → 清 localStorage → 跳登录页
3. **登录**：`login.js` POST `/api/auth/login` → token/user 存 localStorage（`qx-token`/`qx-user`）
4. **顶栏昵称**：`.user-name` 与首页问候语从登录用户 nickname 联动
5. **退出登录**：用户下拉 → `QXAuth.logout()` → POST `/api/auth/logout` → 清本地 → 跳登录
6. **个人中心**：setting-account.html 表单回填 GET profile，"保 存"按钮 POST profile

## 通用渲染规则

- 时间字段：`YYYY-MM-DD HH:mm:ss` 字符串
- 状态类字段（status/online）：转彩色 tag —— 正常/已发布=绿 `#10B981`、
  异常=红 `#EF4444`、中性/内测/中=靛蓝 `#6366F1`、归档/低=灰 `#A1A1AA`
- 文本溢出：`ellipsis-text` class（原站同款截断样式）
- 操作列：常规页 `编辑 | 删除`，只读页 `查看 | 删除`
- 分页器：空表页用捕获的分页模板插入（共 N 条 + 10 条/页）

## 无需接 API 的模块（原站捕获静态数据）

- user（4 行）、template（7 行）、reminder（5 行）、music（20 行）、knowledge（1 行）、
  auth-role（13 行）、config-model（6 行）、config-oss（2 行）、config-stt（2 行）、config-tts（2 行）
- config-mcp（卡片页）、role（权限表单页）、chat（对话页）

## 主题联动

- static.js 主题切换时派发 `qx-theme-change` 事件
- demo-data.js 监听并把行内 `css-97cec0/css-1p8u2sp` class 同步互换
- tag 内联色用 rgba + 固定色值，两主题下均可读
