-- 新增Holographic本地记忆供应器（design §3.3：SQLite + FTS5 + 信任分 + 实体消解，零外部依赖）
INSERT INTO `ai_model_provider` (`id`, `model_type`, `provider_code`, `name`, `fields`, `sort`, `creator`, `create_date`, `updater`, `update_date`)
VALUES ('SYSTEM_Memory_mem_holographic', 'Memory', 'mem_holographic', 'Holographic本地记忆', '[
  {"key":"db_dir","label":"数据库根目录","type":"string","default":"data/memory/"},
  {"key":"auto_extract","label":"自动抽取","type":"boolean","default":true},
  {"key":"default_trust","label":"默认信任分","type":"number","default":0.5},
  {"key":"min_trust_threshold","label":"检索/审核阈值","type":"number","default":0.3},
  {"key":"temporal_decay_half_life","label":"时间衰减半衰期(天,0=关)","type":"number","default":0}
]', 5, 1, NOW(), 1, NOW());

-- 新增Holographic记忆模型默认配置（is_default=0，不改变存量Agent行为；Agent需在编辑页显式绑定）
INSERT INTO `ai_model_config` (`id`, `model_type`, `model_code`, `model_name`, `is_default`, `is_enabled`, `config_json`, `doc_link`, `remark`, `sort`, `creator`, `create_date`, `updater`, `update_date`)
VALUES ('Memory_mem_holographic', 'Memory', 'mem_holographic', 'Holographic本地记忆', 0, 1,
  '{"type": "mem_holographic", "db_dir": "data/memory/", "auto_extract": true, "default_trust": 0.5, "min_trust_threshold": 0.3, "temporal_decay_half_life": 0}',
  NULL,
  '本地条目化记忆：SQLite + FTS5 + 信任分 + 实体消解，每Agent一库（data/memory/{agent_id}.db），支持控制台逐条管理',
  5, 1, NOW(), 1, NOW());
