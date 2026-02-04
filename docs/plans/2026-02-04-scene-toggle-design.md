# Scene Toggle Integration Design

## Overview

A Home Assistant custom component that tracks which scene best matches the current state of lights, and provides buttons to cycle through scenes in order. When lights are manually adjusted, the component automatically determines the closest matching scene so that subsequent toggles feel natural.

## Use Cases

1. **Physical remotes/buttons** - Cycle through room scenes with a single button press
2. **Dashboard controls** - Quick scene stepping without opening a picker
3. **Automation building block** - Services that automations can call to cycle scenes

## Configuration

### Config Flow Steps

1. **Scene Selection** - Multi-select from all HomeAssistant scenes, with ordering controls
2. **Options** - Toggle for wrap-around behavior (default: enabled)

Each config entry creates one "scene tracker" instance. Users can create multiple for different rooms.

### Stored Configuration

```python
{
    "scenes": ["scene.living_room_dim", "scene.living_room_bright", ...],  # ordered list
    "wrap_around": True
}
```

## Entities

| Entity | Type | Purpose |
|--------|------|---------|
| `sensor.{name}_current_scene` | Sensor | Best-matching scene name. Attributes: `scene_entity_id`, `distance_score`, `all_scores` |
| `button.{name}_next_scene` | Button | Activates next scene in list |
| `button.{name}_previous_scene` | Button | Activates previous scene in list |

## Services

- `scene_toggle.next_scene` - Programmatic next (target: config entry)
- `scene_toggle.previous_scene` - Programmatic previous

## Scene Matching Algorithm

### Light Discovery

On startup, extract all `light.*` entities from configured scenes using:

```python
from homeassistant.components.homeassistant.scene import DATA_PLATFORM, HomeAssistantScene
from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN

platform = hass.data.get(DATA_PLATFORM)
for ent in platform.entities.values():
    if isinstance(ent, HomeAssistantScene):
        for entity_id, target in ent.scene_config.states.items():
            if entity_id.startswith(f"{LIGHT_DOMAIN}."):
                # target.state and target.attributes contain the scene's target values
```

Subscribe to state changes for discovered lights only.

### Distance Calculation

When light states change (after 500ms debounce):

1. For each configured scene, calculate total distance as sum of per-light distances
2. Scene with lowest total distance is the "current" scene

Per-light distance calculation:

- **Off lights**: Treated as brightness=0
- **Brightness**: `|current - target| / 255` (normalized 0-1)
- **Color temp**: `|current - target| / max_mireds_range` (normalized 0-1)
- **RGB**: `sqrt((r1-r2)² + (g1-g2)² + (b1-b2)²) / 441`

### Color Space Bridging

When comparing RGB to color_temp (or vice versa):

1. Convert RGB to approximate color temperature using red/blue ratio:
   - `temp_kelvin ≈ 1000 + (blue_ratio * 9000)` where `blue_ratio = B / (R + G + B)`
   - Convert to mireds: `mireds = 1,000,000 / kelvin`

2. For highly saturated colors (not white/warm tones), fall back to RGB comparison

## Toggle Behavior

1. Get current best-matching scene from sensor
2. Find its index in the ordered list
3. Calculate target index (next or previous)
4. Handle boundaries:
   - **Wrap enabled**: `index % len(scenes)`
   - **Wrap disabled**: Clamp to bounds, no-op at edge
5. Call `scene.turn_on` for target scene
6. Sensor auto-updates after lights settle

## State Flow

```
Light changes → [500ms debounce] → Recalculate distances → Update sensor
                                                              ↑
Button press → Determine next scene → Activate scene → Lights change ─┘
```

## File Structure

```
custom_components/scene_toggle/
├── __init__.py          # Entry point, setup config entries, register services
├── const.py             # Constants, domain, defaults
├── config_flow.py       # Config flow for scene selection + options
├── sensor.py            # Current scene sensor entity
├── button.py            # Next/prev buttons tied to config entry
├── coordinator.py       # Central logic - light tracking, distance calc, debounce
├── manifest.json        # Manifest with config_flow flag
├── strings.json         # UI strings for config flow
└── translations/
    └── en.json          # English translations
```

## Key Classes

| Class | File | Responsibility |
|-------|------|----------------|
| `SceneToggleConfigFlow` | config_flow.py | Multi-step config: scene selection, wrap toggle |
| `SceneToggleCoordinator` | coordinator.py | Subscribes to lights, debounces, calculates distances |
| `CurrentSceneSensor` | sensor.py | Exposes coordinator's current scene state |
| `SceneToggleButton` | button.py | Calls coordinator's next/prev methods |
