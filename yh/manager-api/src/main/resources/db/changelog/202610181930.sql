-- 开机壁纸（boot 槽）：壁纸任务表加槽位列。
-- 说明：
--   1. 固件侧双壁纸槽已上线（idle=待机主界面背景 / boot=开机 splash 底图），
--      同一张壁纸图片可以分别下发到两个槽，两槽回执/排队/NVS 完全独立；
--   2. 历史任务无 kind 视为 idle（DEFAULT 'idle'），行为与升级前完全一致；
--   3. Redis 回执键与 Python 补投队列同步分槽（wallpaper:ack:{kind}:{device}），
--      由应用层实现，本文件只加列。
ALTER TABLE `ai_wallpaper_task`
    ADD COLUMN `kind` VARCHAR(8) NOT NULL DEFAULT 'idle' COMMENT '壁纸槽位：idle=待机壁纸/boot=开机壁纸' AFTER `apply_mode`;
