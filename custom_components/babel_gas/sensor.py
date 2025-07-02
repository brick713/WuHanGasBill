import logging
import json
import asyncio
from datetime import timedelta
import aiohttp

from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.entity import Entity
from homeassistant import config_entries, core
from homeassistant.const import CONF_NAME
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import Throttle

_LOGGER = logging.getLogger(__name__)

DEFAULT_NAME = "Babel Gas"
SCAN_INTERVAL = timedelta(minutes=30)
API_URL = "https://wp.babel-group.cn/pay/query-dept"

CONF_TOKEN = "token"
CONF_MEMBER_ID = "member_id"

async def async_setup_platform(
    hass: core.HomeAssistant,
    config: dict,
    async_add_entities,
    discovery_info=None,
):
    """设置平台（旧式配置方式）."""
    _LOGGER.warning("旧式配置方式已弃用，请使用UI配置")

async def async_setup_entry(
    hass: core.HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities,
):
    """通过配置条目设置传感器."""
    config = config_entry.data
    session = async_get_clientsession(hass)
    
    sensor = BabelGasSensor(
        hass,
        session,
        config.get(CONF_NAME, DEFAULT_NAME),
        config[CONF_TOKEN],
        config[CONF_MEMBER_ID],
    )
    
    async_add_entities([sensor], True)

class BabelGasSensor(SensorEntity):
    """表示Babel燃气费用的传感器."""

    def __init__(self, hass, session, name, token, member_id):
        """初始化传感器."""
        self._hass = hass
        self._session = session
        self._name = name
        self._token = token
        self._member_id = member_id
        self._state = None
        self._attributes = {}
        self._available = True

    @property
    def name(self):
        """返回传感器名称."""
        return self._name

    @property
    def unique_id(self):
        """返回唯一ID."""
        return f"babel_gas_{self._member_id}"

    @property
    def state(self):
        """返回传感器状态（用户余额）."""
        return self._state

    @property
    def extra_state_attributes(self):
        """返回额外属性."""
        return self._attributes

    @property
    def icon(self):
        """返回图标."""
        return "mdi:fire"

    @property
    def unit_of_measurement(self):
        """返回计量单位."""
        return "元"

    @property
    def available(self):
        """返回传感器是否可用."""
        return self._available

    @Throttle(SCAN_INTERVAL)
    async def async_update(self):
        """从API获取最新数据."""
        headers = {
            "Host": "wp.babel-group.cn",
            "Connection": "keep-alive",
            "token": self._token,
            "content-type": "application/json",
            "Accept-Encoding": "gzip, deflate, br",
            "User-Agent": "HomeAssistant/BabelGas/1.0",
            "Referer": "https://servicewechat.com/wxf4b325a5170f136c/51/page-frame.html"
        }
        
        payload = {
            "member_id": self._member_id
        }

        try:
            async with self._session.post(
                API_URL,
                headers=headers,
                json=payload,
                timeout=10
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    _LOGGER.debug("API响应: %s", data)

                    if data.get("code") == "0":
                        # 更新状态（用户预存余额）
                        self._state = float(data["data"]["user_presave"])
                        
                        # 设置额外属性
                        self._attributes = {
                            "user_name": data["data"]["user_name"],
                            "user_addr": data["data"]["user_addr"],
                            "all_gasfee": float(data["data"]["all_gasfee"]),
                            "own_total": float(data["data"]["own_total"]),
                            "user_latefee": float(data["data"]["user_latefee"]),
                            "other_fee": float(data["data"]["other_fee"]),
                            "userno": data["data"]["userno"],
                            "last_update": core.helpers.utcnow().isoformat()
                        }
                        self._available = True
                    else:
                        _LOGGER.error("API错误: %s - %s", data.get("code"), data.get("msg"))
                        self._available = False
                else:
                    _LOGGER.error("HTTP错误: %s", response.status)
                    self._available = False
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            _LOGGER.error("请求失败: %s", str(err))
            self._available = False
        except (KeyError, ValueError, TypeError) as err:
            _LOGGER.error("解析错误: %s", str(err))
            self._available = False
