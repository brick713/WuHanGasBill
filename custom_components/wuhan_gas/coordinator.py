"""Data update coordinator for Wuhan Gas."""

from datetime import datetime
import asyncio
import async_timeout
import ssl
import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
# 导入正确的函数，允许我们传递自定义的连接器
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from .const import (
    DOMAIN, LOGGER, DEFAULT_SCAN_INTERVAL,
    API_BASE_URL, API_GET_PERIOD, API_QUERY_DEPT,
    USER_AGENT, DEFAULT_METER_TYPE, DEFAULT_ORG_ID, DEFAULT_TYPE
)

class WuhanGasDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Wuhan Gas data."""
    
    def __init__(self, hass: HomeAssistant, config_data: dict) -> None:
        """Initialize."""
        self.userno = config_data["userno"]
        self.member_id = config_data["member_id"]
        self.token = config_data["token"]
        self.hass = hass
        
        # 在协调器初始化时创建一次自定义的连接器
        # 这避免了每次请求都新建 SSL 上下文
        self._connector = self._create_custom_connector()
        
        self.data = {}
        
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
        )
    
    def _create_custom_connector(self):
        """创建一个自定义的 TCPConnector，配置为使用 TLSv1.2 及以上协议。"""
        # 创建 SSL 上下文，设置最低协议版本为 TLSv1.2
        ssl_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2
        
        # 创建并返回一个使用此 SSL 上下文的连接器
        # 注意：这里创建连接器本身不是阻塞操作，阻塞的证书加载会在后台线程中处理
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        return connector
    
    def _get_headers(self):
        """Generate headers with token."""
        return {
            "Host": "wp.babel-group.cn",
            "Connection": "keep-alive",
            "token": self.token,
            "content-type": "application/json",
            "Accept-Encoding": "gzip,compress,br,deflate",
            "User-Agent": USER_AGENT,
            "Referer": "https://servicewechat.com/wxf4b325a5170f136c/51/page-frame.html"
        }
    
    async def _async_update_data(self):
        """Fetch data from API."""
        try:
            async with async_timeout.timeout(10):
                return await self._fetch_all_data()
        except asyncio.TimeoutError as err:
            raise UpdateFailed(f"Timeout fetching data: {err}") from err
        except Exception as err:
            raise UpdateFailed(f"Error fetching data: {err}") from err
    
    async def _fetch_all_data(self):
        """Fetch all data from APIs."""
        data = {}
        
        # Fetch account balance
        balance_data = await self._fetch_balance()
        if balance_data:
            data.update(balance_data)
        
        # Fetch annual bills
        bills_data = await self._fetch_annual_bills()
        if bills_data:
            data.update(bills_data)
        
        return data
    
    async def _fetch_balance(self):
        """Fetch account balance."""
        url = f"{API_BASE_URL}{API_QUERY_DEPT}"
        payload = {
            "member_id": self.member_id
        }
        
        try:
            headers = self._get_headers()
            # 使用自定义连接器创建客户端会话
            # async_create_clientsession 会处理会话的生命周期，避免资源泄漏
            session = async_create_clientsession(
                self.hass,
                connector=self._connector,
                auto_cleanup=False  # 我们将手动管理连接器的生命周期
            )
            
            async with session.post(url, json=payload, headers=headers) as response:
                if response.status == 200:
                    result = await response.json()
                    LOGGER.debug("Balance API response: %s", result)
                    
                    if result.get("code") == 0 and "data" in result:
                        balance_str = result["data"].get("user_presave", "0")
                        try:
                            # Convert to float and divide by 100
                            balance = float(balance_str) / 100
                        except (ValueError, TypeError):
                            balance = 0.0
                        
                        return {
                            "balance": balance,
                            "user_name": result["data"].get("user_name", ""),
                            "user_addr": result["data"].get("user_addr", ""),
                            "userno": result["data"].get("userno", self.userno)
                        }
                    else:
                        LOGGER.error("API returned error: %s", result.get("msg", "Unknown error"))
                else:
                    LOGGER.error("HTTP error: %s", response.status)
        except Exception as err:
            LOGGER.error("Error fetching balance: %s", err)
        
        return None
    
    async def _fetch_annual_bills(self):
        """Fetch annual bills."""
        url = f"{API_BASE_URL}{API_GET_PERIOD}"
        current_year = datetime.now().year
        
        payload = {
            "year": current_year,
            "userno": self.userno,
            "meterType": DEFAULT_METER_TYPE,
            "orgid": DEFAULT_ORG_ID,
            "type": DEFAULT_TYPE
        }
        
        try:
            headers = self._get_headers()
            # 重用同一个连接器创建会话，提高效率
            session = async_create_clientsession(
                self.hass,
                connector=self._connector,
                auto_cleanup=False
            )
            
            async with session.post(url, json=payload, headers=headers) as response:
                if response.status == 200:
                    result = await response.json()
                    LOGGER.debug("Bills API response: %s", result)
                    
                    if result.get("code") == 0 and "data" in result:
                        bills = result["data"]
                        
                        # Calculate annual total
                        annual_total = 0.0
                        monthly_bills = {}
                        last_month_bill = 0.0
                        last_month = None
                        
                        for bill in bills:
                            try:
                                amount = float(bill.get("own_fee", "0"))
                                month = bill.get("yrmonth", "")
                                
                                annual_total += amount
                                monthly_bills[month] = amount
                                
                                # Find the most recent month
                                if month and (last_month is None or month > last_month):
                                    last_month = month
                                    last_month_bill = amount
                            
                            except (ValueError, TypeError):
                                continue
                        
                        return {
                            "annual_total": annual_total,
                            "last_month_bill": last_month_bill,
                            "last_month": last_month,
                            "monthly_bills": monthly_bills,
                            "all_bills": bills
                        }
                    else:
                        LOGGER.error("API returned error: %s", result.get("msg", "Unknown error"))
                else:
                    LOGGER.error("HTTP error: %s", response.status)
        except Exception as err:
            LOGGER.error("Error fetching bills: %s", err)
        
        return None
    
    async def async_shutdown(self):
        """清理资源，关闭连接器。"""
        if self._connector:
            await self._connector.close()
