# 管理后台接口修复需求文档

**生成时间**: 2026-10-10  
**测试环境**: https://sandyun.top:8001  
**源码路径**: `G:/demo/21_xiaozhi/`

---

## 一、问题汇总

| 用例 ID | 接口 | 错误码 | 严重级别 | 根本原因 |
|---------|------|--------|----------|----------|
| U002 | PUT /user/change-password | 500 | 严重 | 测试数据问题（密码不能为空） |
| A003 | GET /agent/1/sessions | 10169 | 严重 | 智能体 ID 不存在（需使用真实 ID） |
| D002 | POST /device/bind/1 | 500 | 一般 | 测试数据问题（设备 ID 可能无效） |
| M001 | GET /models/list | 500 | 一般 | **缺少 required 参数 modelType** |
| T001 | GET /ttsVoice | 500 | 一般 | **缺少 required 参数 ttsModelId** |
| MEM002 | GET /memory/facts | 500 | 严重 | **记忆模块未实现** |

---

## 二、详细问题与修复方案

### 2.1 【记忆模块缺失】P0 - 高优先级

#### 问题描述
`/memory/agents` 和 `/memory/facts` 接口返回 500 错误，原因是记忆管理模块完全未实现。

#### 影响的源文件

**后端 Java 服务（manager-api）**：

| 文件路径 | 行号 | 状态 | 说明 |
|----------|------|------|------|
| `网页后台/xiaozhi-esp32-server/main/manager-api/src/main/java/xiaozhi/modules/memory/` | - | **缺失** | 整个 memory 模块目录不存在 |

**Python 服务（xiaozhi-server）**：

| 文件路径 | 行号 | 状态 | 说明 |
|----------|------|------|------|
| `网页后台/xiaozhi-esp32-server/main/xiaozhi-server/core/api/memory_handler.py` | - | **缺失** | MemoryManageHandler 类不存在 |
| `网页后台/xiaozhi-esp32-server/main/xiaozhi-server/core/http_server.py` | 1-92 | **缺少路由注册** | 未导入 MemoryManageHandler，未注册 `/api/memory/**` 路由 |

#### 参考实现
镜像仓库已有完整实现：
- `code-server-mirror/xiaozhi-server/core/api/memory_handler.py` (244 行)
- `code-server-mirror/manager-api/src/main/java/xiaozhi/modules/memory/` (9 个 Java 文件)

#### 修复方案

**步骤 1：复制 Python 记忆处理器**
```bash
cp code-server-mirror/xiaozhi-server/core/api/memory_handler.py \
   网页后台/xiaozhi-esp32-server/main/xiaozhi-server/core/api/memory_handler.py
```

**步骤 2：修改 http_server.py**
文件：`网页后台/xiaozhi-esp32-server/main/xiaozhi-server/core/http_server.py`

| 行号范围 | 操作 | 说明 |
|----------|------|------|
| 1-5 | 添加 import | 添加 `from core.api.memory_handler import MemoryManageHandler` |
| 15-20 | 添加中间件 | 添加 `memory_loopback_middleware` 函数（约 40 行） |
| 30-40 | 添加全局变量 | 添加 `_MEMORY_HANDLER = None` |
| 45-55 | 修改 __init__ | 在 SimpleHttpServer.__init__ 中添加 `self.memory_handler = MemoryManageHandler(config)` |
| 60-70 | 注册路由 | 在 start() 方法中添加 memory API 路由注册（约 40 行） |

**步骤 3：复制 Java 记忆模块**
```bash
mkdir -p 网页后台/xiaozhi-esp32-server/main/manager-api/src/main/java/xiaozhi/modules/memory/
cp -r code-server-mirror/manager-api/src/main/java/xiaozhi/modules/memory/* \
      网页后台/xiaozhi-esp32-server/main/manager-api/src/main/java/xiaozhi/modules/memory/
```

**步骤 4：重启服务**
```bash
# 重启 Python 服务
systemctl restart xiaozhi-server

# 重新编译并重启 Java 服务
cd 网页后台/xiaozhi-esp32-server/main/manager-api
mvn clean package -DskipTests
systemctl restart xiaozhi-manager-api
```

---

### 2.2 【测试参数缺失】P1 - 中等优先级

#### 问题描述
以下接口返回 500 错误是因为测试脚本缺少必需的请求参数。

**影响文件**：
- `tests/full_test.py` (第 60-70 行附近)

#### 修复方案

**1. 模型列表接口 (M001)**

| 当前测试 | 修复后 |
|----------|--------|
| `GET /models/list` | `GET /models/list?modelType=llm&page=0&limit=10` |

**2. 音色列表接口 (T001)**

| 当前测试 | 修复后 |
|----------|--------|
| `GET /ttsVoice` | `GET /ttsVoice?ttsModelId=<有效ID>&name=&page=0&limit=10` |

**代码修改示例** (`tests/full_test.py`)：

```python
# 修改前 (第 60 行附近)
runner.add_test_case(TestCase("M001", "获取模型列表", "模型", "GET", "/models/list"))

# 修改后
runner.add_test_case(TestCase("M001", "获取模型列表", "模型", "GET", "/models/list",
                               params={"modelType": "llm", "page": "0", "limit": "10"}))

# 修改前 (第 70 行附近)
runner.add_test_case(TestCase("T001", "获取音色列表", "音色", "GET", "/ttsVoice"))

# 修改后
# 需要先获取有效的 ttsModelId（从 /models/list 返回结果中提取）
runner.add_test_case(TestCase("T001", "获取音色列表", "音色", "GET", "/ttsVoice",
                               params={"ttsModelId": "<从模型列表获取>", "name": "", "page": "0", "limit": "10"}))
```

---

### 2.3 【测试数据问题】P2 - 低优先级

#### 问题描述
以下失败用例是因为使用了不存在的 ID。

| 用例 ID | 接口 | 问题 | 修复建议 |
|---------|------|------|----------|
| U002 | PUT /user/change-password | 密码为空 | 使用真实密码 |
| A003 | GET /agent/1/sessions | agent_id=1 不存在 | 使用真实智能体 ID（如 `88b87cfb642e42268b239eb6b8cd1f02`） |
| D002 | POST /device/bind/1 | 设备 ID 可能无效 | 使用真实设备绑定 ID |

---

## 三、接口调用规范

### 3.1 记忆模块接口（修复后）

| 方法 | 路径 | 参数 | 说明 |
|------|------|------|------|
| GET | `/memory/agents` | 无 | 获取有记忆数据的智能体列表 |
| GET | `/memory/facts` | agent_id, keyword, category, status, page, size | 分页查询记忆条目 |
| GET | `/memory/facts/{fact_id}` | agent_id (query) | 获取记忆条目详情 |
| POST | `/memory/facts` | agent_id, content, category, trust_score | 新增记忆条目 |
| PUT | `/memory/facts/{fact_id}` | agent_id, content, category | 编辑记忆条目 |
| DELETE | `/memory/facts/{fact_id}` | agent_id (query) | 删除记忆条目 |

### 3.2 模型列表接口（修复后）

```
GET /models/list?modelType=llm&page=0&limit=10
```

**必需参数**：
- `modelType`: 模型类型（llm/tts/vllm/memory 等）
- `page`: 页码（从 0 开始）
- `limit`: 每页数量

### 3.3 音色列表接口（修复后）

```
GET /ttsVoice?ttsModelId=<TTS模型ID>&name=&page=0&limit=10
```

**必需参数**：
- `ttsModelId`: TTS 模型 ID（先从 `/models/list?modelType=tts` 获取）
- `name`: 音色名称（可选，用于搜索）
- `page`: 页码（从 0 开始）
- `limit`: 每页数量

---

## 四、验证步骤

### 4.1 记忆模块验证
```bash
# 1. 启动服务后测试
curl -k "https://sandyun.top:8001/xiaozhi/memory/agents" \
  -H "Authorization: Bearer <token>"

# 期望返回：
# {"code":0,"msg":"success","data":[{"agent_id":"...","name":"...","fact_count":0,...}]}

# 2. 测试记忆条目列表
curl -k "https://sandyun.top:8001/xiaozhi/memory/facts?agent_id=<agent_id>&page=1&size=20" \
  -H "Authorization: Bearer <token>"

# 期望返回：
# {"code":0,"msg":"success","data":{"total":0,"list":[]}}
```

### 4.2 模型接口验证
```bash
# 1. 测试模型列表
curl -k "https://sandyun.top:8001/xiaozhi/models/list?modelType=llm&page=0&limit=10" \
  -H "Authorization: Bearer <token>"

# 期望返回：成功，返回模型列表

# 2. 测试音色列表（需要先获取 ttsModelId）
curl -k "https://sandyun.top:8001/xiaozhi/ttsVoice?ttsModelId=<ttsModelId>&page=0&limit=10" \
  -H "Authorization: Bearer <token>"

# 期望返回：成功，返回音色列表
```

---

## 五、文件变更清单

| 操作 | 文件路径 | 说明 |
|------|----------|------|
| 新增 | `xiaozhi-server/core/api/memory_handler.py` | 记忆管理 HTTP 处理器（244 行） |
| 修改 | `xiaozhi-server/core/http_server.py` | 添加记忆路由注册（+60 行） |
| 新增 | `manager-api/.../modules/memory/` | Java 记忆模块（9 个文件） |
| 修改 | `tests/full_test.py` | 修复测试用例参数（+4 行） |

---

## 六、附录：完整源码参考

### 6.1 记忆处理器完整代码
参见：`code-server-mirror/xiaozhi-server/core/api/memory_handler.py`

### 6.2 Java Controller 代码
参见：`code-server-mirror/manager-api/src/main/java/xiaozhi/modules/memory/controller/MemoryFactController.java`

### 6.3 HTTP Server 完整配置
参见：`code-server-mirror/xiaozhi-server/core/http_server.py`

---

*文档生成：WorkBuddy AI Agent*  
*更新时间：2026-10-10 05:59*
