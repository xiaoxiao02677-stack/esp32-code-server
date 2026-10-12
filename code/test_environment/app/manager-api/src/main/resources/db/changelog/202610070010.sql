-- 设备云端配置表兼容迁移（P1-6：JSON_MERGE_PATCH 原子 upsert）
-- MySQL 8 内置 JSON_MERGE_PATCH 函数，upsert 语句级直接可用，无需 ALTER 表结构。
-- 本文件仅做幂等兜底：若所在环境未执行过 202610060030（ai_device_config 建表），
-- 以 CREATE TABLE IF NOT EXISTS 补建，已执行过则为 no-op，Liquibase 重放安全。
CREATE TABLE IF NOT EXISTS `ai_device_config` (
    `device_id`   VARCHAR(32) NOT NULL COMMENT '设备ID（关联 ai_device.id）',
    `config_json` JSON        NOT NULL COMMENT '设备配置（design §5.1 schema，如 {"volume":80,"brightness":60}）',
    `creator`     BIGINT      DEFAULT NULL COMMENT '创建者',
    `create_date` DATETIME    DEFAULT NULL COMMENT '创建时间',
    `updater`     BIGINT      DEFAULT NULL COMMENT '更新者',
    `update_date` DATETIME    DEFAULT NULL COMMENT '更新时间',
    PRIMARY KEY (`device_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='设备云端配置表（B线：配置云端记忆）';
