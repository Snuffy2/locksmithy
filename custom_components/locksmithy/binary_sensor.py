"""Sensor for LockSmithy."""

from dataclasses import dataclass
import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import PlatformNotReady
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_SLOTS, CONF_START, COORDINATOR, DOMAIN
from .coordinator import LockSmithyCoordinator
from .entity import LockSmithyEntity, LockSmithyEntityDescription
from .helpers import async_using_zwave_js

_LOGGER: logging.Logger = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create the LockSmithy Binary Sensors."""
    coordinator: LockSmithyCoordinator = hass.data[DOMAIN][COORDINATOR]
    lslock = await coordinator.get_lock_by_config_entry_id(config_entry.entry_id)
    entities: list = []
    if async_using_zwave_js(hass=hass, lslock=lslock):
        entities.append(
            LockSmithyBinarySensor(
                entity_description=LockSmithyBinarySensorEntityDescription(
                    key="binary_sensor.connected",
                    name="Network",
                    device_class=BinarySensorDeviceClass.CONNECTIVITY,
                    entity_registry_enabled_default=True,
                    hass=hass,
                    config_entry=config_entry,
                    coordinator=coordinator,
                ),
            )
        )
        entities.extend(
            [
                LockSmithyBinarySensor(
                    entity_description=LockSmithyBinarySensorEntityDescription(
                        key=f"binary_sensor.code_slots:{x}.active",
                        name=f"Code Slot {x}: Active",
                        icon="mdi:run",
                        entity_registry_enabled_default=True,
                        hass=hass,
                        config_entry=config_entry,
                        coordinator=coordinator,
                    )
                )
                for x in range(
                    config_entry.data[CONF_START],
                    config_entry.data[CONF_START] + config_entry.data[CONF_SLOTS],
                )
            ]
        )
    else:
        _LOGGER.error("Z-Wave integration not found")
        raise PlatformNotReady

    async_add_entities(entities, True)


@dataclass(frozen=True, kw_only=True)
class LockSmithyBinarySensorEntityDescription(
    LockSmithyEntityDescription, BinarySensorEntityDescription
):
    """Entity Description for LockSmithy Binary Sensors."""


class LockSmithyBinarySensor(LockSmithyEntity, BinarySensorEntity):
    """LockSmithy Binary Sensor Class."""

    entity_description: LockSmithyBinarySensorEntityDescription

    def __init__(
        self,
        entity_description: LockSmithyBinarySensorEntityDescription,
    ) -> None:
        """Initialize binary sensor."""
        super().__init__(
            entity_description=entity_description,
        )
        self._attr_is_on: bool = False
        self._attr_available: bool = True

    @callback
    def _handle_coordinator_update(self) -> None:
        # _LOGGER.debug("[Binary Sensor handle_coordinator_update] self.coordinator.data: %s", self.coordinator.data)
        self._attr_is_on = self._get_property_value()
        self.async_write_ha_state()
