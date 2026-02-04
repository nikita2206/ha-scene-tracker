"""Config flow for Scene Toggle integration."""

from __future__ import annotations

import re
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    BooleanSelector,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    CONF_NAME,
    CONF_SCENES,
    CONF_WRAP_AROUND,
    DEFAULT_WRAP_AROUND,
    DOMAIN,
    LOGGER,
)


def _get_available_scenes(hass) -> list[SelectOptionDict]:
    """Get all available HomeAssistant scenes."""
    from homeassistant.components.homeassistant.scene import (
        DATA_PLATFORM,
        HomeAssistantScene,
    )

    platform = hass.data.get(DATA_PLATFORM)
    if not platform:
        return []

    scenes: list[SelectOptionDict] = []
    for entity in platform.entities.values():
        if isinstance(entity, HomeAssistantScene):
            scenes.append(
                SelectOptionDict(
                    value=entity.entity_id,
                    label=entity.name or entity.entity_id,
                )
            )

    # Sort by label for easier selection
    scenes.sort(key=lambda x: x["label"])
    return scenes


class SceneToggleConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Scene Toggle."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        # Get available scenes
        available_scenes = await self.hass.async_add_executor_job(
            _get_available_scenes, self.hass
        )

        if not available_scenes:
            return self.async_abort(reason="no_scenes")

        if user_input is not None:
            scenes = user_input.get(CONF_SCENES, [])
            name = user_input.get(CONF_NAME, "").strip()
            if not scenes:
                errors["base"] = "min_scenes"
            elif not name:
                errors[CONF_NAME] = "name_required"
            elif not re.match(r"^[a-z0-9_]+$", name):
                errors[CONF_NAME] = "name_invalid"
            else:
                return self.async_create_entry(
                    title=name,
                    data={
                        CONF_NAME: name,
                        CONF_SCENES: scenes,
                        CONF_WRAP_AROUND: user_input.get(
                            CONF_WRAP_AROUND, DEFAULT_WRAP_AROUND
                        ),
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.TEXT)
                    ),
                    vol.Required(CONF_SCENES): SelectSelector(
                        SelectSelectorConfig(
                            options=available_scenes,
                            multiple=True,
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Optional(
                        CONF_WRAP_AROUND, default=DEFAULT_WRAP_AROUND
                    ): BooleanSelector(),
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Get the options flow for this handler."""
        return SceneToggleOptionsFlow(config_entry)


class SceneToggleOptionsFlow(OptionsFlow):
    """Handle options flow for Scene Toggle."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}

        # Get available scenes
        available_scenes = await self.hass.async_add_executor_job(
            _get_available_scenes, self.hass
        )

        if user_input is not None:
            scenes = user_input.get(CONF_SCENES, [])
            if not scenes:
                errors["base"] = "min_scenes"
            else:
                return self.async_create_entry(
                    title="",
                    data={
                        CONF_SCENES: scenes,
                        CONF_WRAP_AROUND: user_input.get(
                            CONF_WRAP_AROUND, DEFAULT_WRAP_AROUND
                        ),
                    },
                )

        # Get current values
        current_scenes = self.config_entry.data.get(CONF_SCENES, [])
        current_wrap = self.config_entry.data.get(CONF_WRAP_AROUND, DEFAULT_WRAP_AROUND)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SCENES, default=current_scenes): SelectSelector(
                        SelectSelectorConfig(
                            options=available_scenes,
                            multiple=True,
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Optional(
                        CONF_WRAP_AROUND, default=current_wrap
                    ): BooleanSelector(),
                }
            ),
            errors=errors,
        )
