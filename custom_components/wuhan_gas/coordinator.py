"""Data update coordinator for Wuhan Gas (production-grade)."""

from datetime import datetime
import asyncio
import async_timeout
import json
import time

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.event import async_track_time_change

from .const import (
    DOMAIN, LOGGER,
    API_BASE_URL, API_GET_PERIOD, API_QUERY_DEPT,
    USER_AGENT, DEFAULT_METER_TYPE, DEFAULT_ORG_ID, DEFAULT_TYPE
)


# =====================
# 配置
# =====================
CACHE_TTL = 60  # 秒
UPDATE_HOURS = [8, 18]  # 每天执行时间


class WuhanGasDataUpdateCoordinator(DataUpdateCoordinator):
    """Production-grade coordinator using curl + scheduled updates."""

    def __init__(self, hass: HomeAssistant, config_data: dict) -> None:
        self.hass = hass
        self.userno = config_data["userno"]
        self.member_id = config_data["member_id"]
        self.token = config_data["token"]

        # headers（复用）
        self.headers = {
            "User-Agent": USER_AGENT,
            "Referer": "https://servicewechat.com/",
        }

        # 缓存
        self._cache_data = None
        self._cache_time = 0

        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            update_interval=None,  # ❗禁用默认轮询
        )

        # ✅ 注册每天两次更新
        self._unsub_timer = async_track_time_change(
            hass,
            self._scheduled_update,
            hour=UPDATE_HOURS,
            minute=0,
            second=0,
        )

    # =====================
    # 成功判断
    # =====================
    def _is_success(self, result):
        return str(result.get("code")) == "0"

    # =====================
    # 定时触发
    # =====================
    @callback
    async def _scheduled_update(self, now: datetime):
        """Scheduled update twice a day."""
        LOGGER.debug("Scheduled update triggered at %s", now)
        await self.async_request_refresh()

    # =====================
    # 主更新
    # =====================
    async def _async_update_data(self):
        now = time.time()

        # ✅ 命中缓存
        if self._cache_data and (now - self._cache_time < CACHE_TTL):
            return self._cache_data

        try:
            async with async_timeout.timeout(20):
                data = await self._fetch_all_data()

                if data:
                    self._cache_data = data
                    self._cache_time = now
                    return data

                # fallback
                if self._cache_data:
                    LOGGER.warning("Using stale cache")
                    return self._cache_data

                raise UpdateFailed("No data")

        except Exception as err:
            if self._cache_data:
                LOGGER.warning("Error, using cache: %s", err)
                return self._cache_data

            raise UpdateFailed(err) from err

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
    # curl 请求
    # =====================
    async def _make_api_request(self, url: str, payload: dict):
        try:
            cmd = [
                "curl",
                "-s",
                url,
                "-H", f"token: {self.token}",
                "-H", "content-type: application/json",
                "-H", f"User-Agent: {self.headers['User-Agent']}",
                "-H", f"Referer: {self.headers['Referer']}",
                "--data", json.dumps(payload)
            ]

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                LOGGER.error("curl failed: %s", stderr.decode())
                return None

            if not stdout:
                return None

            return json.loads(stdout)

        except Exception as err:
            LOGGER.error("curl request error %s: %s", url, err)
            return None

    # =====================
    # 余额
    # =====================
    async def _fetch_balance(self):
        url = f"{API_BASE_URL}{API_QUERY_DEPT}"
        payload = {"member_id": self.member_id}

        result = await self._make_api_request(url, payload)

        if result and self._is_success(result) and "data" in result:
            data = result["data"]

            try:
                balance = float(data.get("user_presave") or 0) / 100
            except Exception:
                balance = 0.0

            return {
                "balance": balance,
                "user_name": data.get("user_name", ""),
                "user_addr": data.get("user_addr", ""),
                "userno": data.get("userno", self.userno)
            }

        if result:
            LOGGER.error("Balance API error: %s", result)

        return None

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

        result = await self._make_api_request(url, payload)

        if result and self._is_success(result) and "data" in result:
            bills = result["data"]

            annual_total = 0.0
            monthly = {}
            last_month = ""
            last_value = 0.0

            for b in bills:
                try:
                    amount = float(b.get("own_fee") or 0)
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

        if result:
            LOGGER.error("Bills API error: %s", result)

        return None

    # =====================
    # 清理
    # =====================
    async def async_shutdown(self):
        """Cleanup when integration unloads."""
        if self._unsub_timer:
            self._unsub_timer()
