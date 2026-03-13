"""Data update coordinator for Wuhan Gas."""

from datetime import datetime
import asyncio
import aiohttp
import ssl
import async_timeout
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
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
        self.data = {}
        
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
        )
    
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
    
    def _create_ssl_context(self):
        """Create SSL context with modern TLS protocols."""
        ssl_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2
        return ssl_context
    
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
            ssl_context = self._create_ssl_context()
            connector = aiohttp.TCPConnector(ssl=ssl_context)
            
            async with aiohttp.ClientSession(connector=connector) as session:
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
            ssl_context = self._create_ssl_context()
            connector = aiohttp.TCPConnector(ssl=ssl_context)
            
            async with aiohttp.ClientSession(connector=connector) as session:
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
