# manager-api 后端骨架侦察报告（用户管理模块落点）

- 侦察人: recon-backend
- 日期: 2026-10-14
- 性质: **只读侦察**，未修改本地镜像与服务器任何文件
- 本地镜像: `G:/demo/21_xiaozhi/code-server-mirror/manager-api`
- 服务器: `ssh -p 22223 root@sandyun.top:/root/yh/app/manager-api`（MySQL: `xiaozhi_esp32_server` @127.0.0.1:3306）

---

## 1. 用户域现状（sys_user）

### 1.1 Entity
`G:/demo/21_xiaozhi/code-server-mirror/manager-api/src/main/java/xiaozhi/modules/sys/entity/SysUserEntity.java`

```java
@TableName("sys_user")            // 无逻辑删除字段（无 @TableLogic）
public class SysUserEntity extends BaseEntity {   // BaseEntity: @TableId Long id; creator; createDate
    private String username;       // 登录名，数据库唯一索引
    private String password;       // BCrypt 密文
    private Integer superAdmin;    // 1=超级管理员 0=普通
    private Integer status;        // 0=停用 1=正常
    @TableField(fill = FieldFill.INSERT_UPDATE)
    private Long updater;
    @TableField(fill = FieldFill.INSERT_UPDATE)
    private Date updateDate;
}
```
结论: **sys_user 没有 deleted 字段，删除=物理删除**；状态语义 `status: 0=停用, 1=正常`；密码使用 BCrypt（见 2.4）。

### 1.2 Dao / Service
- Dao: `.../modules/sys/dao/SysUserDao.java` — `@Mapper interface SysUserDao extends BaseDao<SysUserEntity>`，**空接口**（BaseDao extends BaseMapper）。
- Service 接口: `.../modules/sys/service/SysUserService.java`
  ```java
  SysUserEntity getByUsername(String username);
  SysUserEntity getByUserId(Long userId);
  void save(SysUserDTO dto);
  void deleteById(Long id);
  void changePassword(Long userId, PasswordDTO dto);
  String resetPassword(Long userId);
  String changePasswordDirectly(Long userId, String password);
  PageData<AdminPageUserVO> page(AdminPageUserDTO dto);
  void changeStatus(Integer status, String[] userIds);
  boolean getAllowUserRegister();
  ```
- Impl: `.../modules/sys/service/impl/SysUserServiceImpl.java`
  ```java
  98  @Override
  99  @Transactional(rollbackFor = Exception.class)
 100  public void deleteById(Long id) {
 101      // 检查是否删除自己
 102      if (SecurityUser.getUserId().equals(id)) { throw new RenException(ErrorCode.DEL_MYSELF_ERROR); }
 103      baseDao.deleteById(id);                            // 物理删除
 104      deviceService.deleteByUserId(id);                  // 级联物理删除用户设备
 105      agentService.deleteAgentByUserId(id);              // 级联物理删除用户智能体
 106  }
  ```
  ```java
  72-94  save(): 强密码正则 ^(?=.*[0-9])(?=.*[a-z])(?=.*[A-Z]).+$
        password = PasswordUtils.encode(...)   // BCrypt
        第一个用户(count==0) superAdmin=1，否则 0；status=1
 160-180 page(): baseDao.selectPage + getPageData；username 列 like dto.getMobile()；
        默认按 id asc；组装 AdminPageUserVO（含每用户 deviceCount）
 229-236 changeStatus(): 按 String[] userIds 循环 updateById 改 status
 239+    resetPassword(): 生成12位随机密码(数字+大小写+特殊字符, 洗牌)
  ```
  关键结论: **删除是硬删除**；`changeStatus` 目前**没有保护**：允许禁用自己、允许禁用最后一个超级管理员（无 status=0 时的自检）；`AdminPageUserDTO.getMobile()` 是历史字段名，实际当 username 关键字用。

### 1.3 DTO / VO
- `.../modules/sys/dto/SysUserDTO.java`: 含大量 renren 模板遗留字段（realName/headUrl/gender/email/mobile/deptId/roleIdList/postIdList/deptName）——**sys_user 表没有这些列**，实际 save 只取 username/password。password 标注 `@JsonProperty(access = WRITE_ONLY)`。**新模块应新建精简 DTO，勿复用此 DTO**。
- `.../modules/sys/dto/AdminPageUserDTO.java`: page/limit/mobile。
- `.../modules/sys/vo/AdminPageUserVO.java`: id/username/status(String userId)/deviceCount/mobile/createDate。
- 服务端删除接口：`AdminController` `DELETE /admin/users/{id}` → `sysUserService.deleteById(id)`；改状态 `PUT /admin/users/changeStatus/{status}` body=`String[] userIds`；重置密码 `PUT /admin/users/{id}` 返回 `Result<String>`（data=新密码）。全部 `@RequiresPermissions("sys:role:superAdmin")`。

---

## 2. 鉴权链（Shiro + Token）

### 2.1 过滤器链
`.../modules/security/config/ShiroConfig.java`（本地版行号；服务器版多一行 `/memory/** → oauth2`，见 §9）

```java
filterMap.put("/user/login", "anon");           // 登录、注册、验证码等 anon
filterMap.put("/user/captcha", "anon");
filterMap.put("/user/register", "anon");
filterMap.put("/user/pub-config", "anon");
filterMap.put("/user/smsVerification", "anon");
filterMap.put("/user/retrieve-password", "anon");
filterMap.put("/ota/**", "anon");
filterMap.put("/doc.html", "anon");  filterMap.put("/swagger/**", "anon");  filterMap.put("/webjars/**", "anon");
filterMap.put("/config/**", "server");          // ServerSecretFilter: 设备密钥鉴权
filterMap.put("/device/address-book/call", "server");
filterMap.put("/agent/chat-history/report", "server");
filterMap.put("/agent/chat-summary/**", "server");
filterMap.put("/agent/chat-title/**", "server");
filterMap.put("/**", "oauth2");                 // 其余全部走 Bearer Token
```
同时注册 `AuthorizationAttributeSourceAdvisor`，使 `@RequiresPermissions` 注解生效。

### 2.2 Token 生命周期
`.../modules/security/service/impl/SysUserTokenServiceImpl.java`
```java
private final static int EXPIRE = 3600 * 12;   // 【本地】12小时
// 服务器现网版本: 3600 * 24  （不一致点，见 §9）
public Result<TokenDTO> createToken(Long userId) {
    // 已存在未过期 token → 复用；否则生成新 token 并落库 sys_user_token
}
public SysUserTokenEntity getUserByToken(String token) {
    // token 不存在或已过期 → RenException(ErrorCode.TOKEN_INVALID=10021) / UNAUTHORIZED=401
}
public void logout(String token) {
    // update sys_user_token set expire_date = now() - 1分钟
}
```
- Token 生成: `.../modules/security/oauth2/TokenGenerator.java` — `MD5(UUID随机字节)` hex。
- 表 `sys_user_token`: id/userId/token/expireDate/updateDate/createDate。每次登录复用未过期 token（**滑动续期**：createToken 时若未过期复用、过期重发）。

### 2.3 Realm 权限加载（RBAC 关键落点）
`.../modules/security/oauth2/Oauth2Realm.java`

```java
54  @Override
55  protected AuthorizationInfo doGetAuthorizationInfo(PrincipalCollection principals) {
56      UserDetail user = (UserDetail) principals.getPrimaryPrincipal();
57      Set<String> permsSet = new HashSet<>();
59      // 权限来自 sys_user.super_admin 字段，硬编码，不是从数据库表加载！
60      if (user.getSuperAdmin() == SuperAdminEnum.YES.value()) {
61          permsSet.add("sys:role:superAdmin");
62          permsSet.add("sys:role:normal");
63      } else {
64          permsSet.add("sys:role:normal");
65      }
66      SimpleAuthorizationInfo info = new SimpleAuthorizationInfo();
67      info.setStringPermissions(permsSet);
68      return info;
69  }
```
```java
doGetAuthenticationInfo: token 过期→IncorrectCredentialsException(401)
   user.status == null → DisabledAccountException(ErrorCode 10005)
   user.status == 0    → LockedAccountException(ErrorCode.ACCOUNT_LOCK=10022)
```
**RBAC 结论**: 项目**没有** sys_role / sys_menu / sys_user_role / sys_role_menu 表，权限只有两个硬编码字符串 `sys:role:superAdmin` / `sys:role:normal`。做 RBAC 有三个可选落点：
1. 最小侵入: 保留两档，扩展成「超级管理员 / 普通用户」角色管理（改 superAdmin 开关）。
2. 中等: 在 `doGetAuthorizationInfo` 里增加从新表（如 sys_user_role → sys_role → sys_role_permission）加载 permsSet 的分支，同时保留 superAdmin 兜底。
3. 完整: 新建 sys_role/sys_permission 表 + ShiroServiceImpl 缓存，改造 Realm 查询。
所有 `@RequiresPermissions("sys:role:superAdmin")` 注解点即现有权限锚点（AdminController 全部接口、SysParamsController、ServerSideManageController 等）。

### 2.4 密码与过滤器异常
- `.../modules/security/password/PasswordUtils.java`: `encode`/`matches` 封装 `BCryptPasswordEncoder`（Spring Security Crypto）。
- `.../modules/security/oauth2/Oauth2Filter.java`: 从 `Authorization: Bearer <token>` 取 token；缺失/失败时**直接向 Response 写 JSON**：
  ```java
  response.setContentType("application/json;charset=utf-8");
  response.getWriter().print(JsonUtils.toJsonString(new Result<Void>().error(ErrorCode.UNAUTHORIZED)));
  ```
  即返回体 `{"code":401,"msg":"...","data":null}`，**HTTP 状态码仍是 200**（未调用 setStatus）。带 CORS 头。OPTIONS 预检放行。
- `.../common/exception/RenExceptionHandler.java` (@RestControllerAdvice):
  - `RenException` → `Result.error(错误码)`，HTTP 200（**业务错误码进 body**）
  - `UnauthorizedException`（无权限）→ `Result.error(ErrorCode.FORBIDDEN=403)`，HTTP 200
  - `NoResourceFoundException` → 404
  - `MethodArgumentNotValidException`（@Valid 校验失败）→ 10034 + 第一条 i18n 消息
  - 兜底 `Exception` → `INTERNAL_SERVER_ERROR=500`
- 全局错误码: `.../common/exception/ErrorCode.java`，5 位数字，**已用最大 10219**（WAKE_WORD_INVALID_CHAR）。用户相关现成码: ACCOUNT_PASSWORD_ERROR=10004, TOKEN_INVALID=10021, ACCOUNT_LOCK=10022, PASSWORD_WEAK_ERROR=10031, DEL_MYSELF_ERROR=10032, OLD_PASSWORD_ERROR=10048, FORBIDDEN=403, UNAUTHORIZED=401。**新模块错误码从 10220 起**，并同步在 `resources/i18n/messages.properties` + `messages_zh_CN/en_US/vi_VN/de_DE/pt_BR/zh_TW` 加条目（`{code}={文本}`，\u 转义）。

---

## 3. 公共设施

- `G:/demo/21_xiaozhi/code-server-mirror/manager-api/src/main/java/xiaozhi/common/utils/Result.java`
  ```java
  public class Result<T> { private int code = 0; private String msg = "success"; private T data; }
  // new Result<T>().ok(data) / .error(ErrorCode) / .error(int code, String msg)
  ```
- `.../common/page/PageData.java`: `{int total; List<T> list;}`；`new PageData<>(list, total)`。
- `.../common/page/TokenDTO.java`: `{token, expire, clientHash}`（登录返回）。
- `.../common/constant/Constant.java`: `PAGE="page" LIMIT="limit" ORDER_FIELD="orderField" ORDER="order"`，`AUTHORIZATION="Authorization"`，enums（SysBaseParam/SysMSMParam/DataOperation/DictType），`VERSION="0.9.7"`。
- `.../common/user/UserDetail.java`: `{id, username, superAdmin, token, status}` —— `/user/info` 返回此结构。
- `.../modules/security/user/SecurityUser.java`: 静态 `getUser()/getUserId()/getToken()`（`SecurityUtils.getSubject().getPrincipal()`），服务层拿当前用户的标准入口。
- `.../common/utils/ConvertUtils.java`: `sourceToTarget(Object source, Class<T> target)`（BeanUtils 封装），实体↔DTO/VO 互转标准工具。
- 校验: `.../common/validator/ValidatorUtils.java`（`validateEntity(obj, groups...)`）；分组 `.../common/validator/group/{AddGroup,UpdateGroup,DefaultGroup}.java`；i18n 校验消息 `resources/i18n/validation*.properties`（键如 `{id.null}`/`{username.notBlank}`）。
- 审计现状: `.../common/annotation/LogOperation.java` **存在但没有任何 Aspect 处理**（common/aspect 下只有 RedisAspect）→ **现有审计日志基础设施为零，审计模块需从零建**（建表 + Aspect + 注解埋点）。

---

## 4. 标准 CRUD 模块模板（照抄模式）

最标准的模板是字典类型模块（其余模块同构）：

| 层 | 文件 | 要点 |
|---|---|---|
| Entity | `modules/sys/entity/SysDictTypeEntity.java` | @TableName + 继承 BaseEntity |
| Dao | `modules/sys/dao/SysDictTypeDao.java` | `@Mapper extends BaseDao<T>`，空 |
| DTO | `modules/sys/dto/SysDictTypeDTO.java` | 校验分组：id 上 `@Null(groups=AddGroup)` + `@NotNull(groups=UpdateGroup)`；日期 `@JsonProperty(access=READ_ONLY)` + `@JsonFormat` |
| VO | `modules/sys/vo/SysDictTypeVO.java` | 含 creatorName/updaterName 显示字段 |
| Service | `modules/sys/service/SysDictTypeService.java` | `extends CrudService<Dao, Entity, DTO>` |
| Impl | `modules/sys/service/impl/SysDictTypeServiceImpl.java` | `extends CrudServiceImpl<...>`，实现抽象 `QueryWrapper<T> getWrapper(Map params)` |
| Controller | `modules/sys/controller/SysDictTypeController.java` | `@RequestMapping("/admin/dict/type")`；GET `/page`（Map params）、GET `/{id}`、POST `/save`、PUT `/update`、POST `/delete`（body=Long[]）|
| Mapper XML | `resources/mapper/sys/SysDictTypeDao.xml` | **只有 namespace 的空 XML**（纯 MP 无自定义 SQL）|

Impl 关键代码（`SysDictTypeServiceImpl.java`）：
```java
public PageData<SysDictTypeVO> page(Map<String, Object> params) {
    IPage<SysDictTypeEntity> page = baseDao.selectPage(
        getPage(params, "sort", true),        // 默认按 sort 升序
        getWrapper(params));
    // 批查 creator/updater 的 username 组装 creatorName/updaterName
    return getPageData(page, SysDictTypeVO.class);
}
public void delete(Long[] ids) {
    // 先删除子表 sys_dict_data，再 deleteBatchIds —— 级联删除模板
}
```
- 分页参数约定: `page`/`limit`/`orderField`/`order`（Constant 常量）；`getPage()` 带**默认排序字段+方向**参数。
- Mapper XML 规律: 默认放空 XML 只用 MP；需要自定义 SQL 才写（对照 `resources/mapper/security/SysUserTokenDao.xml` 的 getByToken/getByUserId/logout，或 `mapper/device/DeviceDao.xml`）。

---

## 5. Liquibase 变更集格式

- 主文件: `G:/demo/21_xiaozhi/code-server-mirror/manager-api/src/main/resources/db/changelog/db.changelog-master.yaml`
- SQL 目录: `src/main/resources/db/changelog/`（**最新本地样本**: `202610101100.sql`，author=backend-java）

格式模板（每个 SQL 一个 changeSet，id=文件名时间戳 `YYYYMMDDHHMM`）：
```yaml
  - changeSet:
      id: 202610101100
      author: backend-java
      changes:
        - sqlFile:
            encoding: utf8
            path: classpath:db/changelog/202610101100.sql
```
- **幂等保护模式**（现网表曾被手工 ALTER 过时用，新表不用）——`202610090130` 的写法：
```yaml
  - changeSet:
      id: 202610090130
      author: team-lead
      preConditions:
        onFail: MARK_RAN
        onError: MARK_RAN
        not:
          columnExists:
            tableName: ai_tts_voice
            columnName: dynamic_instruction
      changes:
        - sqlFile:
            encoding: utf8
            path: classpath:db/changelog/202610090130.sql
```
- SQL 风格（`202610101100.sql` 全文）：
```sql
CREATE TABLE IF NOT EXISTS ai_agent_wake_word (
    id VARCHAR(32) PRIMARY KEY COMMENT '主键ID',
    agent_id VARCHAR(32) NOT NULL,
    wake_words JSON,
    creator BIGINT, create_date DATETIME,
    updater BIGINT, update_date DATETIME,
    UNIQUE KEY uk_agent_id (agent_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='智能体唤醒词';
```
- **服务器 DATABASECHANGELOG 实况**（2026-10-14 查询）: 最后应用 = `202610101100` (backend-java, EXECUTED 2026-10-10 01:55)，之前 `202610101030`、`202610100930` EXECUTED，`202610090130` MARK_RAN。**新模块 SQL 用时间戳 > 202610101100**。

---

## 6. MyBatis-Plus 配置

- `.../common/config/MybatisPlusConfig.java`: 拦截器顺序 = `DataFilterInterceptor`（@DataFilter 数据权限）→ `PaginationInnerInterceptor`（分页插件，DbType.MYSQL）→ `OptimisticLockerInnerInterceptor` → `BlockAttackInnerInterceptor`（全表更新/删除拦截）。
- 自动填充: `.../common/handler/FieldMetaObjectHandler.java`
  - insert: creator、createDate（+ 别名 createdAt）、updater、updateDate、dataOperation("I")
  - update: updater、updateDate、dataOperation("U")
  - 实体字段需配 `@TableField(fill = FieldFill.INSERT / INSERT_UPDATE)` 才生效。
- 结论: **框架是 MyBatis-Plus**（BaseMapper/LambdaQueryWrapper），不是原生 MyBatis；pagination 用 MP 分页插件；自动填充走 FieldMetaObjectHandler；`application.yml`: `mybatis-plus.mapper-locations=classpath*:/mapper/**/*.xml`、`typeAliasesPackage=xiaozhi.modules.*.entity`、`id-type: ASSIGN_ID`（雪花，实体 id 用 Long 或 String 均可，如 wake_word 表是 VARCHAR(32)）。

---

## 7. 登录与用户信息接口（现有行为基准）

`G:/demo/21_xiaozhi/code-server-mirror/manager-api/src/main/java/xiaozhi/modules/security/controller/LoginController.java`（`@RequestMapping("/user")`）

| 接口 | 方法/路径 | 入参 | 返回 |
|---|---|---|---|
| 登录 | `POST /user/login` | `{username, password, captcha, uuid}`（password 为 **SM2 加密**，服务端 `Sm2DecryptUtil.decryptAndValidateCaptcha` 先解密再验验证码）| `Result<TokenDTO>` = `{"code":0,"data":{"token":"<md5hex>","expire":43200,"clientHash":...}}` |
| 用户信息 | `GET /user/info` | Bearer token | `Result<UserDetail>` = `{id, username, superAdmin, token, status}` |
| 验证码 | `GET /user/captcha?uuid=xxx` | uuid | 图片流（服务端存 Redis）|
| 注册 | `POST /user/register` | — | Result |
| 修改密码 | `POST /user/change-password` | PasswordDTO | Result |
| 找回密码 | `POST /user/retrieve-password` | RetrievePasswordDTO（短信验证码）| Result |
| 公开配置 | `GET /user/pub-config` | — | SM2 公钥、菜单、版本号 0.9.7 |

- 验证码 Redis key（`.../common/redis/RedisKeys.java` + `.../modules/security/service/impl/CaptchaServiceImpl.java`）:
  - 图形验证码: `sys:captcha:{uuid}`，TTL 300s（SpecCaptcha 150x40 长度5；`renren.redis.open=false` 时降级 Guava localCache）
  - 短信: `sms:Validate:Code:{phone}`、`sms:Validate:Code:{phone}:last_send_time`、`sms:Validate:Code:{phone}:today_count`（60s 发送间隔，每日上限 `server.sms_max_send_count` 默认 5）
- 注意: 服务端真实 EXPIRE=24h（见 §9 差异）。

---

## 8. 默认模型 / 音色实体（默认模型关联落点）

- `G:/demo/21_xiaozhi/code-server-mirror/manager-api/src/main/java/xiaozhi/modules/model/entity/ModelConfigEntity.java`
  - 表 `ai_model_config`: String id；`modelType`（Memory/ASR/VAD/LLM/TTS）；`modelCode`；`modelName`；`isDefault`(0/1)；`isEnabled`；`configJson`（JSONObject + JacksonTypeHandler，@TableName(autoResultMap=true)）；docLink/remark/sort + 审计字段。
- `.../modules/model/service/ModelConfigService.java` 关键方法（默认模型联动直接用）:
  ```java
  void setDefaultModel(String modelType, int isDefault);
  List<ModelConfigEntity> getEnabledModelsByType(String modelType);
  ModelConfigEntity getModelByIdFromCache(String id);
  String getModelNameById(String id);
  int countConfigJsonLlmReference(String llmModelId);
  ```
- `G:/demo/21_xiaozhi/code-server-mirror/manager-api/src/main/java/xiaozhi/modules/timbre/entity/TimbreEntity.java`
  - 表 `ai_tts_voice`: String id；languages；name；remark；referenceAudio/referenceText；voiceInstruction；dynamicInstruction；instructionLlmId；sort（FieldStrategy.NOT_NULL）；ttsModelId；ttsVoice；voiceDemo + 审计字段。
- 「展示项配置/默认模型」建议落点: 新表如 `sys_user_display_config`/`sys_user_default_model`（user_id → model_type + model_id 或 timbre_id），Service 内调 `ModelConfigService.getModelByIdFromCache` 校验关联存在性；Redis key 命名跟随 `RedisKeys.java` 现有前缀风格（`model:name:`、`timbre:name:`）。

---

## 9. 本地镜像 vs 服务器一致性（MD5 结论）

### 9.1 抽查 4 文件（任务要求）

| 文件 | 本地 MD5 | 服务器 MD5 | 一致 |
|---|---|---|---|
| modules/sys/service/impl/SysUserServiceImpl.java | 36a3593efb3282e196839f817a3e2a30 | 36a3593efb3282e196839f817a3e2a30 | ✅ |
| modules/sys/entity/SysUserEntity.java | 10e88c500ceca15b992ad76114552c9b | 10e88c500ceca15b992ad76114552c9b | ✅ |
| modules/security/oauth2/Oauth2Realm.java | 47cb89e67311348540de6f198ea3856f | 47cb89e67311348540de6f198ea3856f | ✅ |
| modules/security/service/impl/SysUserTokenServiceImpl.java | c0f69479041ee7221d6e8c90ead71216 | 91a6642f0613016c4d7b421db0dd9b2d | ❌ |

差异唯一一行:
```java
- private final static int EXPIRE = 3600 * 12;   // 本地
+ private final static int EXPIRE = 3600 * 24;   // 服务器现网：token 有效期 24 小时
```

### 9.2 全量 src 树 MD5 比对（本地 533 vs 服务器 535 个源文件）

**内容级差异清单**（排除仅行尾 CRLF 差异的文件）：

| 文件 | 差异方向与内容 |
|---|---|
| `modules/security/service/impl/SysUserTokenServiceImpl.java` | 本地 EXPIRE=12h；**服务器=24h** |
| `modules/security/config/ShiroConfig.java` | 服务器多一行 `filterMap.put("/memory/**", "oauth2")` |
| `modules/sys/controller/PythonApiProxyController.java` | **仅服务器有**（本地缺失）|
| `modules/memory/controller/MemoryEntityController.java` | **仅服务器有**（本地缺失）|
| `modules/memory/controller/MemoryFactController.java` | 本地多了参数别名兼容（agentId/limit 回退 + size 默认 20）；服务器只有基础 @RequestParam |
| `modules/model/controller/LlmPreviewController.java` | 本地 POST 预览；服务器 GET |
| `modules/sys/controller/SysParamsController.java` | **本地多** `DELETE /admin/params/{id}`（内置参数保护+@LogOperation）；服务器无该接口 |
| `modules/sys/service/impl/SysParamsServiceImpl.java` | 本地多 deleteById/BUILTIN_PARAM_MAX_ID=1000/paramCode 唯一校验/paramType=1；服务器无 |
| `resources/i18n/messages*.properties` | 本地多 10205/10206/10207/10214~10219 键（唤醒词、参数错误码）；服务器只有到 10204 |
| `resources/db/changelog/db.changelog-master.yaml` | **本地多 3 个 changeSet**: 202610090130(team-lead, MARK_RAN 幂等)、202610101030(team-lead)、202610101100(backend-java) |
| `common/config/SwaggerConfig.java` | 仅文案：本地"屿禾工坊管理服务"，服务器"xiaozhi-esp32-manager-api" |
| `agent/controller/AgentChatHistoryController.java`、`agent/dto/AgentChatHistoryReportDTO.java` | 仅注释/Schema 文案（"设备"↔"小智"） |

服务器文件 mtime 佐证: ShiroConfig 2026-10-12 20:57、SysUserTokenServiceImpl 10-12 03:15、PythonApiProxyController 10-12 21:03、MemoryEntityController 10-12 00:18、db.changelog-master.yaml 10-10 20:34。服务器目录**无 git 仓库**（git log 空）。本地镜像 git 状态干净（工作区改动均在 manager-api 仓库之外）。

**MD5 一致性总结论**:
1. 用户域与鉴权核心（SysUserEntity/SysUserServiceImpl/Oauth2Realm）**双方一致**，§1/§2 结论对现网有效。
2. **本地不是服务器的精确镜像**：本地包含 10-09/10-10 的 3 个已上线 changeSet（服务器 DATABASECHANGELOG 证实全部已应用，但其磁盘 yaml 已回退），服务器在 10-12 打过 4 个热修复（token 24h、/memory/** 路由、2 个新控制器），本地均未吸收。
3. **对用户模块扩展的影响**：新增 changeSet 必须**双端同步**（服务器 yaml 落后于数据库，直接基于服务器 yaml 追加会撞上 DB 中已执行的 202610101100）；写代码前应先把本地 3 个 changeSet 与服务器热修复合并进统一基线，或明确以哪端为准。新模块 SQL 时间戳取 > 202610101100。

---

## 10. 用户管理模块落点方案（建议包路径 + 文件清单模板）

### 10.1 包路径（沿用现有分层，全部在 `src/main/java/xiaozhi/modules/sys/` 下）

```
modules/sys/
├── entity/UserRoleEntity.java            # 可选（若做多角色 RBAC）表 sys_user_role
├── entity/SysRoleEntity.java             # 可选 表 sys_role
├── entity/SysAuditLogEntity.java         # 审计 表 sys_audit_log
├── entity/SysUserDisplayConfigEntity.java# 展示项配置 表 sys_user_display_config
├── entity/SysUserDefaultModelEntity.java # 默认模型 表 sys_user_default_model（关联 ai_model_config.id / ai_tts_voice.id）
├── dao/UserRoleDao.java / SysRoleDao.java / SysAuditLogDao.java / ...
├── dto/SysRoleDTO.java / SysAuditLogDTO.java / SysUserDisplayConfigDTO.java / ...
├── vo/SysRoleVO.java / SysAuditLogVO.java / ...
├── service/SysRoleService.java / SysAuditLogService.java / ...
├── service/impl/SysRoleServiceImpl.java / SysAuditLogServiceImpl.java / ...
└── controller/SysRoleController.java / SysAuditLogController.java / ...
resources/
├── mapper/sys/SysRoleDao.xml          # 空 XML（纯 MP）或自定义 SQL
├── db/changelog/20261014XXXX.sql      # 新表 DDL，id 时间戳 > 202610101100
└── db/changelog/db.changelog-master.yaml  # 末尾追加 changeSet
```

### 10.2 每模块标准文件清单（以 SysRole 为例，7 文件模板）
1. `entity/SysRoleEntity.java` — @TableName("sys_role") 继承 BaseEntity
2. `dao/SysRoleDao.java` — `@Mapper interface SysRoleDao extends BaseDao<SysRoleEntity>`
3. `dto/SysRoleDTO.java` — id @Null(AddGroup)+@NotNull(UpdateGroup)，@NotBlank 字段，日期 READ_ONLY
4. `vo/SysRoleVO.java` — 含 creatorName/updaterName
5. `service/SysRoleService.java` — extends `CrudService<SysRoleDao, SysRoleEntity, SysRoleDTO>`
6. `service/impl/SysRoleServiceImpl.java` — extends `CrudServiceImpl<...>` + `getWrapper(params)`
7. `controller/SysRoleController.java` — `@RequestMapping("/admin/role")` + `@RequiresPermissions("sys:role:superAdmin")`；GET /page、GET /{id}、POST /save、PUT /update、POST /delete(Long[])

### 10.3 关键改造点汇总
| 需求 | 落点 | 改造内容 |
|---|---|---|
| RBAC | `security/oauth2/Oauth2Realm.java` doGetAuthorizationInfo | 增加从 sys_user_role/sys_role/permission 表加载 permsSet 分支（保留 superAdmin 硬编码兜底）|
| 用户 CRUD 增强 | `modules/sys/`（AdminController 已有 /admin/users）| 删除需改软删（sys_user 加 deleted + @TableLogic）或保持硬删；补 changeStatus 防自禁/防禁用最后一个超管 |
| 展示项配置 | 新表 sys_user_display_config | 标准 CRUD + `/user/info` 或 pub-config 聚合返回 |
| 默认模型 | 新表 sys_user_default_model | Service 调 ModelConfigService.getModelByIdFromCache/getEnabledModelsByType 校验 |
| 审计 | **从零建** | 建 sys_audit_log 表 + 写 `@Aspect` 处理 @LogOperation（现有注解无 Aspect）+ 在 CUD 接口埋点 |
| 错误码 | ErrorCode.java + i18n/messages*.properties | 从 10220 起分配 |

### 10.4 删除/状态语义与鉴权异常格式（确切结论）
- **删除语义**: 现状=物理删除（sys_user 无 deleted 字段，deleteById 直接 baseDao.deleteById 并级联删设备/智能体）。若要保留审计与数据，需迁移为软删（加列 + @TableLogic + 修改级联逻辑）。
- **状态语义**: `status 0=停用 1=正常`；登录时 status=0 → HTTP 200 + `{"code":10022,"msg":"账号已被锁定"}`；status=null → code 10005。
- **鉴权异常返回格式**: 所有错误均 **HTTP 200** + body `{"code":<code>,"msg":"<i18n>","data":null}`：
  - 无 token / token 无效: code 401（Oauth2Filter 直写）
  - 无权限（@RequiresPermissions 拦截）: code 403（RenExceptionHandler）
  - 业务异常: 各自 5 位码；校验失败: 10034；未捕获: 500。

---

## 附录 A: 关键文件绝对路径速查

```
G:/demo/21_xiaozhi/code-server-mirror/manager-api/src/main/java/xiaozhi/
├── common/
│   ├── utils/Result.java / ConvertUtils.java
│   ├── page/PageData.java / TokenDTO.java
│   ├── constant/Constant.java
│   ├── exception/ErrorCode.java / RenException.java / RenExceptionHandler.java
│   ├── handler/FieldMetaObjectHandler.java
│   ├── config/MybatisPlusConfig.java
│   ├── annotation/LogOperation.java
│   ├── validator/ValidatorUtils.java + group/{AddGroup,UpdateGroup,DefaultGroup}.java
│   └── user/UserDetail.java
├── modules/
│   ├── sys/
│   │   ├── entity/SysUserEntity.java / SysDictTypeEntity.java / SysParamsEntity.java
│   │   ├── dao/SysUserDao.java / SysDictTypeDao.java
│   │   ├── dto/SysUserDTO.java / AdminPageUserDTO.java / SysDictTypeDTO.java
│   │   ├── vo/AdminPageUserVO.java / SysDictTypeVO.java
│   │   ├── service/{SysUserService,SysDictTypeService}.java
│   │   ├── service/impl/{SysUserServiceImpl,SysDictTypeServiceImpl}.java
│   │   └── controller/{AdminController,SysDictTypeController,SysParamsController}.java
│   ├── security/
│   │   ├── oauth2/{Oauth2Filter,Oauth2Realm,TokenGenerator}.java
│   │   ├── config/ShiroConfig.java
│   │   ├── controller/LoginController.java
│   │   ├── service/impl/{SysUserTokenServiceImpl,CaptchaServiceImpl}.java
│   │   ├── password/PasswordUtils.java
│   │   └── user/SecurityUser.java
│   ├── model/entity/ModelConfigEntity.java + service/ModelConfigService.java
│   └── timbre/entity/TimbreEntity.java
G:/demo/21_xiaozhi/code-server-mirror/manager-api/src/main/resources/
├── application.yml / application-dev.yml
├── mapper/sys/{SysUserDao,SysDictTypeDao}.xml / mapper/security/SysUserTokenDao.xml
├── db/changelog/db.changelog-master.yaml + 202610101100.sql
└── i18n/messages*.properties / validation*.properties
```

## 附录 B: 报告依据的实测命令

```bash
# 本地 md5
md5sum <4个抽查文件>
# 服务器 md5
ssh -p 22223 root@sandyun.top "md5sum /root/yh/app/manager-api/src/main/java/xiaozhi/..."
# 全树比对
ssh -p 22223 root@sandyun.top "cd /root/yh/app/manager-api && find src -type f \( -name '*.java' -o -name '*.xml' -o -name '*.yaml' -o -name '*.yml' -o -name '*.sql' -o -name '*.properties' \) -exec md5sum {} \; | sort -k2"
# DB 变更集实况
ssh -p 22223 root@sandyun.top "mysql -uroot -p123456 xiaozhi_esp32_server -N -e 'SELECT ID,AUTHOR,DATEEXECUTED,EXECTYPE FROM DATABASECHANGELOG ORDER BY ORDEREXECUTED DESC LIMIT 12;'"
```
