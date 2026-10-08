-- 新增设备云端配置表（B线：配置云端记忆，design §3.1/§5.1）
-- 一设备一行，device_id 即主键（关联 ai_device.id，按项目惯例不加外键约束）
-- config_json 仅存白名单键（volume/brightness，P1 预留 theme），值域 int 0-100
CREATE TABLE IF NOT EXISTS `ai_device_config` (
    `device_id`   VARCHAR(32) NOT NULL COMMENT '设备ID（关联 ai_device.id）',
    `config_json` JSON        NOT NULL COMMENT '设备配置（design §5.1 schema，如 {"volume":80,"brightness":60}）',
    `creator`     BIGINT      DEFAULT NULL COMMENT '创建者',
    `create_date` DATETIME    DEFAULT NULL COMMENT '创建时间',
    `updater`     BIGINT      DEFAULT NULL COMMENT '更新者',
    `update_date` DATETIME    DEFAULT NULL COMMENT '更新时间',
    PRIMARY KEY (`device_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='设备云端配置表（B线：配置云端记忆）';
