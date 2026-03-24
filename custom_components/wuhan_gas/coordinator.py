"""Data update coordinator for Wuhan Gas (curl version)."""

from datetime import datetime
import asyncio
import async_timeout
import json

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DOMAIN, LOGGER, DEFAULT_SCAN_INTERVAL,
    API_BASE_URL, API_GET_PERIOD, API_QUERY_DEPT,
    USER_AGENT, DEFAULT_METER_TYPE, DEFAULT_ORG_ID, DEFAULT_TYPE
)


class WuhanGasDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Wuhan Gas data via curl."""

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

        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
        )

    async def _async_update_data(self):
        """Fetch data from API."""
        try:
            async with async_timeout.timeout(20):
                return await self._fetch_all_data()
        except asyncio.TimeoutError as err:
            raise UpdateFailed(f"Timeout fetching data: {err}") from err
        except Exception as err:
            raise UpdateFailed(f"Error fetching data: {err}") from err

    async def _fetch_all_data(self):
        """并发获取数据"""
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
        """Use curl to bypass TLS fingerprint detection."""
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
