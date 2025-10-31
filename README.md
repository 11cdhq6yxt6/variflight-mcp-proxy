# 个人MCP工具集合

一个基于工具集模式的MCP（Model Context Protocol）服务器，提供多种实用工具的统一接口。该项目从飞常准MCP代理发展而来，现在支持更多个人工具的扩展。

## 🌟 项目特性

### 架构优势
- **🧩 工具集模式**: 模块化设计，每个工具独立但共享基础设施
- **⚡ 高性能**: 基于FastAPI和aiohttp的异步处理架构
- **🔧 可扩展**: 新增工具只需继承基类，无需修改核心代码
- **📊 统一监控**: 集中化的工具状态管理和健康检查

### 核心功能
- ✅ **Token轮询**: 自动轮询使用多个token，避免单个token额度限制
- ✅ **智能拉黑**: 401/403错误时永久拉黑token，持久化存储拉黑列表
- ✅ **完整Header转发**: 转发所有客户端headers（除Host等特殊headers）
- ✅ **流式传输支持**: 完整支持Server-Sent Events (SSE) 和其他流式HTTP传输
- ✅ **透明代理**: 完全透明地代理所有HTTP方法（GET/POST/PUT/DELETE/OPTIONS/HEAD）
- ✅ **MCP协议兼容**: 正确处理MCP协议要求的headers (Accept: application/json, text/event-stream)
- ✅ **本地处理**: 本地处理ping和notifications/initialized请求，快速响应不消耗token
- ✅ **状态监控**: 提供详细的token使用统计和服务状态监控
- ✅ **错误重试**: 内置重试机制，临时失效和永久拉黑分别处理
- ✅ **IP查询**: 提供IP地址地理位置查询和地理编码功能
- ✅ **多数据源**: IP查询支持多个数据源整合，提高准确性

## 📦 包含的工具

### Variflight Tool
飞常准MCP代理工具，提供航空数据服务的代理功能。

**功能**:
- Token轮询和管理
- MCP请求代理
- 流式传输支持
- 本地处理ping和通知

### IPLookup Tool
IP地址查询工具，提供IP地址地理位置检测和地理编码功能。

**功能**:
- 单个IP详细信息查询
- 批量IP查询
- 本机公网IP检测
- 地理编码（坐标转地址）
- 多数据源整合查询

**数据源** (按优先级排序):
1. **ipgeo-api.hf.space** - getip.js 中的主要数据源
2. **api.live.bilibili.com** - getip.js 中的数据源
3. **apimobile.meituan.com** - getip.js 中的数据源
4. **备用服务**: ip-api.com, ipapi.co, ipgeolocation.io, ipinfo.io

**说明**: IPLookup工具不使用 getip.js 接口，而是直接使用 getip.js 项目中提到的真实数据源（ipgeo-api.hf.space、api.live.bilibili.com、apimobile.meituan.com），确保数据的准确性和可靠性。

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 准备账号文件

确保`accounts.txt`文件存在，每行格式为：
```
username|password|sk-xxxxxxxxxxxxxxxxxxxxxxxxx
```

### 3. 启动服务

```bash
python main.py
```

或使用启动器获得更多配置选项：
```bash
python start.py --port 8080 --log-level debug
```

服务将在 `http://localhost:8000` 启动

### 4. 使用代理

将原本直接请求飞常准MCP服务器的地址：
```
https://ai.variflight.com/servers/aviation/mcp/?api_key=YOUR_TOKEN
```

替换为代理服务器地址：
```
http://localhost:8000/
```

代理会自动处理token轮询，你不需要在请求中包含api_key参数。

### 5. 使用IP查询

```bash
# 获取本机IP
curl http://localhost:8000/ip/my

# 查询指定IP
curl http://localhost:8000/ip/lookup/8.8.8.8

# 批量查询IP
curl -X POST http://localhost:8000/ip/batch \
  -H "Content-Type: application/json" \
  -d '{"ips": ["8.8.8.8", "1.1.1.1", "114.114.114.114"]}'

# 地理编码查询
curl "http://localhost:8000/ip/geo?lat=37.4220&lng=-122.0841"
```

## 🛠️ API端点

### 健康检查
```bash
GET http://localhost:8000/
```
返回服务状态和工具统计信息。

### 工具列表
```bash
GET http://localhost:8000/tools
```
返回所有已注册工具的状态信息。

### 详细统计
```bash
GET http://localhost:8000/stats
```
返回详细的token使用统计和服务信息。

### 健康检查
```bash
GET http://localhost:8000/health
```
执行全系统健康检查。

### 拉黑列表查询
```bash
GET http://localhost:8000/blacklist
```
返回永久拉黑的token信息：
```json
{
  "blacklist_info": {
    "total_blacklisted": 5,
    "blacklist_file": "blacklist.pkl",
    "preview": [
      {
        "token_preview": "sk-B8VkYmkvjQSnLQbj...",
        "full_length": 48
      }
    ]
  }
}
```

### IP查询端点

#### 获取本机IP
```bash
GET http://localhost:8000/ip/my
```
返回本机公网IP地址和详细信息：
```json
{
  "detected_ips": ["x.x.x.x"],
  "primary_ip": "x.x.x.x",
  "info": {
    "ip": "x.x.x.x",
    "country": "美国",
    "city": "Mountain View",
    "isp": "Google LLC"
  }
}
```

#### 查询指定IP
```bash
GET http://localhost:8000/ip/lookup/{ip}
```
返回指定IP的详细信息：
```json
{
  "ip": "8.8.8.8",
  "sources_count": 3,
  "sources": ["ipapi", "ipapi_co", "ipinfo"],
  "data": {
    "ip": "8.8.8.8",
    "country": "美国",
    "country_code": "US",
    "region": "加利福尼亚",
    "city": "Mountain View",
    "zip": "94035",
    "latitude": 37.4220,
    "longitude": -122.0841,
    "timezone": "America/Los_Angeles",
    "isp": "Google LLC",
    "org": "Google LLC",
    "as": "AS15169 Google LLC"
  }
}
```

#### 批量查询IP
```bash
POST http://localhost:8000/ip/batch
Content-Type: application/json

{
  "ips": ["8.8.8.8", "1.1.1.1"]
}
```

#### 地理编码查询
```bash
GET http://localhost:8000/ip/geo?lat={latitude}&lng={longitude}
```
根据坐标查询地址信息：
```json
{
  "coordinates": {
    "latitude": 37.4220,
    "longitude": -122.0841
  },
  "locations": [
    {
      "source": "opencage",
      "formatted": "1600 Amphitheatre Parkway, Mountain View, CA 94043, United States"
    }
  ]
}
```

### 代理请求
所有其他路径的请求都会被透明地代理到飞常准MCP服务器。

## 🔧 MCP客户端配置

在你的MCP客户端配置中，将服务器URL设置为代理地址：

```json
{
    "mcpServers": {
        "VariFlight-Aviation": {
            "url": "http://localhost:8000/",
            "description": "通过代理服务器连接的飞常准航空数据服务"
        },
        "IPLookup": {
            "url": "http://localhost:8000/",
            "description": "IP地址查询工具"
        }
    }
}
```

## 🏗️ 项目架构

```
variflight-mcp-proxy/
├── main.py                 # FastAPI应用入口
├── start.py                # 启动脚本
├── tools/                  # 工具模块目录
│   ├── __init__.py
│   ├── base.py            # 工具基类定义
│   ├── variflight.py      # 飞常准MCP代理工具
│   └── ip_lookup.py       # IP查询工具
├── core/                   # 核心共享组件
│   ├── __init__.py
│   ├── config.py          # 配置管理系统
│   └── registry.py        # 工具注册表
├── requirements.txt        # 项目依赖
└── README.md              # 项目文档
```

### 核心组件

#### ToolProtocol (tools/base.py)
所有工具的基类，提供统一的接口：
- 生命周期管理（init, shutdown）
- 状态监控（运行、停止、错误）
- 统计信息收集
- 健康检查

#### ConfigManager (core/config.py)
配置管理系统，支持：
- 环境变量
- 配置文件（JSON/YAML）
- 类型自动转换
- 工具级配置

#### ToolRegistry (core/registry.py)
工具注册表，统一管理：
- 工具注册和注销
- 生命周期管理
- 依赖关系处理
- 状态监控

## 📊 Token管理机制

### 智能拉黑系统
- **临时失效**: 429(速率限制)等临时错误会标记token为临时失效，稍后重试
- **永久拉黑**: 401/403(认证失败)错误会永久拉黑token，保存到`blacklist.pkl`文件
- **持久化存储**: 拉黑列表在服务重启后仍然有效
- **自动恢复**: 临时失效的token会在所有token都失效时重置

### Token状态监控
访问 `/stats` 端点查看详细统计：
```json
{
  "token_stats": {
    "total_loaded_tokens": 449,
    "temporarily_failed_tokens": 2,
    "permanently_blacklisted_tokens": 5,
    "available_tokens": 442
  }
}
```

## 🌊 流式传输支持

代理服务器完整支持HTTP流式传输：
- **Server-Sent Events (SSE)**: `text/event-stream`
- **NDJSON流**: `application/x-ndjson`
- **其他流式格式**: 自动检测并透明转发

## 💡 本地处理功能

代理服务器本地处理某些特殊请求，无需转发到上游服务器：

### Ping功能
- **快速响应**: 本地处理，响应时间极短
- **节省token**: 不消耗上游服务器的token额度
- **标准格式**: 返回标准的JSON-RPC 2.0格式响应

### Notifications/Initialized处理
- **202状态码**: 返回HTTP 202 Accepted状态码
- **通知确认**: 表示已接收初始化通知
- **无需转发**: 本地处理，不消耗token

### 示例

#### Ping请求
```bash
curl -X POST http://localhost:8000/ \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "ping-test",
    "method": "ping",
    "params": {}
  }'
```

#### Ping响应
```json
{
  "jsonrpc": "2.0",
  "id": "ping-test",
  "result": {}
}
```

#### Notifications/Initialized请求
```bash
curl -X POST http://localhost:8000/ \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "notifications/initialized",
    "params": {}
  }'
```

#### Notifications/Initialized响应
- **HTTP状态码**: 202 Accepted
- **响应体**: 空（表示通知已接收）

## ⚙️ 配置选项

### 环境变量
- `PORT`: 服务端口 (默认: 8000)
- `HOST`: 服务主机 (默认: 0.0.0.0)

### 工具级配置
工具配置支持以下环境变量格式：
- `TOOL_{TOOL_NAME}_{KEY}`: 特定工具的配置
- `MCP_{KEY}`: 全局配置

### IP查询工具配置
```bash
# IPLookup工具配置
TOOL_IPLOOKUP_TIMEOUT=10
TOOL_IPLOOKUP_MAX_RETRIES=2
TOOL_IPLOOKUP_ENABLE_MULTIPLE_SOURCES=true
```

### 启动参数
使用 `start.py` 支持的参数：
- `--host`: 服务主机地址 (默认: 0.0.0.0)
- `--port`: 服务端口 (默认: 8000)
- `--accounts-file`: 账号文件路径 (默认: accounts.txt)
- `--reload`: 启用热重载
- `--log-level`: 日志级别 (debug/info/warning/error)

### 配置文件
支持YAML和JSON配置文件（可选）：
```yaml
# config.yaml
tools:
  Variflight:
    accounts_file: "accounts.txt"
    blacklist_file: "blacklist.pkl"
    max_retries: 3
  IPLookup:
    timeout: 10
    max_retries: 2
    enable_multiple_sources: true
```

## 📝 日志

服务会输出详细的日志信息，包括：
- 工具加载状态
- 请求成功/失败信息
- Token失效标记
- 错误信息
- IP查询日志

## 🔍 故障排除

### 常见问题

1. **"未找到有效的token"**
   - 检查`accounts.txt`文件是否存在
   - 确保token格式正确（以`sk-`开头）

2. **"所有token都已失效"**
   - 检查token是否仍然有效
   - 服务会自动重置失效列表并重试

3. **网络连接错误**
   - 检查网络连接
   - 确认飞常准服务器地址可访问

4. **工具注册失败**
   - 检查工具模块是否存在
   - 验证工具类是否正确继承ToolProtocol

5. **IP查询失败**
   - 检查网络连接是否正常
   - 确认IP格式正确
   - 查看日志中的详细错误信息

### 调试模式

启动时添加调试参数：
```bash
python main.py --log-level debug
```

## 🚀 性能优化

- 使用异步处理，支持高并发
- 智能token轮询，避免频繁使用同一token
- 内置连接池，复用HTTP连接
- 失效token自动跳过，减少无效请求
- 工具模块化，避免不必要的依赖加载
- IP查询工具支持并发查询，提高批量查询性能
- 多数据源查询支持优雅降级，单个数据源失败不影响整体功能

## 🛡️ 安全注意事项

- 保护好`accounts.txt`文件，不要泄露token
- 建议在内网环境使用，避免暴露到公网
- 定期检查token有效性和使用情况
- 配置文件权限管理
- IP查询工具不记录敏感信息，仅用于地理位置检测

## 📦 扩展开发

### 添加新工具

1. 在`tools/`目录创建新的工具模块
2. 继承`ToolProtocol`基类
3. 实现必要的抽象方法
4. 在启动时注册工具

```python
# tools/my_tool.py
from tools.base import ToolProtocol

class MyTool(ToolProtocol):
    def __init__(self):
        super().__init__(
            name="MyTool",
            version="1.0.0",
            description="我的自定义工具"
        )

    async def init(self) -> bool:
        # 初始化逻辑
        return True

    async def shutdown(self) -> bool:
        # 关闭逻辑
        return True

    async def handle_request(self, method: str, params: dict) -> dict:
        # 处理请求
        return {"result": "success"}
```

### 工具注册

在应用启动时注册工具：
```python
from core.registry import get_tool_registry

registry = get_tool_registry()
await registry.register_tool(MyTool)
```

## 📄 版本历史

- **v2.1.0**: 新增IP查询工具
  - 支持IP地理位置查询
  - 支持地理编码功能
  - 支持批量IP查询
  - 多数据源整合
- **v2.0.0**: 工具集重构，支持多工具扩展
- **v1.0.0**: 初始版本，单一飞常准MCP代理

## 📜 许可证

MIT License
