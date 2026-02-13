"""Constants for the SigenEnergy Modbus TCP integration."""

DOMAIN = "sigenergy_modbus_tcp"
SCAN_INTERVAL = 30  # seconds

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
