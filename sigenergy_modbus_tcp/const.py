"""Constants for the SigenEnergy Modbus TCP integration."""

DOMAIN = "sigenergy_modbus_tcp"
SCAN_INTERVAL = 30  # seconds

# ── Cloud API ──────────────────────────────────────────────────────────────────
# Confirmed working endpoints from MySigen prototype (api-aus region)
CLOUD_API_BASE     = "https://api-aus.sigencloud.com"
CLOUD_AUTH_URL     = f"{CLOUD_API_BASE}/auth/oauth/token"
CLOUD_STATION_URL  = f"{CLOUD_API_BASE}/device/owner/station/home"
CLOUD_ENERGY_URL   = f"{CLOUD_API_BASE}/device/sigen/station/energyflow/async"
CLOUD_STATS_URL    = f"{CLOUD_API_BASE}/data-process/sigen/station/statistics/gains"

# Basic auth header value for OAuth token request: base64("sigen:sigen")
CLOUD_CLIENT_BASIC = "c2lnZW46c2lnZW4="   # pre-computed, never changes

# Confirmed request headers (from working prototype)
CLOUD_COMMON_HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept":          "*/*",
    "Origin":          "https://app-aus.sigencloud.com",
    "Referer":         "https://app-aus.sigencloud.com/",
    "Lang":            "en_US",
    "Sg-Bui":          "1",
    "Sg-Env":          "1",
    "Sg-Pkg":          "sigen_app",
    "Version":         "RELEASE",
    "Client-Server":   "aus",
}

# Config-entry key for cloud username (may differ from gateway username)
CONF_CLOUD_USERNAME = "cloud_username"
CONF_CLOUD_PASSWORD = "cloud_password"

# WebSocket message types (inferred from app source analysis)
# The Flutter app uses integer msgType values in its WS envelope
MSG_TYPE_AUTH = 0          # Authentication request
MSG_TYPE_AUTH_RESP = 1     # Authentication response
MSG_TYPE_GET = 2           # Read/query request
MSG_TYPE_SET = 3           # Write/command request
MSG_TYPE_RESPONSE = 4      # General response/ack
MSG_TYPE_PUSH = 5          # Server push / notification

# Data keys used in the Modbus TCP settings payload
# Inferred from the /modbus-tcp-server-enable and /modbus-tcp-server-detail routes
# and confirmed by analogy with the IEC104 sibling feature (same UI pattern)
KEY_MODBUS_ENABLE = "modbusEnable"       # 0 = disabled, 1 = enabled
KEY_MODBUS_PORT   = "modbusPort"          # TCP port (default 502)
KEY_MODBUS_IP     = "modbusIp"            # Optional bind IP (usually not needed)

# The "service" identifier used when querying/setting Modbus TCP config
# Derived from the route name "/modbus-tcp-server-enable"
SERVICE_MODBUS_TCP = "modbusTcpServer"

DEFAULT_WS_PORT   = 8080
DEFAULT_MODBUS_PORT = 502

# Attribute names for HA entities
ATTR_MODBUS_PORT   = "modbus_port"
ATTR_GATEWAY_SN    = "gateway_sn"
ATTR_FIRMWARE      = "firmware_version"
