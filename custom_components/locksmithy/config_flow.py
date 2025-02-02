"""Config flow for LockSmithy."""

from __future__ import annotations

from collections.abc import MutableMapping
import contextlib
import logging
from typing import TYPE_CHECKING, Any

import voluptuous as vol

from homeassistant.components.binary_sensor import DOMAIN as BINARY_DOMAIN
from homeassistant.components.lock import DOMAIN as LOCK_DOMAIN
from homeassistant.components.script import DOMAIN as SCRIPT_DOMAIN
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import HomeAssistant, callback
from homeassistant.util import slugify

from .const import (
    CONF_ALARM_LEVEL_OR_USER_CODE_ENTITY_ID,
    CONF_ALARM_TYPE_OR_ACCESS_CONTROL_ENTITY_ID,
    CONF_DOOR_SENSOR_ENTITY_ID,
    CONF_HIDE_PINS,
    CONF_LOCK_ENTITY_ID,
    CONF_LOCK_NAME,
    CONF_NOTIFY_SCRIPT_NAME,
    CONF_PARENT,
    CONF_SLOTS,
    CONF_START,
    COORDINATOR,
    DEFAULT_CODE_SLOTS,
    DEFAULT_HIDE_PINS,
    DEFAULT_START,
    DOMAIN,
    NONE_TEXT,
)

if TYPE_CHECKING:
    from .coordinator import LockSmithyCoordinator

_LOGGER: logging.Logger = logging.getLogger(__name__)


class LockSmithyConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow for LockSmithy."""

    VERSION: int = 3
    DEFAULTS: MutableMapping[str, Any] = {
        CONF_SLOTS: DEFAULT_CODE_SLOTS,
        CONF_START: DEFAULT_START,
        CONF_DOOR_SENSOR_ENTITY_ID: NONE_TEXT,
        CONF_ALARM_LEVEL_OR_USER_CODE_ENTITY_ID: NONE_TEXT,
        CONF_ALARM_TYPE_OR_ACCESS_CONTROL_ENTITY_ID: NONE_TEXT,
        CONF_HIDE_PINS: DEFAULT_HIDE_PINS,
        CONF_NOTIFY_SCRIPT_NAME: NONE_TEXT,
    }

    async def get_unique_name_error(
        self, user_input: MutableMapping[str, Any]
    ) -> MutableMapping[str, str]:
        """Check if name is unique, returning dictionary error if so."""
        # Validate that lock name is unique
        existing_entry = await self.async_set_unique_id(
            slugify(user_input[CONF_LOCK_NAME]).lower(), raise_on_progress=True
        )
        if existing_entry:
            return {CONF_LOCK_NAME: "same_name"}
        return {}

    async def async_step_user(
        self, user_input: MutableMapping[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a flow initialized by the user."""
        return await _start_config_flow(
            cls=self,
            step_id="user",
            title=user_input[CONF_LOCK_NAME] if user_input else "",
            user_input=user_input,
            defaults=self.DEFAULTS,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> LockSmithyOptionsFlow:
        """Get the options flow for this handler."""
        return LockSmithyOptionsFlow()


class LockSmithyOptionsFlow(OptionsFlow):
    """Options flow for LockSmithy."""

    async def get_unique_name_error(
        self, user_input: MutableMapping[str, Any]
    ) -> MutableMapping[str, str]:
        """Check if name is unique, returning dictionary error if so."""
        # If lock name has changed, make sure new name isn't already being used
        # otherwise show an error
        if self.config_entry.unique_id != slugify(user_input[CONF_LOCK_NAME]).lower():
            for entry in self.hass.config_entries.async_entries(DOMAIN):
                if entry.unique_id == slugify(user_input[CONF_LOCK_NAME]).lower():
                    return {CONF_LOCK_NAME: "same_name"}
        return {}

    async def async_step_init(
        self, user_input: MutableMapping[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a flow initialized by the user."""
        return await _start_config_flow(
            cls=self,
            step_id="init",
            title="",
            user_input=user_input,
            defaults=dict(self.config_entry.data),
            entry_id=self.config_entry.entry_id,
        )


def _available_parent_locks(hass: HomeAssistant, entry_id: str | None = None) -> list:
    """Return other LockSmithy locks if they are not already a child lock."""

    data: list[str] = [NONE_TEXT]
    if DOMAIN not in hass.data:
        return data

    data.extend(
        [
            entry.title
            for entry in hass.config_entries.async_entries(DOMAIN)
            if entry.entry_id != entry_id
            and (CONF_PARENT not in entry.data or entry.data[CONF_PARENT] is None)
        ]
    )
    return data


def _get_entities(
    hass: HomeAssistant,
    domain: str,
    search: list[str] | None = None,
    extra_entities: list[str] | None = None,
    exclude_entities: list[str] | None = None,
    sort: bool = True,
) -> list[str]:
    data: list[str] = []
    if domain not in hass.data:
        return extra_entities or []

    for entity in hass.data[domain].entities:
        if search is not None and not any(map(entity.entity_id.__contains__, search)):
            continue
        data.append(entity.entity_id)

    if extra_entities:
        data.extend(extra_entities)

    if exclude_entities:
        with contextlib.suppress(ValueError):
            for ent in exclude_entities:
                data.remove(ent)
    if sort:
        data.sort()

    return data


def _get_locks_in_use(hass: HomeAssistant, exclude: str | None = None) -> list[str]:
    if DOMAIN not in hass.data or COORDINATOR not in hass.data[DOMAIN]:
        return []
    data: list[str] = []
    coordinator: LockSmithyCoordinator = hass.data[DOMAIN][COORDINATOR]
    data.extend([lslock.lock_entity_id for lslock in coordinator.data.values()])
    if exclude:
        with contextlib.suppress(ValueError):
            data.remove(exclude)

    return data


def _get_schema(
    hass: HomeAssistant,
    user_input: MutableMapping[str, Any] | None,
    default_dict: MutableMapping[str, Any],
    entry_id: str | None = None,
) -> vol.Schema:
    """Get a schema using the default_dict as a backup."""
    if user_input is None:
        user_input = {}

    if CONF_PARENT in default_dict and default_dict[CONF_PARENT] is None:
        check_dict: MutableMapping[str, Any] = dict(default_dict).copy()
        check_dict.pop(CONF_PARENT, None)
        default_dict = check_dict

    def _get_default(key: str, fallback_default: Any | None = None) -> Any | None:
        """Get default value for key."""
        default: Any | None = user_input.get(key)
        if default is None:
            default = default_dict.get(key, fallback_default)
        if default is None:
            default = fallback_default
        return default

    script_default: str | None = _get_default(CONF_NOTIFY_SCRIPT_NAME, NONE_TEXT)
    if script_default is None:
        script_default = NONE_TEXT
    elif script_default != NONE_TEXT and not script_default.startswith("script."):
        script_default = f"script.{script_default}"
    _LOGGER.debug("[get_schema] script_default: %s (%s)", script_default, type(script_default))
    return vol.Schema(
        {
            vol.Required(CONF_LOCK_NAME, default=_get_default(CONF_LOCK_NAME)): str,
            vol.Required(CONF_LOCK_ENTITY_ID, default=_get_default(CONF_LOCK_ENTITY_ID)): vol.In(
                _get_entities(
                    hass=hass,
                    domain=LOCK_DOMAIN,
                    exclude_entities=_get_locks_in_use(
                        hass=hass, exclude=_get_default(CONF_LOCK_ENTITY_ID)
                    ),
                )
            ),
            vol.Optional(CONF_PARENT, default=_get_default(CONF_PARENT, NONE_TEXT)): vol.In(
                _available_parent_locks(hass, entry_id)
            ),
            vol.Required(CONF_SLOTS, default=_get_default(CONF_SLOTS, DEFAULT_CODE_SLOTS)): vol.All(
                vol.Coerce(int), vol.Range(min=1)
            ),
            vol.Required(CONF_START, default=_get_default(CONF_START, DEFAULT_START)): vol.All(
                vol.Coerce(int), vol.Range(min=1)
            ),
            vol.Optional(
                CONF_DOOR_SENSOR_ENTITY_ID,
                default=_get_default(CONF_DOOR_SENSOR_ENTITY_ID, NONE_TEXT),
            ): vol.In(
                _get_entities(
                    hass=hass,
                    domain=BINARY_DOMAIN,
                    extra_entities=[NONE_TEXT],
                )
            ),
            vol.Optional(
                CONF_ALARM_LEVEL_OR_USER_CODE_ENTITY_ID,
                default=_get_default(CONF_ALARM_LEVEL_OR_USER_CODE_ENTITY_ID, NONE_TEXT),
            ): vol.In(
                _get_entities(
                    hass=hass,
                    domain=SENSOR_DOMAIN,
                    search=["alarm_level", "user_code", "alarmlevel"],
                    extra_entities=[NONE_TEXT],
                )
            ),
            vol.Optional(
                CONF_ALARM_TYPE_OR_ACCESS_CONTROL_ENTITY_ID,
                default=_get_default(
                    CONF_ALARM_TYPE_OR_ACCESS_CONTROL_ENTITY_ID,
                    NONE_TEXT,
                ),
            ): vol.In(
                _get_entities(
                    hass=hass,
                    domain=SENSOR_DOMAIN,
                    search=["alarm_type", "access_control", "alarmtype"],
                    extra_entities=[NONE_TEXT],
                )
            ),
            vol.Optional(
                CONF_NOTIFY_SCRIPT_NAME,
                default=script_default,
            ): vol.In(
                _get_entities(
                    hass=hass,
                    domain=SCRIPT_DOMAIN,
                    extra_entities=[NONE_TEXT],
                )
            ),
            vol.Required(
                CONF_HIDE_PINS, default=_get_default(CONF_HIDE_PINS, DEFAULT_HIDE_PINS)
            ): bool,
        },
    )


async def _start_config_flow(
    cls: LockSmithyConfigFlow | LockSmithyOptionsFlow,
    step_id: str,
    title: str,
    user_input: MutableMapping[str, Any] | None,
    defaults: MutableMapping[str, Any] | None = None,
    entry_id: str | None = None,
) -> ConfigFlowResult:
    """Start a config flow."""
    errors: dict[str, Any] = {}
    description_placeholders: dict[str, Any] = {}
    defaults = defaults or {}

    if user_input is not None:
        _LOGGER.debug(
            "[start_config_flow] step_id: %s, initial user_input: %s, errors: %s",
            step_id,
            user_input,
            errors,
        )
        user_input[CONF_SLOTS] = int(user_input[CONF_SLOTS])
        user_input[CONF_START] = int(user_input[CONF_START])

        # Convert (none) to None
        if user_input.get(CONF_PARENT) == NONE_TEXT:
            user_input[CONF_PARENT] = None
        if user_input.get(CONF_NOTIFY_SCRIPT_NAME) == NONE_TEXT:
            user_input[CONF_NOTIFY_SCRIPT_NAME] = None

        errors.update(await cls.get_unique_name_error(user_input))

        # Update options if no errors
        if not errors:
            _LOGGER.debug(
                "[start_config_flow] step_id: %s, final user_input: %s",
                step_id,
                user_input,
            )
            if isinstance(cls, LockSmithyConfigFlow) or step_id == "user" or not entry_id:
                return cls.async_create_entry(title=title, data=user_input)
            cls.hass.config_entries.async_update_entry(cls.config_entry, data=user_input)
            await cls.hass.config_entries.async_reload(entry_id)
            return cls.async_create_entry(title="", data={})

    return cls.async_show_form(
        step_id=step_id,
        data_schema=_get_schema(
            hass=cls.hass, user_input=user_input, default_dict=defaults, entry_id=entry_id
        ),
        errors=errors,
        description_placeholders=description_placeholders,
    )
