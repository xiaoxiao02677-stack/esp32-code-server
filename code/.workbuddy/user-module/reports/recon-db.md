# 数据库侦察报告（recon-db）

> 目标：为「用户管理模块」新增表 DDL 设计提供现状依据。
> 环境：ssh -p 22223 root@sandyun.top → MySQL 8.0.46-0ubuntu0.24.04.4，库 `xiaozhi_esp32_server`（root/123456）。
> 侦察时间：2026-10-14（服务器时间 2026-10-14 00:25 CST）。全程只读（SHOW/DESC/SELECT）。
> 后端栈：Java 21 + Spring Boot 3 + MyBatis-Plus（id-type: ASSIGN_ID 雪花ID）+ Shiro 2.0.2 + Druid + Liquibase 4.20.0（renren 框架底座），context-path `/yuhe`，端口 8002。

---

## 0. 关键发现速览

1. 库中 34 张表（含 2 张 Liquibase 系统表）。业务表全部 InnoDB + utf8mb4，显式 COLLATE=`utf8mb4_0900_ai_ci`（库默认是 utf8mb4_unicode_ci，但所有业务表统一 0900_ai_ci）。
2. ID 双风格：`sys_*` 表用 **bigint 雪花ID**（MyBatis-Plus ASSIGN_ID，样例 2106728446262718466）；`ai_*` 表用 **varchar(32)**（UUID hex 或 `TTS_AliBLStreamTTS` 这类前缀编码）。
3. 公共审计字段四件套：`creator bigint` / `create_date datetime` / `updater bigint` / `update_date datetime`（均 DEFAULT NULL，秒级精度无小数）。ai_agent 一系有历史遗留变体 `created_at/updated_at`。
4. **Liquibase 异常（重要）**：DATABASECHANGELOG 已执行 123 个 changeSet，但当前 `db.changelog-master.yaml` 只挂载 120 个 —— `202610090130`、`202610101030`、`202610101100` 三个已执行却不在当前 yaml 中（且部署 jar 内的 yaml 同样缺失）。对现网无影响（DB 有记录不会重跑），但**全新库初始化会漏建 `ai_agent_wake_word`、`ai_agent_mcp_config` 两张表和 `ai_tts_voice.dynamic_instruction` 两列**。新 DDL 挂载时需注意这一历史欠账。
5. `ai_voice_clone` 表已存在且已有 `user_id bigint` + `train_status tinyint(1)（0待训练 1训练中 2成功 3失败）`，当前 0 行 —— 用户自定义音色「审核」语义可参考/复用该表。
6. `sys_user` 仅 2 行（demo / hermes_test，均 super_admin=1）；无 deleted/锁定/email/phone 字段 —— 软删除、锁定需 ALTER 扩列。
7. `sys_user_token` 对 user_id 做了 UNIQUE（一人一 Token）——「会话管理/强制下线」需求要放开为多 Token。
8. `ai_agent_chat_history` 无 user_id，只有 mac_address/agent_id/session_id；用户维度用量统计需 join `ai_agent.user_id`。该表是全库唯一用 `bigint AUTO_INCREMENT + datetime(3) + CURRENT_TIMESTAMP(3) DEFAULT` 的高频流水表样式。
9. 数据脏点：`ai_model_config` 存在 `model_type='llm'`（小写）与 `'LLM'` 混用；`kimi-k3` 行 model_code 为空串。新表设计枚举值务必统一大小写。
10. 字典表只有 2 个类型（FIRMWARE_TYPE/MOBILE_AREA），dict_type_id 用手工小整数（101/102）；**角色/权限无既有字典**，需新建。

---

## 1. 表清单总览（SHOW TABLES 全量，34 张）

```
DATABASECHANGELOG, DATABASECHANGELOGLOCK,
ai_agent, ai_agent_chat_audio, ai_agent_chat_history, ai_agent_chat_title,
ai_agent_context_provider, ai_agent_correct_word_file, ai_agent_correct_word_item,
ai_agent_correct_word_mapping, ai_agent_mcp_config, ai_agent_plugin_mapping,
ai_agent_snapshot, ai_agent_tag, ai_agent_tag_relation, ai_agent_template,
ai_agent_voice_print, ai_agent_wake_word,
ai_device, ai_device_address_book, ai_device_config,
ai_model_config, ai_model_provider, ai_ota,
ai_rag_dataset, ai_rag_knowledge_document,
ai_tts_voice, ai_voice_clone,
sys_dict_data, sys_dict_type, sys_params, sys_user, sys_user_token
```

行数统计：

| 表 | 行数 |
|---|---|
| sys_user | 2 |
| sys_user_token | 1 |
| ai_model_config | 39 |
| ai_model_provider | 25+（按 model_type 分组） |
| ai_tts_voice | 335（分布在 26 个 TTS 模型下） |
| ai_voice_clone | 0 |
| ai_device | 2（均属 user 2106728446262718466） |
| ai_agent_chat_history | ~3889（AUTO_INCREMENT=3890） |
| DATABASECHANGELOG | 123 个 changeSet |

字符集/版本：

```
character_set_client / connection / database / results / server = utf8mb4
character_set_system = utf8mb3（系统内部，无需理会）
version = 8.0.46-0ubuntu0.24.04.4
SHOW CREATE DATABASE → DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
```

所有业务表 TABLE_COLLATION = `utf8mb4_0900_ai_ci`（information_schema 逐一核实）。无触发器、无存储过程/函数。

---

## 2. 逐表 SHOW CREATE TABLE 完整输出

### 2.1 sys_user（现有用户表 —— 新模块改造核心）

```sql
CREATE TABLE `sys_user` (
  `id` bigint NOT NULL COMMENT 'id',
  `username` varchar(50) NOT NULL COMMENT '用户名',
  `password` varchar(100) DEFAULT NULL COMMENT '密码',
  `super_admin` tinyint unsigned DEFAULT NULL COMMENT '超级管理员   0：否   1：是',
  `status` tinyint DEFAULT NULL COMMENT '状态  0：停用   1：正常',
  `create_date` datetime DEFAULT NULL COMMENT '创建时间',
  `updater` bigint DEFAULT NULL COMMENT '更新者',
  `creator` bigint DEFAULT NULL COMMENT '创建者',
  `update_date` datetime DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_username` (`username`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='系统用户'
```

全量数据（2 行）：

```
id=2106728446262718466  username=demo        password=$2a$10$RMmTyUmNK3DszPtiTguv/.46MSGHVJmle0DlFKuHbpdlBZsUhrWnK
  super_admin=1  status=1  create_date=2026-10-04 12:49:37  updater=2106728446262718466  creator=NULL  update_date=2026-10-08 13:36:07
id=2108202905821700098  username=hermes_test password=$2a$10$ETVLFy6bopoO.xmbzT7iLua6D4AldYVdfWZx0WfmUD80zLLzcmE.q
  super_admin=1  status=1  create_date=2026-10-08 14:28:36  updater=2106728446262718466  creator=NULL  update_date=2026-10-11 14:32:51
```

要点：
- 密码 BCrypt（$2a$10$，60字符），varchar(100) 够用。
- **无** deleted/软删除、locked/锁定、email/phone/备注/最后登录时间/分组标签字段 → P0 软删除、P1 批量导入(需email/phone列)都要 ALTER。
- super_admin 用 `tinyint unsigned`，status 用 `tinyint`（历史不统一，新表建议统一 `tinyint`，注释写明取值）。
- 实体层 `SysUserEntity extends BaseEntity`，BaseEntity 含 `Long id(@TableId) / creator / createDate(INSERT fill)`，子类补 `updater/updateDate(INSERT_UPDATE fill)` —— 新表实体照此模式。

### 2.2 sys_user_token

```sql
CREATE TABLE `sys_user_token` (
  `id` bigint NOT NULL COMMENT 'id',
  `user_id` bigint NOT NULL COMMENT '用户id',
  `token` varchar(100) NOT NULL COMMENT '用户token',
  `expire_date` datetime DEFAULT NULL COMMENT '过期时间',
  `update_date` datetime DEFAULT NULL COMMENT '更新时间',
  `create_date` datetime DEFAULT NULL COMMENT '创建时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `user_id` (`user_id`),
  UNIQUE KEY `token` (`token`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='系统用户Token'
```

现有 1 行：

```
id=2108939881101279234  user_id=2106728446262718466  token=aaf38302dc9ec9fd3c5fea19275d3e76
expire_date=2026-10-14 14:13:24  update_date=2026-10-13 14:13:24  create_date=2026-10-10 15:17:05
```

要点：
- token 为 32 位 hex（无前缀、无 JWT）。
- `UNIQUE(user_id)` = **单终端单会话**；每次续期更新 expire_date + update_date（滑动过期，约 24h 窗口）。
- 会话管理/强制下线需求 → 需要去掉 user_id 唯一约束，增加 device/session 维度字段（建议新 changeset 里 DROP INDEX + ADD COLUMN，配 preConditions）。

### 2.3 ai_model_config

```sql
CREATE TABLE `ai_model_config` (
  `id` varchar(32) NOT NULL COMMENT '主键',
  `model_type` varchar(20) DEFAULT NULL COMMENT '模型类型(Memory/ASR/VAD/LLM/TTS)',
  `model_code` varchar(50) DEFAULT NULL COMMENT '模型编码(如AliLLM、DoubaoTTS)',
  `model_name` varchar(50) DEFAULT NULL COMMENT '模型名称',
  `is_default` tinyint(1) DEFAULT '0' COMMENT '是否默认配置(0否 1是)',
  `is_enabled` tinyint(1) DEFAULT '0' COMMENT '是否启用',
  `config_json` json DEFAULT NULL COMMENT '模型配置(JSON格式)',
  `doc_link` varchar(200) DEFAULT NULL COMMENT '官方文档链接',
  `remark` text COMMENT '备注',
  `sort` int unsigned DEFAULT '0' COMMENT '排序',
  `creator` bigint DEFAULT NULL COMMENT '创建者',
  `create_date` datetime DEFAULT NULL COMMENT '创建时间',
  `updater` bigint DEFAULT NULL COMMENT '更新者',
  `update_date` datetime DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`),
  KEY `idx_ai_model_config_model_type` (`model_type`) COMMENT '创建模型类型的索引，用于快速查找特定类型下的所有配置信息'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='模型配置表'
```

样例行（39 行中取 8）：

```
3248df0b7c0774f322ee0db56e8875d8 | TTS  | NULL           | 豆包声音复刻              | is_default=0 is_enabled=1 sort=0  creator=2106728446262718466
6811c8dabbd064764aea321521437886 | llm  | (空串)         | kimi-k3                  | is_default=0 is_enabled=0 sort=1  creator=2106728446262718466
ASR_AliyunASR                      | ASR  | AliyunASR      | 阿里云语音识别            | is_default=0 is_enabled=0 sort=9  creator=NULL
ASR_AliyunBLStream                 | ASR  | AliyunBLStream | 阿里百炼Paraformer实时ASR | ... sort=21
ASR_AliyunStreamASR                | ASR  | AliyunStreamASR| 阿里云语音识别(流式)      | ... sort=4
ASR_BaiduASR                       | ASR  | BaiduASR       | 百度语音识别              | ... sort=7
ASR_DoubaoASR                      | ASR  | DoubaoASR      | 豆包语音识别              | ... sort=8
ASR_DoubaoStreamASR                | ASR  | DoubaoStreamASR| 豆包语音识别(流式)        | ... sort=5
```

要点：
- id 混合两种风格：32位 UUID hex（用户在界面新建的）与 `ASR_XXX`/`TTS_XXX` 前缀式（系统预置）。
- `is_default` / `is_enabled` 用 `tinyint(1) DEFAULT '0'` —— 布尔语义字段的标准写法。
- **无可见性（visibility）、无 user_id、无状态(维护/下线)字段** —— 需求的「可用/维护/下线」「公开/组织/私有」目前不存在，属于新表/扩列范围。
- 索引命名：`idx_<表名>_<字段>`，且索引带 COMMENT。
- 脏数据：model_type 大小写混用（`llm` vs `LLM`）。

### 2.4 ai_model_provider

```sql
CREATE TABLE `ai_model_provider` (
  `id` varchar(32) NOT NULL COMMENT '主键',
  `model_type` varchar(20) DEFAULT NULL COMMENT '模型类型(Memory/ASR/VAD/LLM/TTS)',
  `provider_code` varchar(50) DEFAULT NULL COMMENT '供应器类型',
  `name` varchar(50) DEFAULT NULL COMMENT '供应器名称',
  `fields` json DEFAULT NULL COMMENT '供应器字段列表(JSON格式)',
  `sort` int unsigned DEFAULT '0' COMMENT '排序',
  `creator` bigint DEFAULT NULL COMMENT '创建者',
  `create_date` datetime DEFAULT NULL COMMENT '创建时间',
  `updater` bigint DEFAULT NULL COMMENT '更新者',
  `update_date` datetime DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`),
  KEY `idx_ai_model_provider_model_type` (`model_type`) COMMENT '创建模型类型的索引，用于快速查找特定类型下的所有供应器信息'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='模型配置表'
```

样例行：`SYSTEM_ASR_AliyunASR | ASR | aliyun | 阿里云语音识别 | [{"key":"appkey","type":"string",...}] | sort=5`。
- `fields` JSON 描述动态表单字段（key/type/label，type 含 string/password）—— **自定义模型的「密钥加密存储」可复用此 provider fields 元数据来渲染表单，password 类型字段落库时加密**。

### 2.5 ai_tts_voice

```sql
CREATE TABLE `ai_tts_voice` (
  `id` varchar(32) NOT NULL COMMENT '主键',
  `tts_model_id` varchar(32) DEFAULT NULL COMMENT '对应 TTS 模型主键',
  `name` varchar(20) DEFAULT NULL COMMENT '音色名称',
  `tts_voice` varchar(50) DEFAULT NULL COMMENT '音色编码',
  `languages` varchar(50) DEFAULT NULL COMMENT '语言',
  `voice_demo` varchar(500) DEFAULT NULL COMMENT '音色 Demo',
  `remark` varchar(255) DEFAULT NULL COMMENT '备注',
  `reference_audio` varchar(500) DEFAULT NULL COMMENT '参考音频路径',
  `reference_text` varchar(500) DEFAULT NULL COMMENT '参考文本',
  `voice_instruction` varchar(500) DEFAULT NULL COMMENT '音色级语气指令',
  `dynamic_instruction` tinyint(1) DEFAULT '0' COMMENT '动态语气指令开关',
  `instruction_llm_id` varchar(64) DEFAULT NULL COMMENT '动态指令生成LLM',
  `sort` int unsigned DEFAULT '0' COMMENT '排序',
  `creator` bigint DEFAULT NULL COMMENT '创建者',
  `create_date` datetime DEFAULT NULL COMMENT '创建时间',
  `updater` bigint DEFAULT NULL COMMENT '更新者',
  `update_date` datetime DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`),
  KEY `idx_ai_tts_voice_tts_model_id` (`tts_model_id`) COMMENT '创建 TTS 模型主键的索引，用于快速查找对应模型的音色信息'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='TTS 音色表'
```

样例：`TTS_AliBLStreamTTS_0001 | TTS_AliBLStreamTTS | 龙小淳-知性积极女 | longxiaochun_v2 | 普通话、英语 | sort=1`；另有用户自建的雪花ID行（`2108126651823071233 | 3248df0b... | 清清`）。
分布（tts_model_id → 音色数）：TTS_QwenTTS_Flash 48、TTS_VolcesAiGatewayTTS 44、TTS_HSDSTTS_V2 39、TTS_MinimaxStreamTTS 37、TTS_HuoshanDoubleStreamTTS 25、TTS_QwenTTS_Instruct 24、TTS_AliyunStreamTTS 20 …… 共 26 个 TTS 模型 335 条音色。

### 2.6 ai_voice_clone（用户自定义音色现状 —— 最相关参考）

```sql
CREATE TABLE `ai_voice_clone` (
  `id` varchar(32) NOT NULL COMMENT '唯一标识',
  `name` varchar(64) DEFAULT NULL COMMENT '声音名称',
  `model_id` varchar(32) DEFAULT NULL COMMENT '模型id',
  `voice_id` varchar(32) DEFAULT NULL COMMENT '声音id',
  `languages` varchar(50) DEFAULT NULL COMMENT '语言',
  `user_id` bigint DEFAULT NULL COMMENT '用户 ID（关联用户表）',
  `voice` longblob COMMENT '声音',
  `train_status` tinyint(1) DEFAULT '0' COMMENT '训练状态：0待训练 1训练中 2训练成功 3训练失败',
  `train_error` varchar(255) DEFAULT NULL COMMENT '训练错误原因',
  `creator` bigint DEFAULT NULL COMMENT '创建者 ID',
  `create_date` datetime DEFAULT NULL COMMENT '创建时间',
  PRIMARY KEY (`id`),
  KEY `idx_ai_voice_clone_user_id_model_id_train_status` (`model_id`,`user_id`,`train_status`),
  KEY `idx_ai_voice_clone_voice_id` (`voice_id`),
  KEY `idx_ai_voice_clone_user_id` (`user_id`),
  KEY `idx_ai_voice_clone_model_id_voice_id` (`model_id`,`voice_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='声音克隆表'
```

要点：
- **已有 user_id bigint 关联 + train_status 状态机（0-3）**，但无 updater/update_date（表不完整审计字段）；无「审核」语义字段（train_status 是技术训练状态，不是管理审核）。
- 复合索引命名 `idx_<表>_<多列缩写>` 风格。
- `sys_user_custom_voice` 新表若走「用户自定义 TTS 音色（非克隆训练）」语义，与该表并存；若要统一，需扩列而非新建（由架构定稿）。

### 2.7 ai_device（数据隔离参考）

```sql
CREATE TABLE `ai_device` (
  `id` varchar(32) NOT NULL COMMENT '设备唯一标识',
  `user_id` bigint DEFAULT NULL COMMENT '关联用户 ID',
  `mac_address` varchar(50) DEFAULT NULL COMMENT 'MAC 地址',
  `last_connected_at` datetime DEFAULT NULL COMMENT '最后连接时间',
  `auto_update` tinyint unsigned DEFAULT '0' COMMENT '自动更新开关(0 关闭/1 开启)',
  `board` varchar(50) DEFAULT NULL COMMENT '设备硬件型号',
  `alias` varchar(64) DEFAULT NULL COMMENT '设备别名',
  `agent_id` varchar(32) DEFAULT NULL COMMENT '智能体 ID',
  `app_version` varchar(20) DEFAULT NULL COMMENT '固件版本号',
  `sort` int unsigned DEFAULT '0' COMMENT '排序',
  `creator` bigint DEFAULT NULL COMMENT '创建者',
  `create_date` datetime DEFAULT NULL COMMENT '创建时间',
  `updater` bigint DEFAULT NULL COMMENT '更新者',
  `update_date` datetime DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`),
  KEY `idx_ai_device_created_at` (`mac_address`) COMMENT '创建mac的索引，用于快速查找设备信息'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='设备信息表'
```

数据隔离模式：`user_id bigint DEFAULT NULL` + 查询按 user_id 过滤（当前 2 台设备均属 demo 用户）。**无外键约束**（全库无 FK），关联纯逻辑约束。

### 2.8 ai_agent（最复杂表 —— 命名/字段学习样本）

```sql
CREATE TABLE `ai_agent` (
  `id` varchar(32) NOT NULL COMMENT '智能体唯一标识',
  `user_id` bigint DEFAULT NULL COMMENT '所属用户 ID',
  `agent_code` varchar(36) DEFAULT NULL COMMENT '智能体编码',
  `agent_name` varchar(64) DEFAULT NULL COMMENT '智能体名称',
  `asr_model_id` varchar(32) DEFAULT NULL COMMENT '语音识别模型标识',
  `vad_model_id` varchar(64) DEFAULT NULL COMMENT '语音活动检测标识',
  `llm_model_id` varchar(32) DEFAULT NULL COMMENT '大语言模型标识',
  `slm_model_id` varchar(255) DEFAULT NULL COMMENT '小模型ID',
  `vllm_model_id` varchar(32) DEFAULT 'VLLM_ChatGLMVLLM' COMMENT '视觉模型标识',
  `tts_model_id` varchar(32) DEFAULT NULL COMMENT '语音合成模型标识',
  `tts_voice_id` varchar(32) DEFAULT NULL COMMENT '音色标识',
  `tts_language` varchar(50) DEFAULT NULL COMMENT '音色语言',
  `tts_volume` int DEFAULT NULL COMMENT 'TTS音量',
  `tts_rate` int DEFAULT NULL COMMENT 'TTS语速',
  `tts_pitch` int DEFAULT NULL COMMENT 'TTS音调',
  `mem_model_id` varchar(32) DEFAULT NULL COMMENT '记忆模型标识',
  `intent_model_id` varchar(32) DEFAULT NULL COMMENT '意图模型标识',
  `system_prompt` text COMMENT '角色设定参数',
  `summary_memory` text COMMENT '总结记忆',
  `wake_words` varchar(255) DEFAULT NULL COMMENT '智能体自定义唤醒词，分号分隔；为空则使用全局 wakeup_words',
  `chat_history_conf` tinyint NOT NULL DEFAULT '0' COMMENT '聊天记录配置（0不记录 1仅记录文本 2记录文本和语音）',
  `lang_code` varchar(10) DEFAULT NULL COMMENT '语言编码',
  `language` varchar(10) DEFAULT NULL COMMENT '交互语种',
  `sort` int unsigned DEFAULT '0' COMMENT '排序权重',
  `creator` bigint DEFAULT NULL COMMENT '创建者 ID',
  `created_at` datetime DEFAULT NULL COMMENT '创建时间',
  `updater` bigint DEFAULT NULL COMMENT '更新者 ID',
  `updated_at` datetime DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`),
  KEY `idx_ai_agent_user_id` (`user_id`) COMMENT '创建用户的索引，用于快速查找用户下的智能体信息'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='智能体配置表'
```

要点：
- 模型引用列命名模式：`<环节>_model_id varchar(32)`（与 ai_model_config.id 对齐）、`tts_voice_id varchar(32)`（与 ai_tts_voice.id 对齐）。
- `*_model_id` 引用类型统一 varchar(32)，例外：vad_model_id varchar(64)、slm_model_id varchar(255)、instruction_llm_id varchar(64)。
- 历史遗留：本表用 `created_at/updated_at` 而非 create_date/update_date（ai_agent_tag_relation、ai_agent_template 同样）；**新表建议统一 create_date/update_date（sys_* 系主流）**。
- `chat_history_conf`：tinyint NOT NULL DEFAULT '0' + 注释枚举 —— 多值开关的标准样式。

### 2.9 ai_agent_chat_history（用量统计参考 + 流水表样式）

```sql
CREATE TABLE `ai_agent_chat_history` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `mac_address` varchar(50) DEFAULT NULL COMMENT 'MAC地址',
  `agent_id` varchar(32) DEFAULT NULL COMMENT '智能体id',
  `session_id` varchar(50) DEFAULT NULL COMMENT '会话ID',
  `chat_type` tinyint DEFAULT NULL COMMENT '消息类型: 1-用户, 2-智能体',
  `content` text COMMENT '聊天内容',
  `audio_id` varchar(32) DEFAULT NULL COMMENT '音频ID',
  `created_at` datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间',
  `updated_at` datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '更新时间',
  PRIMARY KEY (`id`),
  KEY `idx_ai_agent_chat_history_mac` (`mac_address`),
  KEY `idx_ai_agent_chat_history_session_id` (`session_id`),
  KEY `idx_ai_agent_chat_history_agent_id` (`agent_id`),
  KEY `idx_ai_agent_chat_history_agent_session_created` (`agent_id`,`session_id`,`created_at`),
  KEY `idx_ai_agent_chat_history_audio_id` (`audio_id`)
) ENGINE=InnoDB AUTO_INCREMENT=3890 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='智能体聊天记录表'
```

用量统计路径：消息 → agent_id → `ai_agent.user_id`（间接获得用户）。**无直接 user_id 列**；若做用户级用量配额，建议在统计/配额表里冗余 user_id，避免高频 join。

### 2.10 sys_dict_type / sys_dict_data / sys_params（字典与参数）

```sql
CREATE TABLE `sys_dict_type` (
  `id` bigint NOT NULL COMMENT 'id',
  `dict_type` varchar(100) NOT NULL COMMENT '字典类型',
  `dict_name` varchar(255) NOT NULL COMMENT '字典名称',
  `remark` varchar(255) DEFAULT NULL COMMENT '备注',
  `sort` int unsigned DEFAULT NULL COMMENT '排序',
  `creator` bigint DEFAULT NULL COMMENT '创建者',
  `create_date` datetime DEFAULT NULL COMMENT '创建时间',
  `updater` bigint DEFAULT NULL COMMENT '更新者',
  `update_date` datetime DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `dict_type` (`dict_type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='字典类型'

CREATE TABLE `sys_dict_data` (
  `id` bigint NOT NULL COMMENT 'id',
  `dict_type_id` bigint NOT NULL COMMENT '字典类型ID',
  `dict_label` varchar(255) NOT NULL COMMENT '字典标签',
  `dict_value` varchar(255) DEFAULT NULL COMMENT '字典值',
  `remark` varchar(255) DEFAULT NULL COMMENT '备注',
  `sort` int unsigned DEFAULT NULL COMMENT '排序',
  `creator` bigint DEFAULT NULL COMMENT '创建者',
  `create_date` datetime DEFAULT NULL COMMENT '创建时间',
  `updater` bigint DEFAULT NULL COMMENT '更新者',
  `update_date` datetime DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_dict_type_value` (`dict_type_id`,`dict_value`),
  KEY `idx_sort` (`sort`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='字典数据'

CREATE TABLE `sys_params` (
  `id` bigint NOT NULL COMMENT 'id',
  `param_code` varchar(100) DEFAULT NULL COMMENT '参数编码',
  `param_value` varchar(2000) DEFAULT NULL COMMENT '参数值',
  `value_type` varchar(20) DEFAULT 'string' COMMENT '值类型：string-字符串，number-数字，boolean-布尔，array-数组',
  `param_type` tinyint unsigned DEFAULT '1' COMMENT '类型   0：系统参数   1：非系统参数',
  `remark` varchar(200) DEFAULT NULL COMMENT '备注',
  `creator` bigint DEFAULT NULL COMMENT '创建者',
  `create_date` datetime DEFAULT NULL COMMENT '创建时间',
  `updater` bigint DEFAULT NULL COMMENT '更新者',
  `update_date` datetime DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_param_code` (`param_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='参数管理'
```

字典现状：仅 FIRMWARE_TYPE(54项)、MOBILE_AREA(38项) 两类，id 手工小整数（101/102）。角色状态、审核状态等枚举可走 sys_dict，也可直接 tinyint+注释（现有表以 tinyint+注释为主流）。

### 2.11 近期新表的最新写法样本（202610101030 / 202610101100，最应效仿的风格）

```sql
-- 202610101100.sql（ai_agent_wake_word）
CREATE TABLE IF NOT EXISTS `ai_agent_wake_word` (
    `id`          VARCHAR(32)  NOT NULL COMMENT '主键（UUID）',
    `agent_id`    VARCHAR(32)  NOT NULL COMMENT '关联 ai_agent.id',
    `wake_words`  JSON         NOT NULL COMMENT '唤醒词列表 JSON，格式：{"words": ["小智小智", "你好小智"]}',
    `creator`     BIGINT       DEFAULT NULL COMMENT '创建者',
    `create_date` DATETIME     DEFAULT NULL COMMENT '创建时间',
    `updater`     BIGINT       DEFAULT NULL COMMENT '更新者',
    `update_date` DATETIME     DEFAULT NULL COMMENT '更新时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_agent` (`agent_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='智能体唤醒词配置（per-agent）';

-- 202610101030.sql（ai_agent_mcp_config）额外要点：
--   `name`        VARCHAR(128) NOT NULL DEFAULT '' —— 业务名长度用 128
--   `enabled`     TINYINT(1)   NOT NULL DEFAULT 1  —— 布尔列 NOT NULL + DEFAULT 1 的新风格
--   `server_json` JSON         NOT NULL
--   KEY `idx_enabled` (`enabled`)
```

文件头均有中文块注释说明背景与用途（`-- 背景：…`），SQL 内反引号包全部标识符。

---

## 3. Liquibase 挂载约定（新 DDL 必须遵守）

**文件位置**（服务器源码树）：`/root/yh/app/manager-api/src/main/resources/db/changelog/`
**Master 文件**：`db.changelog-master.yaml`（Spring Boot 默认 liquibase changelog 路径，无自定义 change-log 配置；`liquibase-core 4.20.0`；`SystemInitConfig` 依赖 bean `"liquibase"` 在启动后初始化缓存）。

**约定（yaml 头部注释原文）**：
> id生成根据时间时分，文件名对应id，常变数据可以根据模块命名自定义
> 每次对数据表进行改动时，只允许新建新对changeSet，不允许对上一个changeSet配置及文件进行修改

**挂载模板**（追加到 master yaml 末尾）：

```yaml
  - changeSet:
      id: YYYYMMDDHHMM          # 12位时间戳，与 SQL 文件同名
      author: <agent名>          # 现有用过：team-lead、backend-java、John、czc、Goody…
      changes:
        - sqlFile:
            encoding: utf8
            path: classpath:db/changelog/YYYYMMDDHHMM.sql
```

**幂等写法**（两种现成范式）：
1. 建表：SQL 里 `CREATE TABLE IF NOT EXISTS`。
2. ALTER 加列（MySQL 无 ADD COLUMN IF NOT EXISTS）：在 changeSet 上加 preConditions，参考 202610100930：

```yaml
      preConditions:
        onFail: MARK_RAN
        onError: MARK_RAN
        onFailMessage: <表> 已存在 <列> 列（手工建过），跳过
        not:
          columnExists:
            tableName: ai_agent
            columnName: wake_words
```

**DATABASECHANGELOG 记录格式**（FILENAME 列）：`db/changelog/db.changelog-master.yaml`（相对路径，不带 classpath: 前缀）；id=YYYYMMDDHHMM；MD5SUM `8:xxxx` 格式。

**⚠ 现状欠账（挂载新 DDL 前必须知道）**：
- DB 已执行 123 个 changeSet；当前 master yaml（src 与 target、部署 jar 三处一致）只挂 120 个。
- 缺失的是 `202610090130`（ai_tts_voice 加 dynamic_instruction/instruction_llm_id 两列）、`202610101030`（建 ai_agent_mcp_config）、`202610101100`（建 ai_agent_wake_word）。
- 影响：现网无碍（DATABASECHANGELOG 有记录不会重跑、MD5 不校验不存在的 changeSet）；但**全新库从 yaml 初始化会漏这些建表/加列**。建议架构定稿时把这三个 changeSet 重新挂回 master 末尾（内容与已执行版本保持字节一致即可通过 MD5 校验，Liquibase 对已执行且 MD5 一致的直接跳过）。
- 新 changeSet 的 id 必须全局唯一且大于当前时间（服务器当前 2026-10-14，如 `20261014xxxx`），追加在 yaml 最末（当前最后一个是 202610100930）。
- 服务器当前日期 2026-10-14，**id 前缀用 20261014xx**。

**部署链路**：`/root/yh/app/manager-api`（源码）→ mvn package → `target/xiaozhi-esp32-api.jar` → 拷贝到 `/root/yh/deploy/opt-yuhe/xiaozhi-esp32-api.jar`（当前两 jar md5 一致：b7e14d6e024527a2d1b84540f820dc60），java -jar 启动时 Liquibase 自动执行。外置 `application-dev.yml` 无 liquibase 段（用的 jar 内默认）。

---

## 4. 命名/字段约定归纳（新表设计直接套用）

### 4.1 表名
- 前缀分域：`sys_`（系统管理）/ `ai_`（AI 业务）。用户管理模块新表用 `sys_` 前缀。
- 全小写下划线；关联表 `A_B_relation`（如 ai_agent_tag_relation）。
- 表必须有 COMMENT（中文）。

### 4.2 主键
- sys 系：`id bigint NOT NULL COMMENT 'id'`，应用层雪花 ASSIGN_ID（MyBatis-Plus `@TableId`，global `id-type: ASSIGN_ID`）。
- ai 系：`id varchar(32)`（UUID hex / 前缀编码）。
- 高频流水（日志类）可用 `bigint AUTO_INCREMENT`。
- **全库无外键约束**，跨表引用纯逻辑关联 + 索引。

### 4.3 公共审计字段（四件套，绝大多数表都有）
```sql
`creator`     bigint   DEFAULT NULL COMMENT '创建者',
`create_date` datetime DEFAULT NULL COMMENT '创建时间',
`updater`     bigint   DEFAULT NULL COMMENT '更新者',
`update_date` datetime DEFAULT NULL COMMENT '更新时间',
```
- datetime **秒级精度，无小数**；DEFAULT NULL（由 MyBatis-Plus FieldFill 填充，不用 DB 默认值）。
- 例外：高频流水表用 `datetime(3) DEFAULT CURRENT_TIMESTAMP(3)`；ai_agent 系历史遗留 created_at/updated_at（新表不要学）。
- creator/updater 类型 = bigint（存 sys_user.id），与主键风格对齐。

### 4.4 状态/布尔
- 布尔：`tinyint(1) DEFAULT '0'`（新表趋势：`NOT NULL DEFAULT 1/0`），注释写 `（0否 1是）` 或 `（0 关闭/1 开启）`。
- 多值枚举：`tinyint DEFAULT NULL` / `tinyint NOT NULL DEFAULT '0'`，注释全枚举：`'训练状态：0待训练 1训练中 2训练成功 3训练失败'`。
- 现有取值习惯：status 0停用/1正常；sys_params.param_type 0系统/1非系统。

### 4.5 varchar 长度风格（观察到的取值集合）
20（编码/类型）、32（ID/编码）、36（agent_code/UUID带横线）、50（名称/编码/语言）、64（名称）、100（用户名/密码/参数码）、128（配置别名）、200（备注/doc_link）、255（备注/长编码/备注上限）、500（demo/路径/参考文本）、2000（param_value）。
**建议新表取值从中选：名称类 50/64，编码类 20/32/50，备注类 200/255，路径/长文本 500，超大 2000。**

### 4.6 其他字段类型习惯
- 排序：`sort int unsigned DEFAULT '0'`。
- 大文本：`text`（system_prompt/remark 长文）；二进制：`longblob`（voice/audio）。
- 结构化配置：原生 `json` 类型（config_json / fields / wake_words / server_json）—— 动态 schema 一律 JSON 落库。
- 时间列命名：语义化后缀 `_date`（create_date）或 `_at`（last_connected_at）；新表统一 `create_date/update_date`。
- 列名全 snake_case，SQL 文件中标识符一律反引号包裹。

### 4.7 索引/约束命名
- 唯一键：`uk_<语义>`（uk_username、uk_dict_type_value、uk_agent）。
- 普通索引：`idx_<表名>_<列/语义>`（idx_ai_agent_user_id、idx_sort），**索引可带 COMMENT**（说明用途）。
- 复合唯一 (a,b) 常见；MySQL 唯一索引含 NULL 时不判重 —— 设计「系统/角色/用户三级」UK 时用 sentinel 0 代替 NULL。

### 4.8 实体层（Java）约定
- `SysXxxEntity extends BaseEntity`；BaseEntity 含 id/creator/createDate（INSERT fill），业务实体补 updater/updateDate（INSERT_UPDATE fill）。
- `map-underscore-to-camel-case: true`；typeAliasesPackage `yuhe.modules.*.entity`。

---

## 5. 新表设计建议（草案，最终由架构定稿）

> 原则：sys_ 前缀、bigint 雪花 id、四件套审计字段、tinyint 状态+注释枚举、无外键、uk_/idx_ 命名、ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci（新 DDL 建议显式写 COLLATE，与全库一致，比近期只写 CHARSET 的更严谨）。
> 与 ai_* 资源表关联时：模型引用 varchar(32)、用户引用 bigint（两套 id 风格并存是现状，关联字段类型跟随被引表）。

### 5.1 sys_role（角色）

```sql
CREATE TABLE IF NOT EXISTS `sys_role` (
  `id`          BIGINT       NOT NULL COMMENT 'id（雪花ID）',
  `role_code`   VARCHAR(50)  NOT NULL COMMENT '角色编码（如 super_admin/admin/user/readonly）',
  `role_name`   VARCHAR(50)  NOT NULL COMMENT '角色名称',
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

注：需求还有 sys_permission / sys_role_permission（REQUIREMENTS.md §六），本次指派清单未含，但结构同理（permission_code UK、role_id+permission_id UK）；若权限点走「菜单/按钮编码」字符串方案可先不建 permission 表，用 role 上的 JSON/集合字段过渡 —— 由架构定。

### 5.2 sys_user_role（用户-角色关联）

```sql
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
```

（参考样本：ai_agent_tag_relation —— 纯关联表带四件套 + UK(双列) + 双向索引。另建议同步给 sys_user 增 `deleted`/`locked` 列走 ALTER changeSet + preConditions。）

### 5.3 sys_audit_log（审计日志 —— 流水表样式，参考 ai_agent_chat_history）

```sql
CREATE TABLE IF NOT EXISTS `sys_audit_log` (
  `id`           BIGINT      NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `user_id`      BIGINT      DEFAULT NULL COMMENT '操作人ID（sys_user.id）',
  `username`     VARCHAR(50) DEFAULT NULL COMMENT '操作人用户名（冗余，防用户删除后不可读）',
  `module`       VARCHAR(50) DEFAULT NULL COMMENT '模块（如 user/role/model/voice）',
  `operation`    VARCHAR(50) DEFAULT NULL COMMENT '操作类型（如 login/logout/create/update/delete/disable/grant/import/export）',
  `target_type`  VARCHAR(50) DEFAULT NULL COMMENT '目标对象类型',
  `target_id`    VARCHAR(64) DEFAULT NULL COMMENT '目标对象ID',
  `request_uri`  VARCHAR(255) DEFAULT NULL COMMENT '请求URI',
  `request_method` VARCHAR(10) DEFAULT NULL COMMENT 'HTTP方法',
  `params`       JSON        DEFAULT NULL COMMENT '请求参数（脱敏后）',
  `result`       TINYINT     NOT NULL DEFAULT '1' COMMENT '结果（0失败 1成功）',
  `error_msg`    VARCHAR(500) DEFAULT NULL COMMENT '错误信息',
  `ip`           VARCHAR(50) DEFAULT NULL COMMENT '操作IP',
  `user_agent`   VARCHAR(500) DEFAULT NULL COMMENT 'UA',
  `duration`     INT         DEFAULT NULL COMMENT '耗时(ms)',
  `created_at`   DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间',
  PRIMARY KEY (`id`),
  KEY `idx_sys_audit_log_user_id` (`user_id`,`created_at`),
  KEY `idx_sys_audit_log_module_op` (`module`,`operation`),
  KEY `idx_sys_audit_log_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='安全审计日志（追加只写，不提供更新/删除接口）';
```

注：高频写入、无更新语义 → 不放 updater/update_date；datetime(3) 对齐 chat_history。「管理员操作不可篡改」靠应用层不提供 UPDATE/DELETE + 可选定期归档。

### 5.4 sys_display_config（字段级展示配置，系统/角色/用户三级继承）

```sql
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
```

注：role_id/user_id 用 sentinel 0 而非 NULL（MySQL 唯一索引对 NULL 不判重）。

### 5.5 sys_user_default（默认模型/音色/参数，三级）

```sql
CREATE TABLE IF NOT EXISTS `sys_user_default` (
  `id`             BIGINT       NOT NULL COMMENT 'id（雪花ID）',
  `scope_type`     TINYINT      NOT NULL COMMENT '作用域（0平台 1角色 2用户）',
  `role_id`        BIGINT       NOT NULL DEFAULT '0' COMMENT '角色ID（scope_type=1有效，其余0）',
  `user_id`        BIGINT       NOT NULL DEFAULT '0' COMMENT '用户ID（scope_type=2有效，其余0）',
  `llm_model_id`   VARCHAR(32)  DEFAULT NULL COMMENT '默认LLM（ai_model_config.id）',
  `tts_model_id`   VARCHAR(32)  DEFAULT NULL COMMENT '默认TTS模型（ai_model_config.id）',
  `tts_voice_id`   VARCHAR(32)  DEFAULT NULL COMMENT '默认音色（ai_tts_voice.id）',
  `asr_model_id`   VARCHAR(32)  DEFAULT NULL COMMENT '默认ASR（ai_model_config.id）',
  `param_json`     JSON         DEFAULT NULL COMMENT '参数模板（温度/TopP/语速等，如 {"temperature":0.7,"top_p":0.9}）',
  `lock_policy`    TINYINT      NOT NULL DEFAULT '0' COMMENT '冲突策略（0可被下级覆盖 1锁定）',
  `creator`        BIGINT       DEFAULT NULL COMMENT '创建者',
  `create_date`    DATETIME     DEFAULT NULL COMMENT '创建时间',
  `updater`        BIGINT       DEFAULT NULL COMMENT '更新者',
  `update_date`    DATETIME     DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_scope` (`scope_type`,`role_id`,`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='默认模型音色配置（平台→角色→用户三级，冲突按 lock_policy）';
```

注：模型引用列对齐 ai_agent 的 `*_model_id varchar(32)` 命名。

### 5.6 sys_user_custom_model（用户自定义 LLM，含审核+加密+配额）

```sql
CREATE TABLE IF NOT EXISTS `sys_user_custom_model` (
  `id`              VARCHAR(32)  NOT NULL COMMENT '主键（UUID，与 ai_model_config.id 风格对齐）',
  `user_id`         BIGINT       NOT NULL COMMENT '所属用户ID（sys_user.id）',
  `model_type`      VARCHAR(20)  NOT NULL COMMENT '模型类型（LLM/ASR/TTS/VAD/Memory，统一大写）',
  `model_name`      VARCHAR(50)  NOT NULL COMMENT '模型名称',
  `provider_code`   VARCHAR(50)  DEFAULT NULL COMMENT '供应器编码（ai_model_provider.provider_code）',
  `config_json`     JSON         DEFAULT NULL COMMENT '模型配置（api_key 字段存密文，参考 provider.fields 定义）',
  `api_key_cipher`  VARCHAR(500) DEFAULT NULL COMMENT 'API密钥密文（加密存储，接口永不明文返回）',
  `base_url`        VARCHAR(500) DEFAULT NULL COMMENT '接口地址',
  `audit_status`    TINYINT      NOT NULL DEFAULT '0' COMMENT '审核状态（0待审核 1通过 2驳回）',
  `audit_remark`    VARCHAR(255) DEFAULT NULL COMMENT '审核意见',
  `auditor`         BIGINT       DEFAULT NULL COMMENT '审核人',
  `audit_date`      DATETIME     DEFAULT NULL COMMENT '审核时间',
  `status`          TINYINT      NOT NULL DEFAULT '1' COMMENT '状态（0停用 1正常 2维护 3下线）',
  `health_status`   TINYINT      DEFAULT NULL COMMENT '健康检查（0未知 1正常 2异常）',
  `quota_limit`     INT          DEFAULT NULL COMMENT '调用配额（次/日，NULL不限）',
  `used_count`      BIGINT       NOT NULL DEFAULT '0' COMMENT '已用次数（统计冗余）',
  `remark`          VARCHAR(255) DEFAULT NULL COMMENT '备注',
  `sort`            INT UNSIGNED DEFAULT '0' COMMENT '排序',
  `creator`         BIGINT       DEFAULT NULL COMMENT '创建者',
  `create_date`     DATETIME     DEFAULT NULL COMMENT '创建时间',
  `updater`         BIGINT       DEFAULT NULL COMMENT '更新者',
  `update_date`     DATETIME     DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`),
  KEY `idx_ucm_user_type_status` (`user_id`,`model_type`,`status`,`audit_status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='用户自定义模型（仅本人可见，密钥加密，审核后可用）';
```

### 5.7 sys_user_custom_voice（用户自定义音色，含审核）

```sql
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
```

注：与既有 `ai_voice_clone`（克隆训练，含 voice longblob + train_status）语义区分 —— clone 是"训练个人音色"，本表是"登记自定义音色条目"；若架构决定合并，则在 ai_voice_clone 上扩 audit_* 列并补 updater/update_date。

### 5.8 既有表需要的 ALTER（建议随新表 DDL 一起出 changeSet，全部带 preConditions）

```sql
-- sys_user 软删除/锁定（P0 软删除+恢复；P1 锁定）
ALTER TABLE `sys_user`
  ADD COLUMN `deleted`     TINYINT(1)  NOT NULL DEFAULT '0' COMMENT '软删除（0否 1是）' AFTER `status`,
  ADD COLUMN `locked`      TINYINT(1)  NOT NULL DEFAULT '0' COMMENT '锁定（0否 1是）' AFTER `deleted`,
  ADD COLUMN `deleted_date` DATETIME  DEFAULT NULL COMMENT '删除时间' AFTER `locked`,
  ADD COLUMN `last_login_date` DATETIME DEFAULT NULL COMMENT '最后登录时间' AFTER `deleted_date`;
-- （email/phone/分组标签等 P1 字段同法追加）

-- sys_user_token 多端会话（P1 会话管理/强制下线）：去掉 user_id 唯一约束
ALTER TABLE `sys_user_token`
  DROP INDEX `user_id`,
  ADD INDEX `idx_user_id` (`user_id`);
-- 可选：ADD COLUMN `client_type` VARCHAR(20) / `ip` VARCHAR(50) / `status` TINYINT
```

---

## 6. 给 DDL 设计 agent 的落地清单

1. 每张新表一个 SQL 文件（或合并为一个 changeSet 文件，内部多语句 —— liquibase sqlFile 天然支持多语句，wall filter 已开 multi-statement-allow），文件名 `20261014xxxx.sql`，头部中文块注释写背景。
2. master yaml 追加 changeSet（id=文件名，author 用本团队名如 `user-module`），path `classpath:db/changelog/20261014xxxx.sql`，encoding utf8。
3. 建表用 `CREATE TABLE IF NOT EXISTS`；ALTER 用 preConditions(columnExists not + onFail MARK_RAN)。
4. 显式 `ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci`，全库排序规则才一致。
5. 建议（可与 team-lead 确认）顺手把缺失的 202610090130/202610101030/202610101100 三个 changeSet 按原内容重新挂回 master（修复全新库初始化缺表问题）；重挂时内容必须与已执行版本完全一致，否则 MD5 校验失败会阻塞启动。
6. sys_user 扩列后，实体 SysUserEntity 需同步加字段（MyBatis-Plus 驼峰映射）。
7. 枚举取值注释全量写进列 COMMENT（现有表风格）；model_type 等枚举值统一大写（修复现网 llm/LLM 混用隐患，新代码统一 'LLM'）。

---
*报告完。数据获取窗口：2026-10-14 00:25 CST（服务器）。所有 SHOW CREATE TABLE 输出为 mysql 客户端原文，未做删改。*
