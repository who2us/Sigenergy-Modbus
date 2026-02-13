"""Switch platform for SigenEnergy Modbus TCP."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTR_GATEWAY_SN, ATTR_MODBUS_PORT, DOMAIN, KEY_MODBUS_ENABLE, KEY_MODBUS_PORT

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Modbus TCP switch from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    gateway = data["gateway"]

    async_add_entities(
        [SigenEnergyModbusTCPSwitch(coordinator, gateway, entry)],
        update_before_add=True,
    )


class SigenEnergyModbusTCPSwitch(CoordinatorEntity, SwitchEntity):
    """Switch to enable/disable Modbus TCP on the SigenEnergy gateway."""

    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_has_entity_name = True
    _attr_name = "Modbus TCP Server"
    _attr_icon = "mdi:lan-connect"

    def __init__(self, coordinator, gateway, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._gateway = gateway
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_modbus_tcp_enable"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=f"SigenEnergy Gateway ({self._entry.data[CONF_HOST]})",
            manufacturer="SigenEnergy",
            model="SigenStor / ECS Gateway",
        )

    @property
    def is_on(self) -> bool | None:
        """Return True if Modbus TCP is enabled."""
        if self.coordinator.data is None:
            return None
        return bool(self.coordinator.data.get(KEY_MODBUS_ENABLE, 0))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        return {
            ATTR_MODBUS_PORT: data.get(KEY_MODBUS_PORT, 502),
            ATTR_GATEWAY_SN: getattr(self._gateway, "_serial", ""),
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable Modbus TCP server."""
        await self._gateway.set_modbus_tcp_enabled(True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable Modbus TCP server."""
        await self._gateway.set_modbus_tcp_enabled(False)
        await self.coordinator.async_request_refresh()

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()
