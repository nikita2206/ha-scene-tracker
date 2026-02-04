"""Button platform for Scene Toggle."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import SceneToggleCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Scene Toggle buttons from config entry."""
    coordinator: SceneToggleCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities([
        SceneToggleButton(coordinator, entry, "next"),
        SceneToggleButton(coordinator, entry, "previous"),
    ])


class SceneToggleButton(ButtonEntity):
    """Button that toggles to the next/previous scene."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SceneToggleCoordinator,
        entry: ConfigEntry,
        direction: str,
    ) -> None:
        """Initialize the button."""
        self.coordinator = coordinator
        self._direction = direction
        self._attr_unique_id = f"{entry.entry_id}_{direction}_scene"
        self._attr_translation_key = f"{direction}_scene"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            entry_type=DeviceEntryType.SERVICE,
        )

    async def async_press(self) -> None:
        """Handle the button press."""
        if self._direction == "next":
            await self.coordinator.async_next_scene()
        else:
            await self.coordinator.async_previous_scene()
