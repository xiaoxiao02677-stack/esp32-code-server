# 前后端 API 契约（Contract）

**唯一事实来源（FR-01）**：`openapi.json` —— 由后端 springdoc（`/xiaozhi/v3/api-docs`）导出，
覆盖 **141 端点 / 173 方法**。前端所有请求必须能在此文件中找到匹配定义。

## 文件说明

| 文件 | 用途 |
|---|---|
| `openapi.json` | 后端契约快照（当前生产 jar 生成）。**接口变更后必须重新导出**（FR-12/FR-14） |
| `exceptions.json` | 例外登记（FR-15）：无法走统一封装的调用，含原因/替代方案/负责人 |
| `check-report.json` | 最近一次校验报告（CI 产物） |

## 校验（FR-13）

```bash
python scripts/check_contract.py --report contract/check-report.json
```

- 扫描 `src/App.vue` 全部 `this.api()` 调用与直连 `fetch`，比对契约（方法+路径）
- 模板参数自动归一化（`/agent/${id}` ≡ `/agent/{id}`），query 自动剥离
- 结果 PASS（退出码 0）/ FAIL（退出码 1，CI 可直接拦截）
- 直连 fetch 未登记例外的 → FAIL

## 变更流程（FR-12）

1. **先改契约**：后端加/改端点后，重新导出：
   ```bash
   # 生产 jar 运行时
   curl http://127.0.0.1:8002/xiaozhi/v3/api-docs -o contract/openapi.json
   ```
2. 跑 `python scripts/check_contract.py` —— 新契约下前端旧调用若失效立即暴露
3. 前端同步修改 → 再跑校验 → PASS 后提交
4. 本目录随代码一起 git 提交（契约版本可追溯）

## 统一封装约定（FR-06/07/08）

- 所有请求走 `this.api(path, opts)`：
  - `opts.json` → JSON body（自动 Content-Type）
  - `opts.contentType + opts.rawBody` → 二进制上传（Blob）
  - 响应 `audio/*`/`octet-stream` 自动转 Blob
- 认证：`authHeaders()` 统一注入 `Authorization: Bearer <token>`
- 401（清 token 提示重登）/ 403（权限提示）/ 5xx（服务器异常）在 api() **统一拦截**，
  页面代码不重复处理
- 命名转换（如 snake_case ↔ camelCase）只允许出现在 api() 层，业务代码不碰

## baseURL（FR-09）

`API_BASE = '/xiaozhi'`（src/App.vue 顶部常量）。本地 dev 用 vite proxy，
生产走 nginx `/xiaozhi/ → 127.0.0.1:8002`。**前后端零路径硬编码**。

## 版本策略（FR-10）

当前无 URL 版本前缀（契约即当前版本）。未来引入版本时统一在 API_BASE 增加
（如 `/xiaozhi/v2`），契约 servers 字段同步。
