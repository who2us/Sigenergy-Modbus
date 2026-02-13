"""Number platform – Modbus TCP port setting for SigenEnergy gateway."""
from __future__ import annotations

import logging

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEFAULT_MODBUS_PORT, DOMAIN, KEY_MODBUS_PORT

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [SigenEnergyModbusTCPPort(data["coordinator"], data["gateway"], entry)],
        update_before_add=True,
    )


class SigenEnergyModbusTCPPort(CoordinatorEntity, NumberEntity):
    """Number entity for the Modbus TCP server port."""

    _attr_has_entity_name = True
    _attr_name = "Modbus TCP Port"
    _attr_icon = "mdi:numeric"
    _attr_native_min_value = 1
    _attr_native_max_value = 65535
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator, gateway, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._gateway = gateway
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_modbus_tcp_port"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=f"SigenEnergy Gateway ({self._entry.data[CONF_HOST]})",
            manufacturer="SigenEnergy",
            model="SigenStor / ECS Gateway",
        )

    @property
    def native_value(self) -> float:
        if self.coordinator.data is None:
            return DEFAULT_MODBUS_PORT
        return float(self.coordinator.data.get(KEY_MODBUS_PORT, DEFAULT_MODBUS_PORT))

    async def async_set_native_value(self, value: float) -> None:
        await self._gateway.set_modbus_tcp_port(int(value))
        await self.coordinator.async_request_refresh()

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()
