#!/usr/bin/env python3
"""
飞常准MCP服务器代理中间件
实现token轮询机制，避免单个token额度限制
现在支持工具集模式
"""

import asyncio
import logging
from typing import List, Optional, Dict, Any, Set
import aiohttp
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse, Response
from contextlib import asynccontextmanager
import uvicorn
import json

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 导入从tools.variflight模块迁移的类
from tools.variflight import TokenManager, MCPProxy

# 导入工具注册表
from core.registry import get_tool_registry

# 导入IP查询工具
from tools.ip_lookup import IPQueryTool

# 全局变量
token_manager = None
mcp_proxy = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    global token_manager, mcp_proxy

    # 获取工具注册表
    registry = get_tool_registry()

    # 启动时注册和初始化工具
    logger.info("MCP代理服务启动 - 初始化工具集")

    # 注册IP查询工具
    try:
        await registry.register_tool(
            IPQueryTool,
            name="IPLookup",
            config={
                "version": "1.0.0",
                "description": "IP地址查询工具",
                "timeout": 10,
                "max_retries": 2,
                "enable_multiple_sources": True
            }
        )
        logger.info("IPLookup工具注册成功")

        # 启动IP查询工具
        success = await registry.start_tool("IPLookup")
        if success:
            logger.info("IPLookup工具启动成功")
        else:
            logger.warning("IPLookup工具启动失败")
    except Exception as e:
        logger.error(f"IPLookup工具注册失败: {e}")

    # 创建全局token_manager实例（向后兼容）
    token_manager = TokenManager()
    mcp_proxy = MCPProxy(token_manager)
    await mcp_proxy.__aenter__()  # 初始化会话

    logger.info("MCP代理服务启动完成")
    yield

    # 关闭时清理
    logger.info("MCP代理服务关闭")
    if mcp_proxy:
        await mcp_proxy.__aexit__(None, None, None)

    # 关闭IP查询工具
    try:
        await registry.stop_tool("IPLookup")
        logger.info("IPLookup工具已停止")
    except Exception as e:
        logger.error(f"停止IPLookup工具失败: {e}")

# 创建FastAPI应用
app = FastAPI(
    title="个人MCP工具集合",
    description="基于工具集模式的MCP代理服务，支持多种工具扩展",
    version="2.0.0",
    lifespan=lifespan
)

@app.get("/")
async def root():
    """服务概览和快速状态"""
    registry = get_tool_registry()
    tools_status = registry.get_all_tools_status()

    return JSONResponse(
        content={
            "service": "飞常准MCP代理服务",
            "version": "2.0.0",
            "status": "running",
            "tools_count": len(tools_status),
            "tools": {name: status["status"] for name, status in tools_status.items()},
            "token_stats": token_manager.get_stats() if token_manager else {},
            "mcp_proxy": mcp_proxy.base_url if mcp_proxy else None,
            "api_endpoints": {
                "tools_list": "/tools",
                "health": "/health",
                "stats": "/stats",
                "blacklist": "/blacklist",
                "ip_my": "/ip/my",
                "ip_lookup": "/ip/lookup/{ip}",
                "ip_batch": "/ip/batch",
                "ip_geo": "/ip/geo?lat={lat}&lng={lng}"
            }
        },
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream"
        }
    )

@app.get("/stats")
async def get_stats():
    """获取详细统计信息"""
    registry = get_tool_registry()
    tools_stats = registry.get_all_tools_stats()

    return JSONResponse(
        content={
            "service_info": {
                "name": "飞常准MCP代理服务",
                "version": "2.0.0",
                "base_url": mcp_proxy.base_url if mcp_proxy else None,
                "uptime": "N/A"  # 可以添加服务启动时间跟踪
            },
            "token_stats": token_manager.get_stats() if token_manager else {},
            "tools_stats": {
                name: {
                    "status": stats.get("status"),
                    "requests_total": stats.get("requests_total"),
                    "requests_success": stats.get("requests_success"),
                    "requests_failed": stats.get("requests_failed"),
                    "uptime_seconds": stats.get("uptime_seconds"),
                    "last_used": stats.get("last_used")
                }
                for name, stats in tools_stats.items()
            },
            "summary": {
                "total_tools": len(tools_stats),
                "total_requests": sum(s.get("requests_total", 0) for s in tools_stats.values()),
                "success_rate": (
                    sum(s.get("requests_success", 0) for s in tools_stats.values()) /
                    max(sum(s.get("requests_total", 0) for s in tools_stats.values()), 1) * 100
                )
            }
        },
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream"
        }
    )

@app.get("/blacklist")
async def get_blacklist():
    """获取拉黑列表信息"""
    blacklisted_preview = []
    for token in list(token_manager.blacklisted_tokens)[:10]:  # 只显示前10个
        blacklisted_preview.append({
            "token_preview": token[:20] + "...",
            "full_length": len(token)
        })
    
    return JSONResponse(
        content={
            "blacklist_info": {
                "total_blacklisted": len(token_manager.blacklisted_tokens),
                "blacklist_file": token_manager.blacklist_file,
                "preview": blacklisted_preview
            },
            "stats": token_manager.get_stats()
        },
        headers={
            "Content-Type": "application/json"
        }
    )

# ==================== IP查询工具API路由 ====================

@app.get("/ip/my")
async def get_my_ip():
    """获取本机公网IP地址"""
    registry = get_tool_registry()
    tool = registry.get_tool("IPLookup")

    if not tool:
        raise HTTPException(status_code=503, detail="IPLookup工具未注册")

    try:
        result = await tool.handle_request("get_my_ip", {})
        return JSONResponse(
            content=result,
            headers={"Content-Type": "application/json"}
        )
    except Exception as e:
        logger.error(f"获取本机IP失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取本机IP失败: {str(e)}")


@app.get("/ip/lookup/{ip}")
async def lookup_ip(ip: str):
    """查询指定IP地址的详细信息"""
    registry = get_tool_registry()
    tool = registry.get_tool("IPLookup")

    if not tool:
        raise HTTPException(status_code=503, detail="IPLookup工具未注册")

    try:
        result = await tool.handle_request("lookup", {"ip": ip})
        return JSONResponse(
            content=result,
            headers={"Content-Type": "application/json"}
        )
    except Exception as e:
        logger.error(f"IP查询失败: {e}")
        raise HTTPException(status_code=500, detail=f"IP查询失败: {str(e)}")


@app.post("/ip/batch")
async def batch_lookup_ips(request: Request):
    """批量查询多个IP地址"""
    registry = get_tool_registry()
    tool = registry.get_tool("IPLookup")

    if not tool:
        raise HTTPException(status_code=503, detail="IPLookup工具未注册")

    try:
        data = await request.json()
        ips = data.get("ips", [])

        if not ips:
            raise HTTPException(status_code=400, detail="缺少IP地址列表")

        result = await tool.handle_request("batch_lookup", {"ips": ips})
        return JSONResponse(
            content=result,
            headers={"Content-Type": "application/json"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"批量IP查询失败: {e}")
        raise HTTPException(status_code=500, detail=f"批量IP查询失败: {str(e)}")


@app.get("/ip/geo")
async def geo_lookup(
    lat: float,
    lng: float
):
    """地理编码查询 - 根据坐标查询地址"""
    registry = get_tool_registry()
    tool = registry.get_tool("IPLookup")

    if not tool:
        raise HTTPException(status_code=503, detail="IPLookup工具未注册")

    try:
        result = await tool.handle_request("geo_lookup", {
            "latitude": lat,
            "longitude": lng
        })
        return JSONResponse(
            content=result,
            headers={"Content-Type": "application/json"}
        )
    except Exception as e:
        logger.error(f"地理编码查询失败: {e}")
        raise HTTPException(status_code=500, detail=f"地理编码查询失败: {str(e)}")

# ==================== 工具管理API路由 ====================

@app.get("/tools")
async def list_tools():
    """列出所有已注册的工具及其状态"""
    registry = get_tool_registry()
    tools_status = registry.get_all_tools_status()
    tools_stats = registry.get_all_tools_stats()

    return JSONResponse(
        content={
            "total_tools": len(tools_status),
            "running_tools": sum(1 for t in tools_status.values() if t["status"] == "running"),
            "tools": {
                name: {
                    "status": status["status"],
                    "version": status["version"],
                    "description": status["description"],
                    "uptime_seconds": status["uptime_seconds"],
                    "error_count": status["error_count"],
                    "request_count": status["request_count"],
                    "stats": tools_stats.get(name, {})
                }
                for name, status in tools_status.items()
            }
        },
        headers={"Content-Type": "application/json"}
    )


@app.get("/health")
async def health_check():
    """执行全系统健康检查"""
    registry = get_tool_registry()
    health_status = registry.get_tools_health()

    # 检查整体健康状态
    overall_healthy = all(h["healthy"] for h in health_status.values())
    mcp_proxy_healthy = mcp_proxy is not None and token_manager is not None

    # 详细的健康检查报告
    checks = {
        "overall": {
            "healthy": overall_healthy and mcp_proxy_healthy,
            "status": "healthy" if (overall_healthy and mcp_proxy_healthy) else "degraded"
        },
        "tools": health_status,
        "mcp_proxy": {
            "healthy": mcp_proxy_healthy,
            "base_url": mcp_proxy.base_url if mcp_proxy else None,
            "token_manager": token_manager is not None
        },
        "services": {
            "fastapi": "healthy",
            "memory": "healthy",  # 可以添加更详细的内存检查
            "disk_space": "healthy"  # 可以添加磁盘空间检查
        }
    }

    return JSONResponse(
        content=checks,
        headers={"Content-Type": "application/json"}
    )


# ==================== 代理路由 ====================

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
async def proxy_request(request: Request, path: str):
    """完整代理所有请求到MCP服务器，支持流式传输"""
    global mcp_proxy
    
    if not mcp_proxy:
        raise HTTPException(status_code=503, detail="代理服务未初始化")
    
    try:
        # 获取原始请求体
        body = await request.body() if request.method in ["POST", "PUT", "PATCH"] else None
        
        # 处理特殊请求
        if body:
            try:
                request_data = json.loads(body.decode('utf-8'))
                method = request_data.get('method')
                
                if method == 'ping':
                    # 返回标准的ping响应
                    ping_response = {
                        "jsonrpc": "2.0",
                        "id": request_data.get('id'),
                        "result": {}
                    }
                    return JSONResponse(
                        content=ping_response,
                        status_code=200,
                        headers={
                            "Content-Type": "application/json",
                            "Cache-Control": "no-cache"
                        }
                    )
                
                elif method == 'notifications/initialized':
                    # 返回202 Accepted状态码，表示通知已接收
                    logger.info("收到 notifications/initialized 通知")
                    return Response(
                        status_code=202,
                        headers={
                            "Content-Type": "application/json",
                            "Cache-Control": "no-cache"
                        }
                    )
                    
            except (json.JSONDecodeError, KeyError, AttributeError):
                # 如果解析失败，继续正常代理流程
                pass
        
        # 获取所有headers
        headers = dict(request.headers)
        
        # 使用代理发送请求
        upstream_response = await mcp_proxy.proxy_request(
            method=request.method,
            path=path,
            headers=headers,
            body=body
        )
        
        # 准备响应headers（过滤掉不应该返回的headers）
        response_headers = {}
        skip_response_headers = {
            'content-length', 'content-encoding', 'transfer-encoding',
            'connection', 'upgrade', 'proxy-connection'
        }
        
        for key, value in upstream_response.headers.items():
            if key.lower() not in skip_response_headers:
                response_headers[key] = value
        
        # 检查是否是流式响应
        content_type = upstream_response.headers.get('content-type', '').lower()
        
        if 'text/event-stream' in content_type or 'application/x-ndjson' in content_type:
            # 流式响应
            logger.info(f"返回流式响应，Content-Type: {content_type}")
            
            return StreamingResponse(
                mcp_proxy.stream_response(upstream_response),
                status_code=upstream_response.status,
                headers=response_headers,
                media_type=content_type
            )
        
        else:
            # 非流式响应，读取完整内容
            content = await upstream_response.read()
            await upstream_response.release()
            
            return Response(
                content=content,
                status_code=upstream_response.status,
                headers=response_headers,
                media_type=content_type or "application/octet-stream"
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"代理请求时出错: {e}")
        raise HTTPException(status_code=500, detail=f"代理服务器内部错误: {str(e)}")


if __name__ == "__main__":
    # 启动服务
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
