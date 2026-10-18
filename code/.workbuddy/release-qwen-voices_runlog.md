# 千问TTS音色管理默认数据上线 runlog（2026-10-06 18:19–18:45 CST）

> 任务：/model-config 页面音色管理里 Qwen 模型音色为空 → 注入默认音色 + 预填 base_url
> 环境：sandyun.top 生产（工具 ssh_run.py / sftp_push.py，MSYS_NO_PATHCONV=1 必加）

## 背景与根因
- 线上已有 4 个 Qwen TTS 模型（TTS_QwenTTS_Flash/Instruct、TTS_QwenAudio_Flash/Plus，api_key 已由 202610061700.sql 填入）
- 音色管理弹窗数据源是 `ai_tts_voice` 表按 `tts_model_id` 查询（TimbreServiceImpl.page，无缓存）
- 根因：`ai_tts_voice` 表里 4 个 Qwen 模型 0 条音色记录 → 弹窗为空

## 用户提供的凭据（已实测）
- base_url1：`https://maas.qianwenaiapi.com/compatible-mode/v1` → OpenAI 兼容端点，/models 200（262 个模型，17 个 tts）✓
- base_url2：`https://maas.qianwenaiapi.com/apps/anthropic` → Anthropic 协议端点（LLM 用，与 TTS 无关，不用于 TTS 配置）
- api_key：`sk-ws-H.PRYRHYR...`（已在线上 4 模型 config_json）
- 合成验证：qwen3-tts-flash + Cherry 经 multimodal-generation 端点返回 output.audio.url ✓

## 改动内容（全部幂等）
1. `code-server-mirror/manager-api/src/main/resources/db/changelog/202610071100.sql`（新增，程序化生成）
   - provider `SYSTEM_TTS_qwen_tts` fields 追加 `base_url`（服务地址）字段 → 编辑对话框可见可改
   - 4 模型 config_json 补 `base_url=https://maas.qianwenaiapi.com/compatible-mode/v1`（仅缺失时）
   - 音色注入 98 条：Flash 48 / Instruct 24 / Audio-Flash 12 / Audio-Plus 14（名称带中文、语种分普通话/国际音色/方言）
2. `db.changelog-master.yaml` 注册 202610071100 changeSet
3. 生成脚本 `G:/demo/21_xiaozhi/code/.workbuddy/gen_qwen_tts_seed.py`（唯一生成源，校验器 validate_qwen_seed.py）

## 执行记录
- 备份：`/root/backup/2026-10-08-qtts-voice/`（ai_tts_voice 48K + ai_model_config 31K，md5 已登记）
- 传输：sftp_push.py 上传 /tmp/202610071100.sql，md5=49a88b5a0d47ab028f94f0faf227c245 双端一致
- 执行：mysql --default-character-set=utf8mb4 直接导入（Liquibase 登记靠下次 jar 重启自动补跑，UPDATE 条件幂等不冲突）
- 验证：
  - DB：4 模型音色 48/24/12/14=98 ✓，base_url 全部就位 ✓，中文无乱码 ✓，provider fields 含 base_url ✓
  - API（本机 8002，demo 用户既有 token）：
    - GET /yuhe/ttsVoice?ttsModelId=TTS_QwenTTS_Flash → code=0 total=48（Cherry/Serena/Ethan…）✓
    - GET /yuhe/models/list?modelType=TTS → 4 个 Qwen 行 base_url 就位、api_key 正常脱敏 ✓
- 服务：xiaozhi-manager-api active 未重启（无 Java 代码改动，直改 DB 即时生效）
- 清理：/tmp/202610071100.sql、/tmp/jarx 已删

## 回滚剧本
```bash
# 恢复两张表
mysql -uroot -p123456 xiaozhi_esp32_server < /root/backup/2026-10-08-qtts-voice/ai_tts_voice_before.sql
mysql -uroot -p123456 xiaozhi_esp32_server < /root/backup/2026-10-08-qtts-voice/ai_model_config_before.sql
# 删除 Liquibase 登记（若 jar 已重启过）
mysql -uroot -p123456 xiaozhi_esp32_server -e "DELETE FROM DATABASECHANGELOG WHERE ID='202610071100';"
# 本地镜像删除 changelog/202610071100.sql 与 master.yaml 注册行
```

## 遗留说明
- 镜像 202610071100.sql 已注册但线上 jar 未重启：下次重启时 Liquibase 会补登记（SQL 幂等，重跑无副作用）
- apps/anthropic baseurl 未写入配置（Anthropic 协议端点面向 LLM 客户端，TTS 不适用）；若后续接 Claude 协议 LLM 可另配
- UI 验收（浏览器打开 /model-config → TTS → 音色管理）留给用户，PWA 需强刷
