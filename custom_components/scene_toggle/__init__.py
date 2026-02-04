"""Scene Toggle integration."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import discovery

from .const import (
    ATTR_DIRECTION,
    DOMAIN,
    LOGGER,
    SERVICE_TOGGLE_SCENE,
)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Scene Toggle integration."""

    async def handle_toggle(call: ServiceCall) -> None:
        direction = call.data.get(ATTR_DIRECTION)
        LOGGER.info("Scene toggle requested: %s", direction)

    hass.services.async_register(DOMAIN, SERVICE_TOGGLE_SCENE, handle_toggle)

    hass.async_create_task(
        discovery.async_load_platform(hass, Platform.BUTTON, DOMAIN, {}, config)
    )
    return True
