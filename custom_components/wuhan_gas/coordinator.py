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
    """Class to manage fetching Wuhan Gas data."""
    
    def __init__(self, hass: HomeAssistant, config_data: dict) -> None:
        """Initialize."""
        self.userno = config_data["userno"]
        self.member_id = config_data["member_id"]
        self.token = config_data["token"]
        self.hass = hass
        self._connector: Optional[aiohttp.TCPConnector] = None
        self.data = {}
        
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
        )
    
    async def _create_custom_connector_in_executor(self) -> aiohttp.TCPConnector:
        """Create custom TCPConnector in executor to avoid blocking I/O."""
        def _blocking_create_connector() -> aiohttp.TCPConnector:
            ssl_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
            ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2
            ssl_context.check_hostname = True
            
            connector = aiohttp.TCPConnector(
                ssl=ssl_context,
                use_dns_cache=True,
                ttl_dns_cache=300,
                limit=10
            )
            return connector
        
        return await self.hass.async_add_executor_job(_blocking_create_connector)
    
    async def _get_or_create_connector(self) -> aiohttp.TCPConnector:
        """Get or create custom connector."""
        if self._connector is None or self._connector.closed:
            self._connector = await self._create_custom_connector_in_executor()
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
            async with async_timeout.timeout(15):
                return await self._fetch_all_data()
        except asyncio.TimeoutError as err:
            raise UpdateFailed(f"Timeout fetching data: {err}") from err
        except Exception as err:
            raise UpdateFailed(f"Error fetching data: {err}") from err
    
    async def _fetch_all_data(self):
        """Fetch all data from APIs."""
        data = {}
        
        balance_data = await self._fetch_balance()
        if balance_data:
            data.update(balance_data)
        
        bills_data = await self._fetch_annual_bills()
        if bills_data:
            data.update(bills_data)
        
        return data
    
    async def _make_api_request(self, url: str, payload: dict):
        """Make API request with custom connector."""
        try:
            headers = self._get_headers()
            connector = await self._get_or_create_connector()
            
            session = async_create_clientsession(
                self.hass,
                connector=connector,
                auto_cleanup=False
            )
            
            async with session.post(url, json=payload, headers=headers) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    LOGGER.error("HTTP error %s for URL: %s", response.status, url)
                    return None
        except Exception as err:
            LOGGER.error("Request error for URL %s: %s", url, err)
            return None
    
    async def _fetch_balance(self):
        """Fetch account balance."""
        url = f"{API_BASE_URL}{API_QUERY_DEPT}"
        payload = {"member_id": self.member_id}
        
        result = await self._make_api_request(url, payload)
        if result and result.get("code") == 0 and "data" in result:
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
        elif result:
            LOGGER.error("Balance API returned error: %s", result.get("msg"))
        
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
        
        result = await self._make_api_request(url, payload)
        if result and result.get("code") == 0 and "data" in result:
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
        elif result:
            LOGGER.error("Bills API returned error: %s", result.get("msg"))
        
        return None
    
    async def async_shutdown(self):
        """Clean up resources."""
        if self._connector and not self._connector.closed:
            await self._connector.close()
