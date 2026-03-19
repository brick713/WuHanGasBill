"""Data update coordinator for Wuhan Gas."""

from datetime import datetime
import asyncio
import async_timeout
import ssl
import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
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
        
        # 创建一次SSL上下文，避免每次请求都创建
        self._ssl_context = self._create_ssl_context()
        self._connector = None
        self.data = {}
        
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
        )
    
    def _create_ssl_context(self):
        """创建自定义的SSL上下文，基于CURL输出中的TLS握手信息。"""
        # 根据CURL输出，服务器使用TLSv1.2，加密套件为AES256-SHA256
        # 证书链：*.babel-group.cn <- RapidSSL TLS RSA CA G1 <- DigiCert Global Root G2 <- DigiCert Global Root CA
        ssl_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        
        # 设置最低TLS版本为1.2，与服务器保持一致
        ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2
        ssl_context.maximum_version = ssl.TLSVersion.TLSv1_3  # 允许TLS 1.3
        
        # 根据CURL输出，服务器使用AES256-SHA256加密套件
        # 我们可以设置优先的密码套件
        ssl_context.set_ciphers('ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20:ECDHE+AES256:ECDHE+AES128:DHE+AES256:DHE+AES128')
        
        # 禁用不安全的协议
        ssl_context.options |= ssl.OP_NO_SSLv2
        ssl_context.options |= ssl.OP_NO_SSLv3
        ssl_context.options |= ssl.OP_NO_TLSv1
        ssl_context.options |= ssl.OP_NO_TLSv1_1
        
        # 根据CURL输出，服务器证书验证成功
        # 使用系统默认的CA证书（与CURL使用的/etc/ssl/cert.pem相同）
        ssl_context.load_default_certs(ssl.Purpose.SERVER_AUTH)
        
        # 设置服务器名称指示（SNI），对*.babel-group.cn非常重要
        ssl_context.check_hostname = True
        
        return ssl_context
    
    def _get_connector(self):
        """获取或创建TCP连接器，使用自定义的SSL上下文。"""
        if self._connector is None:
            # 创建TCP连接器，重用SSL上下文
            self._connector = aiohttp.TCPConnector(
                ssl=self._ssl_context,
                use_dns_cache=True,
                ttl_dns_cache=300,
                limit=20,
                limit_per_host=5
            )
        return self._connector
    
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
            async with async_timeout.timeout(15):  # 增加超时时间到15秒
                return await self._fetch_all_data()
        except asyncio.TimeoutError as err:
            raise UpdateFailed(f"Timeout fetching data: {err}") from err
        except Exception as err:
            raise UpdateFailed(f"Error fetching data: {err}") from err
    
    async def _fetch_all_data(self):
        """Fetch all data from APIs."""
        data = {}
        
        # 并发获取数据，提高效率
        balance_task = asyncio.create_task(self._fetch_balance())
        bills_task = asyncio.create_task(self._fetch_annual_bills())
        
        balance_data, bills_data = await asyncio.gather(
            balance_task, bills_task, return_exceptions=True
        )
        
        # 处理余额数据
        if isinstance(balance_data, Exception):
            LOGGER.error("Error fetching balance: %s", balance_data)
        elif balance_data:
            data.update(balance_data)
        
        # 处理账单数据
        if isinstance(bills_data, Exception):
            LOGGER.error("Error fetching bills: %s", bills_data)
        elif bills_data:
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
            connector = self._get_connector()
            
            # 使用async_create_clientsession并传入自定义连接器
            session = async_create_clientsession(
                self.hass,
                connector=connector,
                auto_cleanup=False
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
        except ssl.SSLError as err:
            LOGGER.error("SSL error fetching balance: %s", err)
            # 如果是SSL握手失败，可以尝试回退方案
            return await self._fetch_balance_fallback(url, payload)
        except Exception as err:
            LOGGER.error("Error fetching balance: %s", err)
        
        return None
    
    async def _fetch_balance_fallback(self, url, payload):
        """回退方案：使用更宽松的SSL设置"""
        try:
            headers = self._get_headers()
            # 创建更宽松的SSL上下文
            ssl_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            
            connector = aiohttp.TCPConnector(ssl=ssl_context)
            session = async_create_clientsession(
                self.hass,
                connector=connector,
                auto_cleanup=False
            )
            
            async with session.post(url, json=payload, headers=headers) as response:
                if response.status == 200:
                    result = await response.json()
                    if result.get("code") == 0 and "data" in result:
                        balance_str = result["data"].get("user_presave", "0")
                        try:
                            balance = float(balance_str) / 100
                        except (ValueError, TypeError):
                            balance = 0.0
                        
                        return {
                            "balance": balance,
                            "user_name": result["data"].get("user_name", ""),
                            "user_addr": result["data"].get("user_addr", ""),
                            "userno": result["data"].get("userno", self.userno)
                        }
        except Exception as err:
            LOGGER.error("Fallback also failed: %s", err)
        
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
            connector = self._get_connector()
            
            session = async_create_clientsession(
                self.hass,
                connector=connector,
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
        except ssl.SSLError as err:
            LOGGER.error("SSL error fetching bills: %s", err)
            return await self._fetch_annual_bills_fallback(url, payload)
        except Exception as err:
            LOGGER.error("Error fetching bills: %s", err)
        
        return None
    
    async def _fetch_annual_bills_fallback(self, url, payload):
        """回退方案：使用更宽松的SSL设置"""
        try:
            headers = self._get_headers()
            ssl_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            
            connector = aiohttp.TCPConnector(ssl=ssl_context)
            session = async_create_clientsession(
                self.hass,
                connector=connector,
                auto_cleanup=False
            )
            
            async with session.post(url, json=payload, headers=headers) as response:
                if response.status == 200:
                    result = await response.json()
                    if result.get("code") == 0 and "data" in result:
                        bills = result["data"]
                        
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
        except Exception as err:
            LOGGER.error("Fallback also failed: %s", err)
        
        return None
    
    async def async_shutdown(self):
        """清理资源，关闭连接器。"""
        if self._connector:
            await self._connector.close()
