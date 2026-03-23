"""Data update coordinator for Wuhan Gas."""
from datetime import datetime
import asyncio
import async_timeout
import ssl
import aiohttp
from typing import Optional
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from .const import (
    DOMAIN, LOGGER, DEFAULT_SCAN_INTERVAL,
    API_BASE_URL, API_GET_PERIOD, API_QUERY_DEPT,
    USER_AGENT, DEFAULT_METER_TYPE, DEFAULT_ORG_ID, DEFAULT_TYPE
)

class WuhanGasDataUpdateCoordinator(DataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant, config_data: dict) -> None:
        self.userno = config_data["userno"]
        self.member_id = config_data["member_id"]
        self.token = config_data["token"]
        self.hass = hass
        self._connector: Optional[aiohttp.TCPConnector] = None
        self.data = {}
        super().__init__(hass, LOGGER, name=DOMAIN, update_interval=DEFAULT_SCAN_INTERVAL)

    async def _create_custom_connector_in_executor(self) -> aiohttp.TCPConnector:
        """在执行器中创建自定义TCPConnector，避免阻塞事件循环。"""
        def _blocking_create_connector() -> aiohttp.TCPConnector:
            # 此函数在后台线程运行，可安全执行阻塞I/O
            ssl_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
            # 根据您之前成功的CURL测试，服务器使用TLSv1.2，强制使用TLSv1.2或更高
            ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2
            # 禁用不安全的旧协议
            ssl_context.options |= ssl.OP_NO_SSLv2 | ssl.OP_NO_SSLv3 | ssl.OP_NO_TLSv1 | ssl.OP_NO_TLSv1_1
            # 启用主机名检查
            ssl_context.check_hostname = True
            # 创建并返回连接器
            return aiohttp.TCPConnector(ssl=ssl_context, use_dns_cache=True)
        return await self.hass.async_add_executor_job(_blocking_create_connector)

    async def _get_or_create_connector(self) -> aiohttp.TCPConnector:
        """获取或创建自定义连接器（懒加载）。"""
        if self._connector is None or self._connector.closed:
            self._connector = await self._create_custom_connector_in_executor()
        return self._connector

    def _get_headers(self):
        """生成请求头。"""
        return {
            "Host": "wp.babel-group.cn",
            "Connection": "keep-alive",
            "token": self.token,  # 注意：如果链接返回“鉴权失败”，此token可能需要更新
            "content-type": "application/json",
            "Accept-Encoding": "gzip,compress,br,deflate",
            "User-Agent": USER_AGENT,
            "Referer": "https://servicewechat.com/wxf4b325a5170f136c/51/page-frame.html"
        }

    async def _async_update_data(self):
        """获取数据。"""
        try:
            async with async_timeout.timeout(15):
                return await self._fetch_all_data()
        except asyncio.TimeoutError as err:
            raise UpdateFailed(f"超时获取数据: {err}") from err
        except Exception as err:
            raise UpdateFailed(f"获取数据错误: {err}") from err

    async def _fetch_all_data(self):
        """获取所有数据。"""
        data = {}
        balance_data = await self._fetch_balance()
        if balance_data:
            data.update(balance_data)
        bills_data = await self._fetch_annual_bills()
        if bills_data:
            data.update(bills_data)
        return data

    async def _make_api_request(self, url: str, payload: dict):
        """发起API请求。"""
        # 调试：打印URL，确认其正确性
        LOGGER.debug("准备请求URL: %s", url)
        if not url or '//' not in url:
            LOGGER.error("URL格式错误或为空: %s", url)
            return None

        try:
            headers = self._get_headers()
            connector = await self._get_or_create_connector()
            session = async_create_clientsession(self.hass, connector=connector, auto_cleanup=False)
            async with session.post(url, json=payload, headers=headers) as response:
                if response.status == 200:
                    result = await response.json()
                    LOGGER.debug("API响应: %s", result)
                    # 检查鉴权结果
                    if result.get("code") == 1003:
                        LOGGER.error("API鉴权失败，请检查token是否有效。响应: %s", result)
                    return result
                else:
                    LOGGER.error("HTTP错误 %s, URL: %s", response.status, url)
                    return None
        except ssl.SSLError as e:
            LOGGER.error("SSL握手失败 (URL: %s): %s", url, e)
            return None
        except Exception as e:
            LOGGER.error("请求失败 (URL: %s): %s", url, e)
            return None

    async def _fetch_balance(self):
        """获取账户余额。"""
        url = f"{API_BASE_URL}{API_QUERY_DEPT}"
        payload = {"member_id": self.member_id}
        result = await self._make_api_request(url, payload)
        if result and result.get("code") == 0 and "data" in result:
            # ... 处理成功响应，解析余额 ...
            pass
        return None

    async def _fetch_annual_bills(self):
        """获取年度账单。"""
        url = f"{API_BASE_URL}{API_GET_PERIOD}"
        current_year = datetime.now().year
        payload = {
            "year": current_year,
            "userno": self.userno,
            "meterType": DEFAULT_METER_TYPE,
            "orgid": DEFAULT_ORG_ID,
            "type": DEFAULT_TYPE
        }
        result = await self._make_api_request(url, payload)
        if result and result.get("code") == 0 and "data" in result:
            # ... 处理成功响应，解析账单 ...
            pass
        return None

    async def async_shutdown(self):
        """清理资源。"""
        if self._connector and not self._connector.closed:
            await self._connector.close()
