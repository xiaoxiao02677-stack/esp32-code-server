# 豆包小何音色修复 + role-config 音色试听上线 runlog（2026-10-06 22:50–23:20 CST）

## 问题 1：豆包小何不能使用 — 根因与修复

### 根因（日志实锤）
```
core.providers.tts.doubao_v3 error: code=55000000,
message=resource ID is mismatched with speaker related resource
```
- 设备实际下发 `private_voice: zh_female_wanwanxiaohe_moon_bigtts`（婉婉小何，moon=1.0 系）
- resource_id 固定 `seed-tts-2.0` → 仅支持 uranus（2.0 系）音色
- 上一轮预置的 12 音色混入 moon/jupiter/wvae 系，账号只开通了 seed-tts-2.0 资源 → 8 个不可用
- 「小何」本身（zh_female_xiaohe_uranus_bigtts）直连可用，坏的是用户选的「婉婉小何」

### 账号音色实测（52 候选探针）
可用仅 5 个（均已购组合）：
- zh_female_xiaohe_uranus_bigtts（小何）
- zh_female_gaolengyujie_uranus_bigtts（高冷御姐）
- zh_female_vv_uranus_bigtts（VV 多方言）
- zh_female_shaoergushi_uranus_bigtts（少儿故事）
- zh_female_meilinvyou_uranus_bigtts（魅力女友）

### 修复动作
1. changelog 202610071200.sql 重新生成（gen_doubao_v3_seed.py）：音色表清为 5 条可用
2. 生产直导修复 SQL；agent「女友1」（a5115345278a45c68282ade58c4fdc3e）tts_voice_id V02→V01（真·小何）
3. 清 Redis 陈旧缓存 timbre:details/name:TTS_DoubaoV3_V02
4. 设备重连自动拉新配置（每次连接都拉差异化配置，无 agent 级缓存残留）

## 问题 2：role-config 音色试听 — 实现

### 架构（三栈）
- Python：`core/api/tts_preview_handler.py`（新）+ `core/http_server.py`（路由+回环中间件扩展 /api/tts/）
  - POST /api/tts/preview?voice=&text=，body=完整 TTS config_json（Java 查 DB 明文传入）
  - Bearer server.secret 鉴权 + 127.0.0.1 回环限制（沿 memory API 安全模式）
  - handler 在 aiohttp 事件循环内 → 直接 await provider.text_to_speak（不可 asyncio.run，踩坑1次）
- Java：`TtsPreviewController`（新）/models/ttsPreview（Shiro sys:role:normal）→ 查 getRawConfigJson → POST 127.0.0.1:8003
  - `ModelConfigService.getProviderType/getRawConfigJson`（新方法，raw 直读 DB 不脱敏）
  - `VoiceDTO` 加 providerType/ttsVoice 字段；`getVoiceList` 附带 providerType；`TimbreServiceImpl.getVoiceNames` 附带 ttsVoice
- 前端：roleConfig.vue
  - hasAudioPreview：已选 TTS 模型即显示播放键（原有 voiceDemo URL 逻辑保留，克隆音色优先）
  - playVoicePreview：无静态 URL → Api.model.ttsVoicePreview(modelId, ttsVoice) → blob objectURL 播放
  - model.js 新增 ttsVoicePreview（fetch + Bearer token 头，非 cookie）

### 踩坑记录
1. Python 初版查自身配置定位模型 → 全模块部署下全局配置无该 TTS → 404；改为 Java 传完整 config（更干净：凭据不出内网）
2. asyncio.run 嵌套事件循环报错 → await
3. Java @Parameters 缺 import → 编译失败 1 次
4. 服务器构建不含新 changelog 资源 → 已同步 SQL+master.yaml 到服务器源码树（本次 jar 未含，DB 已手工应用，下次构建自然带上）
5. tar 打包 G:/ 盘符路径需 MSYS_NO_PATHCONV=1
6. Java 接口业务码 401 但 HTTP 200（Result 包装惯例），用响应体判断而非 %{http_code}

## 部署与验证
- Python：tts_preview_handler.py + http_server.py 部署重启 active；直接 POST 测试 200/56KB WAV
- Java：服务器 mvn 构建 SUCCESS（85356223B），备份旧 jar 后部署重启 active（8002=200）
- 前端：npm build → rsync /var/www/xiaozhi-manager（index 200 / app.js 200，ttsPreview 在 app.790b3ff2.js）
- 端到端：Java 代理（带登录 token）5 音色全部 HTTP 200（94K–163K WAV）；无 token/坏 token → 401 JSON
- Web 备份：/root/backup/2026-10-08-doubao-v3/web-js-bak + jar.bak

## 回滚剧本
```bash
# Java: cp /root/backup/2026-10-08-doubao-v3/xiaozhi-esp32-api.jar.bak /opt/xiaozhi/xiaozhi-esp32-api.jar && systemctl restart xiaozhi-manager-api
# Web: rsync -a --delete /root/backup/2026-10-08-doubao-v3/web-js-bak/ /var/www/xiaozhi-manager/js/
# Python: 删 tts_preview_handler.py + 还原 http_server.py（git）+ restart
# DB: 音色表已由 202610071200.sql（幂等）重写；agent voice 已指向可用音色，无需回滚
```

## 遗留
- UI 验收（浏览器 /role-config → 选豆包模型 → 音色下拉点播放键）留给用户，PWA 强刷
- 若未来账号购买更多 2.0 音色，在音色管理手动添加即可（试听接口对任意 voice 通用）
