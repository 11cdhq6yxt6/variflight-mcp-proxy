#!/usr/bin/env python3
"""
飞常准MCP服务器代理中间件
实现token轮询机制，避免单个token额度限制
"""

import asyncio
import logging
import pickle
import os
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

class TokenManager:
    """Token管理器，负责token轮询和状态管理"""
    
    def __init__(self, accounts_file: str = "accounts.txt", blacklist_file: str = "blacklist.pkl"):
        self.accounts_file = accounts_file
        self.blacklist_file = blacklist_file
        self.tokens: List[str] = []
        self.current_index = 0
        self.failed_tokens: Set[str] = set()  # 临时失效
        self.blacklisted_tokens: Set[str] = set()  # 永久拉黑
        self.load_blacklist()
        self.load_tokens()
    
    def load_blacklist(self):
        """从文件加载永久拉黑的token列表"""
        try:
            if os.path.exists(self.blacklist_file):
                with open(self.blacklist_file, 'rb') as f:
                    self.blacklisted_tokens = pickle.load(f)
                logger.info(f"加载了 {len(self.blacklisted_tokens)} 个永久拉黑的token")
        except Exception as e:
            logger.warning(f"加载拉黑列表失败: {e}")
            self.blacklisted_tokens = set()
    
    def save_blacklist(self):
        """保存永久拉黑的token列表到文件"""
        try:
            with open(self.blacklist_file, 'wb') as f:
                pickle.dump(self.blacklisted_tokens, f)
            logger.info(f"保存了 {len(self.blacklisted_tokens)} 个永久拉黑的token")
        except Exception as e:
            logger.error(f"保存拉黑列表失败: {e}")
    
    def load_tokens(self):
        """从accounts.txt文件加载token"""
        try:
            with open(self.accounts_file, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if line:
                        # 解析格式: username|password|token
                        parts = line.split('|')
                        if len(parts) >= 3:
                            token = parts[-1]  # 取最后一部分作为token
                            if token.startswith('sk-'):
                                # 只加载未被永久拉黑的token
                                if token not in self.blacklisted_tokens:
                                    self.tokens.append(token)
                                else:
                                    logger.info(f"跳过已拉黑的token: {token[:20]}...")
                            else:
                                logger.warning(f"第{line_num}行token格式可能不正确: {token[:20]}...")
                        else:
                            logger.warning(f"第{line_num}行格式不正确: {line[:50]}...")
            
            logger.info(f"成功加载 {len(self.tokens)} 个可用token")
            if not self.tokens:
                raise ValueError("未找到有效的token")
                
        except FileNotFoundError:
            logger.error(f"账号文件 {self.accounts_file} 不存在")
            raise
        except Exception as e:
            logger.error(f"加载token时出错: {e}")
            raise
    
    def get_next_token(self) -> Optional[str]:
        """获取下一个可用的token"""
        if not self.tokens:
            return None
        
        # 过滤掉临时失效和永久拉黑的token
        available_tokens = [t for t in self.tokens 
                          if t not in self.failed_tokens and t not in self.blacklisted_tokens]
        
        if not available_tokens:
            logger.warning("所有token都已失效，重置临时失败列表")
            self.failed_tokens.clear()
            available_tokens = [t for t in self.tokens if t not in self.blacklisted_tokens]
            
            if not available_tokens:
                logger.error("所有token都已被永久拉黑！")
                return None
        
        # 轮询获取token
        token = available_tokens[self.current_index % len(available_tokens)]
        self.current_index += 1
        
        return token
    
    def mark_token_failed(self, token: str):
        """标记token为临时失效"""
        self.failed_tokens.add(token)
        logger.warning(f"Token标记为临时失效: {token[:20]}...")
    
    def blacklist_token(self, token: str, reason: str = "认证失败"):
        """永久拉黑token"""
        if token in self.blacklisted_tokens:
            logger.info(f"Token已在拉黑列表中: {token[:20]}...")
            return
            
        self.blacklisted_tokens.add(token)
        # 从可用token列表中移除
        if token in self.tokens:
            self.tokens.remove(token)
            logger.info(f"从可用列表中移除token: {token[:20]}...")
        # 从临时失效列表中移除（如果存在）
        if token in self.failed_tokens:
            self.failed_tokens.discard(token)
            logger.info(f"从临时失效列表中移除token: {token[:20]}...")
        
        # 保存到文件
        self.save_blacklist()
        logger.error(f"🚫 Token已永久拉黑 ({reason}): {token[:20]}... | 当前拉黑总数: {len(self.blacklisted_tokens)}")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取token使用统计"""
        return {
            "total_loaded_tokens": len(self.tokens),
            "temporarily_failed_tokens": len(self.failed_tokens),
            "permanently_blacklisted_tokens": len(self.blacklisted_tokens),
            "available_tokens": len([t for t in self.tokens 
                                   if t not in self.failed_tokens and t not in self.blacklisted_tokens])
        }

class MCPProxy:
    """MCP代理客户端 - 支持完整header转发和流式传输"""
    
    def __init__(self, token_manager: TokenManager):
        self.token_manager = token_manager
        self.base_url = "https://ai.variflight.com/servers/aviation/mcp/"
        self.session: Optional[aiohttp.ClientSession] = None
        # 不应该转发的headers
        self.skip_headers = {
            'host', 'content-length', 'connection', 'upgrade', 
            'proxy-connection', 'proxy-authorization', 'te', 'trailers'
        }
    
    async def __aenter__(self):
        if not self.session or self.session.closed:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=300),  # 增加超时时间支持流式传输
                connector=aiohttp.TCPConnector(limit=100, ttl_dns_cache=300, use_dns_cache=True)
            )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None
    
    def _prepare_headers(self, original_headers: Dict[str, str]) -> Dict[str, str]:
        """准备转发的headers，过滤掉不应该转发的headers"""
        headers = {}
        
        # 转发原始headers（除了跳过的headers）
        for key, value in original_headers.items():
            if key.lower() not in self.skip_headers:
                headers[key] = value
        
        # 确保包含MCP协议要求的headers
        if 'accept' not in headers:
            headers['Accept'] = 'application/json, text/event-stream'
        elif 'text/event-stream' not in headers.get('accept', ''):
            # 如果Accept header存在但不包含text/event-stream，则添加
            headers['Accept'] = f"{headers['accept']}, text/event-stream"
        
        # 设置User-Agent
        if 'user-agent' not in headers:
            headers['User-Agent'] = 'MCP-Proxy/1.0.0'
        
        return headers
    
    async def proxy_request(self, method: str, path: str, 
                           headers: Dict[str, str], 
                           body: Optional[bytes] = None,
                           max_retries: int = 3) -> aiohttp.ClientResponse:
        """代理请求到MCP服务器，返回原始响应以支持流式传输"""
        
        if not self.session:
            raise RuntimeError("MCPProxy未正确初始化，请使用async with")
        
        for attempt in range(max_retries):
            token = self.token_manager.get_next_token()
            if not token:
                raise HTTPException(status_code=503, detail="没有可用的token")
            
            # 构建完整URL
            url = f"{self.base_url.rstrip('/')}/{path.lstrip('/')}" if path else self.base_url
            params = {"api_key": token}
            
            # 准备headers
            request_headers = self._prepare_headers(headers)
            
            try:
                logger.info(f"代理请求 {method} {url} (attempt {attempt + 1}/{max_retries})")
                
                # 发送请求但不立即读取响应体
                response = await self.session.request(
                    method,
                    url,
                    params=params,
                    headers=request_headers,
                    data=body
                )
                
                # 检查响应状态
                if response.status == 200:
                    logger.info(f"请求成功: {token[:20]}...")
                    return response  # 返回响应对象以支持流式读取
                
                elif response.status in [401, 403]:
                    # 永久拉黑token
                    reason = f"HTTP {response.status} 认证失败"
                    logger.error(f"Token认证失败({response.status})，永久拉黑: {token[:20]}...")
                    self.token_manager.blacklist_token(token, reason)
                    await response.release()  # 释放连接
                    continue  # 尝试下一个token
                
                elif response.status == 429:
                    # 速率限制，临时失效
                    logger.warning(f"Token达到速率限制: {token[:20]}...")
                    self.token_manager.mark_token_failed(token)
                    await response.release()
                    await asyncio.sleep(1)  # 等待1秒后重试
                    continue
                
                else:
                    # 其他错误
                    response_text = await response.text()
                    logger.error(f"请求失败: {response.status} - {response_text[:200]}")
                    await response.release()
                    
                    if attempt == max_retries - 1:
                        raise HTTPException(
                            status_code=response.status,
                            detail=f"上游服务器错误: {response.status}"
                        )
                    await asyncio.sleep(0.5)  # 短暂等待后重试
            
            except aiohttp.ClientError as e:
                logger.error(f"网络错误: {e}")
                if attempt == max_retries - 1:
                    raise HTTPException(status_code=503, detail="网络连接错误")
                await asyncio.sleep(1)
        
        raise HTTPException(status_code=503, detail="所有重试都失败了")
    
    async def stream_response(self, response: aiohttp.ClientResponse):
        """流式读取响应数据"""
        try:
            async for chunk in response.content.iter_chunked(8192):
                yield chunk
        finally:
            await response.release()

# 全局变量
token_manager = TokenManager()
mcp_proxy = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    global mcp_proxy
    # 启动时初始化
    mcp_proxy = MCPProxy(token_manager)
    await mcp_proxy.__aenter__()  # 初始化会话
    logger.info("MCP代理服务启动")
    yield
    # 关闭时清理
    if mcp_proxy:
        await mcp_proxy.__aexit__(None, None, None)
    logger.info("MCP代理服务关闭")

# 创建FastAPI应用
app = FastAPI(
    title="飞常准MCP代理服务",
    description="提供token轮询功能的飞常准MCP服务器代理",
    version="1.0.0",
    lifespan=lifespan
)

@app.get("/")
async def root():
    """健康检查和服务信息"""
    stats = token_manager.get_stats()
    return JSONResponse(
        content={
            "service": "飞常准MCP代理服务",
            "status": "running",
            "token_stats": stats
        },
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream"
        }
    )

@app.get("/stats")
async def get_stats():
    """获取详细统计信息"""
    return JSONResponse(
        content={
            "token_stats": token_manager.get_stats(),
            "service_info": {
                "base_url": mcp_proxy.base_url if mcp_proxy else None,
                "version": "1.0.0"
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
