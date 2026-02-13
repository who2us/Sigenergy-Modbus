"""
Sensor platform for the SigenEnergy integration.

Sensors are split into two groups:

  CLOUD SENSORS (via SigenCloudCoordinator — confirmed real data)
  ──────────────────────────────────────────────────────────────
  Battery:
    • Battery SoC            (%)        — energy_flow.batterySoc
    • Battery Power          (kW)       — energy_flow.batteryPower  ÷1000
  Solar:
    • PV Power               (kW)       — energy_flow.pvPower       ÷1000
  Grid:
    • Grid Power             (kW)       — energy_flow.buySellPower  ÷1000
                                          (+ve = importing, −ve = exporting)
  Load:
    • Load Power             (kW)       — energy_flow.loadPower     ÷1000
  Generation totals:
    • Day Generation         (kWh)      — statistics.dayGeneration
    • Month Generation       (kWh)      — statistics.monthGeneration
    • Year Generation        (kWh)      — statistics.yearGeneration
    • Lifetime Generation    (kWh)      — statistics.lifetimeGeneration

  DIAGNOSTIC SENSORS (via SigenLocalCoordinator — local WS)
  ──────────────────────────────────────────────────────────
    • Modbus TCP Status      (Enabled/Disabled)
    • Modbus TCP Port        (integer)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    EntityCategory,
    PERCENTAGE,
    UnitOfEnergy,
    UnitOfPower,
)
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

# ── Helpers ───────────────────────────────────────────────────────────────────

def _w_to_kw(value) -> float | None:
    """Convert watts to kW, handling both W and already-kW values from the API."""
    if value is None:
        return None
    # The API sometimes returns W (>100) and sometimes kW (<10) depending on firmware
    # Mirror the prototype's heuristic: if |value| > 100, it's in W
    return round(value / 1000, 2) if abs(value) > 100 else value


# ── Cloud sensor descriptors ──────────────────────────────────────────────────

@dataclass
class SigenCloudSensorDescription(SensorEntityDescription):
    """Adds a value_fn that extracts the reading from the coordinator data dict."""
    value_fn: Callable[[dict], Any] = None


CLOUD_SENSORS: tuple[SigenCloudSensorDescription, ...] = (
    # ── Battery ──────────────────────────────────────────────────────────────
    SigenCloudSensorDescription(
        key="battery_soc",
        name="Battery SoC",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:battery",
        value_fn=lambda d: d.get("energy_flow", {}).get("batterySoc"),
    ),
    SigenCloudSensorDescription(
        key="battery_power",
        name="Battery Power",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:battery-charging",
        value_fn=lambda d: _w_to_kw(d.get("energy_flow", {}).get("batteryPower")),
    ),
    # ── Solar ─────────────────────────────────────────────────────────────────
    SigenCloudSensorDescription(
        key="pv_power",
        name="PV Power",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:solar-power",
        value_fn=lambda d: _w_to_kw(d.get("energy_flow", {}).get("pvPower")),
    ),
    # ── Grid ──────────────────────────────────────────────────────────────────
    SigenCloudSensorDescription(
        key="grid_power",
        name="Grid Power",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:transmission-tower",
        value_fn=lambda d: _w_to_kw(d.get("energy_flow", {}).get("buySellPower")),
    ),
    # ── Load ──────────────────────────────────────────────────────────────────
    SigenCloudSensorDescription(
        key="load_power",
        name="Load Power",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:home-lightning-bolt",
        value_fn=lambda d: _w_to_kw(d.get("energy_flow", {}).get("loadPower")),
    ),
    # ── Generation totals ─────────────────────────────────────────────────────
    SigenCloudSensorDescription(
        key="day_generation",
        name="Day Generation",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:solar-power-variant",
        value_fn=lambda d: d.get("statistics", {}).get("dayGeneration"),
    ),
    SigenCloudSensorDescription(
        key="month_generation",
        name="Month Generation",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:solar-power-variant",
        value_fn=lambda d: d.get("statistics", {}).get("monthGeneration"),
    ),
    SigenCloudSensorDescription(
        key="year_generation",
        name="Year Generation",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:solar-power-variant",
        value_fn=lambda d: d.get("statistics", {}).get("yearGeneration"),
    ),
    SigenCloudSensorDescription(
        key="lifetime_generation",
        name="Lifetime Generation",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:counter",
        value_fn=lambda d: d.get("statistics", {}).get("lifetimeGeneration"),
    ),
)


# ── Platform setup ────────────────────────────────────────────────────────────

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up all SigenEnergy sensor entities."""
    entry_data = hass.data[DOMAIN][config_entry.entry_id]
    local_coordinator = entry_data["local_coordinator"]
    cloud_coordinator = entry_data["cloud_coordinator"]
    gateway = entry_data["gateway"]

    entities: list[SensorEntity] = []

    # Cloud energy sensors
    for description in CLOUD_SENSORS:
        entities.append(
            SigenCloudSensor(cloud_coordinator, description, config_entry)
        )

    # Local diagnostic sensors
    entities.append(SigenModbusTcpStatusSensor(local_coordinator, gateway, config_entry))
    entities.append(SigenModbusTcpPortSensor(local_coordinator, gateway, config_entry))

    async_add_entities(entities)


# ── Entity classes ────────────────────────────────────────────────────────────

_DEVICE_INFO = lambda entry_id: {
    "identifiers": {(DOMAIN, entry_id)},
    "name": "SigenEnergy Gateway",
    "manufacturer": "SigenEnergy",
    "model": "SigenStor Gateway",
}


class SigenCloudSensor(CoordinatorEntity, SensorEntity):
    """A sensor backed by the SigenEnergy cloud API."""

    entity_description: SigenCloudSensorDescription

    def __init__(self, coordinator, description: SigenCloudSensorDescription, config_entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._config_entry = config_entry
        self._attr_unique_id = f"{config_entry.entry_id}_{description.key}"
        self._attr_has_entity_name = True

    @property
    def native_value(self):
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def device_info(self):
        return _DEVICE_INFO(self._config_entry.entry_id)


class SigenModbusTcpStatusSensor(CoordinatorEntity, SensorEntity):
    """Human-readable Modbus TCP status (Enabled / Disabled)."""

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
        data = self.coordinator.data
        if data is None:
            return None
        return "Enabled" if data.get(KEY_MODBUS_ENABLE) else "Disabled"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        return {
            ATTR_GATEWAY_SN: getattr(self._gateway, "_serial", ""),
            "raw_value": data.get(KEY_MODBUS_ENABLE),
        }

    @property
    def device_info(self):
        return _DEVICE_INFO(self._config_entry.entry_id)


class SigenModbusTcpPortSensor(CoordinatorEntity, SensorEntity):
    """Current Modbus TCP port number."""

    _attr_name = "Modbus TCP Port"
    _attr_icon = "mdi:numeric"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, gateway, config_entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._gateway = gateway
        self._config_entry = config_entry
        self._attr_unique_id = f"{config_entry.entry_id}_modbus_port"

    @property
    def native_value(self) -> int | None:
        data = self.coordinator.data
        if data is None:
            return None
        return data.get(KEY_MODBUS_PORT)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {ATTR_GATEWAY_SN: getattr(self._gateway, "_serial", "")}

    @property
    def device_info(self):
        return _DEVICE_INFO(self._config_entry.entry_id)
