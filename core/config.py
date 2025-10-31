#!/usr/bin/env python3
"""
配置管理系统
支持环境变量、配置文件等多种配置来源
"""

import os
import json
from typing import Any, Dict, Optional, Union
from pathlib import Path
import logging

try:
    import yaml
    HAS_YAML = True
except ImportError:
    yaml = None
    HAS_YAML = False

logger = logging.getLogger(__name__)


class ConfigManager:
    """
    配置管理器

    支持多种配置源：
    1. 环境变量 (最高优先级)
    2. 配置文件 (JSON/YAML)
    3. 默认值 (最低优先级)

    配置格式：
    - 工具配置: TOOL_{NAME}_{KEY}
    - 全局配置: MCP_{KEY}
    """

    def __init__(self, config_file: Optional[str] = None):
        """
        初始化配置管理器

        Args:
            config_file: 配置文件路径，支持.json和.yaml格式
        """
        self.config_file = config_file
        self._config_cache: Dict[str, Any] = {}
        self._load_config()

    def _load_config(self):
        """从配置文件加载配置"""
        if not self.config_file or not os.path.exists(self.config_file):
            logger.info("未找到配置文件或未指定配置文件")
            return

        try:
            file_path = Path(self.config_file)

            if file_path.suffix.lower() == '.json':
                with open(file_path, 'r', encoding='utf-8') as f:
                    self._config_cache = json.load(f)
            elif file_path.suffix.lower() in ['.yaml', '.yml']:
                if not HAS_YAML:
                    logger.warning("未安装PyYAML，无法加载YAML配置文件")
                    return
                with open(file_path, 'r', encoding='utf-8') as f:
                    self._config_cache = yaml.safe_load(f) or {}
            else:
                logger.warning(f"不支持的配置文件格式: {file_path.suffix}")

            logger.info(f"已加载配置文件: {self.config_file}")

        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
            self._config_cache = {}

    def get(self, key: str, default: Any = None, tool_name: Optional[str] = None) -> Any:
        """
        获取配置值

        优先级：
        1. 环境变量 TOOL_{TOOL_NAME}_{KEY}
        2. 环境变量 MCP_{KEY}
        3. 配置文件 tool.{tool_name}.{key}
        4. 配置文件 {key}
        5. 默认值

        Args:
            key: 配置键名
            default: 默认值
            tool_name: 工具名称（可选）

        Returns:
            Any: 配置值
        """
        # 1. 检查环境变量 (TOOL_{TOOL_NAME}_{KEY})
        if tool_name:
            env_key = f"TOOL_{tool_name.upper()}_{key.upper()}"
            env_value = os.environ.get(env_key)
            if env_value is not None:
                return self._convert_env_value(env_value)

        # 2. 检查全局环境变量 (MCP_{KEY})
        global_env_key = f"MCP_{key.upper()}"
        env_value = os.environ.get(global_env_key)
        if env_value is not None:
            return self._convert_env_value(env_value)

        # 3. 检查配置文件
        if self._config_cache:
            # 3.1 尝试工具级配置
            if tool_name and 'tools' in self._config_cache:
                tool_config = self._config_cache.get('tools', {})
                if tool_name in tool_config:
                    value = tool_config[tool_name].get(key)
                    if value is not None:
                        return value

            # 3.2 尝试全局配置
            value = self._config_cache.get(key)
            if value is not None:
                return value

        # 4. 返回默认值
        return default

    def set(self, key: str, value: Any, tool_name: Optional[str] = None):
        """
        设置配置值（仅内存中，不写入文件）

        Args:
            key: 配置键名
            value: 配置值
            tool_name: 工具名称（可选）
        """
        cache_key = f"{tool_name}.{key}" if tool_name else key
        self._config_cache[cache_key] = value

    def get_tool_config(self, tool_name: str) -> Dict[str, Any]:
        """
        获取工具的完整配置

        Args:
            tool_name: 工具名称

        Returns:
            Dict[str, Any]: 工具配置字典
        """
        config = {}

        # 从配置文件获取
        if self._config_cache and 'tools' in self._config_cache:
            tool_config = self._config_cache.get('tools', {})
            if tool_name in tool_config:
                config.update(tool_config[tool_name])

        return config

    def get_all_configs(self) -> Dict[str, Any]:
        """
        获取所有配置

        Returns:
            Dict[str, Any]: 所有配置（敏感信息会被隐藏）
        """
        # 返回配置副本，隐藏敏感信息
        safe_config = self._config_cache.copy()

        # 隐藏可能包含token或密码的配置项
        sensitive_keys = ['token', 'password', 'secret', 'key', 'api_key', 'auth']
        for key in list(safe_config.keys()):
            key_lower = key.lower()
            if any(sk in key_lower for sk in sensitive_keys):
                safe_config[key] = "***HIDDEN***"

        return safe_config

    def _convert_env_value(self, value: str) -> Union[str, int, float, bool, list, dict]:
        """
        转换环境变量值为合适的类型

        Args:
            value: 环境变量原始值

        Returns:
            Union[str, int, float, bool, list, dict]: 转换后的值
        """
        # 尝试解析JSON格式
        if value.startswith(('{', '[')):
            try:
                return json.loads(value)
            except (json.JSONDecodeError, ValueError):
                pass

        # 布尔值
        if value.lower() in ('true', 'yes', '1', 'on'):
            return True
        elif value.lower() in ('false', 'no', '0', 'off'):
            return False

        # 数字
        try:
            if '.' in value:
                return float(value)
            else:
                return int(value)
        except (ValueError, TypeError):
            pass

        # 列表（逗号分隔）
        if ',' in value:
            return [item.strip() for item in value.split(',')]

        # 默认返回字符串
        return value

    def reload(self):
        """重新加载配置文件"""
        logger.info("重新加载配置文件")
        self._config_cache = {}
        self._load_config()

    def validate_required_configs(self, tool_name: str, required_keys: list) -> bool:
        """
        验证工具必需的配置项

        Args:
            tool_name: 工具名称
            required_keys: 必需的配置键列表

        Returns:
            bool: 验证是否通过
        """
        missing_keys = []
        for key in required_keys:
            value = self.get(key, tool_name=tool_name)
            if value is None:
                missing_keys.append(key)

        if missing_keys:
            logger.error(f"工具 {tool_name} 缺少必需的配置项: {missing_keys}")
            return False

        return True

    def __repr__(self) -> str:
        return f"<ConfigManager file={self.config_file}>"


# 全局配置实例
_global_config_manager: Optional[ConfigManager] = None


def get_config_manager(config_file: Optional[str] = None) -> ConfigManager:
    """
    获取全局配置管理器实例

    Args:
        config_file: 配置文件路径

    Returns:
        ConfigManager: 配置管理器实例
    """
    global _global_config_manager

    if _global_config_manager is None:
        _global_config_manager = ConfigManager(config_file)

    return _global_config_manager


def get_config(key: str, default: Any = None, tool_name: Optional[str] = None) -> Any:
    """
    便捷函数：获取配置值

    Args:
        key: 配置键名
        default: 默认值
        tool_name: 工具名称

    Returns:
        Any: 配置值
    """
    return get_config_manager().get(key, default, tool_name)


def set_config(key: str, value: Any, tool_name: Optional[str] = None):
    """
    便捷函数：设置配置值

    Args:
        key: 配置键名
        value: 配置值
        tool_name: 工具名称
    """
    get_config_manager().set(key, value, tool_name)
