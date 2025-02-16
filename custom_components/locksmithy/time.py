"""Support for LockSmithy Time."""

from collections.abc import MutableMapping
from dataclasses import dataclass
from datetime import time as dt_time
import logging

from homeassistant.components.time import TimeEntity, TimeEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_SLOTS, CONF_START, COORDINATOR, DAY_NAMES, DOMAIN
from .coordinator import LockSmithyCoordinator
from .entity import LockSmithyEntity, LockSmithyEntityDescription
from .lock import LockSmithyCodeSlot, LockSmithyCodeSlotDayOfWeek

_LOGGER: logging.Logger = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create LockSmithy Time entities."""
    coordinator: LockSmithyCoordinator = hass.data[DOMAIN][COORDINATOR]
    entities: list = []

    for x in range(
        config_entry.data[CONF_START],
        config_entry.data[CONF_START] + config_entry.data[CONF_SLOTS],
    ):
        for i, dow in enumerate(DAY_NAMES):
            dow_time_entities: list[MutableMapping[str, str]] = [
                {
                    "prop": f"time.code_slots:{x}.accesslimit_day_of_week:{i}.time_start",
                    "name": f"Code Slot {x}: {dow} - Start Time",
                    "icon": "mdi:clock-start",
                },
                {
                    "prop": f"time.code_slots:{x}.accesslimit_day_of_week:{i}.time_end",
                    "name": f"Code Slot {x}: {dow} - End Time",
                    "icon": "mdi:clock-end",
                },
            ]
            entities.extend(
                [
                    LockSmithyTime(
                        entity_description=LockSmithyTimeEntityDescription(
                            key=ent["prop"],
                            name=ent["name"],
                            icon=ent["icon"],
                            entity_registry_enabled_default=True,
                            hass=hass,
                            config_entry=config_entry,
                            coordinator=coordinator,
                        ),
                    )
                    for ent in dow_time_entities
                ]
            )

    async_add_entities(entities, True)


@dataclass(frozen=True, kw_only=True)
class LockSmithyTimeEntityDescription(LockSmithyEntityDescription, TimeEntityDescription):
    """Entity Description for LockSmithy Time entities."""


class LockSmithyTime(LockSmithyEntity, TimeEntity):
    """Class for LockSmithy Time entities."""

    entity_description: LockSmithyTimeEntityDescription

    def __init__(
        self,
        entity_description: LockSmithyTimeEntityDescription,
    ) -> None:
        """Initialize Time."""
        super().__init__(
            entity_description=entity_description,
        )
        self._attr_native_value: dt_time | None = None

    @callback
    def _handle_coordinator_update(self) -> None:
        # _LOGGER.debug(f"[Time handle_coordinator_update] self.coordinator.data: {self.coordinator.data}")
        if not self._lslock or not self._lslock.connected:
            self._attr_available = False
            self.async_write_ha_state()
            return

        if (
            ".code_slots" in self._property
            and self._lslock.parent_name is not None
            and (
                not self._lslock.code_slots
                or not self._code_slot
                or not self._lslock.code_slots[self._code_slot].override_parent
            )
        ):
            self._attr_available = False
            self.async_write_ha_state()
            return

        if ".code_slots" in self._property and (
            not self._lslock.code_slots or self._code_slot not in self._lslock.code_slots
        ):
            self._attr_available = False
            self.async_write_ha_state()
            return

        if ".accesslimit_day_of_week" in self._property and (
            not self._lslock.code_slots
            or not self._code_slot
            or not self._lslock.code_slots[self._code_slot].accesslimit_day_of_week_enabled
        ):
            self._attr_available = False
            self.async_write_ha_state()
            return

        if self._property.endswith(".time_start") or self._property.endswith(".time_end"):
            code_slots: MutableMapping[int, LockSmithyCodeSlot] | None = self._lslock.code_slots
            if self._code_slot is None or code_slots is None or self._code_slot not in code_slots:
                self._attr_available = False
                self.async_write_ha_state()
                return

            accesslimit_day_of_week: MutableMapping[int, LockSmithyCodeSlotDayOfWeek] | None = (
                code_slots[self._code_slot].accesslimit_day_of_week
            )
            if (
                self._day_of_week_num is None
                or accesslimit_day_of_week is None
                or self._day_of_week_num not in accesslimit_day_of_week
            ):
                self._attr_available = False
                self.async_write_ha_state()
                return

            day_of_week: LockSmithyCodeSlotDayOfWeek | None = accesslimit_day_of_week[
                self._day_of_week_num
            ]
            if day_of_week is None or not day_of_week.dow_enabled or not day_of_week.limit_by_time:
                self._attr_available = False
                self.async_write_ha_state()
                return

        self._attr_available = True
        self._attr_native_value = self._get_property_value()
        self.async_write_ha_state()

    async def async_set_value(self, value: dt_time) -> None:
        """Update value for a time entity."""
        _LOGGER.debug(
            "[Time async_set_value] %s: value: %s",
            self.name,
            value,
        )
        if (
            (self._property.endswith(".time_start") or self._property.endswith(".time_end"))
            and self._lslock
            and self._lslock.parent_name
            and (
                not self._lslock.code_slots
                or not self._code_slot
                or not self._lslock.code_slots[self._code_slot].override_parent
            )
        ):
            _LOGGER.debug(
                "[Time async_set_value] %s: Child lock and code slot %s not set to override parent. Ignoring change",
                self._lslock.lock_name,
                self._code_slot,
            )
            return
        if self._set_property_value(value):
            self._attr_native_value = value
            await self.coordinator.async_refresh()
