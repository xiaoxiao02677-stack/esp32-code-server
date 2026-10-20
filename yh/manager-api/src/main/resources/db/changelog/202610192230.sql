-- 单台设备 OTA 定向升级 + 主题轨道。
-- 背景：三套 UI 主题固件（xiaoyou/pixel-pet/emopet）共用同一版型源码，靠
-- BOARD_TYPE 后缀区分轨道（如 yh-154tft-wifi-emopet）。ai_ota 按 type 精确
-- 匹配，无法对单台设备指定固件，也无法让一台设备跨主题升级。新增两列：
--   target_ota_id：单台指定 ai_ota 记录（优先级最高）。设备上报版本+type 与
--                  目标一致时自动清空（升级完成自愈）。
--   ota_type：     主题轨道覆盖。空 = 跟随设备实时上报 type（默认，行为不变）；
--                  非空 = autoUpdate=1 时按此轨道取最新固件，轨道与上报 type
--                  不同时无视版本号强制下发（主题切换）。
ALTER TABLE `ai_device`
    ADD COLUMN `target_ota_id` VARCHAR(32) NULL DEFAULT NULL COMMENT '单台指定固件（ai_ota.id，空=不指定）' AFTER `auto_update`,
    ADD COLUMN `ota_type` VARCHAR(64) NULL DEFAULT NULL COMMENT 'OTA主题轨道（空=跟随设备上报type）' AFTER `target_ota_id`;
