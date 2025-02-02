"""Support for LockSmithy buttons."""

from collections.abc import MutableMapping
from dataclasses import dataclass
import logging

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_SLOTS, CONF_START, COORDINATOR, DOMAIN
from .coordinator import LockSmithyCoordinator
from .entity import LockSmithyEntity, LockSmithyEntityDescription

_LOGGER: logging.Logger = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up LockSmithy button."""
    coordinator: LockSmithyCoordinator = hass.data[DOMAIN][COORDINATOR]
    entities: list = []
    entities.append(
        LockSmithyButton(
            entity_description=LockSmithyButtonEntityDescription(
                key="button.reset_lock",
                name="Reset Lock",
                icon="mdi:nuke",
                entity_registry_enabled_default=True,
                hass=hass,
                config_entry=config_entry,
                coordinator=coordinator,
            ),
        )
    )
    entities.extend(
        [
            LockSmithyButton(
                entity_description=LockSmithyButtonEntityDescription(
                    key=f"button.code_slots:{x}.reset",
                    name=f"Code Slot {x}: Reset",
                    icon="mdi:lock-reset",
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
    async_add_entities(entities, True)


@dataclass(frozen=True, kw_only=True)
class LockSmithyButtonEntityDescription(LockSmithyEntityDescription, ButtonEntityDescription):
    """Entity Description for LockSmithy Buttons."""


class LockSmithyButton(LockSmithyEntity, ButtonEntity):
    """Representation of a LockSmithy button."""

    entity_description: LockSmithyButtonEntityDescription

    def __init__(
        self,
        entity_description: LockSmithyButtonEntityDescription,
    ) -> None:
        """Initialize button."""
        super().__init__(
            entity_description=entity_description,
        )
        self._attr_available: bool = True

    @callback
    def _handle_coordinator_update(self) -> None:
        if not self._lslock or not self._lslock.connected:
            self._attr_available = False
            self.async_write_ha_state()
            return

        if (
            ".code_slots" in self._property
            and isinstance(self._lslock.code_slots, MutableMapping)
            and self._code_slot not in self._lslock.code_slots
        ):
            self._attr_available = False
            self.async_write_ha_state()
            return

        self._attr_available = True
        self.async_write_ha_state()

    async def async_press(self) -> None:
        """Handle button press event.

        For reset_lock: Resets the entire lock to factory settings.
        For code slot reset: Clears the PIN and resets all settings for the specific slot.
        """
        if self._property.endswith(".reset_lock"):
            await self.coordinator.reset_lock(
                config_entry_id=self._config_entry.entry_id,
            )
        elif self._property.endswith(".reset") and self._code_slot:
            await self.coordinator.reset_code_slot(
                config_entry_id=self._config_entry.entry_id,
                code_slot_num=self._code_slot,
            )
