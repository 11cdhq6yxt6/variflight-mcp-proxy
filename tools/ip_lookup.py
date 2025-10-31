#!/usr/bin/env python3
"""
IP查询工具
提供IP地址查询、地理位置检测、ISP信息等功能
支持多个数据源查询和结果合并
"""

import asyncio
import json
from typing import Dict, Any, Optional, List
import aiohttp
from fastapi import HTTPException

from .base import ToolProtocol
from core.config import get_config

logger = __import__('logging').getLogger(__name__)


class IPQueryTool(ToolProtocol):
    """
    IP查询工具

    支持功能：
    - 获取客户端IP地址
    - 查询IP的地理位置信息
    - 查询ISP和ASN信息
    - 多数据源整合
    - 地理编码（坐标转地址）
    """

    def __init__(self, name: str = "IPLookup", version: str = "1.0.0", description: str = "IP地址查询工具"):
        """
        初始化IP查询工具

        Args:
            name: 工具名称
            version: 工具版本
            description: 工具描述
        """
        super().__init__(name, version, description)

        # 配置参数
        self.timeout = get_config("timeout", 10, "IPLookup")
        self.max_retries = get_config("max_retries", 2, "IPLookup")
        self.enable_multiple_sources = get_config("enable_multiple_sources", True, "IPLookup")

        # API 端点配置 - 使用 getip.js 中的数据源接口
        self.api_endpoints = {
            # getip.js 中使用的数据源
            "ipgeo_api": "https://ipgeo-api.hf.space/{ip}",
            "bilibili_api": "https://api.live.bilibili.com/client/v1/Ip/getInfoNew?ip={ip}",
            "meituan_api": "https://apimobile.meituan.com/locate/v2/ip/loc?rgeo=true&ip={ip}",

            # 备用接口
            "ipapi": "http://ip-api.com/json/{ip}",
            "ipapi_co": "https://ipapi.co/{ip}/json/",
            "ipgeolocation": "https://api.ipgeolocation.io/ipgeo",
            "ipinfo": "https://ipinfo.io/{ip}/json",
        }

        # HTTP 会话
        self.session: Optional[aiohttp.ClientSession] = None

    async def init(self) -> bool:
        """
        初始化IP查询工具

        Returns:
            bool: 初始化是否成功
        """
        try:
            # 创建HTTP会话
            connector = aiohttp.TCPConnector(
                limit=100,
                ttl_dns_cache=300,
                use_dns_cache=True,
                keepalive_timeout=30,
                enable_cleanup_closed=True
            )

            timeout = aiohttp.ClientTimeout(total=self.timeout)
            self.session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                headers={
                    "User-Agent": "IPLookup-Tool/1.0.0"
                }
            )

            self.logger.info("IP查询工具初始化完成")
            return True

        except Exception as e:
            self.logger.error(f"IP查询工具初始化失败: {e}")
            return False

    async def shutdown(self) -> bool:
        """
        关闭IP查询工具

        Returns:
            bool: 关闭是否成功
        """
        try:
            if self.session and not self.session.closed:
                await self.session.close()
                self.session = None

            self.logger.info("IP查询工具关闭完成")
            return True

        except Exception as e:
            self.logger.error(f"IP查询工具关闭失败: {e}")
            return False

    async def handle_request(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理IP查询请求

        Args:
            method: 请求方法名
            params: 请求参数字典

        Returns:
            Dict[str, Any]: 查询结果

        Raises:
            Exception: 处理失败时抛出异常
        """
        if not self.session:
            raise HTTPException(status_code=503, detail="IP查询工具未初始化")

        self.increment_request()

        try:
            # 从 params 中获取 action，如果没有则根据 method 参数推断
            action = params.get("action") or method
            if not action:
                raise HTTPException(status_code=400, detail="缺少 action 参数")

            if action == "lookup":
                ip = params.get("ip")
                if not ip:
                    raise HTTPException(status_code=400, detail="缺少IP地址参数")

                return await self.lookup_ip(ip)

            elif action == "batch_lookup":
                ips = params.get("ips", [])
                if not ips:
                    raise HTTPException(status_code=400, detail="缺少IP列表参数")

                return await self.batch_lookup(ips)

            elif action == "geo_lookup":
                """地理编码查询 - 根据坐标查询地址"""
                lat = params.get("latitude")
                lng = params.get("longitude")
                if lat is None or lng is None:
                    raise HTTPException(status_code=400, detail="缺少坐标参数")

                return await self.geo_lookup(float(lat), float(lng))

            elif action == "my_ip" or action == "get_my_ip":
                """获取本机IP"""
                return await self.get_my_ip()

            else:
                raise HTTPException(status_code=400, detail=f"不支持的操作: {action}")

        except HTTPException:
            raise
        except Exception as e:
            self.increment_request(success=False)
            self.logger.error(f"处理请求失败: {e}")
            raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")

    async def lookup_ip(self, ip: str) -> Dict[str, Any]:
        """
        查询单个IP的详细信息

        Args:
            ip: IP地址

        Returns:
            Dict[str, Any]: IP信息
        """
        self.logger.info(f"查询IP信息: {ip}")

        if not self.enable_multiple_sources:
            # 单数据源查询
            result = await self._query_single_source(ip)
            return {
                "ip": ip,
                "source": "single",
                "data": result
            }
        else:
            # 多数据源查询
            results = await self._query_multiple_sources(ip)

            # 合并和去重结果
            merged_data = self._merge_results(results)

            return {
                "ip": ip,
                "sources_count": len(results),
                "sources": list(results.keys()),
                "data": merged_data
            }

    async def batch_lookup(self, ips: List[str]) -> Dict[str, Any]:
        """
        批量查询多个IP

        Args:
            ips: IP地址列表

        Returns:
            Dict[str, Any]: 批量查询结果
        """
        self.logger.info(f"批量查询 {len(ips)} 个IP")

        tasks = []
        for ip in ips:
            tasks.append(self.lookup_ip(ip))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 处理结果
        response = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                response.append({
                    "ip": ips[i],
                    "error": str(result)
                })
            else:
                response.append(result)

        return {
            "total": len(ips),
            "success": len([r for r in response if "error" not in r]),
            "failed": len([r for r in response if "error" in r]),
            "results": response
        }

    async def geo_lookup(self, latitude: float, longitude: float) -> Dict[str, Any]:
        """
        地理编码查询 - 根据坐标查询地址

        Args:
            latitude: 纬度
            longitude: 经度

        Returns:
            Dict[str, Any]: 地址信息
        """
        self.logger.info(f"地理编码查询: {latitude}, {longitude}")

        try:
            # 使用多个地理编码服务
            results = await asyncio.gather(
                self._query_opencage(latitude, longitude),
                self._query_nominatim(latitude, longitude),
                return_exceptions=True
            )

            # 合并结果
            locations = []
            for result in results:
                if not isinstance(result, Exception) and result:
                    locations.append(result)

            return {
                "coordinates": {
                    "latitude": latitude,
                    "longitude": longitude
                },
                "locations": locations
            }

        except Exception as e:
            self.logger.error(f"地理编码查询失败: {e}")
            raise HTTPException(status_code=500, detail=f"地理编码查询失败: {str(e)}")

    async def get_my_ip(self) -> Dict[str, Any]:
        """
        获取本机公网IP地址

        Returns:
            Dict[str, Any]: 本机IP信息
        """
        self.logger.info("获取本机公网IP")

        try:
            # 使用多个服务检测本机IP
            results = await asyncio.gather(
                self._query_my_ip("https://api.ipify.org?format=json"),
                self._query_my_ip("https://api.my-ip.io/ip"),
                self._query_my_ip("https://checkip.amazonaws.com"),
                return_exceptions=True
            )

            # 提取有效的IP
            ips = []
            for result in results:
                if not isinstance(result, Exception) and result:
                    ip = result.get("ip") if isinstance(result, dict) else result.strip()
                    if ip and ip not in ips:
                        ips.append(ip)

            if not ips:
                raise HTTPException(status_code=503, detail="无法检测到本机IP")

            # 查询第一个IP的详细信息
            primary_ip = ips[0]
            ip_info = await self.lookup_ip(primary_ip)

            return {
                "detected_ips": ips,
                "primary_ip": primary_ip,
                "info": ip_info
            }

        except Exception as e:
            self.logger.error(f"获取本机IP失败: {e}")
            raise HTTPException(status_code=500, detail=f"获取本机IP失败: {str(e)}")

    async def _query_single_source(self, ip: str) -> Dict[str, Any]:
        """使用单一数据源查询IP信息 - 优先使用 getip.js 中的数据源"""
        # 优先使用 ipgeo-api.hf.space (getip.js 中的主要数据源)
        url = self.api_endpoints["ipgeo_api"].format(ip=ip)

        for attempt in range(self.max_retries + 1):
            try:
                async with self.session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        # 使用 ipgeo-api 的标准化响应
                        return self._normalize_ipgeo_api_response(data)
                    else:
                        self.logger.warning(f"API请求失败: {response.status}")
            except Exception as e:
                self.logger.warning(f"查询尝试 {attempt + 1} 失败: {e}")

            if attempt < self.max_retries:
                await asyncio.sleep(1)

        raise HTTPException(status_code=503, detail=f"无法查询IP信息: {ip}")

    async def _query_multiple_sources(self, ip: str) -> Dict[str, Any]:
        """使用多个数据源查询IP信息 - 优先使用 getip.js 中的数据源"""
        # 优先使用 getip.js 中的数据源
        tasks = {
            "ipgeo_api": self._query_ipgeo_api(ip),
            "bilibili_api": self._query_bilibili_api(ip),
            "meituan_api": self._query_meituan_api(ip),
            "ipapi": self._query_ipapi(ip),
            "ipapi_co": self._query_ipapi_co(ip),
            "ipgeolocation": self._query_ipgeolocation(ip),
            "ipinfo": self._query_ipinfo(ip),
        }

        results = await asyncio.gather(
            *[task for task in tasks.values()],
            return_exceptions=True
        )

        # 整理结果
        response = {}
        for name, result in zip(tasks.keys(), results):
            if not isinstance(result, Exception) and result:
                response[name] = result

        if not response:
            raise HTTPException(status_code=503, detail=f"所有数据源查询失败: {ip}")

        return response

    async def _query_ipapi(self, ip: str) -> Optional[Dict[str, Any]]:
        """查询 ip-api.com"""
        try:
            url = f"http://ip-api.com/json/{ip}?lang=zh-CN"
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("status") == "success":
                        return self._normalize_ipapi_response(data)
        except Exception as e:
            self.logger.debug(f"ip-api.com 查询失败: {e}")

        return None

    async def _query_ipgeo_api(self, ip: str) -> Optional[Dict[str, Any]]:
        """查询 ipgeo-api.hf.space (getip.js 使用的数据源)"""
        try:
            url = f"https://ipgeo-api.hf.space/{ip}"
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return self._normalize_ipgeo_api_response(data)
        except Exception as e:
            self.logger.debug(f"ipgeo-api.hf.space 查询失败: {e}")

        return None

    async def _query_bilibili_api(self, ip: str) -> Optional[Dict[str, Any]]:
        """查询 api.live.bilibili.com (getip.js 使用的数据源)"""
        try:
            url = f"https://api.live.bilibili.com/client/v1/Ip/getInfoNew?ip={ip}"
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("code") == 0 and data.get("data"):
                        return self._normalize_bilibili_api_response(data["data"])
        except Exception as e:
            self.logger.debug(f"api.live.bilibili.com 查询失败: {e}")

        return None

    async def _query_meituan_api(self, ip: str) -> Optional[Dict[str, Any]]:
        """查询 apimobile.meituan.com (getip.js 使用的数据源)"""
        try:
            url = f"https://apimobile.meituan.com/locate/v2/ip/loc?rgeo=true&ip={ip}"
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("status") == 0 and data.get("data"):
                        return self._normalize_meituan_api_response(data["data"])
        except Exception as e:
            self.logger.debug(f"apimobile.meituan.com 查询失败: {e}")

        return None

    async def _query_ipapi_co(self, ip: str) -> Optional[Dict[str, Any]]:
        """查询 ipapi.co"""
        try:
            url = f"https://ipapi.co/{ip}/json/"
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return self._normalize_ipapi_co_response(data)
        except Exception as e:
            self.logger.debug(f"ipapi.co 查询失败: {e}")

        return None

    async def _query_ipgeolocation(self, ip: str) -> Optional[Dict[str, Any]]:
        """查询 ipgeolocation.io"""
        try:
            # 需要 API Key，这里仅作示例
            url = f"https://api.ipgeolocation.io/ipgeo?ip={ip}"
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return self._normalize_ipgeolocation_response(data)
        except Exception as e:
            self.logger.debug(f"ipgeolocation.io 查询失败: {e}")

        return None

    async def _query_ipinfo(self, ip: str) -> Optional[Dict[str, Any]]:
        """查询 ipinfo.io"""
        try:
            url = f"https://ipinfo.io/{ip}/json"
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return self._normalize_ipinfo_response(data)
        except Exception as e:
            self.logger.debug(f"ipinfo.io 查询失败: {e}")

        return None

    async def _query_opencage(self, lat: float, lng: float) -> Optional[Dict[str, Any]]:
        """查询 OpenCage 地理编码服务"""
        try:
            url = f"https://api.opencagedata.com/geocode/v1/json?q={lat}+{lng}&language=zh"
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("results"):
                        result = data["results"][0]
                        return {
                            "source": "opencage",
                            "formatted": result.get("formatted"),
                            "components": result.get("components")
                        }
        except Exception as e:
            self.logger.debug(f"OpenCage 查询失败: {e}")

        return None

    async def _query_nominatim(self, lat: float, lng: float) -> Optional[Dict[str, Any]]:
        """查询 Nominatim 地理编码服务 (OpenStreetMap)"""
        try:
            url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lng}&accept-language=zh"
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return {
                        "source": "nominatim",
                        "display_name": data.get("display_name"),
                        "address": data.get("address")
                    }
        except Exception as e:
            self.logger.debug(f"Nominatim 查询失败: {e}")

        return None

    async def _query_my_ip(self, url: str) -> Optional[Dict[str, Any]]:
        """查询本机IP"""
        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    content = await response.text()
                    try:
                        return json.loads(content)
                    except json.JSONDecodeError:
                        return {"ip": content.strip()}
        except Exception as e:
            self.logger.debug(f"查询本机IP失败 ({url}): {e}")

        return None

    def _normalize_ipapi_response(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """标准化 ip-api.com 响应"""
        return {
            "ip": data.get("query"),
            "country": data.get("country"),
            "country_code": data.get("countryCode"),
            "region": data.get("regionName"),
            "city": data.get("city"),
            "zip": data.get("zip"),
            "latitude": data.get("lat"),
            "longitude": data.get("lon"),
            "timezone": data.get("timezone"),
            "isp": data.get("isp"),
            "org": data.get("org"),
            "as": data.get("as"),
            "status": data.get("status")
        }

    def _normalize_ipapi_co_response(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """标准化 ipapi.co 响应"""
        return {
            "ip": data.get("ip"),
            "country": data.get("country_name"),
            "country_code": data.get("country_code"),
            "region": data.get("region"),
            "city": data.get("city"),
            "zip": data.get("postal"),
            "latitude": data.get("latitude"),
            "longitude": data.get("longitude"),
            "timezone": data.get("timezone"),
            "isp": data.get("org"),
            "as": data.get("asn")
        }

    def _normalize_ipgeolocation_response(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """标准化 ipgeolocation.io 响应"""
        return {
            "ip": data.get("ip"),
            "country": data.get("country_name"),
            "country_code": data.get("country_code2"),
            "region": data.get("state_prov"),
            "city": data.get("city"),
            "zip": data.get("zipcode"),
            "latitude": data.get("latitude"),
            "longitude": data.get("longitude"),
            "timezone": data.get("time_zone", {}).get("name"),
            "isp": data.get("isp"),
            "currency": data.get("currency", {}).get("name")
        }

    def _normalize_ipinfo_response(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """标准化 ipinfo.io 响应"""
        coords = data.get("loc", "").split(",")
        return {
            "ip": data.get("ip"),
            "country": data.get("country"),
            "region": data.get("region"),
            "city": data.get("city"),
            "zip": data.get("postal"),
            "latitude": float(coords[0]) if len(coords) > 0 else None,
            "longitude": float(coords[1]) if len(coords) > 1 else None,
            "timezone": data.get("timezone"),
            "org": data.get("org"),
            "asn": data.get("org", "").split(" ")[0]
        }

    def _normalize_ipgeo_api_response(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        标准化 ipgeo-api.hf.space 响应 (getip.js 使用的数据源)
        """
        # 提取 location 信息
        location = data.get("location", {}) or {}
        country_info = data.get("country", {}) or {}
        as_info = data.get("as", {}) or {}

        return {
            "ip": data.get("ip"),
            "country": country_info.get("name") if isinstance(country_info, dict) else country_info,
            "country_code": data.get("country_code"),
            "region": data.get("regions", [None])[0] if data.get("regions") else data.get("region"),
            "city": data.get("city"),
            "zip": data.get("postal"),
            "latitude": float(location.get("latitude")) if location.get("latitude") else None,
            "longitude": float(location.get("longitude")) if location.get("longitude") else None,
            "timezone": location.get("timezone"),
            "isp": as_info.get("name") if isinstance(as_info, dict) else as_info,
            "org": as_info.get("name") if isinstance(as_info, dict) else as_info,
            "as": as_info.get("asn") if isinstance(as_info, dict) else None,
            "type": data.get("type")
        }

    def _normalize_bilibili_api_response(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        标准化 api.live.bilibili.com 响应 (getip.js 使用的数据源)
        """
        return {
            "ip": data.get("ip"),
            "country": data.get("country_name"),
            "country_code": data.get("country_code"),
            "region": data.get("region_name"),
            "city": data.get("city_name"),
            "zip": data.get("zip_code"),
            "latitude": float(data.get("latitude")) if data.get("latitude") else None,
            "longitude": float(data.get("longitude")) if data.get("longitude") else None,
            "timezone": data.get("timezone_name"),
            "isp": data.get("isp"),
            "org": data.get("isp"),
            "as": data.get("asn")
        }

    def _normalize_meituan_api_response(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        标准化 apimobile.meituan.com 响应 (getip.js 使用的数据源)
        """
        location = data.get("location", {}) or {}

        return {
            "ip": data.get("ip"),
            "country": data.get("country_name"),
            "country_code": data.get("country_code"),
            "region": data.get("province"),
            "city": data.get("city"),
            "zip": data.get("zip_code"),
            "latitude": float(location.get("lat")) if location.get("lat") else None,
            "longitude": float(location.get("lng")) if location.get("lng") else None,
            "timezone": location.get("timezone"),
            "isp": data.get("isp"),
            "org": data.get("isp"),
            "as": data.get("asn")
        }

    def _normalize_getip_response(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        标准化 getip.js /info 响应
        getip.js 整合了多个数据源，包括 cloudflare、ipgeo、bilibili 等
        """
        # 从 cloudflare 数据源提取信息（最可靠）
        cloudflare_data = data.get("sources", {}).get("cloudflare", {})

        # 从 ipgeo 数据源提取信息
        ipgeo_data = data.get("sources", {}).get("ipgeo", {})

        # 从 bilibili 数据源提取信息
        bilibili_data = data.get("sources", {}).get("bilibili", {})

        # 优先使用 cloudflare 的地理位置数据
        latitude = cloudflare_data.get("latitude") or (
            ipgeo_data.get("location", {}).get("latitude") if ipgeo_data.get("location") else None
        )
        longitude = cloudflare_data.get("longitude") or (
            ipgeo_data.get("location", {}).get("longitude") if ipgeo_data.get("location") else None
        )

        # 构建标准化的响应
        normalized = {
            "ip": data.get("ip"),
            "country": (
                cloudflare_data.get("country") or
                ipgeo_data.get("country", {}).get("name") if isinstance(ipgeo_data.get("country"), dict) else
                ipgeo_data.get("country")
            ),
            "country_code": cloudflare_data.get("country_code"),
            "region": cloudflare_data.get("region") or bilibili_data.get("region_name"),
            "city": cloudflare_data.get("city") or bilibili_data.get("city"),
            "zip": cloudflare_data.get("postal_code"),
            "latitude": float(latitude) if latitude else None,
            "longitude": float(longitude) if longitude else None,
            "timezone": cloudflare_data.get("timezone"),
            "isp": bilibili_data.get("isp") or cloudflare_data.get("asOrganization"),
            "org": cloudflare_data.get("asOrganization") or ipgeo_data.get("as", {}).get("name") if isinstance(ipgeo_data.get("as"), dict) else ipgeo_data.get("as", {}),
            "as": cloudflare_data.get("asn"),
            "sources": list(data.get("sources", {}).keys())
        }

        return normalized

    def _normalize_getip_debug_response(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        标准化 getip.js /debug 响应
        包含更详细的信息，包括多个数据源和地理编码
        """
        # 使用基础信息
        normalized = self._normalize_getip_response(data)

        # 添加调试信息
        normalized["debug"] = {
            "method": data.get("method"),
            "url": data.get("url"),
            "headers": data.get("headers", {}),
            "security": data.get("security", {}),
            "geocode": data.get("geocode", [])
        }

        return normalized

    def _merge_results(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """
        合并多个数据源的查询结果
        优先使用 getip.js 中的数据源
        """
        # 定义数据源的可靠性优先级（数字越小越可靠）
        priority = {
            "ipgeo_api": 0,  # 最高优先级 - getip.js 中的主要数据源
            "bilibili_api": 1,  # 高优先级 - getip.js 中的数据源
            "meituan_api": 2,  # 高优先级 - getip.js 中的数据源
            "ipapi": 3,
            "ipapi_co": 4,
            "ipgeolocation": 5,
            "ipinfo": 6
        }

        # 按优先级排序
        sorted_sources = sorted(results.keys(), key=lambda x: priority.get(x, 999))

        # 使用最可靠的数据作为基础
        merged = {}
        used_fields = set()

        # 从优先级高的源开始填充数据
        for source in sorted_sources:
            data = results[source]
            for key, value in data.items():
                if value is not None and key not in used_fields:
                    merged[key] = value
                    used_fields.add(key)

        merged["sources_used"] = sorted_sources
        return merged

    def get_stats(self) -> Dict[str, Any]:
        """
        获取工具统计信息

        Returns:
            Dict[str, Any]: 统计信息
        """
        stats = super().get_stats()
        stats["supported_actions"] = [
            "lookup",
            "batch_lookup",
            "geo_lookup",
            "my_ip"
        ]
        stats["api_sources"] = list(self.api_endpoints.keys())

        return stats
