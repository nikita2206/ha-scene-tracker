"""Constants for the Scene Toggle integration."""

from __future__ import annotations

import logging

DOMAIN = "scene_toggle"

ATTR_DIRECTION = "direction"
DIRECTION_NEXT = "next"
DIRECTION_PREVIOUS = "previous"

SERVICE_TOGGLE_SCENE = "toggle_scene"

LOGGER = logging.getLogger(__name__)
