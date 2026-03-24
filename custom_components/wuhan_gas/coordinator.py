"""Data update coordinator for Wuhan Gas."""

from datetime import datetime
import asyncio
import async_timeout
import ssl

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    DOMAIN, LOGGER, DEFAULT_SCAN_INTERVAL,
    API_BASE_URL, API_GET_PERIOD, API_QUERY_DEPT,
    USER_AGENT, DEFAULT_METER_TYPE, DEFAULT_ORG_ID, DEFAULT_TYPE
)


# =====================
# SSL（全局复用）
# =====================
def _create_ssl_context():
    ctx = ssl.create_default_context()
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.set_ciphers("ECDHE+AESGCM:ECDHE+CHACHA20:!aNULL:!eNULL:!MD5")
    return ctx


SSL_CONTEXT = _create_ssl_context()


class WuhanGasDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Wuhan Gas data."""

    def __init__(self, hass: HomeAssistant, config_data: dict) -> None:
        self.hass = hass
        self.userno = config_data["userno"]
        self.member_id = config_data["member_id"]
        self.token = config_data["token"]

        # ✅ 复用 session
        self.session = async_get_clientsession(hass)

        # ✅ headers 只构建一次
        self.headers = {
            "Host": "wp.babel-group.cn",
            "Connection": "keep-alive",
            "token": self.token,
            "content-type": "application/json",
            "Accept-Encoding": "gzip,compress,br,deflate",
            "User-Agent": USER_AGENT,
            "Referer": "https://servicewechat.com/wxf4b325a5170f136c/51/page-frame.html"
        }

        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
        )

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
        """并发获取数据（优化）"""
        balance_task = self._fetch_balance()
        bills_task = self._fetch_annual_bills()

        balance_data, bills_data = await asyncio.gather(
            balance_task,
            bills_task,
            return_exceptions=True
        )

        data = {}

        if isinstance(balance_data, dict):
            data.update(balance_data)

        if isinstance(bills_data, dict):
            data.update(bills_data)

        return data

    async def _make_api_request(self, url: str, payload: dict):
        """统一请求方法"""
        try:
            async with self.session.post(
                url,
                json=payload,
                headers=self.headers,
                ssl=SSL_CONTEXT   # ✅ 正确方式
            ) as response:

                if response.status == 200:
                    return await response.json()

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
            data = result["data"]

            try:
                balance = float(data.get("user_presave", 0)) / 100
            except Exception:
                balance = 0.0

            return {
                "balance": balance,
                "user_name": data.get("user_name", ""),
                "user_addr": data.get("user_addr", ""),
                "userno": data.get("userno", self.userno)
            }

        if result:
            LOGGER.error("Balance API returned error: %s", result.get("msg"))

        return None

    async def _fetch_annual_bills(self):
        """Fetch annual bills."""
        url = f"{API_BASE_URL}{API_GET_PERIOD}"

        payload = {
            "year": datetime.now().year,
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
            last_month = ""
            last_month_bill = 0.0

            for bill in bills:
                try:
                    amount = float(bill.get("own_fee", 0))
                    month = bill.get("yrmonth", "")

                    annual_total += amount
                    monthly_bills[month] = amount

                    if month > last_month:
                        last_month = month
                        last_month_bill = amount

                except Exception:
                    continue

            return {
                "annual_total": annual_total,
                "last_month_bill": last_month_bill,
                "last_month": last_month,
                "monthly_bills": monthly_bills,
                "all_bills": bills
            }

        if result:
            LOGGER.error("Bills API returned error: %s", result.get("msg"))

        return None
