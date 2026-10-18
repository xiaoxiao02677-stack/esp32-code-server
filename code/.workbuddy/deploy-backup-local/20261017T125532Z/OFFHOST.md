# 异地副本说明（OFFHOST）

## 这是什么

sandyun.top 生产服务器上 `/root/deploy-backup/20261017T125532Z/` 的**完整异地副本**。
快照时间为 **2026-10-17 20:55:32 CST（UTC 20261017T125532Z）**，是本次发布（21:02 py / 21:04 jar / 21:05 前端）**之前的基线**。

## 来源

| 项 | 值 |
|---|---|
| 服务器 | sandyun.top:22222 (root) |
| 源目录 | `/root/deploy-backup/20261017T125532Z/` |
| 本地目录 | `G:/demo/21_xiaozhi/code/.workbuddy/deploy-backup-local/20261017T125532Z/` |
| 下载时间 | 2026-10-17 21:13 CST |
| 传输方式 | paramiko SFTP（逐文件 get，分块读，无 /tmp 中转） |
| 下载脚本 | `.workbuddy/pull_backup.py`（含双向 md5 校验） |

## 校验结论

**16 文件 md5 双向一致（本地 hashlib vs 服务器 md5sum），RESULT=PASS**，合计 172,101,698 B（164.1 MiB）；其中 10 项为回滚原件、5 项为发布后新制品、1 项为本说明。

| 相对路径 | 字节 | md5（本地 = 服务器） |
|---|---:|---|
| jar/xiaozhi-esp32-api.jar | 85504251 | 385db9779a6891e8c4e4742454b6fcb8 |
| py/core/services/wake_word_service.py | 8420 | 388dd075a4577e0d7cd415186e298aa0 |
| py/core/http_server.py | 26680 | f9bb20ba2c49123eaed81ef6323bf203 |
| py/core/api/wake_word_handler.py | 4083 | 5ef2c3a370cf9833cab3747002b80aef |
| db/ai_tables_full.sql | 19749 | 36d722bb8ae3884545cfb9077ec24ced |
| db/ai_tables_4tables.sql | 14076 | a6dd9fa27d79571b4c67bc5c24354936 |
| db/ai_tables.sql | 12534 | dcf35d172a135fdd9e0310be7bd9bc2c |
| web-admin.tar.gz | 178152 | f07f78564781fbdf4d03187ab50e8fb2 |
| jar-new/xiaozhi-esp32-api.jar | 85840471 | 4efef7161ab3ed69474bdb27ee5b468b |
| py-new/core/services/wake_word_service.py | 24745 | 38c7fe7734618af416c4f35818663b42 |
| py-new/core/http_server.py | 26890 | 1a8f01c8399d67bc6db62da1707fa25e |
| py-new/core/api/wake_word_handler.py | 7649 | 9588a97a9210c3db1ff9fffb0328bcc2 |
| web-new.tar.gz | 355984 | ab497e04fa93a9d353d71f50eff507fc |
| MANIFEST.txt | 56461 | b7382abdec98729cf0f83af6f57c085c |
| ROLLBACK.sh | 16372 | a235de40bfaf44a17eeb4ea87ed412c2 |

## 回滚方法（重要）

本地副本**不能直接执行**。脚本内路径全部是服务器绝对路径（`/opt/xiaozhi`、`/root/xiaozhi-server`、`/var/www/console-v2`、`/root/deploy-backup/...`），必须先把文件送回服务器对应路径：

```bash
# 1) 回传到服务器快照目录（保持相对结构）
#    可用 .workbuddy/push_file.py 逐文件 base64 上传（SFTP put 在本机到该服务器会 ENOENT）
MSYS_NO_PATHCONV=1 python push_file.py \
  "G:/demo/21_xiaozhi/code/.workbuddy/deploy-backup-local/20261017T125532Z/ROLLBACK.sh" \
  "/root/deploy-backup/20261017T125532Z/ROLLBACK.sh" 755
# 其余 jar/py/db/web-admin.tar.gz/MANIFEST.txt 同理逐个回传

# 2) 校验回传后 md5 与本文件表格一致

# 3) 再执行
bash /root/deploy-backup/20261017T125532Z/ROLLBACK.sh check
bash /root/deploy-backup/20261017T125532Z/ROLLBACK.sh all
```

若服务器整个 `/root` 丢失，则需先重建目录结构，再把 jar/py/web-admin.tar.gz 还原到运行路径（脚本里的 `do_jar` / `do_py` / `do_web` 逻辑可手工照抄）。

## 内含脚本能力（ROLLBACK.sh，16372 B）

- `check`：基线自校验 8 项 + 发布后快照校验 5 项 + 线上对比 + 健康断言（NRestarts / StartTimestamp / 端口 PID / 最近 200 行 Traceback）+ 只读路由探针（push=401 PASS / 404 FAIL）+ 功能级证据 WARN（不判失败）
- `jar` / `py` / `web`：回滚到 20:55 基线（py 三文件同批，systemd restart）
- `jar-new` / `py-new` / `web-new`：正向重放到 21:02–21:05 上线版
- `db`：仅打印指引，不自动执行
  - A1 首选 `db/ai_tables_full.sql`（四表含结构，含 DROP TABLE，执行前必须 dump 现场）
  - A2 `db/ai_tables_4tables.sql`（四表纯数据）
  - A3 `db/ai_tables.sql`（两表纯数据，降级；单独用会让 ai_device 绑定与 config 脱节）
  - C PITR：已降级为兜底且命令被注释（缺 `--start-position` 会整段重放，实害），真实起点 `13727846`
  - `config_json` 为原生 JSON，回灌只能 `mysql < file`

## 注意

1. 本副本**已含**发布后版本（`jar-new` / `py-new`×3 / `web-new.tar.gz`），可双向重放；仍缺 3 个 `mysqldump*.err`（仅密码警告，无信息量）。
2. `db/*.sql` 是**发布前基线数据**，不是当前生产数据。
3. 本副本与服务器快照相比少了 `db/mysqldump*.err`（仅密码警告，无信息量）。
4. 服务器快照**仍然保留**，未被删除或修改（除本轮新增的 MANIFEST 段与脚本更新）。
5. `MANIFEST.txt` 的 `[18]` 是事实更正追加段（`ai_device` 发布窗口内两行心跳写入 + PITR 回退影响），`[16]` 原文保留未改，便于审计演进。
6. `MANIFEST.txt` 的 `[19]` 是一次性合并追加：澄清 `ai_tables_full.sql`/`ai_tables_4tables.sql` 实际为 21:09/21:08 导出（非 20:55 基线），并说明两条回滚路径对 `44:bd.last_connected_at` 结果不同；同时记录 `POST /api/device-config/push → 401` 的运行态含义。**回灌后勿按「全字段一致」核对这两行。**
