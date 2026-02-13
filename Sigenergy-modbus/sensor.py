"""
Sensor platform for SigenEnergy Modbus TCP integration.

Exposes read-only diagnostic sensors:
  - Modbus TCP status   (enabled / disabled)
  - Modbus TCP port     (current configured port number)
  - Gateway connection  (connected / disconnected)
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    ATTR_GATEWAY_SN,
    KEY_MODBUS_ENABLE,
    KEY_MODBUS_PORT,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SigenEnergy Modbus TCP sensor entities."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    gateway = hass.data[DOMAIN][config_entry.entry_id]["gateway"]

    async_add_entities(
        [
            SigenModbusTcpStatusSensor(coordinator, gateway, config_entry),
            SigenModbusTcpPortSensor(coordinator, gateway, config_entry),
        ]
    )


class SigenModbusTcpStatusSensor(CoordinatorEntity, SensorEntity):
    """
    Human-readable Modbus TCP status sensor.

    State: "Enabled" or "Disabled"
    """

    _attr_name = "Modbus TCP Status"
    _attr_icon = "mdi:ethernet"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, gateway, config_entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._gateway = gateway
        self._config_entry = config_entry
        self._attr_unique_id = f"{config_entry.entry_id}_modbus_status"

    @property
    def native_value(self) -> str | None:
        """Return 'Enabled' or 'Disabled' based on coordinator data."""
        data = self.coordinator.data
        if data is None:
            return None
        enabled = data.get(KEY_MODBUS_ENABLE, 0)
        return "Enabled" if enabled else "Disabled"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        return {
            ATTR_GATEWAY_SN: getattr(self._gateway, "_serial", ""),
            "raw_value": data.get(KEY_MODBUS_ENABLE),
        }

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._config_entry.entry_id)},
            "name": "SigenEnergy Gateway",
            "manufacturer": "SigenEnergy",
            "model": "SigenStor Gateway",
        }


class SigenModbusTcpPortSensor(CoordinatorEntity, SensorEntity):
    """
    Modbus TCP port number sensor.

    State: integer port number (e.g. 502)
    """

    _attr_name = "Modbus TCP Port"
    _attr_icon = "mdi:numeric"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_native_unit_of_measurement = None

    def __init__(self, coordinator, gateway, config_entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._gateway = gateway
        self._config_entry = config_entry
        self._attr_unique_id = f"{config_entry.entry_id}_modbus_port"

    @property
    def native_value(self) -> int | None:
        """Return the configured Modbus TCP port number."""
        data = self.coordinator.data
        if data is None:
            return None
        return data.get(KEY_MODBUS_PORT)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {ATTR_GATEWAY_SN: getattr(self._gateway, "_serial", "")}

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._config_entry.entry_id)},
            "name": "SigenEnergy Gateway",
            "manufacturer": "SigenEnergy",
            "model": "SigenStor Gateway",
        }
