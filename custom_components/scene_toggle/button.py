"""Button entities for scene toggling."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ATTR_DIRECTION,
    DIRECTION_NEXT,
    DIRECTION_PREVIOUS,
    DOMAIN,
    SERVICE_TOGGLE_SCENE,
)


async def async_setup_platform(
    hass: HomeAssistant,
    config: dict,
    async_add_entities: AddEntitiesCallback,
    discovery_info: dict | None = None,
) -> None:
    """Set up Scene Toggle buttons."""
    async_add_entities(
        [
            SceneToggleButton(
                ButtonEntityDescription(
                    key="next",
                    name="Next scene",
                ),
                DIRECTION_NEXT,
            ),
            SceneToggleButton(
                ButtonEntityDescription(
                    key="previous",
                    name="Previous scene",
                ),
                DIRECTION_PREVIOUS,
            ),
        ]
    )


class SceneToggleButton(ButtonEntity):
    """Button that toggles to the next/previous scene."""

    _attr_has_entity_name = True

    def __init__(self, description: ButtonEntityDescription, direction: str) -> None:
        self.entity_description = description
        self._direction = direction
        self._attr_unique_id = f"{DOMAIN}_{description.key}"
        self._attr_name = description.name

    async def async_press(self) -> None:
        """Handle the button press."""
        await self.hass.services.async_call(
            DOMAIN,
            SERVICE_TOGGLE_SCENE,
            {ATTR_DIRECTION: self._direction},
            blocking=False,
        )
