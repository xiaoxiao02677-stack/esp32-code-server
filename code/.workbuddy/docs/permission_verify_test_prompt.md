# 权限设置→生效验证测试提示词（用户模块 / 管理端配置 → 用户端实测）

> 用途：把本提示词交给执行 agent（或代码生成 AI），即可自动化验证"管理端设置的权限，
> 用户端是否真的按设置生效"。基于 2026-10-21 对 yuhe 权限体系的源码实读。
> 目标环境：测试环境（22223）优先，避免污染生产。

---

## 主提示词（可直接整段粘贴给执行 agent）

```
请开发并执行一套"权限设置→生效验证"的自动化测试，验证管理端对用户模块的权限设置
是否在用户端（前端导航 + API 层）真实生效。按下述已核实的权限架构执行，不要凭空假设。

【已被核实的权限架构（源码实读，测试的判定依据）】

权限生效共三层，每层机制不同，必须分开验证：

L1 Shiro 认证层（后端，所有 /yuhe/** 接口）：
- Oauth2Realm.doGetAuthorizationInfo 只发放两个权限码：
  DB superAdmin=1 → "sys:role:superAdmin" + "sys:role:normal"；
  其余登录用户 → 只有 "sys:role:normal"。
- @RequiresPermissions 注解只使用这两个码（AgentController/SysAdminModuleController 等），
  即后端接口层只有"超管 / 普通登录用户 / 未登录"三档粗粒度。
- 无 token 或 token 过期 → HTTP 层 401（业务码也是 401）。

L2 前端管理端准入（console-v2）：
- hasAdminRole()（lib/api.js:103）：superAdmin===1 或 roles 数组含 roleCode
  'super_admin' 或 'admin' → 允许进入 /admin 路由；否则路由守卫弹回 /customer。
- 路由守卫（main.js:110-123）：无 token → /login；非管理员访问 /admin/* → /customer。

L3 展示配置（模块显隐，管理端可配）：
- 三层合并优先级：用户(2) > 角色(1) > 系统(0)（scopeType）。
- 配置形状 modules['/admin/orders'] = { visible: false }，仅显式 false 才隐藏，
  未配置默认可见（fail-open）。
- 前端两个执行点：DockNav 导航过滤 + 路由守卫 URL 直达拦截（防手输绕过）。
- 超管豁免：任何配置不得对 superAdmin=1 用户隐藏模块。
- 用户端拉取接口：GET /user/display-config（登录态，返回生效合并结果）。

【重要已知 Gap（测试时不要误报为 bug）】
sys_role.permissions 里的 16 个细粒度权限点（admin:user:list / admin:role:save /
menu:admin / user:custom:* 等，见 Roles.vue PERM_GROUPS）在后端 Java 代码中没有
对应的 @RequiresPermissions 检查——它们目前只影响管理端前端展示域（角色编辑器勾选），
不构成 API 层拦截。所以"给角色勾掉 admin:user:list 后直接调 GET /admin/users 仍成功"
是当前架构的已知现状，记录为"架构观察"而非缺陷；本测试的重点是三层权限各自的
真实拦截行为与配置传播链路是否正确。

【测试环境与程序化登录（复用项目已验证方法）】
- 登录链：GET /user/captcha?uuid=<uuid>（图片）→ 从 Redis 读该 uuid 的验证码值
  （JSON parse，测试环境 Redis）→ GET /user/publicKey 取 SM2 公钥 → 密码 SM2 加密 →
  POST /user/login {username, password, uuid, captcha} → 拿 {token, expire}。
- 所有后续请求带 Authorization: Bearer <token>。
- 响应约定：{code:0, msg, data}，code=0 才成功；401 = 未登录/过期。
- API_BASE = /yuhe（nginx 同源反代 manager-api:8002）。

【测试数据准备（用管理端 API 或 SQL 造）】
1. 造 4 个测试角色（POST /admin/role/save，超管 token）：
   - roleA：permissions 含 menu:admin + admin:user:list（模拟"能进管理端+看用户"）
   - roleB：permissions 只有 user:custom:list（无 menu:admin → 前端进不了管理端）
   - roleC：permissions = ["*"]（通配全权限）
   - roleD：空 permissions（无任何权限点）
2. 造 4 个测试用户并绑定角色（POST /admin/users {username, roleIds}）：
   uA→roleA，uB→roleB，uC→roleC，uD→roleD
3. 展示配置（PUT /admin/display-config，超管 token）：
   - 系统层(scopeType=0)：隐藏 /admin/orders 和 /admin/voices
   - 角色层(scopeType=1, roleId=roleA)：恢复显示 /admin/voices（验证角色覆盖系统）

【测试矩阵（每个用例=前端行为 + API 实测两栏结论）】

| 用户 | 前端预期（导航/路由） | API 预期 |
|---|---|---|
| 超管 | 全模块可见（含被系统层隐藏的，豁免） | 全部成功 |
| uA | /admin 可进；orders 隐藏、voices 因角色层恢复显示 | GET /admin/users 成功（normal 码）；GET /admin/display-config 应 403/无权限（需 superAdmin 码） |
| uB | /admin 被路由守卫弹回 /customer；无"切换管理端"按钮 | 同左无阻断的接口仍可用（L1 只看登录态） |
| uC | 全模块可见（* 通配；若前端按权限点过滤） | 同超管的 API 结果？实测验证（预期：L1 层与 uA 相同，因 Shiro 码不看 permissions） |
| uD | /admin 进不去（无 menu:admin） | 登录可用，顾客端接口正常 |
| 未登录 | 全部跳 /login | 任意接口 401 |

【API 层逐条验证清单（每用户跑一遍，记录 code/msg）】
- GET /user/info → 验证返回的 superAdmin/roles 与造数一致（身份传播正确性）
- GET /user/display-config → 验证 L3 合并结果与矩阵预期一致（核心断言点）
- GET /admin/role/page → 预期超管 0、普通管理员按现状可能成功（记录实测）
- GET /admin/users → 同上
- PUT /admin/display-config → 预期非超管失败（RequiresPermissions superAdmin）
- POST /admin/role/save → 同上
- GET /agent/page 类（RequiresPermissions normal）→ 预期所有登录用户成功

【越权与边界用例】
1. URL 直达：以 uB 登录后直接访问 #/admin/users → 应被守卫弹回 /customer
2. 展示配置隐藏后 URL 直达：以 uA 访问 #/admin/orders → 应被弹回 /admin
3. 前端隐藏 ≠ 后端拦截：uA 直接 curl GET /yuhe/admin/orders 相关接口 → 记录实测
   （预期成功，属已知 Gap，写入报告"架构观察"节）
4. 角色删除后用户在线：删 roleA → uA 的旧 token 仍有效（Shiro 权限码与 role 无关）→ 记录
5. 展示配置改"用户层"（scopeType=2）：对 uA 单独再隐藏 voices → /user/display-config
   合并结果应变（用户>角色>系统 优先级验证）

【产出要求】
1. 一份 Markdown 测试报告：矩阵表（预期 vs 实测，PASS/FAIL/架构观察三态）+
   每条 API 的请求/响应摘要 + 三层权限各自结论。
2. 测试脚本（Python requests 即可）入 .workbuddy/ 下，可重复执行；
   测试数据用完清理（删测试用户/角色/展示配置行，或标记 deleted）。
3. 发现 FAIL 项给出源码定位（哪个文件哪个环节与预期不符）。
```

---

## 附：关键代码坐标速查（执行者排查用）

| 环节 | 文件:行 | 说明 |
|---|---|---|
| Shiro 双权限码发放 | security/oauth2/Oauth2Realm.java doGetAuthorizationInfo | superAdmin=1 才有 superAdmin 码 |
| 接口权限注解 | AgentController.java:101-114 等 | 只用 sys:role:normal / superAdmin 两码 |
| Shiro 过滤链 | security/config/ShiroConfig.java:79-91 | anon 白名单（login/captcha/ota 等） |
| 角色表实体 | sys/entity/SysRoleEntity.java | roleCode/permissions(JSON)/isBuiltin/status |
| 角色六件套 | sys/controller/SysAdminModuleController.java:49-85 | /admin/role/page·{id}·save·update·delete |
| 展示配置读写 | SysAdminModuleController.java:121-146 | GET/PUT /admin/display-config（需 superAdmin 码） |
| 用户端合并拉取 | security/controller/LoginController.java:172 | GET /user/display-config |
| 前端 hasAdminRole | console-v2/src/lib/api.js:103-109 | superAdmin 或 roleCode∈{super_admin,admin} |
| 前端模块显隐 | lib/api.js:120-131 | 超管豁免 + fail-open |
| 路由守卫 | main.js:110-123 | URL 直达拦截 |
| 导航过滤 | components/DockNav.vue:161-164 | isModuleVisible 过滤 adminItems |
| 细粒度权限点定义 | views/admin/Roles.vue:144-150 | 16 点分 5 组 + * 通配 |

## 附：测试账号造数 SQL 兜底（API 不可用时的备选）

```sql
-- 角色（permissions 为 JSON 数组字符串）
INSERT INTO sys_role (role_code, role_name, permissions, status, is_builtin, sort, create_date)
VALUES ('test_role_a', '测试A-管理可见', '["menu:admin","admin:user:list"]', 1, 0, 99, NOW()), ...;
-- 用户（密码用 BCrypt，建议直接走 API 造以便拿到明文初始密码）
-- 关联
INSERT INTO sys_user_role (user_id, role_id) VALUES (<uid>, <rid>);
-- 展示配置
-- 建议走 PUT /admin/display-config（scopeType 0/1/2），表为 sys_display_config
```
