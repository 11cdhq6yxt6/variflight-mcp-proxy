# 飞常准MCP服务器代理中间件

这是一个用于代理飞常准MCP服务器请求的中间件，实现了token轮询机制来避免单个token的额度限制。

## 功能特性

- ✅ **Token轮询**: 自动轮询使用多个token，避免单个token额度限制
- ✅ **智能拉黑**: 401/403错误时永久拉黑token，持久化存储拉黑列表
- ✅ **完整Header转发**: 转发所有客户端headers（除Host等特殊headers）
- ✅ **流式传输支持**: 完整支持Server-Sent Events (SSE) 和其他流式HTTP传输
- ✅ **透明代理**: 完全透明地代理所有HTTP方法（GET/POST/PUT/DELETE/OPTIONS/HEAD）
- ✅ **MCP协议兼容**: 正确处理MCP协议要求的headers (Accept: application/json, text/event-stream)
- ✅ **本地处理**: 本地处理ping和notifications/initialized请求，快速响应不消耗token
- ✅ **状态监控**: 提供详细的token使用统计和服务状态监控
- ✅ **异步处理**: 基于FastAPI和aiohttp的高性能异步处理
- ✅ **错误重试**: 内置重试机制，临时失效和永久拉黑分别处理

## 快速开始

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

## API端点

### 健康检查
```bash
GET http://localhost:8000/
```

返回服务状态和token统计信息。

### 详细统计
```bash
GET http://localhost:8000/stats
```

返回详细的token使用统计和服务信息。

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

### 代理请求
所有其他路径的请求都会被透明地代理到飞常准MCP服务器。

## MCP客户端配置

在你的MCP客户端配置中，将服务器URL设置为代理地址：

```json
{
    "mcpServers": {
        "VariFlight-Aviation": {
            "url": "http://localhost:8000/"
        }
    }
}
```

## Token管理机制

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

## 流式传输支持

代理服务器完整支持HTTP流式传输：
- **Server-Sent Events (SSE)**: `text/event-stream`
- **NDJSON流**: `application/x-ndjson`
- **其他流式格式**: 自动检测并透明转发

## 本地处理功能

代理服务器本地处理某些特殊请求，无需转发到上游服务器：

### Ping功能
- **快速响应**: 本地处理，响应时间极短
- **节省token**: 不消耗上游服务器的token额度
- **标准格式**: 返回标准的JSON-RPC 2.0格式响应

### Notifications/Initialized处理
- **202状态码**: 返回HTTP 202 Accepted状态码
- **通知确认**: 表示已接收初始化通知
- **无需转发**: 本地处理，不消耗token

### Ping请求示例
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

### Ping响应示例
```json
{
  "jsonrpc": "2.0",
  "id": "ping-test", 
  "result": {}
}
```

### Notifications/Initialized请求示例
```bash
curl -X POST http://localhost:8000/ \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "notifications/initialized",
    "params": {}
  }'
```

### Notifications/Initialized响应
- **HTTP状态码**: 202 Accepted
- **响应体**: 空（表示通知已接收）

## 配置选项

### 环境变量
- `PORT`: 服务端口 (默认: 8000)
- `HOST`: 服务主机 (默认: 0.0.0.0)

### 代码配置
在`main.py`中可以修改以下配置：
- `accounts_file`: 账号文件路径 (默认: "accounts.txt")
- `blacklist_file`: 拉黑列表文件路径 (默认: "blacklist.pkl")
- `max_retries`: 最大重试次数 (默认: 3)
- `timeout`: 请求超时时间 (默认: 300秒)

## 日志

服务会输出详细的日志信息，包括：
- Token加载状态
- 请求成功/失败信息
- Token失效标记
- 错误信息

## 故障排除

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

### 调试模式

启动时添加调试参数：
```bash
python main.py --log-level debug
```

## 性能优化

- 使用异步处理，支持高并发
- 智能token轮询，避免频繁使用同一token
- 内置连接池，复用HTTP连接
- 失效token自动跳过，减少无效请求

## 安全注意事项

- 保护好`accounts.txt`文件，不要泄露token
- 建议在内网环境使用，避免暴露到公网
- 定期检查token有效性和使用情况

## 许可证

MIT License