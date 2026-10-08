# 豆包TTS v3 上线 runlog（2026-10-06 21:56–22:20 CST）

> 任务：用户凭据接入豆包语音合成（v3 HTTP 端点）
> 环境：sandyun.top 生产（ssh_run.py / sftp_push.py，MSYS_NO_PATHCONV=1）

## 凭据实测（用户提供）
- appID: 2717008086 / accessToken: W6P9P9w4...（旧版双头鉴权）→ **有效**
- apikey: d9f77dba-...（新版单头，备用）
- SecretKey: wy25ZXwk...（仅控制台签名场景，HTTP 端点不使用）
- 用户给的 baseurl `https://openspeech.bytedance.com/api/v3/tts/create` 是 seed-audio-1.0 **音频生成创作端点**（非实时 TTS）
- 正确的 v3 一次性合成端点：`POST /api/v3/tts/unidirectional`（查官方文档 + 实测确认）
- 响应格式：HTTP chunked，每个 chunk 一个 JSON `{"code","message","data"}`，data 为独立 base64 音频分片（可能无填充符），末片 data=null code=20000000

## 改动内容
1. **Python Provider**（新）：`core/providers/tts/doubao_v3.py`
   - 双鉴权模式：有 api_key 走 X-Api-Key 单头；否则 X-Api-App-Id + X-Api-Access-Key 双头（与实测一致）
   - chunked JSON 流解析：JSONDecoder.raw_decode 逐对象提取，分片独立 base64 解码（补填充）后拼接
   - 支持 private_voice/speaker、format/sample_rate/speech_rate/loudness_rate
2. **契约单测**（新）：`tests/core/providers/tts/test_doubao_v3.py` 12 用例（鉴权头×2/payload/private_voice/chunked拼接/无填充base64/写盘/HTTP错误/业务错误/空音频/畸形分片/默认值）——本地 12/12 PASS（PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 绕 dash 插件缺 flask；conftest 全模块 fail-fast 用临时改 data/.config.yaml 再还原的方式绕过）
3. **种子 SQL**（新）：changelog `202610071200.sql`（生成脚本 .workbuddy/gen_doubao_v3_seed.py）
   - provider `SYSTEM_TTS_doubao_v3`（11 字段，sort=22）
   - 模型 `TTS_DoubaoV3`（豆包语音合成v3(HTTP)，sort=28，凭据已预填）
   - 音色 12 个（豆包 2.0 精选：小何/婉婉小何/高冷御姐/VV/开心/北京小爷/东北黑润/少年自心/M392/凯哥/主播/Rapunzel）
   - 已注册 db.changelog-master.yaml（id 202610071200）

## 部署记录
- 备份：`/root/backup/2026-10-08-doubao-v3/tables_before.sql`（三表，md5 f6c9963a）
- 传输：3 文件 sftp 上传，md5 双端一致（provider b44d08bf / test 892c5044 / sql cb973dbf）
- 落位：`/root/xiaozhi-server/main/xiaozhi-server/core/providers/tts/doubao_v3.py` + tests；py_compile OK
- 真机合成：服务器 venv 直跑 provider → 144756 字节 WAV（RIFF 头正常）LIVE TEST OK
- SQL 导入：直导成功（provider 动态加载，无需重启 Python 服务；Liquibase 登记待下次 jar 重启自动补，幂等安全）
- API 验证：
  - `GET /xiaozhi/models/list?modelType=TTS` → TTS_DoubaoV3 在列，enabled=1，凭据字段齐全
  - `GET /xiaozhi/ttsVoice?ttsModelId=TTS_DoubaoV3` → code=0 total=12（中文名称+语种正常）
- 清理：/tmp 三文件已删；服务日志无异常

## 回滚剧本
```bash
# DB 三表恢复
mysql -uroot -p123456 xiaozhi_esp32_server < /root/backup/2026-10-08-doubao-v3/tables_before.sql
# Liquibase 登记（若 jar 已重启过）
mysql -uroot -p123456 xiaozhi_esp32_server -e "DELETE FROM DATABASECHANGELOG WHERE ID='202610071200';"
# Python 文件删除即可（provider 动态加载）
rm /root/xiaozhi-server/main/xiaozhi-server/core/providers/tts/doubao_v3.py /root/xiaozhi-server/main/xiaozhi-server/tests/core/providers/tts/test_doubao_v3.py
# 本地镜像删除对应文件 + master.yaml 注册行
```

## 遗留说明
- Java 不需要改动（provider fields 驱动表单，模型列表/音色列表 API 均为通用接口）
- 前端不需要改动（AddModelDialog/ModelEditDialog 按_provider fields 动态渲染）
- UI 验收：控制台 → 模型配置 → 语音合成 → 豆包语音合成v3(HTTP) → 音色管理（12 音色可选）
