#!/usr/bin/env python3
"""
工具注册表
统一管理所有MCP工具的注册、启动、停止和状态监控
"""

from typing import Dict, List, Optional, Type, Any
import asyncio
import logging
from datetime import datetime

from .config import get_config_manager
from tools.base import ToolProtocol, ToolStatus

logger = logging.getLogger(__name__)


class ToolRegistry:
    """
    工具注册表

    负责：
    - 工具注册和注销
    - 工具生命周期管理（启动、停止、重启）
    - 工具状态监控
    - 工具统计信息收集
    - 工具间依赖管理
    """

    def __init__(self):
        """初始化工具注册表"""
        self._tools: Dict[str, ToolProtocol] = {}
        self._tool_classes: Dict[str, Type[ToolProtocol]] = {}
        self._tool_dependencies: Dict[str, List[str]] = {}
        self._lock = asyncio.Lock()

    async def register_tool(
        self,
        tool_class: Type[ToolProtocol],
        name: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        dependencies: Optional[List[str]] = None,
    ) -> bool:
        """
        注册工具类

        Args:
            tool_class: 工具类（必须是ToolProtocol的子类）
            name: 工具名称（默认为类名）
            config: 工具配置
            dependencies: 依赖的工具名称列表

        Returns:
            bool: 注册是否成功
        """
        if not issubclass(tool_class, ToolProtocol):
            logger.error(f"工具类 {tool_class.__name__} 不是ToolProtocol的子类")
            return False

        tool_name = name or tool_class.__name__
        config = config or {}

        async with self._lock:
            # 检查是否已注册
            if tool_name in self._tools:
                logger.warning(f"工具 {tool_name} 已经注册，将被覆盖")

            # 注册工具类
            self._tool_classes[tool_name] = tool_class

            # 设置依赖关系
            if dependencies:
                self._tool_dependencies[tool_name] = dependencies

            # 创建工具实例
            try:
                tool_instance = tool_class(
                    name=tool_name,
                    version=config.get('version', '1.0.0'),
                    description=config.get('description', '')
                )
                self._tools[tool_name] = tool_instance

                logger.info(f"工具 {tool_name} 注册成功")
                return True

            except Exception as e:
                logger.error(f"创建工具实例失败: {e}")
                return False

    async def unregister_tool(self, name: str) -> bool:
        """
        注销工具

        Args:
            name: 工具名称

        Returns:
            bool: 注销是否成功
        """
        async with self._lock:
            if name not in self._tools:
                logger.warning(f"工具 {name} 未注册")
                return False

            # 停止工具
            tool = self._tools[name]
            if tool.status == ToolStatus.RUNNING:
                await tool.stop()

            # 从注册表移除
            del self._tools[name]
            self._tool_classes.pop(name, None)
            self._tool_dependencies.pop(name, None)

            logger.info(f"工具 {name} 已注销")
            return True

    async def start_tool(self, name: str) -> bool:
        """
        启动指定工具

        Args:
            name: 工具名称

        Returns:
            bool: 启动是否成功
        """
        if name not in self._tools:
            logger.error(f"工具 {name} 未注册")
            return False

        tool = self._tools[name]

        # 检查依赖关系
        if not await self._check_dependencies(name):
            logger.error(f"工具 {name} 的依赖项未满足")
            return False

        try:
            success = await tool.start()
            if success:
                logger.info(f"工具 {name} 启动成功")
            else:
                logger.error(f"工具 {name} 启动失败")
            return success

        except Exception as e:
            logger.error(f"启动工具 {name} 时发生异常: {e}")
            return False

    async def start_all_tools(self) -> Dict[str, bool]:
        """
        启动所有已注册的工具

        Returns:
            Dict[str, bool]: 各工具启动结果
        """
        results = {}
        started_tools = set()

        # 拓扑排序确定启动顺序
        sorted_tools = self._topological_sort()

        for tool_name in sorted_tools:
            if tool_name in self._tools:
                results[tool_name] = await self.start_tool(tool_name)
                if results[tool_name]:
                    started_tools.add(tool_name)

        # 启动未排序的工具（无依赖的工具）
        for name, tool in self._tools.items():
            if name not in started_tools and tool.status == ToolStatus.STOPPED:
                results[name] = await self.start_tool(name)

        return results

    async def stop_tool(self, name: str) -> bool:
        """
        停止指定工具

        Args:
            name: 工具名称

        Returns:
            bool: 停止是否成功
        """
        if name not in self._tools:
            logger.error(f"工具 {name} 未注册")
            return False

        tool = self._tools[name]

        try:
            success = await tool.stop()
            if success:
                logger.info(f"工具 {name} 停止成功")
            else:
                logger.error(f"工具 {name} 停止失败")
            return success

        except Exception as e:
            logger.error(f"停止工具 {name} 时发生异常: {e}")
            return False

    async def stop_all_tools(self) -> Dict[str, bool]:
        """
        停止所有已注册的工具

        Returns:
            Dict[str, bool]: 各工具停止结果
        """
        results = {}

        # 按依赖关系的逆序停止
        sorted_tools = self._topological_sort()
        sorted_tools.reverse()

        for tool_name in sorted_tools:
            if tool_name in self._tools:
                results[tool_name] = await self.stop_tool(tool_name)

        # 停止剩余工具
        for name, tool in self._tools.items():
            if name not in results:
                results[name] = await self.stop_tool(name)

        return results

    async def restart_tool(self, name: str) -> bool:
        """
        重启指定工具

        Args:
            name: 工具名称

        Returns:
            bool: 重启是否成功
        """
        if name not in self._tools:
            logger.error(f"工具 {name} 未注册")
            return False

        logger.info(f"正在重启工具 {name}")
        return await self._tools[name].restart()

    def get_tool(self, name: str) -> Optional[ToolProtocol]:
        """
        获取工具实例

        Args:
            name: 工具名称

        Returns:
            Optional[ToolProtocol]: 工具实例，如果不存在则返回None
        """
        return self._tools.get(name)

    def list_tools(self) -> List[str]:
        """
        获取所有已注册的工具名称列表

        Returns:
            List[str]: 工具名称列表
        """
        return list(self._tools.keys())

    def get_tool_status(self, name: str) -> Optional[Dict[str, Any]]:
        """
        获取工具状态

        Args:
            name: 工具名称

        Returns:
            Optional[Dict[str, Any]]: 工具状态信息
        """
        tool = self._tools.get(name)
        if not tool:
            return None

        return tool.get_status()

    def get_all_tools_status(self) -> Dict[str, Dict[str, Any]]:
        """
        获取所有工具状态

        Returns:
            Dict[str, Dict[str, Any]]: 各工具状态信息
        """
        return {name: tool.get_status() for name, tool in self._tools.items()}

    def get_tool_stats(self, name: str) -> Optional[Dict[str, Any]]:
        """
        获取工具统计信息

        Args:
            name: 工具名称

        Returns:
            Optional[Dict[str, Any]]: 工具统计信息
        """
        tool = self._tools.get(name)
        if not tool:
            return None

        return tool.get_stats()

    def get_all_tools_stats(self) -> Dict[str, Dict[str, Any]]:
        """
        获取所有工具统计信息

        Returns:
            Dict[str, Dict[str, Any]]: 各工具统计信息
        """
        return {name: tool.get_stats() for name, tool in self._tools.items()}

    def get_tools_health(self) -> Dict[str, Dict[str, Any]]:
        """
        获取所有工具的健康状态

        Returns:
            Dict[str, Dict[str, Any]]: 各工具健康状态
        """
        return {name: tool.get_health() for name, tool in self._tools.items()}

    def is_tool_running(self, name: str) -> bool:
        """
        检查工具是否正在运行

        Args:
            name: 工具名称

        Returns:
            bool: 工具是否运行中
        """
        tool = self._tools.get(name)
        return tool is not None and tool.status == ToolStatus.RUNNING

    async def _check_dependencies(self, name: str) -> bool:
        """
        检查工具的依赖关系是否满足

        Args:
            name: 工具名称

        Returns:
            bool: 依赖是否满足
        """
        dependencies = self._tool_dependencies.get(name, [])
        for dep_name in dependencies:
            if not self.is_tool_running(dep_name):
                logger.warning(f"工具 {name} 依赖的工具 {dep_name} 未运行")
                return False
        return True

    def _topological_sort(self) -> List[str]:
        """
        对工具进行拓扑排序

        Returns:
            List[str]: 排序后的工具名称列表
        """
        visited = set()
        temp_visited = set()
        result = []

        def visit(name: str):
            if name in temp_visited:
                logger.warning(f"检测到工具依赖循环: {name}")
                return
            if name in visited:
                return

            temp_visited.add(name)

            # 先访问依赖的工具
            for dep in self._tool_dependencies.get(name, []):
                if dep in self._tools:
                    visit(dep)

            temp_visited.remove(name)
            visited.add(name)
            result.append(name)

        for name in self._tools.keys():
            if name not in visited:
                visit(name)

        return result

    async def cleanup(self):
        """清理资源：停止所有工具"""
        logger.info("正在清理工具注册表...")
        await self.stop_all_tools()
        self._tools.clear()
        self._tool_classes.clear()
        self._tool_dependencies.clear()


# 全局注册表实例
_global_registry: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    """
    获取全局工具注册表实例

    Returns:
        ToolRegistry: 工具注册表实例
    """
    global _global_registry

    if _global_registry is None:
        _global_registry = ToolRegistry()

    return _global_registry
