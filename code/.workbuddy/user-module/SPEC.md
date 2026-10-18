# 用户管理模块 实施规格书（SPEC v1）

> 唯一事实来源。所有实施 agent 以本文档为准；与侦察报告冲突时以本文档为准。
> 前置基线：本地镜像已与服务器统一（md5 对齐，git commit 已固化）。
> 侦察报告：reports/recon-backend.md（代码骨架）、reports/recon-db.md（DDL 约定）、reports/recon-frontend.md（前端模板）。

## 0. 技术底线（不可违反）

- 后端：Spring Boot 3 + Shiro + MyBatis-Plus（ASSIGN_ID 雪花）+ Liquibase，源码 `G:/demo/21_xiaozhi/code-server-mirror/manager-api`，包根 `yuhe.modules.sys`
- 前端：Vue3 + vite + hash 路由，源码 `G:/demo/21_xiaozhi/console-v2`
- 服务器：`ssh -p 22223 root@sandyun.top`，后端 8002（context-path /yuhe），MySQL root/123456 xiaozhi_esp32_server
- 所有响应 `Result<T>`：`{code:0成功, msg, data}`，HTTP 恒 200；401/403 也走 body code
- 新 changeSet id：`202610140100`（建表+种子）与 `202610140200`（sys_user ALTER）
- 严禁修改既有 changeSet；严禁动服务器数据库（Liquibase 启动时自动执行）

## 1. DDL 定稿（foundation agent 照此写，不再自行设计）

单文件 `src/main/resources/db/changelog/202610140100.sql`（建表+种子，CREATE TABLE IF NOT EXISTS + INSERT...SELECT...WHERE NOT EXISTS 幂等）+ `202610140200.sql`（ALTER，yaml 配 preConditions: not columnExists sys_user.deleted, onFail/onError MARK_RAN）。

### 1.1 sys_role（在 recon-db 草案 5.1 基础上加 permissions 列）
```sql
CREATE TABLE IF NOT EXISTS `sys_role` (
  `id`          BIGINT       NOT NULL COMMENT 'id（内置角色用固定小整数，自建角色雪花ID）',
  `role_code`   VARCHAR(50)  NOT NULL COMMENT '角色编码',
  `role_name`   VARCHAR(50)  NOT NULL COMMENT '角色名称',
  `permissions` JSON         DEFAULT NULL COMMENT '权限点列表 JSON 数组，如 ["admin:user:list"]',
  `remark`      VARCHAR(200) DEFAULT NULL COMMENT '备注',
  `status`      TINYINT      NOT NULL DEFAULT '1' COMMENT '状态（0停用 1正常）',
  `is_builtin`  TINYINT(1)   NOT NULL DEFAULT '0' COMMENT '内置角色（0否 1是，内置不可删）',
  `sort`        INT UNSIGNED DEFAULT '0' COMMENT '排序',
  `creator`     BIGINT       DEFAULT NULL COMMENT '创建者',
  `create_date` DATETIME     DEFAULT NULL COMMENT '创建时间',
  `updater`     BIGINT       DEFAULT NULL COMMENT '更新者',
  `update_date` DATETIME     DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_role_code` (`role_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='角色';
```

### 1.2 sys_user_role —— 照 recon-db 草案 5.2 原样。

### 1.3 sys_audit_log —— 照 recon-db 草案 5.3 原样。

### 1.4 sys_display_config —— 照 recon-db 草案 5.4 原样（scope sentinel 0）。

### 1.5 sys_user_default —— 照 recon-db 草案 5.5 原样。

### 1.6 sys_user_custom_model —— 照 recon-db 草案 5.6 原样。

### 1.7 sys_user_custom_voice —— 照 recon-db 草案 5.7 原样。

### 1.8 202610140200.sql（sys_user 扩列）
```sql
ALTER TABLE `sys_user`
  ADD COLUMN `deleted`         TINYINT(1) NOT NULL DEFAULT '0' COMMENT '软删除（0否 1是）' AFTER `status`,
  ADD COLUMN `deleted_date`    DATETIME  DEFAULT NULL COMMENT '删除时间' AFTER `deleted`,
  ADD COLUMN `locked`          TINYINT(1) NOT NULL DEFAULT '0' COMMENT '锁定（0否 1是，锁定后禁止登录）' AFTER `deleted_date`,
  ADD COLUMN `last_login_date` DATETIME  DEFAULT NULL COMMENT '最后登录时间' AFTER `locked`,
  ADD COLUMN `must_change_pwd` TINYINT(1) NOT NULL DEFAULT '0' COMMENT '强制改密（0否 1是，管理员新建/重置后置1）' AFTER `last_login_date`,
  ADD COLUMN `pwd_update_date` DATETIME  DEFAULT NULL COMMENT '密码最后修改时间' AFTER `must_change_pwd`;
```

### 1.9 种子数据（202610140100.sql 内，幂等 INSERT）
4 个内置角色（is_builtin=1, status=1, creator=0）：
| id | role_code | role_name | permissions JSON |
|---|---|---|---|
| 1 | super_admin | 超级管理员 | ["*"] |
| 2 | admin | 管理员 | ["admin:user:*","admin:role:list","admin:display:config","admin:default:config","admin:custom:audit","admin:audit:list","menu:admin"] |
| 3 | user | 普通用户 | ["user:custom:*","menu:customer"] |
| 4 | readonly | 只读访客 | ["menu:customer"] |

## 2. RBAC 语义定稿

- **Realm（Oauth2Realm.doGetAuthorizationInfo）**：superAdmin==1 → permsSet = {"*","sys:role:superAdmin","sys:role:normal"}（保留旧串兼容既有注解）。否则 → 查 sys_user_role JOIN sys_role（status=1）→ 收集 permissions JSON 数组元素 + 固定加 "sys:role:normal"。查询失败静默降级为仅 normal（不能让权限子系统故障阻塞登录鉴权）。
- **权限点清单**（@RequiresPermissions 用）：
  - admin:user:list / create / update / delete / assign / resetPwd
  - admin:role:list / save / update / delete
  - admin:display:config、admin:default:config、admin:custom:audit、admin:audit:list
  - user:custom:create / update / delete / list
  - menu:admin、menu:customer（前端用，后端不校验）
- **实时生效**：Shiro 每次鉴权都调 Realm（无缓存配置即实时；不得引入权限缓存）。
- **越权**：@RequiresPermissions 不通过 → UnauthorizedException → RenExceptionHandler → code 403 + 审计记录（audit agent 负责）。

## 3. 错误码分配（foundation agent 一次性全部写入 ErrorCode.java + 7 个 i18n 文件，其他 agent 只引用）

- 10220 USERNAME_EXISTS 用户名已存在
- 10221 USER_NOT_FOUND 用户不存在
- 10222 USER_DELETED 用户已删除
- 10223 CANNOT_DISABLE_SELF 不能停用自己
- 10224 CANNOT_DELETE_LAST_ADMIN 不能操作最后一个启用的超级管理员
- 10225 IMPORT_PARTIAL 导入部分失败（data 携带明细）
- 10226 ROLE_CODE_EXISTS 角色编码已存在
- 10227 ROLE_BUILTIN 内置角色不可删除/不可停用
- 10228 ROLE_NOT_FOUND 角色不存在
- 10229 MUST_CHANGE_PWD 需要先修改密码
- 10230 DISPLAY_CONFIG_SCOPE 无效的作用域参数
- 10231 DEFAULT_MODEL_INVALID 默认模型不存在或未启用
- 10232 DEFAULT_VOICE_INVALID 默认音色不存在
- 10233 CUSTOM_MODEL_NOT_FOUND 自定义模型不存在
- 10234 CUSTOM_MODEL_DUPLICATE 同类型同名模型已存在
- 10235 CUSTOM_VOICE_NOT_FOUND / 10236 CUSTOM_VOICE_DUPLICATE 同上语义
- 10237 CUSTOM_AUDIT_INVALID 无效的审核状态
- 10238 QUOTA_EXCEEDED 调用配额已用尽
- 10239 CRYPTO_ERROR 密钥加解密失败
- 10240 AUDIT_QUERY_INVALID 审计查询参数无效
（i18n：properties \u 转义中文；英文/繁体/德/葡/越 各给一句对应翻译，其余文件用英文占位即可）

## 4. API 契约（后端实现与前端 api.js 封装必须逐字对齐）

Controller 相对路径（context /yuhe 已由 nginx 剥离）。分页参数 page/limit；列表返回 `data:{list,total}`。

### 4.1 角色（rbac agent，新文件 SysRoleController）
| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | /admin/role/page?keyword&page&limit | admin:role:list | VO 含 userCount |
| GET | /admin/role/list | admin:role:list | 启用角色下拉 [{id,roleCode,roleName}] |
| GET | /admin/role/{id} | admin:role:list | |
| POST | /admin/role/save | admin:role:save | body {roleCode,roleName,permissions[],remark,sort,status} |
| PUT | /admin/role/update | admin:role:update | 同上+id；内置角色仅允许改 permissions/remark |
| POST | /admin/role/delete | admin:role:delete | body [ids]；内置报 10227 |

### 4.2 用户管理（user-mgmt agent，改 AdminController + SysUserService*）
| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | /admin/users?page&limit&keyword&deleted&roleId | admin:user:list | keyword 匹配 username；默认排除 deleted；VO 增 roleNames[]、deleted、locked、lastLoginDate |
| POST | /admin/users | admin:user:create | {username,password?,roleIds?}；密码缺省自动生成12位；mustChangePwd=1；返回 data=初始密码 |
| GET | /admin/users/{id} | admin:user:list | data={user, roles, defaults, displayConfig} |
| PUT | /admin/users/roles | admin:user:assign | {userId, roleIds[]} |
| PUT | /admin/users/restore/{id} | admin:user:delete | 软删恢复 |
| DELETE | /admin/users/{id} | admin:user:delete | **改为软删除**（deleted=1, deleted_date=now）；已删返回 10222；不级联删设备/智能体 |
| PUT | /admin/users/changeStatus/{status} | admin:user:update | status 0/1；防自禁(10223)、防最后一个启用超管(10224)、跳过已删用户 |
| PUT | /admin/users/{id} | admin:user:resetPwd | 重置密码（保留）；同时 mustChangePwd=1 |
| POST | /admin/users/import | admin:user:create | body [{username,password?,roleCode?}]；data={success:[],failed:[{username,reason}]}；有失败抛 10225 且 data 带明细 |
| GET | /admin/users/export?keyword&deleted | admin:user:list | CSV 附件流（username,状态,角色,创建时间,最后登录）；Content-Type text/csv; charset=UTF-8; BOM 头防 Excel 乱码 |
| GET | /admin/users/sessions?page&limit | admin:user:list | sys_user_token JOIN 用户（username,token 前8位掩码,expireDate,createDate） |
| POST | /admin/users/forceLogout/{id} | admin:user:update | 过期该用户全部 token |
| 登录联动 | LoginController | — | 登录成功：更新 last_login_date、审计 login；locked=1 或 status=0 → 10022；TokenDTO/UserDetail 增加 mustChangePwd、roles[]；/user/info 返回同字段 |

### 4.3 展示配置与默认模型（display-default agent，新文件 2 个 Controller）
| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | /admin/display-config?scopeType&roleId&userId | admin:display:config | scopeType 0系统/1角色/2用户 |
| PUT | /admin/display-config | admin:display:config | upsert {scopeType,roleId,userId,configJson}；校验 10230 |
| GET | /user/display-config | 登录即可 | 生效合并：用户>角色>系统（同 key 用户覆盖角色覆盖系统） |
| GET | /admin/user-default?scopeType&roleId&userId | admin:default:config | |
| PUT | /admin/user-default | admin:default:config | upsert；模型/音色 id 校验存在且启用（10231/10232，用 ModelConfigService/TimbreDao） |
| GET | /user/defaults | 登录即可 | 生效合并（用户>角色>平台），带 lockPolicy 标记 |
| GET | /user/resources | 登录即可 | **模型为0规则的数据源**：data={llmModels:[{id,modelName}], ttsVoices:[{id,name,ttsModelId}], defaults, displayConfig}；llmModels=平台启用 LLM（model_type 统一大写比较）+ 本人审核通过的自定义 LLM；ttsVoices=平台音色+本人通过的自定义音色 |

configJson 字段级权限格式（前后端共同遵守）：
```json
{"fields":{"llm_model":{"visible":true,"editable":true},"tts_voice":{"visible":true,"editable":false},"system_prompt":{"visible":true,"editable":true},"temperature":{"visible":false}}}
```
可选值：visible/editable。缺省 field 视为 {"visible":true,"editable":true}。

### 4.4 自定义模型/音色（custom agent，新文件）
用户端（均为登录即可，数据自动按 SecurityUser.getUserId() 过滤）：
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /user/custom-models?modelType&auditStatus | 本人列表；apiKey 永远掩码（前4+****） |
| POST | /user/custom-models | {modelType(大写),modelName,providerCode,baseUrl,apiKey,configJson,remark}；同型同名查重 10234；apiKey AES-256-GCM 加密落 api_key_cipher |
| PUT | /user/custom-models/{id} | 同上部分更新；apiKey 传空串/不传=不改 |
| DELETE | /user/custom-models/{id} | 仅本人（非本人返回 10233） |
| POST | /user/custom-models/{id}/health | 对 baseUrl 做 HTTP GET(10s 超时)，返回 {status:1正常/2异常, latencyMs} |
| GET/POST/PUT/DELETE | /user/custom-voices | 同构；无 health；referenceAudio 存路径 |
管理端：
| 方法 | 路径 | 权限 |
|---|---|---|
| GET | /admin/custom-models/page?auditStatus&modelType&keyword | admin:custom:audit |
| POST | /admin/custom-models/audit | {id,pass:boolean,remark}；通过→audit_status=1，驳回→2；记审计 |
| PUT | /admin/custom-models/quota | {id,quotaLimit(int|null)} |
| GET | /admin/custom-voices/page、POST /admin/custom-voices/audit | 同构 |

**加密规范**：AES-256-GCM，密钥从配置 `security.user-module.api-key-secret`（application.yml 默认值 `xzh-user-module-aes-key-2026-CHANGE-ME`，部署时外置 yml 覆盖）。存储格式 `base64(iv[12] + ciphertext+tag)`，工具类 `yuhe.common.utils.AesGcmUtils`（encrypt/decrypt/mask 三静态方法）。

### 4.5 审计（audit agent）
| 方法 | 路径 | 权限 |
|---|---|---|
| GET | /admin/audit/page?userId&module&operation&startDate&endDate&page&limit | admin:audit:list |
| GET | /admin/audit/modules | admin:audit:list | 去重 module 列表（筛选用） |

`AuditService` 接口（**user-mgmt 与 custom agent 按此签名调用，audit agent 实现**）：
```java
public interface AuditService {
    /** 异步落审计；当前用户/请求上下文由实现方自行获取，params 会做脱敏（password/apiKey 字段移除） */
    void log(String module, String operation, String targetType, String targetId, Object params, boolean success, String errorMsg);
}
```
埋点要求（各 agent 在自己的接口里调 log）：
- user-mgmt：login/logout、user create/delete(软)/restore/disable/enable/resetPwd/assignRoles/import/export/forceLogout（module=user）
- rbac：role save/update/delete（module=role）
- custom：custom model/voice create/update/delete/audit（module=custom）
- audit agent 自身：RenExceptionHandler 捕获 UnauthorizedException 时 log(module=security, operation=forbidden, success=false)，再返回 403
- LogOperationAspect：处理已有 @LogOperation 注解（若注解属性不足则新增 module 属性），作为兜底通用埋点

## 5. 文件归属矩阵（并行冲突防护——严禁越界改他人文件）

| Agent | 独占文件（可新建/修改） |
|---|---|
| foundation | db/changelog/202610140100.sql、202610140200.sql、db.changelog-master.yaml（仅追加）、ErrorCode.java（仅追加常量）、i18n/messages*.properties（仅追加）、SysUserEntity.java（加 deleted/locked/lastLoginDate/mustChangePwd/pwdUpdateDate/deletedDate 字段）、common/utils/AesGcmUtils.java（新）、application.yml（加 security.user-module 段） |
| rbac | 新建 sys/{SysRoleEntity,SysUserRoleEntity,SysRoleDao,SysUserRoleDao,SysRoleDTO,SysRoleVO,UserDetailVO?}.java、sys/service/{SysRoleService,+Impl}、sys/controller/SysRoleController.java、mapper/sys/{SysRoleDao,SysUserRoleDao}.xml、security/oauth2/Oauth2Realm.java（改造）、common/user/UserDetail.java（加 roles 字段）、security/user/SecurityUser.java（如需） |
| user-mgmt | sys/controller/AdminController.java、sys/service/SysUserService.java + Impl、sys/dto/*（用户相关新建）、sys/vo/AdminPageUserVO.java、security/controller/LoginController.java、security/dto 或 common/page/TokenDTO.java、security/service/SysUserTokenService(+Impl 如需 forceLogout 查询) |
| display-default | 新建 sys/{SysDisplayConfigEntity,SysUserDefaultEntity,...Dao/DTO/VO/Service/Impl}、sys/controller/{SysDisplayConfigController,SysUserDefaultController,UserResourceController}.java、对应 mapper xml |
| custom | 新建 sys/{SysUserCustomModelEntity,SysUserCustomVoiceEntity,...}、sys/controller/{UserCustomModelController,UserCustomVoiceController,AdminCustomModelController,AdminCustomVoiceController}.java、service/impl |
| audit | 新建 sys/{SysAuditLogEntity,SysAuditLogDao,SysAuditLogDTO,SysAuditLogVO,SysAuditLogService,+Impl}、sys/controller/SysAuditLogController.java、common/aspect/LogOperationAspect.java、common/exception/RenExceptionHandler.java（加审计调用）、common/annotation/LogOperation.java（如需加属性） |
| fe-integration | api.js、main.js、DockNav.vue、TopBar.vue（**只做注册，不写页面**） |
| fe-users | views/admin/Users.vue（改造） |
| fe-roles-audit | views/admin/Roles.vue、AuditLog.vue（新建） |
| fe-config-pages | views/admin/DisplayConfig.vue、UserDefaults.vue、CustomReview.vue（新建） |
| fe-customer | views/customer/Profile.vue、MyModels.vue（新建）、Home.vue/Voices.vue（空状态改造）、Login.vue/App.vue（强制改密弹窗，App.vue 仅加全局弹窗组件挂载） |
| build-deploy | 服务器操作（scp/mvn/重启/nginx），不改源码 |

公共纪律：所有新 Java 文件遵循 recon-backend.md §4 七文件模板；所有新前端页面遵循 recon-frontend.md §3 骨架。

## 6. 前端 api.js 方法名契约（fe-integration 与各页面 agent 逐字对齐）

```js
// adminApi 追加：
rolePage:(p)=>api.get('/admin/role/page',p), roleList:()=>api.get('/admin/role/list'),
roleDetail:(id)=>api.get(`/admin/role/${id}`), roleSave:(b)=>api.post('/admin/role/save',b),
roleUpdate:(b)=>api.put('/admin/role/update',b), roleDelete:(ids)=>api.post('/admin/role/delete',ids),
userCreate:(b)=>api.post('/admin/users',b), userDetail:(id)=>api.get(`/admin/users/${id}`),
userAssignRoles:(b)=>api.put('/admin/users/roles',b), userRestore:(id)=>api.put(`/admin/users/restore/${id}`),
userImport:(list)=>api.post('/admin/users/import',list),
userExportUrl:(p)=>`/yuhe/admin/users/export?${new URLSearchParams(p)}`,
userSessions:(p)=>api.get('/admin/users/sessions',p), userForceLogout:(id)=>api.post(`/admin/users/forceLogout/${id}`,{}),
displayConfigGet:(p)=>api.get('/admin/display-config',p), displayConfigSave:(b)=>api.put('/admin/display-config',b),
userDefaultGet:(p)=>api.get('/admin/user-default',p), userDefaultSave:(b)=>api.put('/admin/user-default',b),
customModelAuditPage:(p)=>api.get('/admin/custom-models/page',p),
customModelAudit:(b)=>api.post('/admin/custom-models/audit',b),
customModelQuota:(b)=>api.put('/admin/custom-models/quota',b),
customVoiceAuditPage:(p)=>api.get('/admin/custom-voices/page',p),
customVoiceAudit:(b)=>api.post('/admin/custom-voices/audit',b),
auditPage:(p)=>api.get('/admin/audit/page',p), auditModules:()=>api.get('/admin/audit/modules'),
// userApi 新导出组（api.js export const userApi = {...}）：
myResources:()=>api.get('/user/resources'), myDisplayConfig:()=>api.get('/user/display-config'),
myDefaults:()=>api.get('/user/defaults'),
customModelPage:(p)=>api.get('/user/custom-models',p), customModelCreate:(b)=>api.post('/user/custom-models',b),
customModelUpdate:(id,b)=>api.put(`/user/custom-models/${id}`,b), customModelDelete:(id)=>api.del(`/user/custom-models/${id}`),
customModelHealth:(id)=>api.post(`/user/custom-models/${id}/health`,{}),
customVoicePage:(p)=>api.get('/user/custom-voices',p), customVoiceCreate:(b)=>api.post('/user/custom-voices',b),
customVoiceUpdate:(id,b)=>api.put(`/user/custom-voices/${id}`,b), customVoiceDelete:(id)=>api.del(`/user/custom-voices/${id}`),
```

路由/菜单注册（fe-integration 执行）：
- main.js：/admin/roles→Roles、/admin/audit→AuditLog、/admin/display→DisplayConfig、/admin/defaults→UserDefaults、/admin/custom-review→CustomReview、/customer/profile→Profile、/customer/my-models→MyModels
- DockNav adminItems 追加：🎭 角色 /admin/roles、📜 审计 /admin/audit、🖼 展示配置 /admin/display、🎯 默认配置 /admin/defaults、✅ 自定义审核 /admin/custom-review
- DockNav customerItems 追加：👤 个人中心 /customer/profile、🧩 我的模型 /customer/my-models（TopBar adminNav/customerNav 同步）
- 路由守卫强化：/admin/** 需 userInfo.roles 含 admin 系角色或 superAdmin（roles 为空数组时视为普通用户，跳 /customer 并 toast）；meta 不引入，直接在守卫里判断 path

## 7. 用户端关键交互定稿

- **模型为 0**：所有模型选择 UI 先调 userApi.myResources()；llmModels.length===0 → 隐藏 select、显示 .empty-state「暂无可用模型，请联系管理员或前往我的模型添加」；ttsVoices 同理
- **强制改密**：Login 成功后 res.data.mustChangePwd===true 或 /user/info mustChangePwd → App.vue 全局弹窗（旧密码+新密码+确认），调 PUT /user/change-password；成功后 mustChangePwd=false；期间遮罩不可关闭
- **不可切回管理端**：DockNav 的 ⇄ 切换按钮在 role=customer 且无 admin 权限时隐藏（判断 userInfo.roles）；路由守卫兜底；后端 403 兜底
- **用量展示**：Profile 页展示自定义模型 usedCount/quotaLimit（P1 范围，平台级 token 用量不在本期）

## 8. 里程碑与验收挂钩

| 验收清单项 | 负责实现 | 验证方式 |
|---|---|---|
| 管理员添加/禁用/删除(软)/恢复用户 | user-mgmt | API + 浏览器 |
| 修改权限等级（角色分配） | rbac+user-mgmt | API |
| 权限变更实时生效 | rbac（无缓存） | 改角色后立即 403/放行 |
| 配置展示项 | display-default+fe-config | 浏览器 |
| 配置默认 LLM/音色 | display-default+fe-config | API |
| 模型 0 用户端不展示 | display-default(/user/resources)+fe-customer | 前端 |
| 用户端无法切回管理端 | fe-integration 守卫+后端 403 | 浏览器 |
| 越权 403 | 既有机制+audit 记录 | API |
| 用户自定义 LLM/音色 | custom+fe-customer | API+浏览器 |
| 审核/加密/配额 | custom | DB 查密文+掩码断言 |
| 敏感操作审计 | audit | 查 sys_audit_log |
| 空状态/错误提示 | 各前端页 | 浏览器 |
