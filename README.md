# esp32-code-server

小智 ESP32 智能硬件项目总仓。核心代码按「固件 / web 后台」分为两大目录，第三方与工具独立归类。

## 目录导航

| 路径 | 内容 |
|---|---|
| **`hardware/`** | **固件源码（ESP32 端）** |
| `hardware/big_secreen/yuhe-esp32/` | 大屏固件工作区（ESP-IDF，独立 .aoci 治理） |
| `hardware/small_secreen/yuhe-esp32/` | 小屏固件**主工作区**（my-s3-tft 板，COM12） |
| `hardware/small_secreen_test/` | 小屏试验沙盒（本地不入库） |
| `hardware/camera/` | 摄像头板固件（上游完整仓嵌套 git，lckfb/szpi-esp32s3，IDF v6.1） |
| `hardware/small_screen_camera/` | 摄像头板×小屏工作区（活跃开发中） |
| `hardware/{fixes,artifacts,tests}/` | 固件相关补丁、取证样本、测试工具（含 push-audio RCA 与链路模拟器） |
| **`yh/`** | **web 后台与服务端源码**（后端从生产 22222 同步） |
| `yh/manager-api/` | Java 后端源码（含 AdminApplication、modules） |
| `yh/manager-web/` | 管理台前端源码（含运行必需的 public/generator 资源） |
| `yh/yuhe-server/` | Python 服务端（app.py、core/、config.yaml） |
| `yh/console-v2/` | 生产管理台前端源码（app + admin 双构建） |
| `yh/cc-console/` | 旧版控制台前端（线上 /cc/ 仍在用） |
| `yh/_archive-order-module/` | order 模块归档（**两套 order 不可混用，部署红线见项目记忆**） |
| `third_party/` | 第三方参考仓：hermes-agent-main（agent 框架）、stylekit（UI 样式库） |
| `tools/aoci-code/` | AOCI 治理工具源码（Go） |
| `docs/` | 项目文档（PRD、交接手册、验收清单、归档区） |
| `code/` | 剩余工作产物（reports 报告、.workbuddy 记忆） |

## 运维速查

- 生产：`ssh -p 22222 root@sandyun.top`；测试：`ssh -p 22223 root@sandyun.top`
- 生产后端源码位置：`/root/xiaozhi-server/main/`（manager-api / manager-web / yuhe-server）
- 测试环境根：`/root/yh/`（app/manager-api、app/yuhe-server）
- 生产前端部署位置：`/var/www/console-v2/{app,admin,firmware-flash}` + `/var/www/cc-console/`
- 详细环境拓扑、部署流程、红线事项见 `docs/PROJECT-HANDOFF.md` 与 `code/.workbuddy/memory/MEMORY.md`

## 同步说明

`yh/` 后端源码于 2026-10-15 从生产服务器（22222 `/root/xiaozhi-server/main/`）同步，已排除构建产物（`target/`、`node_modules/`、`dist/`、`models/`、`data/`、`.venv/`、`.webpack_cache/`、日志与 `*.bak`）。
`yh/manager-web/public/generator/`（约 75M）为上游 yuhe-assets-generator 打包成品，被 DeviceManagement.vue 直接引用且本地无法重建，**必须入库**。
