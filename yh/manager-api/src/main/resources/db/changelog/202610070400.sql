-- 数据修复：消除「占位 key 模型」引用链（2026-10-07 事故根因）
-- 事故：模板默认 LLM_ChatGLMLLM 携带中文占位 key「你的api_key」，下发后 Python httpx
--       拼 Authorization 头 ascii 编码崩溃，用户只听到兜底话术。
-- 代码防御（Java resolveUsableModel + Python fail-fast）已上线，本 changelog 清理存量引用：
--   1) 模板指向坏模型 → 重指当前启用+默认的 LLM
--   2) Intent_intent_llm / Memory_mem_local_short 的 config_json.llm 同样处理
-- 幂等：仅当目标模型确实坏（禁用或占位 key）且存在可用默认时才改，重复执行 no-op

-- 1. 智能体模板：坏 LLM → 默认启用 LLM
UPDATE `ai_agent_template` t
JOIN `ai_model_config` m ON m.id = t.llm_model_id AND m.model_type = 'LLM'
SET t.llm_model_id = (
    SELECT id FROM (
        SELECT id FROM `ai_model_config`
        WHERE model_type = 'LLM' AND is_enabled = 1 AND is_default = 1
        LIMIT 1
    ) ok
)
WHERE (m.is_enabled = 0
       OR JSON_UNQUOTE(JSON_EXTRACT(m.config_json, '$.api_key')) LIKE '%你%')
  AND EXISTS (
    SELECT 1 FROM `ai_model_config`
    WHERE model_type = 'LLM' AND is_enabled = 1 AND is_default = 1
  );

-- 2. 存量智能体：同规则修复（防用户自建 agent 引用坏模型）
UPDATE `ai_agent` a
JOIN `ai_model_config` m ON m.id = a.llm_model_id AND m.model_type = 'LLM'
SET a.llm_model_id = (
    SELECT id FROM (
        SELECT id FROM `ai_model_config`
        WHERE model_type = 'LLM' AND is_enabled = 1 AND is_default = 1
        LIMIT 1
    ) ok
)
WHERE (m.is_enabled = 0
       OR JSON_UNQUOTE(JSON_EXTRACT(m.config_json, '$.api_key')) LIKE '%你%')
  AND EXISTS (
    SELECT 1 FROM `ai_model_config`
    WHERE model_type = 'LLM' AND is_enabled = 1 AND is_default = 1
  );

-- 3. 存量智能体 SLM：同规则（标题生成/摘要曾因此 401）
UPDATE `ai_agent` a
JOIN `ai_model_config` m ON m.id = a.slm_model_id AND m.model_type = 'LLM'
SET a.slm_model_id = (
    SELECT id FROM (
        SELECT id FROM `ai_model_config`
        WHERE model_type = 'LLM' AND is_enabled = 1 AND is_default = 1
        LIMIT 1
    ) ok
)
WHERE (m.is_enabled = 0
       OR JSON_UNQUOTE(JSON_EXTRACT(m.config_json, '$.api_key')) LIKE '%你%')
  AND EXISTS (
    SELECT 1 FROM `ai_model_config`
    WHERE model_type = 'LLM' AND is_enabled = 1 AND is_default = 1
  );

-- 4. Intent 意图模型配置：config_json.llm 指向坏模型 → 指向默认 LLM
-- 注：不能用 JOIN 自 ai_model_config 更新 ai_model_config（MySQL 1093），先取坏 LLM id 集合到变量
SET @bad_llm_1 := (
    SELECT GROUP_CONCAT(id) FROM `ai_model_config`
    WHERE model_type = 'LLM'
      AND (is_enabled = 0 OR JSON_UNQUOTE(JSON_EXTRACT(config_json, '$.api_key')) LIKE '%你%')
);
SET @default_llm_1 := (
    SELECT id FROM `ai_model_config`
    WHERE model_type = 'LLM' AND is_enabled = 1 AND is_default = 1
    LIMIT 1
);
UPDATE `ai_model_config`
SET config_json = JSON_SET(config_json, '$.llm', @default_llm_1)
WHERE model_type = 'Intent'
  AND @default_llm_1 IS NOT NULL
  AND @bad_llm_1 IS NOT NULL
  AND FIND_IN_SET(JSON_UNQUOTE(JSON_EXTRACT(config_json, '$.llm')), @bad_llm_1);

-- 5. Memory 本地短记忆模型配置：同规则
SET @bad_llm_2 := (
    SELECT GROUP_CONCAT(id) FROM `ai_model_config`
    WHERE model_type = 'LLM'
      AND (is_enabled = 0 OR JSON_UNQUOTE(JSON_EXTRACT(config_json, '$.api_key')) LIKE '%你%')
);
SET @default_llm_2 := (
    SELECT id FROM `ai_model_config`
    WHERE model_type = 'LLM' AND is_enabled = 1 AND is_default = 1
    LIMIT 1
);
UPDATE `ai_model_config`
SET config_json = JSON_SET(config_json, '$.llm', @default_llm_2)
WHERE model_type = 'Memory'
  AND @default_llm_2 IS NOT NULL
  AND @bad_llm_2 IS NOT NULL
  AND FIND_IN_SET(JSON_UNQUOTE(JSON_EXTRACT(config_json, '$.llm')), @bad_llm_2);
