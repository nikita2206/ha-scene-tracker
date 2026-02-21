"""Sensor platform for Scene Toggle."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ATTR_ALL_SCORES,
    ATTR_DISTANCE_SCORE,
    ATTR_SCENE_ENTITY_ID,
    DOMAIN,
)
from .coordinator import SceneToggleCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Scene Toggle sensor from config entry."""
    coordinator: SceneToggleCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([CurrentSceneSensor(coordinator, entry)])


class CurrentSceneSensor(SensorEntity):
    """Sensor showing the current (best-matching) scene."""

    _attr_has_entity_name = True
    _attr_translation_key = "current_scene"

    def __init__(
        self,
        coordinator: SceneToggleCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        self.coordinator = coordinator
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_current_scene"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def native_value(self) -> str | None:
        """Return the current scene entity ID."""
        return self.coordinator.current_scene

    @property
    def extra_state_attributes(self) -> dict:
        """Return additional state attributes."""
        return {
            ATTR_SCENE_ENTITY_ID: self.coordinator.current_scene,
            ATTR_DISTANCE_SCORE: round(self.coordinator.current_distance, 4),
            ATTR_ALL_SCORES: {
                scene: round(score, 4)
                for scene, score in self.coordinator.all_distances.items()
            },
        }

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        await super().async_added_to_hass()
        self.coordinator.add_listener(self._handle_coordinator_update)

    async def async_will_remove_from_hass(self) -> None:
        """Run when entity will be removed from hass."""
        self.coordinator.remove_listener(self._handle_coordinator_update)
        await super().async_will_remove_from_hass()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()
