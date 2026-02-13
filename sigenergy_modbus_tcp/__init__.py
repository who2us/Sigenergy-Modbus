"""
SigenEnergy — Home Assistant Custom Integration

Two data paths:

1. Local WebSocket (ws://<gateway>:8080/ws)
   ─ Reverse-engineered from the Flutter app
   ─ Used to enable / configure the Modbus TCP server
   ─ Coordinator: SigenLocalCoordinator (polls every 30 s)

2. SigenEnergy Cloud API (api-aus.sigencloud.com)
   ─ Confirmed working endpoints from MySigen prototype
   ─ OAuth2 password-grant auth (Basic sigen:sigen)
   ─ Provides live energy flow + generation statistics
   ─ Coordinator: SigenCloudCoordinator (polls every 30 s)

Both coordinators share the same config entry so everything appears as one device.
"""

from __future__ import annotations

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

from .cloud_api import CloudAuthError, CloudAPIError, SigenCloudAPI
from .const import (
    CONF_CLOUD_USERNAME,
    CONF_CLOUD_PASSWORD,
    DOMAIN,
    SCAN_INTERVAL,
)
from .gateway import GatewayError, SigenEnergyGateway

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SWITCH, Platform.NUMBER, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SigenEnergy from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # ── 1. Local gateway (WebSocket) ──────────────────────────────────────────
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
        raise ConfigEntryNotReady(
            f"Cannot connect to SigenEnergy local gateway: {err}"
        ) from err

    local_coordinator = SigenLocalCoordinator(hass, gateway)
    await local_coordinator.async_config_entry_first_refresh()

    # ── 2. Cloud API ──────────────────────────────────────────────────────────
    cloud_username = entry.data.get(CONF_CLOUD_USERNAME) or entry.data.get(CONF_USERNAME, "")
    cloud_password = entry.data.get(CONF_CLOUD_PASSWORD) or entry.data.get(CONF_PASSWORD, "")

    cloud_api = SigenCloudAPI(cloud_username, cloud_password)
    cloud_coordinator = SigenCloudCoordinator(hass, cloud_api)

    # Cloud connectivity is optional — don't fail the whole entry if cloud is down
    try:
        await cloud_coordinator.async_config_entry_first_refresh()
    except Exception as err:
        _LOGGER.warning(
            "SigenEnergy cloud API unavailable at startup (will retry): %s", err
        )

    # ── Store both in hass.data ───────────────────────────────────────────────
    hass.data[DOMAIN][entry.entry_id] = {
        "gateway":            gateway,
        "local_coordinator":  local_coordinator,
        "cloud_api":          cloud_api,
        "cloud_coordinator":  cloud_coordinator,
        # Legacy key kept for backwards compat with existing switch/number entities
        "coordinator":        local_coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        data = hass.data[DOMAIN].pop(entry.entry_id)
        await data["gateway"].disconnect()
        await data["cloud_api"].close()
    return unload_ok


# ── Coordinators ──────────────────────────────────────────────────────────────

class SigenLocalCoordinator(DataUpdateCoordinator):
    """
    Polls the local WebSocket gateway for Modbus TCP state.

    Data shape: { "modbusEnable": 0|1, "modbusPort": 502 }
    """

    def __init__(self, hass: HomeAssistant, gateway: SigenEnergyGateway) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_local",
            update_interval=timedelta(seconds=SCAN_INTERVAL),
        )
        self.gateway = gateway

    async def _async_update_data(self) -> dict:
        try:
            return await self.gateway.get_modbus_tcp_status()
        except GatewayError as err:
            raise UpdateFailed(f"Local gateway error: {err}") from err


class SigenCloudCoordinator(DataUpdateCoordinator):
    """
    Polls the SigenEnergy cloud API for live energy data.

    Data shape:
    {
      "energy_flow": {
        "batterySoc": 72.5,
        "batteryPower": -1200,   # W, negative = charging
        "pvPower": 3400,         # W
        "buySellPower": 800,     # W, positive = importing
        "loadPower": 2600,       # W
        ...
      },
      "statistics": {
        "dayGeneration": 12.4,        # kWh
        "monthGeneration": 340.2,     # kWh
        "yearGeneration": 4210.0,     # kWh
        "lifetimeGeneration": 18500,  # kWh
        ...
      }
    }
    """

    def __init__(self, hass: HomeAssistant, cloud_api: SigenCloudAPI) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_cloud",
            update_interval=timedelta(seconds=SCAN_INTERVAL),
        )
        self.cloud_api = cloud_api

    async def _async_update_data(self) -> dict:
        try:
            return await self.cloud_api.fetch_all()
        except (CloudAuthError, CloudAPIError) as err:
            raise UpdateFailed(f"Cloud API error: {err}") from err
