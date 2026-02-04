"""Constants for the Scene Toggle integration."""

from __future__ import annotations

import logging
from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "scene_toggle"
LOGGER = logging.getLogger(__name__)

# Platforms
PLATFORMS: Final = [Platform.SENSOR, Platform.BUTTON]

# Config keys
CONF_NAME: Final = "name"
CONF_SCENES: Final = "scenes"
CONF_WRAP_AROUND: Final = "wrap_around"

# Defaults
DEFAULT_WRAP_AROUND: Final = True
DEFAULT_DEBOUNCE_SECONDS: Final = 0.5

# Service names
SERVICE_NEXT_SCENE: Final = "next_scene"
SERVICE_PREVIOUS_SCENE: Final = "previous_scene"

# Attributes
ATTR_SCENE_ENTITY_ID: Final = "scene_entity_id"
ATTR_DISTANCE_SCORE: Final = "distance_score"
ATTR_ALL_SCORES: Final = "all_scores"

# Distance calculation constants
MAX_BRIGHTNESS: Final = 255
MAX_RGB_DISTANCE: Final = 441.67  # sqrt(255^2 + 255^2 + 255^2)
MIN_MIREDS: Final = 153  # ~6500K (cool)
MAX_MIREDS: Final = 500  # ~2000K (warm)

# Distance weighting constants (tune these to adjust matching behavior)
# Higher values = more influence on the final distance score
WEIGHT_BRIGHTNESS: Final = 4.0  # Brightness is weighted 4x more than color
WEIGHT_COLOR: Final = 1.0

# RGB mode brightness scaling factor
# RGB LEDs typically produce fewer lumens than white LEDs at the same brightness setting
# This factor scales the effective brightness when comparing RGB vs color_temp modes
# e.g., 0.7 means RGB brightness 100 is treated as equivalent to color_temp brightness 70
RGB_BRIGHTNESS_SCALE: Final = 0.7
