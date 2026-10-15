# esp32-code-server

小智 ESP32 智能硬件项目总仓：固件（大屏/小屏/摄像头板）+ 服务端源码镜像 + 管理控制台前端 + 治理与交付产物。

## 目录导航

| 路径 | 内容 |
|---|---|
| `code/big_secreen/xiaozhi-esp32/` | 大屏固件工作区（ESP-IDF，独立 .aoci 治理） |
| `code/small_secreen/xiaozhi-esp32/` | 小屏固件**主工作区**（my-s3-tft 板，COM12） |
| `code/small_secrenn_test/` | 小屏试验沙盒（本地不入库；与主区差异见项目记忆） |
| `code/camera/` | 摄像头板固件（上游完整仓嵌套 git，lckfb/szpi-esp32s3，IDF v6.1） |
| `code/super_small_screen/` | 早期小屏原型（已被 small_secreen 取代，归档） |
| `code-server-mirror/` | 服务端源码本地镜像（Java manager-api + manager-web + Python xiaozhi-server） |
| `console-v2/` | 生产管理台前端（app + admin 双构建，源码权威副本） |
| `cc-console/` | 旧版控制台（线上 /cc/ 仍在用） |
| `hermes-agent-main/` | 上游 agent 框架参考仓（.aoci 治理） |
| `stylekit/`、`aoci-code/` | UI 样式库参考 / AOCI 治理工具源码 |
| `code/fixes/`、`code/reports/`、`code/tests/` | 修复补丁 / 报告（RCA、审计）/ 测试工具 |
| `docs/` | 项目文档（PRD、交接手册、验收清单、归档区） |

## 运维速查

- 生产：`ssh -p 22222 root@sandyun.top`；测试：`ssh -p 22223 root@sandyun.top`
- 生产前端部署位置：`/var/www/console-v2/{app,admin,firmware-flash}` + `/var/www/cc-console/`
- 详细环境拓扑、部署流程、红线事项见 `docs/PROJECT-HANDOFF.md` 与 `code/.workbuddy/memory/MEMORY.md`
