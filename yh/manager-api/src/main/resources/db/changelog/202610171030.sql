-- P1-3 壁纸管理（ai_wallpaper / ai_wallpaper_task / ai_wallpaper_task_device）
-- 说明：
--   1. 壁纸资源本身为 RGB565 小端原始像素（240x240x2 = 115200 字节），元数据存 ai_wallpaper；
--   2. 下发任务按「任务 + 设备明细」两表拆分，便于逐台回执与重试；
--   3. 设备侧的生效依赖 ai_device_config.config_json 中的 wallpaper 子对象（JSON_MERGE_PATCH 写入，
--      不覆盖 volume/brightness 等既有键），本文件不改动该表。
CREATE TABLE IF NOT EXISTS `ai_wallpaper` (
    `id`          VARCHAR(32)  NOT NULL COMMENT '壁纸ID',
    `name`        VARCHAR(64)  NOT NULL COMMENT '壁纸名称',
    `url`         VARCHAR(512) NOT NULL COMMENT 'RGB565 壁纸文件下载地址',
    `thumb_url`   VARCHAR(512) DEFAULT NULL COMMENT 'PNG 缩略图地址',
    `md5`         CHAR(32)     NOT NULL COMMENT 'RGB565 文件 MD5（小写hex）',
    `size`        INT          NOT NULL COMMENT 'RGB565 文件字节数',
    `width`       INT          NOT NULL COMMENT '像素宽',
    `height`      INT          NOT NULL COMMENT '像素高',
    `format`      VARCHAR(16)  NOT NULL DEFAULT 'rgb565' COMMENT '像素格式',
    `scope`       VARCHAR(16)  NOT NULL DEFAULT 'global' COMMENT '可见范围（global）',
    `creator`     BIGINT       DEFAULT NULL COMMENT '创建者',
    `create_date` DATETIME     DEFAULT NULL COMMENT '创建时间',
    PRIMARY KEY (`id`),
    KEY `idx_wallpaper_md5` (`md5`),
    KEY `idx_wallpaper_create_date` (`create_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='壁纸资源表';

CREATE TABLE IF NOT EXISTS `ai_wallpaper_task` (
    `id`           VARCHAR(32) NOT NULL COMMENT '任务ID',
    `wallpaper_id` VARCHAR(32) NOT NULL COMMENT '壁纸ID（关联 ai_wallpaper.id）',
    `target_type`  VARCHAR(16) NOT NULL COMMENT '目标类型：devices/group/all',
    `target_ids`   TEXT        DEFAULT NULL COMMENT '目标ID列表（JSON数组，all 时为空）',
    `apply_mode`   VARCHAR(16) NOT NULL COMMENT '生效方式：immediate/next_boot',
    `status`       VARCHAR(16) NOT NULL DEFAULT 'pending' COMMENT '任务状态：pending/sent/partial/failed',
    `total`        INT         NOT NULL DEFAULT 0 COMMENT '目标设备总数',
    `sent`         INT         NOT NULL DEFAULT 0 COMMENT '已成功推送在线通道的设备数',
    `success`      INT         NOT NULL DEFAULT 0 COMMENT '设备回执成功数',
    `failed`       INT         NOT NULL DEFAULT 0 COMMENT '失败数（推送失败或回执失败）',
    `creator`      BIGINT      DEFAULT NULL COMMENT '创建者',
    `create_date`  DATETIME    DEFAULT NULL COMMENT '创建时间',
    PRIMARY KEY (`id`),
    KEY `idx_wallpaper_task_wallpaper_id` (`wallpaper_id`),
    KEY `idx_wallpaper_task_create_date` (`create_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='壁纸下发任务表';

CREATE TABLE IF NOT EXISTS `ai_wallpaper_task_device` (
    `id`         BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键',
    `task_id`    VARCHAR(32)  NOT NULL COMMENT '任务ID（关联 ai_wallpaper_task.id）',
    `device_id`  VARCHAR(32)  NOT NULL COMMENT '设备ID（关联 ai_device.id）',
    `status`     VARCHAR(16)  NOT NULL DEFAULT 'pending' COMMENT '设备状态：pending/sent/failed/applied',
    `error`      VARCHAR(255) DEFAULT NULL COMMENT '失败原因',
    `ack_time`   DATETIME     DEFAULT NULL COMMENT '设备回执时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_wallpaper_task_device` (`task_id`, `device_id`),
    KEY `idx_wallpaper_task_device_device_id` (`device_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='壁纸下发任务设备明细表';
