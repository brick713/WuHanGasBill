"""Data update coordinator for Wuhan Gas (optimized with cache)."""

from datetime import datetime, timedelta
import asyncio
import async_timeout
import ssl
import time

from aiohttp import ClientSession

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    DOMAIN, LOGGER,
    API_BASE_URL, API_GET_PERIOD, API_QUERY_DEPT,
    USER_AGENT, DEFAULT_METER_TYPE, DEFAULT_ORG_ID, DEFAULT_TYPE
)


# =====================
# 全局配置
# =====================
UPDATE_INTERVAL = timedelta(minutes=30)   # ✅ 降低请求频率
CACHE_TTL = 60                            # ✅ 60秒缓存


# =====================
# SSL（只初始化一次）
# =====================
def _create_ssl_context():
    ctx = ssl.create_default_context()
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.set_ciphers("ECDHE+AESGCM:ECDHE+CHACHA20:!aNULL:!eNULL:!MD5")
    return ctx


SSL_CONTEXT = _create_ssl_context()


# =====================
# Coordinator
# =====================
class WuhanGasDataUpdateCoordinator(DataUpdateCoordinator):
    """Efficient Wuhan Gas data coordinator with cache."""

    def __init__(self, hass: HomeAssistant, config_data: dict) -> None:
        self.hass = hass
        self.userno = config_data["userno"]
        self.member_id = config_data["member_id"]
        self.token = config_data["token"]

        # HA session（复用）
        self.session: ClientSession = async_get_clientsession(hass)

        # headers（只构建一次）
        self.headers = {
            "Host": "wp.babel-group.cn",
            "Connection": "keep-alive",
            "token": self.token,
            "content-type": "application/json",
            "Accept-Encoding": "gzip,compress,br,deflate",
            "User-Agent": USER_AGENT,
            "Referer": "https://servicewechat.com/wxf4b325a5170f136c/51/page-frame.html"
        }

        # ✅ 缓存
        self._cache_data = None
        self._cache_time = 0

        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )

    # =====================
    # 主更新入口
    # =====================
    async def _async_update_data(self):
        now = time.time()

        # ✅ 命中缓存（避免频繁请求）
        if self._cache_data and (now - self._cache_time < CACHE_TTL):
            LOGGER.debug("Using cached data")
            return self._cache_data

        try:
            async with async_timeout.timeout(15):
                data = await self._fetch_all_data()

                if data:
                    # ✅ 更新缓存
                    self._cache_data = data
                    self._cache_time = now
                    return data

                # ⚠️ fallback
                if self._cache_data:
                    LOGGER.warning("Using stale cache due to API failure")
                    return self._cache_data

                raise UpdateFailed("No data received")

        except asyncio.TimeoutError as err:
            if self._cache_data:
                LOGGER.warning("Timeout, using cache")
                return self._cache_data

            raise UpdateFailed(f"Timeout: {err}") from err

        except Exception as err:
            if self._cache_data:
                LOGGER.warning("Error, using cache: %s", err)
                return self._cache_data

            raise UpdateFailed(f"Error: {err}") from err

    # =====================
    # 并发请求
    # =====================
    async def _fetch_all_data(self):
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

    # =====================
    # HTTP请求封装
    # =====================
    async def _post(self, url: str, payload: dict):
        try:
            async with self.session.post(
                url,
                json=payload,
                headers=self.headers,
                ssl=SSL_CONTEXT
            ) as resp:

                if resp.status != 200:
                    LOGGER.error("HTTP %s: %s", resp.status, url)
                    return None

                return await resp.json()

        except Exception as err:
            LOGGER.error("Request error %s: %s", url, err)
            return None

    # =====================
    # 余额
    # =====================
    async def _fetch_balance(self):
        url = f"{API_BASE_URL}{API_QUERY_DEPT}"
        payload = {"member_id": self.member_id}

        result = await self._post(url, payload)

        if not result or result.get("code") != 0:
            return None

        data = result["data"]

        try:
            balance = float(data.get("user_presave", 0)) / 100
        except Exception:
            balance = 0.0

        return {
            "balance": balance,
            "user_name": data.get("user_name", ""),
            "user_addr": data.get("user_addr", ""),
            "userno": data.get("userno", self.userno),
        }

    # =====================
    # 账单
    # =====================
    async def _fetch_annual_bills(self):
        url = f"{API_BASE_URL}{API_GET_PERIOD}"

        payload = {
            "year": datetime.now().year,
            "userno": self.userno,
            "meterType": DEFAULT_METER_TYPE,
            "orgid": DEFAULT_ORG_ID,
            "type": DEFAULT_TYPE
        }

        result = await self._post(url, payload)

        if not result or result.get("code") != 0:
            return None

        bills = result["data"]

        annual_total = 0.0
        monthly = {}
        last_month = ""
        last_value = 0.0

        for b in bills:
            try:
                amount = float(b.get("own_fee", 0))
                month = b.get("yrmonth", "")

                annual_total += amount
                monthly[month] = amount

                if month > last_month:
                    last_month = month
                    last_value = amount

            except Exception:
                continue

        return {
            "annual_total": annual_total,
            "last_month_bill": last_value,
            "last_month": last_month,
            "monthly_bills": monthly,
            "all_bills": bills
        }
