-- ============================================================
-- 背景：用户管理模块（建表 + 种子数据）
-- 新建 7 张表：sys_role / sys_user_role / sys_audit_log /
--   sys_display_config / sys_user_default /
--   sys_user_custom_model / sys_user_custom_voice
-- 并幂等写入 4 个内置角色（is_builtin=1）。
-- 约定：CREATE TABLE IF NOT EXISTS 幂等建表；
--   INSERT ... SELECT ... WHERE NOT EXISTS 幂等种子；
--   全部标识符反引号，显式 COLLATE utf8mb4_0900_ai_ci。
-- ============================================================

-- 1. 角色表（permissions 为 JSON 数组，内置角色用固定小整数 id）
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

-- 2. 用户-角色关联表
CREATE TABLE IF NOT EXISTS `sys_user_role` (
  `id`          BIGINT   NOT NULL COMMENT 'id（雪花ID）',
  `user_id`     BIGINT   NOT NULL COMMENT '用户ID（sys_user.id）',
  `role_id`     BIGINT   NOT NULL COMMENT '角色ID（sys_role.id）',
  `creator`     BIGINT   DEFAULT NULL COMMENT '创建者',
  `create_date` DATETIME DEFAULT NULL COMMENT '创建时间',
  `updater`     BIGINT   DEFAULT NULL COMMENT '更新者',
  `update_date` DATETIME DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_user_role` (`user_id`,`role_id`),
  KEY `idx_role_id` (`role_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='用户角色关联';

-- 3. 安全审计日志表（追加只写，不提供更新/删除接口）
CREATE TABLE IF NOT EXISTS `sys_audit_log` (
  `id`             BIGINT      NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `user_id`        BIGINT      DEFAULT NULL COMMENT '操作人ID（sys_user.id）',
  `username`       VARCHAR(50) DEFAULT NULL COMMENT '操作人用户名（冗余，防用户删除后不可读）',
  `module`         VARCHAR(50) DEFAULT NULL COMMENT '模块（如 user/role/model/voice）',
  `operation`      VARCHAR(50) DEFAULT NULL COMMENT '操作类型（如 login/logout/create/update/delete/disable/grant/import/export）',
  `target_type`    VARCHAR(50) DEFAULT NULL COMMENT '目标对象类型',
  `target_id`      VARCHAR(64) DEFAULT NULL COMMENT '目标对象ID',
  `request_uri`    VARCHAR(255) DEFAULT NULL COMMENT '请求URI',
  `request_method` VARCHAR(10) DEFAULT NULL COMMENT 'HTTP方法',
  `params`         JSON        DEFAULT NULL COMMENT '请求参数（脱敏后）',
  `result`         TINYINT     NOT NULL DEFAULT '1' COMMENT '结果（0失败 1成功）',
  `error_msg`      VARCHAR(500) DEFAULT NULL COMMENT '错误信息',
  `ip`             VARCHAR(50) DEFAULT NULL COMMENT '操作IP',
  `user_agent`     VARCHAR(500) DEFAULT NULL COMMENT 'UA',
  `duration`       INT         DEFAULT NULL COMMENT '耗时(ms)',
  `created_at`     DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间',
  PRIMARY KEY (`id`),
  KEY `idx_sys_audit_log_user_id` (`user_id`,`created_at`),
  KEY `idx_sys_audit_log_module_op` (`module`,`operation`),
  KEY `idx_sys_audit_log_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='安全审计日志（追加只写，不提供更新/删除接口）';

-- 4. 字段级展示配置表（系统→角色→用户三级覆盖，sentinel 0 占位）
CREATE TABLE IF NOT EXISTS `sys_display_config` (
  `id`          BIGINT       NOT NULL COMMENT 'id（雪花ID）',
  `scope_type`  TINYINT      NOT NULL COMMENT '作用域（0系统默认 1角色 2用户）',
  `role_id`     BIGINT       NOT NULL DEFAULT '0' COMMENT '角色ID（scope_type=1时有效，其余填0）',
  `user_id`     BIGINT       NOT NULL DEFAULT '0' COMMENT '用户ID（scope_type=2时有效，其余填0）',
  `config_json` JSON         NOT NULL COMMENT '展示配置 JSON，如 {"fields":{"llm_model":{"visible":true,"editable":false},"tts_voice":{...}}}',
  `creator`     BIGINT       DEFAULT NULL COMMENT '创建者',
  `create_date` DATETIME     DEFAULT NULL COMMENT '创建时间',
  `updater`     BIGINT       DEFAULT NULL COMMENT '更新者',
  `update_date` DATETIME     DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_scope` (`scope_type`,`role_id`,`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='展示项配置（系统→角色→用户三级覆盖）';

-- 5. 默认模型/音色/参数配置表（平台→角色→用户三级，冲突按 lock_policy）
CREATE TABLE IF NOT EXISTS `sys_user_default` (
  `id`           BIGINT       NOT NULL COMMENT 'id（雪花ID）',
  `scope_type`   TINYINT      NOT NULL COMMENT '作用域（0平台 1角色 2用户）',
  `role_id`      BIGINT       NOT NULL DEFAULT '0' COMMENT '角色ID（scope_type=1有效，其余0）',
  `user_id`      BIGINT       NOT NULL DEFAULT '0' COMMENT '用户ID（scope_type=2有效，其余0）',
  `llm_model_id` VARCHAR(32)  DEFAULT NULL COMMENT '默认LLM（ai_model_config.id）',
  `tts_model_id` VARCHAR(32)  DEFAULT NULL COMMENT '默认TTS模型（ai_model_config.id）',
  `tts_voice_id` VARCHAR(32)  DEFAULT NULL COMMENT '默认音色（ai_tts_voice.id）',
  `asr_model_id` VARCHAR(32)  DEFAULT NULL COMMENT '默认ASR（ai_model_config.id）',
  `param_json`   JSON         DEFAULT NULL COMMENT '参数模板（温度/TopP/语速等，如 {"temperature":0.7,"top_p":0.9}）',
  `lock_policy`  TINYINT      NOT NULL DEFAULT '0' COMMENT '冲突策略（0可被下级覆盖 1锁定）',
  `creator`      BIGINT       DEFAULT NULL COMMENT '创建者',
  `create_date`  DATETIME     DEFAULT NULL COMMENT '创建时间',
  `updater`      BIGINT       DEFAULT NULL COMMENT '更新者',
  `update_date`  DATETIME     DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_scope` (`scope_type`,`role_id`,`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='默认模型音色配置（平台→角色→用户三级，冲突按 lock_policy）';

-- 6. 用户自定义模型表（仅本人可见，密钥加密，审核后可用）
CREATE TABLE IF NOT EXISTS `sys_user_custom_model` (
  `id`             VARCHAR(32)  NOT NULL COMMENT '主键（UUID，与 ai_model_config.id 风格对齐）',
  `user_id`        BIGINT       NOT NULL COMMENT '所属用户ID（sys_user.id）',
  `model_type`     VARCHAR(20)  NOT NULL COMMENT '模型类型（LLM/ASR/TTS/VAD/Memory，统一大写）',
  `model_name`     VARCHAR(50)  NOT NULL COMMENT '模型名称',
  `provider_code`  VARCHAR(50)  DEFAULT NULL COMMENT '供应器编码（ai_model_provider.provider_code）',
  `config_json`    JSON         DEFAULT NULL COMMENT '模型配置（api_key 字段存密文，参考 provider.fields 定义）',
  `api_key_cipher` VARCHAR(500) DEFAULT NULL COMMENT 'API密钥密文（加密存储，接口永不明文返回）',
  `base_url`       VARCHAR(500) DEFAULT NULL COMMENT '接口地址',
  `audit_status`   TINYINT      NOT NULL DEFAULT '0' COMMENT '审核状态（0待审核 1通过 2驳回）',
  `audit_remark`   VARCHAR(255) DEFAULT NULL COMMENT '审核意见',
  `auditor`        BIGINT       DEFAULT NULL COMMENT '审核人',
  `audit_date`     DATETIME     DEFAULT NULL COMMENT '审核时间',
  `status`         TINYINT      NOT NULL DEFAULT '1' COMMENT '状态（0停用 1正常 2维护 3下线）',
  `health_status`  TINYINT      DEFAULT NULL COMMENT '健康检查（0未知 1正常 2异常）',
  `quota_limit`    INT          DEFAULT NULL COMMENT '调用配额（次/日，NULL不限）',
  `used_count`     BIGINT       NOT NULL DEFAULT '0' COMMENT '已用次数（统计冗余）',
  `remark`         VARCHAR(255) DEFAULT NULL COMMENT '备注',
  `sort`           INT UNSIGNED DEFAULT '0' COMMENT '排序',
  `creator`        BIGINT       DEFAULT NULL COMMENT '创建者',
  `create_date`    DATETIME     DEFAULT NULL COMMENT '创建时间',
  `updater`        BIGINT       DEFAULT NULL COMMENT '更新者',
  `update_date`    DATETIME     DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`),
  KEY `idx_ucm_user_type_status` (`user_id`,`model_type`,`status`,`audit_status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='用户自定义模型（仅本人可见，密钥加密，审核后可用）';

-- 7. 用户自定义音色表（仅本人可见，审核后可用）
CREATE TABLE IF NOT EXISTS `sys_user_custom_voice` (
  `id`              VARCHAR(32)  NOT NULL COMMENT '主键（UUID，与 ai_tts_voice.id 风格对齐）',
  `user_id`         BIGINT       NOT NULL COMMENT '所属用户ID（sys_user.id）',
  `name`            VARCHAR(64)  NOT NULL COMMENT '音色名称',
  `tts_model_id`    VARCHAR(32)  DEFAULT NULL COMMENT '对应TTS模型（ai_model_config.id）',
  `tts_voice`       VARCHAR(50)  DEFAULT NULL COMMENT '音色编码',
  `languages`       VARCHAR(50)  DEFAULT NULL COMMENT '语言',
  `reference_audio` VARCHAR(500) DEFAULT NULL COMMENT '参考音频路径',
  `reference_text`  VARCHAR(500) DEFAULT NULL COMMENT '参考文本',
  `audit_status`    TINYINT      NOT NULL DEFAULT '0' COMMENT '审核状态（0待审核 1通过 2驳回）',
  `audit_remark`    VARCHAR(255) DEFAULT NULL COMMENT '审核意见',
  `auditor`         BIGINT       DEFAULT NULL COMMENT '审核人',
  `audit_date`      DATETIME     DEFAULT NULL COMMENT '审核时间',
  `status`          TINYINT      NOT NULL DEFAULT '1' COMMENT '状态（0停用 1正常）',
  `remark`          VARCHAR(255) DEFAULT NULL COMMENT '备注',
  `sort`            INT UNSIGNED DEFAULT '0' COMMENT '排序',
  `creator`         BIGINT       DEFAULT NULL COMMENT '创建者',
  `create_date`     DATETIME     DEFAULT NULL COMMENT '创建时间',
  `updater`         BIGINT       DEFAULT NULL COMMENT '更新者',
  `update_date`     DATETIME     DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`),
  KEY `idx_ucv_user_status` (`user_id`,`status`,`audit_status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='用户自定义音色（仅本人可见，审核后可用）';

-- ============================================================
-- 种子数据：4 个内置角色（幂等，permissions 为 JSON 列字符串字面量）
-- ============================================================
INSERT INTO sys_role (id,role_code,role_name,permissions,status,is_builtin,sort,creator,create_date)
SELECT 1,'super_admin','超级管理员','["*"]',1,1,0,0,NOW() WHERE NOT EXISTS (SELECT 1 FROM sys_role WHERE id=1);

INSERT INTO sys_role (id,role_code,role_name,permissions,status,is_builtin,sort,creator,create_date)
SELECT 2,'admin','管理员','["admin:user:*","admin:role:list","admin:display:config","admin:default:config","admin:custom:audit","admin:audit:list","menu:admin"]',1,1,0,0,NOW() WHERE NOT EXISTS (SELECT 1 FROM sys_role WHERE id=2);

INSERT INTO sys_role (id,role_code,role_name,permissions,status,is_builtin,sort,creator,create_date)
SELECT 3,'user','普通用户','["user:custom:*","menu:customer"]',1,1,0,0,NOW() WHERE NOT EXISTS (SELECT 1 FROM sys_role WHERE id=3);

INSERT INTO sys_role (id,role_code,role_name,permissions,status,is_builtin,sort,creator,create_date)
SELECT 4,'readonly','只读访客','["menu:customer"]',1,1,0,0,NOW() WHERE NOT EXISTS (SELECT 1 FROM sys_role WHERE id=4);
