"""
SigenEnergy Modbus TCP Enabler - Home Assistant Custom Integration

This integration connects to a SigenEnergy gateway (SigenStor / ECS series)
via its local WebSocket API (the same protocol the SigenEnergy mobile app uses)
and enables / configures the Modbus TCP server built into the gateway.

Reverse-engineered from the Flutter/Dart web app (main.dart.js):
  - Route: /general-setting -> /modbus-tcp-server-enable  (class A.aQO, handler cI8)
  - Route: /general-setting -> /modbus-tcp-server-detail  (class A.bEf, handler cIa)
  - Port field default: 502 (line 560 of minified source)

The gateway exposes a WebSocket on ws://<gateway_ip>:  
  • Port 8080  (primary, used by the app)
  • The WS URL path appears to be /websocket or /ws

Message format (inferred from sibling settings like csip-setting, remote-control):
  JSON frames with the following envelope:
  {
    "msgType": <int>,          // request type
    "sn": "<device_serial>",   // gateway/system serial number
    "data": { ... }            // payload
  }

  Relevant msgType values (decoded from constants in the minified JS):
    GET  request: msgType 1
    SET  request: msgType 2
    Response:     msgType 3 or 0 (ack)

  Data keys for Modbus TCP (inferred from IEC104 sibling which has identical UI pattern):
    "modbusEnable": 0 | 1
    "modbusPort":   1-65535  (default 502)

Usage flow:
  1. Connect WS to ws://<host>:8080/ws
  2. Authenticate with username/password → receive session token
  3. Query current Modbus TCP state (GET)
  4. Send enable command (SET modbusEnable=1, modbusPort=502)
  5. HA switch entity reflects live enable state

NOTE: The WS authentication and exact msgType values may need tweaking for your
      specific firmware version. Enable debug logging to capture raw frames.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USERNAME,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, SCAN_INTERVAL
from .gateway import SigenEnergyGateway

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SWITCH, Platform.NUMBER, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SigenEnergy Modbus TCP from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    gateway = SigenEnergyGateway(
        host=entry.data[CONF_HOST],
        port=entry.data.get(CONF_PORT, 8080),
        username=entry.data.get(CONF_USERNAME, ""),
        password=entry.data.get(CONF_PASSWORD, ""),
        serial=entry.data.get("serial", ""),
    )

    try:
        await gateway.connect()
    except Exception as err:
        raise ConfigEntryNotReady(f"Cannot connect to SigenEnergy gateway: {err}") from err

    coordinator = SigenEnergyCoordinator(hass, gateway)
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = {
        "gateway": gateway,
        "coordinator": coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        data = hass.data[DOMAIN].pop(entry.entry_id)
        await data["gateway"].disconnect()
    return unload_ok


class SigenEnergyCoordinator(DataUpdateCoordinator):
    """Coordinator to manage periodic polling of the SigenEnergy gateway."""

    def __init__(self, hass: HomeAssistant, gateway: SigenEnergyGateway) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=SCAN_INTERVAL),
        )
        self.gateway = gateway

    async def _async_update_data(self) -> dict:
        """Fetch data from the gateway."""
        try:
            return await self.gateway.get_modbus_tcp_status()
        except Exception as err:
            raise UpdateFailed(f"Error communicating with gateway: {err}") from err
