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

# 默认请求参数
DEFAULT_METER_TYPE = "1"
DEFAULT_ORG_ID = "1"
DEFAULT_TYPE = 1
