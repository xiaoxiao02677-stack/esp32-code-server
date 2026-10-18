-- post-save EVIDENCE snapshot, NOT a rollback asset
-- purpose : prove wake_word_display / interrupt_threshold were persisted after deploy
-- source  : sandyun.top  db=xiaozhi_esp32_server
-- taken_at: 2026-10-17 21:38 CST (UTC+8)
-- scope   : ai_device_config (all 5 rows) + ai_agent (id, wake_words only)
-- rollback: use /root/deploy-backup/20261017T125532Z/db/ai_tables_full.sql instead


/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

/*!40000 ALTER TABLE `ai_device_config` DISABLE KEYS */;
INSERT INTO `ai_device_config` (`device_id`, `config_json`, `creator`, `create_date`, `updater`, `update_date`) VALUES ('14:c1:9f:d1:33:48','{\"volume\": 98, \"wake_word\": [\"琳琳\", \"玲玲\", \"灵灵\"], \"wallpaper\": {\"md5\": \"bf22d39e91d67f54cf2b70de9669578c\", \"url\": \"http://sandyun.top:8002/yuhe/wallpaperMag/download/bf22d39e91d67f54cf2b70de9669578c.bin\", \"size\": 115200, \"scope\": \"global\", \"width\": 240, \"format\": \"rgb565\", \"height\": 240, \"version\": \"3-bf22d39e91d67f54cf2b70de9669578c\"}, \"brightness\": 100}',NULL,NULL,NULL,'2026-10-17 06:03:11');
INSERT INTO `ai_device_config` (`device_id`, `config_json`, `creator`, `create_date`, `updater`, `update_date`) VALUES ('44:bd:8d:7b:3a:e4','{\"wake_word\": [\"guigui\"], \"wallpaper\": {\"md5\": \"2545633c8f99934fc172c36d01d82419\", \"url\": \"http://sandyun.top:8002/yuhe/wallpaperMag/download/2545633c8f99934fc172c36d01d82419.bin\", \"size\": 115200, \"scope\": \"global\", \"width\": 240, \"format\": \"rgb565\", \"height\": 240, \"version\": \"3-2545633c8f99934fc172c36d01d82419\"}, \"wake_word_display\": [\"guigui\"], \"interrupt_threshold\": 0}',NULL,NULL,NULL,'2026-10-17 13:27:58');
INSERT INTO `ai_device_config` (`device_id`, `config_json`, `creator`, `create_date`, `updater`, `update_date`) VALUES ('b8:1f:3f:c3:96:20','{\"volume\": 95, \"wake_word\": [\"你好\"], \"wallpaper\": {\"md5\": \"bf22d39e91d67f54cf2b70de9669578c\", \"url\": \"http://sandyun.top:8002/yuhe/wallpaperMag/download/bf22d39e91d67f54cf2b70de9669578c.bin\", \"size\": 115200, \"scope\": \"global\", \"width\": 240, \"format\": \"rgb565\", \"height\": 240, \"version\": \"3-bf22d39e91d67f54cf2b70de9669578c\"}, \"brightness\": 100}',NULL,NULL,NULL,'2026-10-17 06:03:11');
INSERT INTO `ai_device_config` (`device_id`, `config_json`, `creator`, `create_date`, `updater`, `update_date`) VALUES ('c4:9e:7e:08:c2:b4','{\"volume\": 20, \"wallpaper\": {\"md5\": \"bf22d39e91d67f54cf2b70de9669578c\", \"url\": \"http://sandyun.top:8002/yuhe/wallpaperMag/download/bf22d39e91d67f54cf2b70de9669578c.bin\", \"size\": 115200, \"scope\": \"global\", \"width\": 240, \"format\": \"rgb565\", \"height\": 240, \"version\": \"3-bf22d39e91d67f54cf2b70de9669578c\"}}',NULL,NULL,NULL,'2026-10-17 06:03:11');
INSERT INTO `ai_device_config` (`device_id`, `config_json`, `creator`, `create_date`, `updater`, `update_date`) VALUES ('e0:72:a1:f2:6f:3c','{\"wallpaper\": {\"md5\": \"bf22d39e91d67f54cf2b70de9669578c\", \"url\": \"http://sandyun.top:8002/yuhe/wallpaperMag/download/bf22d39e91d67f54cf2b70de9669578c.bin\", \"size\": 115200, \"scope\": \"global\", \"width\": 240, \"format\": \"rgb565\", \"height\": 240, \"version\": \"3-bf22d39e91d67f54cf2b70de9669578c\"}}',NULL,NULL,NULL,'2026-10-17 06:03:11');
/*!40000 ALTER TABLE `ai_device_config` ENABLE KEYS */;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;


-- ai_agent: id + wake_words only (5 rows)
INSERT INTO ai_agent (id, wake_words) VALUES ('1fdb4d8b44ac4a4cb59b7e6b13b15bdd', '');
INSERT INTO ai_agent (id, wake_words) VALUES ('2e29ed835c7049f887f9808411cf4f15', '');
INSERT INTO ai_agent (id, wake_words) VALUES ('32ff63483c0e4002974ef43666f76c88', '琳琳;玲玲;灵灵');
INSERT INTO ai_agent (id, wake_words) VALUES ('62ce730ce29e4f7d82b4b87264f1f215', '你好');
INSERT INTO ai_agent (id, wake_words) VALUES ('97254a564446432cba4b21e8fbb6dd74', 'guigui');
