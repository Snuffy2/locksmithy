"""Sensor for LockSmithy."""

from dataclasses import dataclass
import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_SLOTS, CONF_START, COORDINATOR, DOMAIN
from .coordinator import LockSmithyCoordinator
from .entity import LockSmithyEntity, LockSmithyEntityDescription

_LOGGER: logging.Logger = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Create LockSmithy Sensor entities."""

    coordinator: LockSmithyCoordinator = hass.data[DOMAIN][COORDINATOR]
    lslock = await coordinator.get_lock_by_config_entry_id(config_entry.entry_id)
    entities: list = []

    entities.append(
        LockSmithySensor(
            entity_description=LockSmithySensorEntityDescription(
                key="sensor.lock_name",
                name="Lock Name",
                icon="mdi:account-lock",
                entity_registry_enabled_default=True,
                hass=hass,
                config_entry=config_entry,
                coordinator=coordinator,
            ),
        )
    )

    if lslock and hasattr(lslock, "parent_name") and lslock.parent_name is not None:
        entities.append(
            LockSmithySensor(
                entity_description=LockSmithySensorEntityDescription(
                    key="sensor.parent_name",
                    name="Parent Lock",
                    icon="mdi:human-male-boy",
                    entity_registry_enabled_default=True,
                    hass=hass,
                    config_entry=config_entry,
                    coordinator=coordinator,
                ),
            )
        )

    entities.extend(
        [
            LockSmithySensor(
                entity_description=LockSmithySensorEntityDescription(
                    key=f"sensor.code_slots:{x}.synced",
                    name=f"Code Slot {x}: Sync Status",
                    icon="mdi:sync-circle",
                    entity_registry_enabled_default=True,
                    hass=hass,
                    config_entry=config_entry,
                    coordinator=coordinator,
                ),
            )
            for x in range(
                config_entry.data[CONF_START],
                config_entry.data[CONF_START] + config_entry.data[CONF_SLOTS],
            )
        ]
    )

    async_add_entities(entities, True)


@dataclass(frozen=True, kw_only=True)
class LockSmithySensorEntityDescription(LockSmithyEntityDescription, SensorEntityDescription):
    """Entity Description for LockSmithy Sensors."""


class LockSmithySensor(LockSmithyEntity, SensorEntity):
    """Class for LockSmithy Sensors."""

    entity_description: LockSmithySensorEntityDescription

    def __init__(
        self,
        entity_description: LockSmithySensorEntityDescription,
    ) -> None:
        """Initialize sensor."""
        super().__init__(
            entity_description=entity_description,
        )
        self._attr_native_value: Any | None = None

    @callback
    def _handle_coordinator_update(self) -> None:
        # _LOGGER.debug(f"[Sensor handle_coordinator_update] self.coordinator.data: {self.coordinator.data}")
        if not self._lslock or not self._lslock.connected:
            self._attr_available = False
            self.async_write_ha_state()
            return

        if ".code_slots" in self._property and (
            not self._lslock.code_slots or self._code_slot not in self._lslock.code_slots
        ):
            self._attr_available = False
            self.async_write_ha_state()
            return

        self._attr_available = True
        self._attr_native_value = self._get_property_value()
        self.async_write_ha_state()
