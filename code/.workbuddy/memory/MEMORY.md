# yuhe（原 xiaozhi-esp32）项目记忆（长期索引）
> 2026-10-18 全仓改名 xiaozhi→yuhe（目录 yh/yuhe-server、Java包 yuhe、WS /yuhe/v1/、OTA /yuhe/ota/、产物 yuhe.bin；旧路径双兼容）。分库：服务端/OTA/壁纸/鉴权→topics/server-side.md；崩溃→topics/firmware-crash-cookbook.md；引脚→hardware/sets/README.md；皮肤→UI_SKIN.md；逐日→2026-*.md。

## 仓/git/ESP-IDF
- 仓根 G:/demo/21_xiaozhi：docs/ hardware/ yh/ third_party/ tools/ code/；分支 master；.workbuddy/.trash/不入库；构建产物不入库；yh_skin/未跟踪；改名切版型删 build/ 全量重编
- IDF v6.1：IDF_PATH=D:\INSTALL\esp\v6.1\esp-idf、IDF_TOOLS_PATH=D:\INSTALL\esp、venv D:\INSTALL\esp\tools\python\v6.1\venv。**idf.py Git Bash 假绿**→校验用 CMD/PS；编译用 IDF venv python；ESP_IDF_VERSION 必补
- tools/yh_syntax_check.py 参数相对 hardware/sets/yuhe-esp32/；改完 sets_diff_audit.py 必须 PASS

## sets 多版型+烧录
- build.py(--server prod|test)/flash.py(三道闸)/diag.py；背光 yh-154tft-wifi=BL20、yh-n16r8-st7789=42、yh-cam 唯一 AEC
- 硬约束：①config.json type/builds[].name 唯一 ^[a-z0-9.-]+$；②sdkconfig_append 真源；③CMakeLists board 分支4行含 DEFAULT_EMOJI_COLLECTION
- 16m.csv：ota_0 0x20000/ota_1 0x410000/assets 0x800000(无factory)；assets 全量烧；baud 230400
- 三道闸：layout 一致→回读→复位判循环；一镜像一会话升序 assets 垫底
- ★复位反相(COM18)：boot:0x13/0x32 反相、0x1b 标准；反相板同 flash_args 单会话只换复位
- 死机 bootloader_reset+rst:0x3=分区表app不同源→diag+flash --clean；COM12 独占

## LVGL 皮肤/壁纸
- 共享层 main/display/yh_skin/；改共享层必同步 hardware/sets/boards/<board>/ 源副本
- 基类占位族必修；持锁禁调 SetEmotion/SetTheme；换字体旧对象进退休池+全树改绑
- 壁纸 version 内容寻址幂等；dispatch 清 sent/offline；双壁纸 slots[2] boot 槽 NVS wallpaper_boot

## 语音链路(duplex 详 2026-10-22/23.md)
- 百炼全模态 TTS aliyun_multimodal.py app_id mm_8e05cd6cb37544dc9219f9d78c0f；实测音色仅15(龙14+loongbella)
- ★duplex：full_duplex:true 音频直推百炼。坑①opus encode N=样本数960非字节②上行固定16k(非 conn.sample_rate=24k下行)③推完持续推静音(20s断会话)④websockets UA 用 user_agent_header=
- ★音乐类空响应：百炼语音音乐请求返空(根因编排)。兜底 monitor 检测 Thinking 后无 RespondingStarted→本地对话兜底。**红线：绝不 transcript 重发用户原话**(死循环)；SpeechContent 全量覆盖非增量
- duplex技术文档：docs/duplex通信链路与实时打断逻辑.md(自包含，含12坑索引+§12回滚清单)
- duplex 打断：检测百炼VAD云端；★服务端打断桥已回滚(10-23 22:28 md5 e5be5845，非AEC板打断无收益；备份.bak-pre-rollback勿提交；音乐播放期不可语音打断，仅百炼自治轮+设备按钮)；非AEC板静音替换防回声；duplex 下 LLM/ASR/Intent/记忆全旁路
- ★dashscope SDK 不迁移(同步threading/保活不托管/两缺陷；换SDK空响应依旧)
- ★人设注入(10-24 已验证)：百炼控制台须在{x}自定义变量声明变量(**prompt 是系统保留名不可用，现用 prompts**)，正文 ${prompts} 引用；Start 帧 biz_params.user_prompt_params={"prompts":人设} 连接级；变量名配在 ai_model_config.config_json.prompt_variable(默认值 prompt)，改后清 model:data:+model:name: 缓存，设备重连生效
- log_level 真源 sys_params；"主人小智有点忙"先 grep LLM stream processing error
- ★音色自动探测(10-24 已上线；★10-24 深夜两轮修复)：Python POST /api/tts/voice-probe(push2talk+transcript合成探测,InvalidTtsVoice=确定性失效,其余限流/内部错走_TransientError指数退避重试)+Java /ttsVoice/probe(**参数是query的ttsModelId**非body；删失效/增有效/迁移引用/清缓存)+前端Voices.vue探测按钮；候选池**三池并集123个**(46个3.1+**62个cosyvoice-v2官方全量**+15个v3遗留)引擎无关自动适配,并发10,52s全量;测试服库名 xiaozhi_esp32_server、音色列名 languages(复数)；百炼官方无音色查询API,探测是唯一途径;**硬编码清单必须对照官方文档**(help.aliyun.com cosyvoice-voice-list 页超长WebFetch只回v3段,v2段从ISI长文本合成文档页拿),同名前缀不同版本音色名称性别可能完全不同;**百炼控制台引擎切换(如qwen-audio-3.1→cosyvoice-v2)后旧音色全InvalidTtsVoice,handler无日志排障须独立脚本直调百炼**
- ★duplex 第二轮起字幕消失(10-24 已修测试服)：sendAudioHandle.sendAudioMessage FIRST 分支只查 sentence_id 相等就 add_message 进流控队列，但 tts stop 已 stop_sending()、duplex 轮间 chat() 旁路致 sentence_id 永不更新→sentence_start 进死队列被 MIDDLE 触发的 reset() queue.clear() 丢弃；修复=流控条件追加 pending_send_task 存活校验（与 reset 判定对齐），任务死→立即直发。**生产未部署**。本地链路每轮新建 sentence_id 不踩坑，仅 duplex 复现

## 崩溃排查
- elf 同源(日志SHA256前9位==sha256sum yuhe.elf)；EXCVADDR=0x14+lv_event_mark_deleted=event_head悬垂；PC=0x0+Refreshing theme=字体已释放

## 子代理/多开
- teamCancelled 置 true 后 team 砖化不清不自愈；批量 spawn 显式唯一 name 单轮≤6-8

## 生产(sandyun.top:22222)/测试(22223)
- 生产：Java /opt/xiaozhi/yuhe-esp32-api.jar(8002,systemd xiaozhi-manager-api,外置配置 application-dev.yml 只覆盖URL/Tomcat/AES)+Python /root/xiaozhi-server(8000WS/8003http)+前端 /var/www/console-v2/{app,admin}；**前端真实入口 https://sandyun.top:8001/**(443/5001 是端口跳转页)；MySQL root/123456(jar内置)
- ★测试服已重组(10-23)：Python → /root/yh/app/xiaozhi-server、Java → /root/yh/deploy/opt-xiaozhi/yuhe-esp32-api.jar(dev)；MySQL debian-sys-maint
- ★★测试服前端部署真目录(10-25 踩坑)：nginx web根=/var/www/console-v2/admin/（`/` 与 `/admincc/` 两 URL 同指此目录，index.html 引 /admincc/assets/ 前缀但文件在 admin/assets/）；**app/ 与 admincc/ 目录不在任何 location，传了=死目录**（10-25 XDDPay 前端+manual-dismiss 两轮曾误传 admincc/，当晚发现已补传 admin/ 纠正）；部署口诀：dist-admin/*→admin/、dist/*→app/、传完 find 清旧 hash、md5 对比本地
- ★生产前端两目录同批更新(app/根路径进管理页走它+admin/)；顺序 Java→Python→Web；Python三文件同批；验 inode；MySQL datetime UTC 早8h
- 测试：OTA/WS 8144明文；YH心跳8199；OTA带 Device-Id 头(冒号MAC)；全量切 /yuhe/；Liquibase 红线勿改已执行 changeset
- 壁纸URL幂等只比version；下载URL由 sys_params.server.ota 推导
- 测试登录：uuid→captcha→Redis读值→sm2→token UPDATE sys_user_token

## Git Bash/推送
- MSYS 改写 / 开头参数→MSYS_NO_PATHCONV=1；sftp_push.py 硬编码22222，测试须 connect(port=22223) 曾误推生产

## 配置真源(manager-api)
- config.yaml 大部分键无效，配置整包从 Java /config/server-base 拉。**系统参数改 sys_params：UPDATE→redis-cli DEL server:config→重启，先UPDATE后清缓存**。Java模型配置改DB须 del model:data:{id} model:name:{id}。服务 venv .venv/bin/python

## 前端API陷阱
- POST /device/bind/{agentId}=MQTT转发；已绑列表真契约 GET /device/bind/{agentId}。/agent/list 设备数=deviceCount
- ★移动端适配(10-24 测试已部署)：global.css 尾部 @media≤768 骨架层（dock→底部标签栏/画布全宽/表格横滚 min-width:560/modal 94vw/按钮换行）+12 页 scoped 补丁；480 超窄层+hover:none 触屏反馈；改移动端布局先看 global.css 尾部规则再写页面级覆盖；★跨断点覆盖必须匹配选择器特异性（900px 的 html:not(.dock-collapsed) 前缀 (0,2,1) 曾压过 768px 的 .dock (0,1,0) 致手机 dock 钳 64px）
- ★商店模块已删(10-24 测试)：前端 8 文件+路由+导航+API 段全清；后端 Goods/Cart/Order Controller 与三表保留仅不可见；DisplayConfig ADMIN_MODULES 同步删
- ★共享授权(10-24 已推生产)：ai_agent_share(user/role)；hasAgentPermission/getUserAgents(超管看全部)/getUserDevices(共享用户看agent名下全部)三生效点+删除级联+视同自建增删改查(10-23第三轮：unbind/updateDeviceInfo/manualAddDevice 三处补齐+customer前端编辑删除入口)；端点 GET/PUT /agent/{id}/shares；前端Agents.vue抽屉(仅超管可见)。生产已于 10-24 部署(md5 439debac4646)，解绑假成功bug已随包修复
- ★/user/resources 契约(10-24 已推生产)：keys=[llmModels,ttsVoices]。llmModels=平台启用LLM(过滤占位api_key)+本人审核通过自定义；**生产DB列名 is_enabled/is_default(无status列)**、设备表 ai_device(无last_active，活跃看nginx access log)；-N模式2>/dev/null会吞SQL列名错误→误判空表
- ★改密契约(10-24 已推生产)：PUT /user/change-password body 字段是 **password**+newPassword（非 oldPassword！前端曾因字段名不匹配误报"密码不能为空"）；登录分流(10-24 已推生产)：defaultRouteAfterLogin=hasAdminRole→/admin 其余→/customer，TopBar/DockNav 切换按钮已删，demo 特例已删(demo 超管进管理端)；冒烟 UPDATE token 须同时顺延 expire_date
- mvn：JAVA_HOME=/d/INSTALL/jdk21 + /d/INSTALL/maven/mvn/bin/mvn.cmd；测试服活跃超管=demo(非admin)；debian-sys-maint 可操作 MySQL（仅测试服；生产 MySQL=root/123456 jar内置）

## 待办
- 百炼音乐插件检查(用户)；天气prompt weather_info 二选一；OTA checkDeviceActive NPE；git提交积压；音色切换第二期；支付宝 sys_params pay.alipay.*(mvn OOM MAVEN_OPTS=-Xmx1024m)
