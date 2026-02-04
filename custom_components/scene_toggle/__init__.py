"""Scene Toggle integration."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import (
    DOMAIN,
    LOGGER,
    PLATFORMS,
    SERVICE_NEXT_SCENE,
    SERVICE_PREVIOUS_SCENE,
)
from .coordinator import SceneToggleCoordinator

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Scene Toggle component."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Scene Toggle from a config entry."""
    coordinator = SceneToggleCoordinator(hass, entry)
    await coordinator.async_setup()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    # Forward setup to platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register services (only once)
    _register_services(hass)

    # Listen for options updates
    entry.async_on_unload(entry.add_update_listener(async_update_options))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        coordinator: SceneToggleCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_unload()

    return unload_ok


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)


def _register_services(hass: HomeAssistant) -> None:
    """Register services for Scene Toggle."""
    if hass.services.has_service(DOMAIN, SERVICE_NEXT_SCENE):
        return  # Already registered

    async def handle_next_scene(call: ServiceCall) -> None:
        """Handle next scene service call."""
        entry_id = call.data.get("entry_id")

        if entry_id:
            # Specific entry
            coordinator = hass.data[DOMAIN].get(entry_id)
            if coordinator:
                await coordinator.async_next_scene()
        else:
            # All entries
            for coordinator in hass.data[DOMAIN].values():
                await coordinator.async_next_scene()

    async def handle_previous_scene(call: ServiceCall) -> None:
        """Handle previous scene service call."""
        entry_id = call.data.get("entry_id")

        if entry_id:
            # Specific entry
            coordinator = hass.data[DOMAIN].get(entry_id)
            if coordinator:
                await coordinator.async_previous_scene()
        else:
            # All entries
            for coordinator in hass.data[DOMAIN].values():
                await coordinator.async_previous_scene()

    service_schema = vol.Schema(
        {
            vol.Optional("entry_id"): cv.string,
        }
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_NEXT_SCENE,
        handle_next_scene,
        schema=service_schema,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_PREVIOUS_SCENE,
        handle_previous_scene,
        schema=service_schema,
    )

    LOGGER.debug("Registered Scene Toggle services")
