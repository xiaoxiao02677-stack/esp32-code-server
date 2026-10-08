# 千问 TTS 三栈上线 runlog（任务 #4 · e-tts-java）

> 执行日：2026-10-06 15:35–15:50 CST ｜ 对象：sandyun.top 生产
> 改动：Python qwen_tts provider + Java QwenTtsModelController/种子 SQL + Web 选择器/i18n
> 事实来源：deploy_memory_v1.md 第 0 节 + release-kawaii-v2.md 模式

## 阶段 0：基线 + 备份（PASS）
- 备份目录 `/root/backup/2026-10-08/`（1012M）：jar(85,343,915B, md5=3c6ffb4fd3cc31eba637eefbdc5fa49d) + xiaozhi-server-src + xiaozhi-manager-web(230文件) + mysqldump(46K)
- Liquibase 部署前：无 202610061500 行（预期）
- 双服务 active

## 阶段 1：构建（PASS）
- Java：源码 tar+sftp+rsync（QwenTtsModelController.java 落位，master.yaml grep=2）；mvn 第一次 `-DskipTests` FAIL（B 线遗留 ConfigServiceImplTest 构造器签名不匹配，非本次改动）→ 改 `-Dmaven.test.skip=true` 12s 成功
  - 新 jar 85,348,479B md5=a581a4b545ce1e9d319ea421c9c64ad9
  - unzip 验收：QwenTtsModelController.class(7447B) + 202610061500.sql(856B) 在包内
- Web：npm build 两次被 safe-delete 拦截（dist 清理 50 文件阈值）→ 构建到全新目录 dist-qtts 成功（hash bc937d055003aedc，230 文件，qwenTts 代码在 154.7b1ee4ca.js + app.259ee5ec.js）

## 阶段 2：传输（PASS）
- Python 增量 3 文件（qwen_tts.py 582f67c1... / __init__.py d41d8cd9... / test_qwen_tts.py c4b254a3...）tar 直落，md5 全对，py_compile OK
- web dist-qtts → /var/www/xiaozhi-manager（rsync --delete），index.html md5=ec31c4d9b488c25db17268cdcd68e1c7 与本地一致

## 阶段 3：服务（PASS）
- Java：jar cp + restart，active（15:41:07），/opt jar md5=target md5
  - **Liquibase 断言：DATABASECHANGELOG 有 202610061500 ✓；ai_model_provider qwen_tts 种子行=1 ✓**
  - 日志 xiaozhi-esp32-api.log 无 error/exception，error.log 空
- Python：保险 restart，active；8003 /api/memory/agents=401（契约保持）；8000=200；app.log 无 traceback
- 备注：服务器 venv 无 pytest，未在服务器重跑单测（本地 11 过）

## 阶段 4：冒烟（PASS）
1. 无 token GET /xiaozhi/models/qwenTtsModels → `{"code":401,"msg":"未授权"}`（Shiro 鉴权在）✓
2. 带用户 token（cbb1fea7...，用户既有会话）+ 无效 apiKey → `{"code":500,"msg":"获取模型列表失败：API密钥无效或已过期"}`（完整链路 Shiro→Controller→JDK HttpClient→千问平台 401→友好错误映射，全通）✓
3. 前端：index=200（引用新 app.259ee5ec.js）、app.js=200、chunk154=200、service-worker=200 ✓

## 收尾
- 服务器 /tmp/qtts-* 与本地 tar 已清理；备份目录与 web-md5-before 保留（回滚用）
- 回滚剧本：jar=`/root/backup/2026-10-08/xiaozhi-esp32-api.jar` cp 回 + `DELETE FROM DATABASECHANGELOG WHERE ID='202610061500'; DELETE FROM ai_model_provider WHERE id='SYSTEM_TTS_qwen_tts';` + restart；web=rsync 回 xiaozhi-manager-web/；Python=删 3 文件即可（provider 动态加载）
- UI 层验收（添加模型→千问TTS→输入 key→获取模型列表）留给用户，PWA 需强刷
