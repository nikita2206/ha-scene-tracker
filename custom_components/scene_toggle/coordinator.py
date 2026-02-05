"""Coordinator for Scene Toggle integration."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.light import ATTR_BRIGHTNESS, ATTR_COLOR_TEMP, ATTR_RGB_COLOR, DOMAIN as LIGHT_DOMAIN
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID, ATTR_FRIENDLY_NAME, EVENT_CALL_SERVICE, STATE_OFF, STATE_ON
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.event import async_call_later, async_track_state_change_event

from .const import (
    CONF_SCENES,
    CONF_WRAP_AROUND,
    DEFAULT_DEBOUNCE_SECONDS,
    DEFAULT_WRAP_AROUND,
    LOGGER,
    MAX_BRIGHTNESS,
    MAX_MIREDS,
    MAX_RGB_DISTANCE,
    MIN_MIREDS,
    RGB_BRIGHTNESS_SCALE,
    WEIGHT_BRIGHTNESS,
    WEIGHT_COLOR,
)


@dataclass
class LightTarget:
    """Target state for a light in a scene."""

    state: str  # "on" or "off"
    brightness: int | None = None
    color_temp: int | None = None  # in mireds
    rgb_color: tuple[int, int, int] | None = None


class SceneToggleCoordinator:
    """Coordinator that tracks light states and calculates current scene."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.hass = hass
        self.config_entry = config_entry

        # Configuration
        self.scenes: list[str] = list(config_entry.data.get(CONF_SCENES, []))
        self.wrap_around: bool = config_entry.data.get(CONF_WRAP_AROUND, DEFAULT_WRAP_AROUND)

        # Scene data: scene_id -> {light_id -> LightTarget}
        self._scene_targets: dict[str, dict[str, LightTarget]] = {}

        # All lights we need to track
        self._tracked_lights: set[str] = set()

        # Current state
        self._current_scene: str | None = None
        self._current_distance: float = float("inf")
        self._all_distances: dict[str, float] = {}

        # Debounce handling
        self._debounce_cancel: Callable[[], None] | None = None

        # Listeners for state updates
        self._listeners: list[Callable[[], None]] = []

        # State change unsubscribe
        self._unsubscribe_state_change: Callable[[], None] | None = None
        
        # Service call event unsubscribe
        self._unsubscribe_service_call: Callable[[], None] | None = None

    @property
    def current_scene(self) -> str | None:
        """Return the current scene entity ID."""
        return self._current_scene

    @property
    def current_scene_name(self) -> str | None:
        """Return the friendly name of the current scene."""
        if not self._current_scene:
            return None
        state = self.hass.states.get(self._current_scene)
        if state:
            return state.attributes.get(ATTR_FRIENDLY_NAME, self._current_scene)
        return self._current_scene

    @property
    def current_distance(self) -> float:
        """Return the distance score for the current scene."""
        return self._current_distance

    @property
    def all_distances(self) -> dict[str, float]:
        """Return all scene distance scores."""
        return self._all_distances.copy()

    async def async_setup(self) -> None:
        """Set up the coordinator."""
        # Load scene data
        self._load_scene_data()

        if not self._tracked_lights:
            LOGGER.warning("No lights found in configured scenes")
            return

        # Subscribe to light state changes
        self._unsubscribe_state_change = async_track_state_change_event(
            self.hass,
            list(self._tracked_lights),
            self._on_light_state_change,
        )
        
        # Subscribe to service call events to detect scene activations
        self._unsubscribe_service_call = self.hass.bus.async_listen(
            EVENT_CALL_SERVICE,
            self._on_service_call,
        )

        # Calculate initial state
        self._recalculate_current_scene()

    def _load_scene_data(self) -> None:
        """Load scene configurations from Home Assistant."""
        from homeassistant.components.homeassistant.scene import (
            DATA_PLATFORM,
            HomeAssistantScene,
        )

        platform = self.hass.data.get(DATA_PLATFORM)
        if not platform:
            LOGGER.error("Scene platform not available")
            return

        self._scene_targets.clear()
        self._tracked_lights.clear()

        for scene_id in self.scenes:
            # Find the scene entity
            scene_entity = None
            for entity in platform.entities.values():
                if isinstance(entity, HomeAssistantScene) and entity.entity_id == scene_id:
                    scene_entity = entity
                    break

            if not scene_entity:
                LOGGER.warning("Scene %s not found", scene_id)
                continue

            # Extract light targets from scene config
            light_targets: dict[str, LightTarget] = {}
            for entity_id, target in scene_entity.scene_config.states.items():
                if not entity_id.startswith(f"{LIGHT_DOMAIN}."):
                    continue

                light_target = LightTarget(
                    state=target.state,
                    brightness=target.attributes.get(ATTR_BRIGHTNESS),
                    color_temp=target.attributes.get(ATTR_COLOR_TEMP),
                    rgb_color=target.attributes.get(ATTR_RGB_COLOR),
                )
                light_targets[entity_id] = light_target
                self._tracked_lights.add(entity_id)

            self._scene_targets[scene_id] = light_targets

        LOGGER.debug(
            "Loaded %d scenes with %d total lights",
            len(self._scene_targets),
            len(self._tracked_lights),
        )

    @callback
    def _on_light_state_change(self, event: Event) -> None:
        """Handle light state change event."""
        entity_id = event.data.get("entity_id")
        if entity_id not in self._tracked_lights:
            return

        # Cancel existing debounce timer
        if self._debounce_cancel:
            self._debounce_cancel()
            self._debounce_cancel = None

        # Schedule recalculation after debounce period
        self._debounce_cancel = async_call_later(
            self.hass,
            DEFAULT_DEBOUNCE_SECONDS,
            self._debounce_callback,
        )

    @callback
    def _on_service_call(self, event: Event) -> None:
        """Handle service call event to detect scene activations."""
        # Check if this is a scene.turn_on call
        if event.data.get("domain") != "scene":
            return
        if event.data.get("service") not in ("turn_on", "apply"):
            return
        
        # Get the entity_id(s) from service data
        service_data = event.data.get("service_data", {})
        entity_ids = service_data.get(ATTR_ENTITY_ID)
        
        if not entity_ids:
            return
        
        # Normalize to list
        if isinstance(entity_ids, str):
            entity_ids = [entity_ids]
        
        # Check if any of our tracked scenes was activated
        for entity_id in entity_ids:
            if entity_id in self.scenes:
                # Immediately update current scene without waiting for debounce
                LOGGER.debug("Scene %s activated, updating immediately", entity_id)
                
                # Cancel any pending debounce
                if self._debounce_cancel:
                    self._debounce_cancel()
                    self._debounce_cancel = None
                
                # Set the activated scene as current immediately
                self._set_current_scene_immediately(entity_id)
                self._notify_listeners()
                
                # Still schedule a debounced recalculation in case the scene
                # activation doesn't match expectations (e.g., some lights unavailable)
                self._debounce_cancel = async_call_later(
                    self.hass,
                    DEFAULT_DEBOUNCE_SECONDS,
                    self._debounce_callback,
                )
                break

    @callback
    def _debounce_callback(self, _now: Any) -> None:
        """Handle debounce timer completion."""
        self._debounce_cancel = None
        self._recalculate_current_scene()
        self._notify_listeners()
    
    def _set_current_scene_immediately(self, scene_id: str) -> None:
        """Set current scene immediately without full recalculation.
        
        This is used when we know a scene was just activated and want to
        reflect it immediately without waiting for debounce.
        """
        # Set the scene as current with a very low distance (0.0)
        # since we know it was just activated
        self._current_scene = scene_id
        self._current_distance = 0.0
        
        # We don't update all_distances here since we're skipping full calculation
        # The debounced callback will still run and update everything properly
        LOGGER.debug(
            "Immediately set current scene to: %s",
            scene_id,
        )

    def _recalculate_current_scene(self) -> None:
        """Recalculate which scene best matches current light states."""
        if not self._scene_targets:
            self._current_scene = None
            self._current_distance = float("inf")
            self._all_distances = {}
            return

        best_scene: str | None = None
        best_distance = float("inf")
        all_distances: dict[str, float] = {}

        for scene_id, light_targets in self._scene_targets.items():
            distance = self._calculate_scene_distance(light_targets)
            all_distances[scene_id] = distance

            if distance < best_distance:
                best_distance = distance
                best_scene = scene_id

        self._current_scene = best_scene
        self._current_distance = best_distance
        self._all_distances = all_distances

        LOGGER.debug(
            "Current scene: %s (distance: %.4f)",
            self._current_scene,
            self._current_distance,
        )

    def _calculate_scene_distance(self, light_targets: dict[str, LightTarget]) -> float:
        """Calculate total distance between current state and scene targets."""
        if not light_targets:
            return float("inf")

        total_distance = 0.0
        counted_lights = 0

        for light_id, target in light_targets.items():
            state = self.hass.states.get(light_id)
            if not state:
                # Missing entity should not affect distance
                continue
            if state.state == "unavailable":
                # Unavailable entities should have no effect
                continue

            light_distance = self._calculate_light_distance(state, target)
            total_distance += light_distance
            counted_lights += 1

        # Normalize by number of lights
        return total_distance / counted_lights if counted_lights else float("inf")

    def _calculate_light_distance(self, current_state, target: LightTarget) -> float:
        """Calculate distance between current light state and target.
        
        Uses weighted average of brightness and color distances.
        Brightness is weighted more heavily (WEIGHT_BRIGHTNESS vs WEIGHT_COLOR).
        
        RGB mode brightness is scaled down (RGB_BRIGHTNESS_SCALE) to account for
        the fact that RGB LEDs typically produce fewer lumens than white LEDs.
        """
        # Handle on/off state
        current_is_on = current_state.state == STATE_ON
        target_is_on = target.state == STATE_ON

        # Get current values (off = brightness 0)
        if current_is_on:
            current_brightness = current_state.attributes.get(ATTR_BRIGHTNESS, 255)
            current_color_temp = current_state.attributes.get(ATTR_COLOR_TEMP)
            current_rgb = current_state.attributes.get(ATTR_RGB_COLOR)
        else:
            current_brightness = 0
            current_color_temp = None
            current_rgb = None

        # Get target values (off = brightness 0)
        if target_is_on:
            target_brightness = target.brightness if target.brightness is not None else 255
            target_color_temp = target.color_temp
            target_rgb = target.rgb_color
        else:
            target_brightness = 0
            target_color_temp = None
            target_rgb = None

        # Determine color modes for brightness scaling
        current_is_rgb = current_rgb is not None and current_color_temp is None
        target_is_rgb = target_rgb is not None and target_color_temp is None

        # Apply RGB brightness scaling when comparing across color modes
        # RGB mode produces fewer lumens, so we scale down the effective brightness
        effective_current_brightness = current_brightness
        effective_target_brightness = target_brightness
        
        if current_is_rgb and not target_is_rgb and target_is_on:
            # Current is RGB, target is color_temp: scale current brightness down
            effective_current_brightness = current_brightness * RGB_BRIGHTNESS_SCALE
        elif not current_is_rgb and target_is_rgb and current_is_on:
            # Current is color_temp, target is RGB: scale target brightness down
            effective_target_brightness = target_brightness * RGB_BRIGHTNESS_SCALE

        # Calculate weighted distance
        total_weight = 0.0
        weighted_distance = 0.0

        # Brightness distance (always compare, with higher weight)
        brightness_dist = abs(effective_current_brightness - effective_target_brightness) / MAX_BRIGHTNESS
        weighted_distance += brightness_dist * WEIGHT_BRIGHTNESS
        total_weight += WEIGHT_BRIGHTNESS

        # Color comparison (only if both are on and have color info)
        if current_is_on and target_is_on:
            color_dist = self._calculate_color_distance(
                current_color_temp, current_rgb,
                target_color_temp, target_rgb,
            )
            if color_dist is not None:
                weighted_distance += color_dist * WEIGHT_COLOR
                total_weight += WEIGHT_COLOR

        # Return weighted average distance
        return weighted_distance / total_weight if total_weight > 0 else 0.0

    def _calculate_color_distance(
        self,
        current_temp: int | None,
        current_rgb: tuple[int, int, int] | None,
        target_temp: int | None,
        target_rgb: tuple[int, int, int] | None,
    ) -> float | None:
        """Calculate color distance, handling RGB/color_temp conversion."""
        # Case 1: Both have color_temp
        if current_temp is not None and target_temp is not None:
            return self._normalize_mireds_distance(current_temp, target_temp)

        # Case 2: Both have RGB
        if current_rgb is not None and target_rgb is not None:
            return self._normalize_rgb_distance(current_rgb, target_rgb)

        # Case 3: Current has RGB, target has color_temp -> convert RGB to temp
        if current_rgb is not None and target_temp is not None:
            current_temp_approx = self._rgb_to_approximate_mireds(current_rgb)
            if current_temp_approx is not None:
                return self._normalize_mireds_distance(current_temp_approx, target_temp)
            # Saturated color, can't compare meaningfully
            return 0.5  # Moderate penalty

        # Case 4: Current has color_temp, target has RGB -> convert RGB to temp
        if current_temp is not None and target_rgb is not None:
            target_temp_approx = self._rgb_to_approximate_mireds(target_rgb)
            if target_temp_approx is not None:
                return self._normalize_mireds_distance(current_temp, target_temp_approx)
            # Saturated color, can't compare meaningfully
            return 0.5  # Moderate penalty

        # No color info available
        return None

    def _normalize_mireds_distance(self, current: int, target: int) -> float:
        """Calculate normalized distance between two mired values."""
        mireds_range = MAX_MIREDS - MIN_MIREDS
        return abs(current - target) / mireds_range

    def _normalize_rgb_distance(
        self, current: tuple[int, int, int], target: tuple[int, int, int]
    ) -> float:
        """Calculate normalized Euclidean distance in RGB space."""
        r_diff = current[0] - target[0]
        g_diff = current[1] - target[1]
        b_diff = current[2] - target[2]
        distance = math.sqrt(r_diff**2 + g_diff**2 + b_diff**2)
        return distance / MAX_RGB_DISTANCE

    def _rgb_to_approximate_mireds(self, rgb: tuple[int, int, int]) -> int | None:
        """Convert RGB to approximate color temperature in mireds.

        Returns None if the color is too saturated (not a white/warm tone).
        """
        r, g, b = rgb
        total = r + g + b

        if total == 0:
            return None

        # Check if color is saturated (not a white/warm tone)
        # A "white" color has relatively balanced RGB values
        max_val = max(r, g, b)
        min_val = min(r, g, b)
        saturation = (max_val - min_val) / max_val if max_val > 0 else 0

        if saturation > 0.5:
            # Too saturated, not a white tone
            return None

        # Calculate color temperature from blue ratio
        # More blue = cooler (lower mireds), more red = warmer (higher mireds)
        blue_ratio = b / total
        # Map blue_ratio (0.0-0.5) to kelvin (2000K-6500K roughly)
        # blue_ratio near 0.33 is neutral
        kelvin = 1000 + (blue_ratio * 9000)
        kelvin = max(2000, min(6500, kelvin))  # Clamp to reasonable range

        return int(1_000_000 / kelvin)

    async def async_next_scene(self) -> None:
        """Activate the next scene in the list."""
        await self._change_scene(1)

    async def async_previous_scene(self) -> None:
        """Activate the previous scene in the list."""
        await self._change_scene(-1)

    async def _change_scene(self, direction: int) -> None:
        """Change to the next or previous scene."""
        if not self.scenes:
            LOGGER.warning("No scenes configured")
            return

        # Find current scene index
        current_index = 0
        if self._current_scene and self._current_scene in self.scenes:
            current_index = self.scenes.index(self._current_scene)

        # Calculate new index
        new_index = current_index + direction

        if self.wrap_around:
            new_index = new_index % len(self.scenes)
        else:
            # Clamp to bounds
            if new_index < 0:
                new_index = 0
            elif new_index >= len(self.scenes):
                new_index = len(self.scenes) - 1

            # If already at boundary, do nothing
            if new_index == current_index:
                LOGGER.debug("Already at boundary, not changing scene")
                return

        target_scene = self.scenes[new_index]
        LOGGER.info("Activating scene: %s", target_scene)

        await self.hass.services.async_call(
            "scene",
            "turn_on",
            {"entity_id": target_scene},
            blocking=False,
        )

    def add_listener(self, callback_func: Callable[[], None]) -> None:
        """Add a listener for state updates."""
        self._listeners.append(callback_func)

    def remove_listener(self, callback_func: Callable[[], None]) -> None:
        """Remove a listener."""
        if callback_func in self._listeners:
            self._listeners.remove(callback_func)

    @callback
    def _notify_listeners(self) -> None:
        """Notify all listeners of state change."""
        for listener in self._listeners:
            listener()

    async def async_unload(self) -> None:
        """Unload the coordinator."""
        # Cancel debounce timer
        if self._debounce_cancel:
            self._debounce_cancel()
            self._debounce_cancel = None

        # Unsubscribe from state changes
        if self._unsubscribe_state_change:
            self._unsubscribe_state_change()
            self._unsubscribe_state_change = None
        
        # Unsubscribe from service calls
        if self._unsubscribe_service_call:
            self._unsubscribe_service_call()
            self._unsubscribe_service_call = None

        self._listeners.clear()
