
==============================================================================
 sandyun.top 生产发布验收报告（只读）
==============================================================================

[PASS] J-01 service active
        期望: systemctl is-active = active
        实际: active（active/running/，ActiveEnter=Sat 2026-10-17 21:04:19 CST）

[PASS] J-02 本轮重启时间
        期望: 进程 30 分钟内启动
        实际: 进程已运行 944s

[PASS] J-03 jar 磁盘 md5
        期望: 4efef7161ab3ed69474bdb27ee5b468b
        实际: 4efef7161ab3ed69474bdb27ee5b468b  /opt/xiaozhi/xiaozhi-esp32-api.jar（4980818 85840471 1792242257）

[PASS] J-04 运行中 jar inode
        期望: fd inode == 磁盘 inode(4980818)
        实际: @@FD /proc/675741/fd/4 -> /opt/xiaozhi/xiaozhi-esp32-api.jar inode=4980818; @@FD /proc/675741/fd/5 -> /opt/xiaozhi/xiaozhi-esp32-api.jar inode=4980818

[PASS] J-05 jar 与进程新老关系
        期望: 进程启动时间 >= jar mtime
        实际: 进程启动 1792242259 >= jar mtime 1792242257（差 2s）

[PASS] J-07 回滚件在位
        期望: jar 同级存在 .bak* 备份
        实际: 23 个：/opt/xiaozhi/xiaozhi-esp32-api.jar.bak-v3,/opt/xiaozhi/xiaozhi-esp32-api.jar.bak-wakeword-20261017,/opt/xiaozhi/xiaozhi-esp32-api.jar.bak-wcdeploy,

[PASS] J-06 manager-api 监听 8002
        期望: 8002 LISTEN
        实际: 命中 1 行；cmdline=/usr/bin/java -jar /opt/xiaozhi/xiaozhi-esp32-api.jar --spring.profiles.active=dev

[PASS] P-01 单进程
        期望: 恰好 1 个 python app.py
        实际: 1 个：674256 六 10月 17 21:02:52 2026 1032 /root/xiaozhi-server/main/yuhe-server/.venv/bin/python app.py

[PASS] P-02 yuhe-server unit
        期望: systemctl is-active = active
        实际: active；进程 etimes=1032s；启动于 六 10月 17 21:02:52 2026

[PASS] P-03 wake_word_service md5
        期望: 38c7fe7734618af416c4f35818663b42
        实际: 38c7fe7734618af416c4f35818663b42  mtime=2026-10-17 21:02:50.738263477 +0800

[PASS] P-04 http_server 含新路由
        期望: /api/device-config/push 出现 >=1 次（路由注册处）
        实际: 命中 1 次；md5=1a8f01c8399d67bc6db62da1707fa25e mtime=2026-10-17 21:02:50.747156666 +0800（本次未给 http_server.py 基线 md5，md5 仅存档）

[PASS] P-05 wake_word_handler 下发函数
        期望: handle_push_device_config 存在
        实际: 命中 1 次

[PASS] P-06 Python 监听 8000/8003
        期望: 8000 与 8003 均 LISTEN
        实际: 8000=1 8003=1；LISTEN 0 100 0.0.0.0:8000 0.0.0.0:* users:(("python",pid=674256,fd=17)) |LISTEN 0 128 0.0.0.0:8003 0.0.0.0:* users:(("python",pid=674256,fd=18)) |LISTEN 0 100 *:8002 *:* users:(("java",pid=675741,fd=148)) |

[PASS] F-01 admin/index.html md5
        期望: 4fb703fa03ac224938d5115edea770eb
        实际: 4fb703fa03ac224938d5115edea770eb  mtime=2026-10-17 21:05:37.312117213 +0800

[PASS] F-02 index.html 引用新 hash
        期望: 含 index-CR0JikiI.js
        实际: 命中 1 次；文件内所有 index-*.js 引用 = assets/index-CR0JikiI.js,

[PASS] F-03 新 asset 指纹
        期望: md5=9f5d974f3893d8c9733064123e7ccec5 size=510157
        实际: md5=9f5d974f3893d8c9733064123e7ccec5 size=510157

[FAIL] I-01 /admin/ 入口
        期望: 200 且返回体含新 hash
        实际: code=000 size=0 hash_hits=0 —— 200 也可能是旧 index，必须比对返回体内容

[FAIL] I-02 /admincc/ 入口
        期望: 200 且返回体含新 hash
        实际: code=000 size=0 hash_hits=0 —— 200 也可能是旧 index，必须比对返回体内容

[FAIL] I-03 新 asset 可下载
        期望: 200 且 size=510157
        实际: code=000 size=0 —— 404/403 说明 nginx root 与部署目录不一致

[FAIL] I-04 OpenAPI 可匿名访问
        期望: 至少一个 /yuhe/v3/api-docs* 返回 200 且 >2KB
        实际: /yuhe/v3/api-docs: 000/0B; /yuhe/v3/api-docs/agent: 000/0B; /yuhe/v3/api-docs/config: 000/0B —— OpenAPI 拿不到，后续字段断言全部失效；先确认 jar 是否起来、Shiro 的 /v3/api-docs/** anon 是否还在

[SKIP] I-05 DTO 含新字段
        期望: wakeWordThreshold + interruptThreshold
        实际: 依赖 I-04

[PASS] I-07 Python 新路由已注册
        期望: POST 无 token → 401 {"code":401}
        实际: code=401 body={"code":401,"msg":"无效的认证token","data":null}；GET 同路径=405（405 也说明路由存在）

[PASS] I-08 路由对照组
        期望: 老路由同样 401（400/403 亦可）
        实际: 新路由=401；老路由 /api/wake-word/devices=401（body {"code":401,"msg":"无效的认证token","data":null}）；/api/memory/agents=401 —— 三条并列正常，404 只可能来自应用层

[PASS] L-01 Java 启动日志
        期望: 启动(Sat 2026-10-17 21:04:19 CST)后无 ERROR/Exception
        实际: Oct 17 21:04:19 sand-VMware20-1 systemd[1]: xiaozhi-manager-api.service: Main process exited, code=exited, status=143/n/a
              Oct 17 21:04:19 sand-VMware20-1 systemd[1]: xiaozhi-manager-api.service: Failed with result 'exit-code'.
              Oct 17 21:04:19 sand-VMware20-1 systemd[1]: Stopped xiaozhi-manager-api.service - Yuhe Manager API (Spring Boot).
              Oct 17 21:04:19 sand-VMware20-1 systemd[1]: xiaozhi-manager-api.service: Consumed 2min 56.511s CPU time, 913.5M memory peak, 0B memory swap peak.
              Oct 17 21:04:19 sand-VMware20-1 systemd[1]: Started xiaozhi-manager-api.service - Yuhe Manager API (Spring Boot).

[PASS] L-02 Python 启动日志
        期望: 启动(261017 21:02:47，已前拨 5s)后无 Traceback/ERROR
        实际: 本轮切片 108 行内未发现 Traceback/ERROR；历史异常 19 条位于窗口外（data/app.log:27），不计入本轮。（无前缀行按上一条时间戳继承归属）尾部：
              261017 21:19:05[0.9.7-00000000000000][core.heartbeat]-INFO-心跳 [yuhe-44bd8d7b3ae4] 117.67.213.203:19484
              261017 21:19:30[0.9.7-00000000000000][core.heartbeat]-INFO-心跳 [yuhe-44bd8d7b3ae4] 117.67.213.203:19484
              261017 21:19:55[0.9.7-00000000000000][core.heartbeat]-INFO-心跳 [yuhe-44bd8d7b3ae4] 117.67.213.203:19484
              WARNING:core.api.wake_word_handler:[core.api.wake_word_handler] 鉴权失败（token为空或服务端未配置auth_key）
              WARNING:core.api.wake_word_handler:[core.api.wake_word_handler] 鉴权失败（token为空或服务端未配置auth_key）

[WARN] L-03 正向链路已触发
        期望: 本轮切片出现「已下发云端设备配置」或推送日志
        实际: 0 条 —— **尚未验证**（不是通过）。pinyin4j / WakeWordPinyinUtils 首次调用才初始化，冷启动不加载，接口 200 不能证明拼音链路可用；需在管理端保存一次唤醒词或让设备重连后重跑。

[PASS] L-04 负向用例命中
        期望: 出现预期 WARNING（不是故障）
        实际: 32 条：鉴权失败/忽略未知键/忽略越界/无目标设备 —— 说明探针真实打到了新代码；这些不计入 L-02

[SKIP] B-01 阈值已落库
        期望: ai_device_config 出现 wake_word_threshold / interrupt_threshold
        实际: 未提供 --db-cmd 或 XZ_MYSQL_CMD（形如 mysql -uroot -p*** xiaozhi_esp32_server）；人工 SQL 见 verify_plan.md §3

[SKIP] B-02 唤醒词双键成对
        期望: wake_word 与 wake_word_display 同长同序
        实际: 同上

------------------------------------------------------------------------------
合计 29 条：PASS=21  FAIL=4  WARN=1  SKIP=3
FAIL 列表：I-01 /admin/ 入口、I-02 /admincc/ 入口、I-03 新 asset 可下载、I-04 OpenAPI 可匿名访问
结论：发布未达验收标准，按 verify_plan.md 的排查动作逐条定位。
==============================================================================
耗时 20.5s；jar=/opt/xiaozhi/xiaozhi-esp32-api.jar；py_root=/root/xiaozhi-server/main/yuhe-server