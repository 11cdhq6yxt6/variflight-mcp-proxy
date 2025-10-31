#!/usr/bin/env python3
"""
MCP工具基类定义
所有MCP工具都必须继承此类并实现其抽象方法
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, List
import asyncio
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class ToolStatus:
    """工具状态枚举"""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


class ToolProtocol(ABC):
    """
    MCP工具基类抽象协议

    所有工具都必须继承此类并实现以下抽象方法：
    - init(): 初始化工具
    - shutdown(): 关闭工具
    - handle_request(): 处理MCP请求
    """

    def __init__(self, name: str, version: str = "1.0.0", description: str = ""):
        """
        初始化工具基类

        Args:
            name: 工具名称
            version: 工具版本
            description: 工具描述
        """
        self.name = name
        self.version = version
        self.description = description
        self.status = ToolStatus.STOPPED
        self.created_at = datetime.now()
        self.started_at: Optional[datetime] = None
        self.error_count = 0
        self.request_count = 0
        self.logger = logging.getLogger(f"tool.{name}")

        # 工具统计信息
        self.stats = {
            "requests_total": 0,
            "requests_success": 0,
            "requests_failed": 0,
            "last_used": None,
            "uptime_seconds": 0,
        }

    @abstractmethod
    async def init(self) -> bool:
        """
        初始化工具

        Returns:
            bool: 初始化是否成功

        Raises:
            Exception: 初始化失败时抛出异常
        """
        pass

    @abstractmethod
    async def shutdown(self) -> bool:
        """
        关闭工具

        Returns:
            bool: 关闭是否成功
        """
        pass

    @abstractmethod
    async def handle_request(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理MCP请求

        Args:
            method: 请求方法名
            params: 请求参数

        Returns:
            Dict[str, Any]: 响应结果

        Raises:
            Exception: 处理失败时抛出异常
        """
        pass

    async def start(self) -> bool:
        """启动工具"""
        if self.status == ToolStatus.RUNNING:
            self.logger.warning(f"工具 {self.name} 已经在运行中")
            return True

        try:
            self.status = ToolStatus.STARTING
            self.logger.info(f"正在启动工具 {self.name} v{self.version}")

            success = await self.init()

            if success:
                self.status = ToolStatus.RUNNING
                self.started_at = datetime.now()
                self.logger.info(f"工具 {self.name} 启动成功")
                return True
            else:
                self.status = ToolStatus.ERROR
                self.error_count += 1
                self.logger.error(f"工具 {self.name} 启动失败")
                return False

        except Exception as e:
            self.status = ToolStatus.ERROR
            self.error_count += 1
            self.logger.error(f"工具 {self.name} 启动异常: {e}")
            raise

    async def stop(self) -> bool:
        """停止工具"""
        if self.status == ToolStatus.STOPPED:
            self.logger.warning(f"工具 {self.name} 已经停止")
            return True

        try:
            self.status = ToolStatus.STOPPING
            self.logger.info(f"正在停止工具 {self.name}")

            success = await self.shutdown()

            if success:
                self.status = ToolStatus.STOPPED
                self.started_at = None
                self.logger.info(f"工具 {self.name} 停止成功")
                return True
            else:
                self.status = ToolStatus.ERROR
                self.error_count += 1
                self.logger.error(f"工具 {self.name} 停止失败")
                return False

        except Exception as e:
            self.status = ToolStatus.ERROR
            self.error_count += 1
            self.logger.error(f"工具 {self.name} 停止异常: {e}")
            raise

    async def restart(self) -> bool:
        """重启工具"""
        self.logger.info(f"正在重启工具 {self.name}")
        await self.stop()
        await asyncio.sleep(0.5)  # 短暂等待
        return await self.start()

    def get_status(self) -> Dict[str, Any]:
        """
        获取工具状态信息

        Returns:
            Dict[str, Any]: 状态信息字典
        """
        uptime = 0
        if self.started_at:
            uptime = int((datetime.now() - self.started_at).total_seconds())

        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "uptime_seconds": uptime,
            "error_count": self.error_count,
            "request_count": self.request_count,
        }

    def get_stats(self) -> Dict[str, Any]:
        """
        获取工具统计信息

        Returns:
            Dict[str, Any]: 统计信息字典
        """
        self.stats["uptime_seconds"] = 0
        if self.started_at:
            self.stats["uptime_seconds"] = int((datetime.now() - self.started_at).total_seconds())

        return self.stats.copy()

    def increment_request(self, success: bool = True):
        """增加请求计数"""
        self.request_count += 1
        self.stats["requests_total"] += 1
        self.stats["last_used"] = datetime.now().isoformat()

        if success:
            self.stats["requests_success"] += 1
        else:
            self.stats["requests_failed"] += 1

    def get_health(self) -> Dict[str, Any]:
        """
        获取工具健康状态

        Returns:
            Dict[str, Any]: 健康状态信息
        """
        is_healthy = self.status == ToolStatus.RUNNING and self.error_count < 5

        return {
            "healthy": is_healthy,
            "status": self.status,
            "error_count": self.error_count,
            "last_error": None,  # 可扩展存储最后错误信息
        }

    def __repr__(self) -> str:
        return f"<Tool {self.name} v{self.version} status={self.status}>"
