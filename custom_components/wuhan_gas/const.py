"""Constants for Wuhan Gas integration."""

from datetime import timedelta
import logging

DOMAIN = "wuhan_gas"
DEFAULT_SCAN_INTERVAL = timedelta(hours=1)
LOGGER = logging.getLogger(__name__)

# API endpoints
API_BASE_URL = "https://wp.babel-group.cn"
API_GET_PERIOD = "/user/get-period"
API_QUERY_DEPT = "/pay/query-dept"

# Configuration keys
CONF_USERNO = "userno"
CONF_MEMBER_ID = "member_id"
CONF_TOKEN = "token"

# Headers
USER_AGENT = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_4_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.59(0x18003b2e) NetType/4G Language/zh_CN"

# 默认请求参数
DEFAULT_METER_TYPE = "1"
DEFAULT_ORG_ID = "1"
DEFAULT_TYPE = 1
