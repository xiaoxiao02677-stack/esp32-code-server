# _archive-order-module（仅归档，禁止直接部署）

来源：`code-server-mirror/manager-api/src/main/java/xiaozhi/modules/order/`（旧本地服务端镜像，于 2026-10-15 外移归档到 `G:/demo/archive-20261015/code-server-mirror`）。

## 部署红线

该模块**从未部署到生产/测试环境**，且存在**路径双前缀缺陷**：Controller 的 `@RequestMapping` 与网关前缀叠加后会产生 `/xiaozhi/xiaozhi/...` 双前缀，导致接口 404。

**禁止**把本目录直接拷进 `yh/manager-api/src/main/java/xiaozhi/modules/order/` 后编译上线。若要启用，必须先修复路径前缀并经完整回归验证。

## 与生产 order 模块不是同一套代码

- 本目录（归档）：`OrderTableController / OrderTableDao / OrderTableDTO / OrderTableEntity / OrderTableService(+impl) / OrderTableVO`，共 7 个文件。
- 生产 `yh/manager-api/src/main/java/xiaozhi/modules/order/`：`OrderController / OrderMapper / OrderEntity / OrderService`，共 4 个文件，为**已部署**版本。

两者文件集合**无重叠**（逐个 diff 均为"生产缺失"），因此本目录是该 `OrderTable*` 变体的**唯一源码留存**，有独立保留价值。切勿与生产 order 模块混用或相互覆盖。
