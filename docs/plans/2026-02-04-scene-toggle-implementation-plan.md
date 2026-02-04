# Scene Toggle Implementation Plan

## Phase 1: Foundation

### 1.1 Update constants and manifest

**File: `const.py`**
- Add constants for config keys: `CONF_SCENES`, `CONF_WRAP_AROUND`
- Add defaults: `DEFAULT_DEBOUNCE_MS = 500`, `DEFAULT_WRAP_AROUND = True`
- Add platform list: `PLATFORMS = [Platform.SENSOR, Platform.BUTTON]`

**File: `manifest.json`**
- Add `"config_flow": true`
- Add `"dependencies": ["homeassistant"]` (for scene access)

### 1.2 Create config flow

**File: `config_flow.py`**

Create `SceneToggleConfigFlow` with:
- `async_step_user`: Entry point, redirects to scene selection
- `async_step_select_scenes`: Multi-select scenes from available HA scenes
  - Fetch scenes via `hass.data[DATA_PLATFORM].entities`
  - Use `SelectSelector` with `multiple=True`
- `async_step_options`: Wrap around toggle
- `_async_get_available_scenes()`: Helper to list all HomeAssistantScene entities

Create `SceneToggleOptionsFlow` for editing existing config:
- Allow re-selecting scenes and changing wrap behavior

**Files: `strings.json`, `translations/en.json`**
- Add UI strings for config flow steps

---

## Phase 2: Coordinator

### 2.1 Create the coordinator

**File: `coordinator.py`**

Create `SceneToggleCoordinator`:

```python
class SceneToggleCoordinator:
    def __init__(self, hass, config_entry):
        self.hass = hass
        self.config_entry = config_entry
        self.scenes: list[str] = config_entry.data[CONF_SCENES]
        self.wrap_around: bool = config_entry.data.get(CONF_WRAP_AROUND, True)
        
        self._tracked_lights: set[str] = set()
        self._scene_targets: dict[str, dict[str, LightTarget]] = {}
        self._current_scene: str | None = None
        self._current_distance: float = 0.0
        self._all_distances: dict[str, float] = {}
        self._debounce_cancel: Callable | None = None
        self._listeners: list[Callable] = []
```

Methods to implement:

**`async_setup()`**
- Call `_load_scene_data()` to get light targets from scenes
- Subscribe to light state changes via `async_track_state_change_event`
- Calculate initial current scene

**`_load_scene_data()`**
- Read scene configs from `hass.data[DATA_PLATFORM]`
- Extract light entity IDs and their target states (brightness, color_temp, rgb_color)
- Build `_scene_targets` dict and `_tracked_lights` set

**`_on_light_state_change(event)`**
- Check if changed entity is in `_tracked_lights`
- Cancel existing debounce timer if any
- Schedule new debounce: `async_call_later(hass, 0.5, _recalculate)`

**`_recalculate()`**
- For each scene, calculate total distance
- Find scene with minimum distance
- Update `_current_scene`, `_current_distance`, `_all_distances`
- Notify listeners

**`_calculate_scene_distance(scene_id) -> float`**
- Sum per-light distances for all lights in scene
- Handle missing lights (treat as infinite distance or skip?)

**`_calculate_light_distance(current_state, target) -> float`**
- Implement normalized distance for brightness, color_temp, rgb
- Handle off state as brightness=0
- Implement color space bridging (RGB ↔ color_temp)

**`async_next_scene()`**
- Find current scene index
- Calculate next index (with wrap handling)
- Call `scene.turn_on`

**`async_previous_scene()`**
- Same as next but decrement

**`add_listener(callback)` / `remove_listener(callback)`**
- For sensor to subscribe to updates

**`async_unload()`**
- Cancel debounce timer
- Unsubscribe from state changes

### 2.2 Color utilities

**File: `coordinator.py`** (or separate `color_utils.py` if large)

Helper functions:
- `rgb_to_approximate_mireds(rgb: tuple[int,int,int]) -> int`
- `mireds_to_approximate_rgb(mireds: int) -> tuple[int,int,int]`
- `is_saturated_color(rgb: tuple[int,int,int]) -> bool`
- `normalize_brightness_distance(current: int, target: int) -> float`
- `normalize_mireds_distance(current: int, target: int, min_mireds: int, max_mireds: int) -> float`
- `normalize_rgb_distance(current: tuple, target: tuple) -> float`

---

## Phase 3: Entry Point & Services

### 3.1 Update __init__.py

**File: `__init__.py`**

Replace current setup with config entry based setup:

```python
async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = SceneToggleCoordinator(hass, entry)
    await coordinator.async_setup()
    
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    # Register services (once, check if already registered)
    _register_services(hass)
    
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = hass.data[DOMAIN].pop(entry.entry_id)
    await coordinator.async_unload()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
```

**Service registration:**
- `scene_toggle.next_scene` - Takes target (config entry), calls coordinator
- `scene_toggle.previous_scene` - Same

Remove old `async_setup` function (we're config-entry only now).

---

## Phase 4: Entities

### 4.1 Sensor entity

**File: `sensor.py`**

```python
class CurrentSceneSensor(SensorEntity):
    _attr_has_entity_name = True
    
    def __init__(self, coordinator: SceneToggleCoordinator, entry: ConfigEntry):
        self.coordinator = coordinator
        self._attr_unique_id = f"{entry.entry_id}_current_scene"
        self._attr_name = "Current scene"
        self._attr_device_info = ...  # Link to config entry device
    
    @property
    def native_value(self) -> str | None:
        return self.coordinator.current_scene_name
    
    @property
    def extra_state_attributes(self) -> dict:
        return {
            "scene_entity_id": self.coordinator.current_scene,
            "distance_score": self.coordinator.current_distance,
            "all_scores": self.coordinator.all_distances,
        }
    
    async def async_added_to_hass(self):
        self.coordinator.add_listener(self.async_write_ha_state)
    
    async def async_will_remove_from_hass(self):
        self.coordinator.remove_listener(self.async_write_ha_state)
```

**Platform setup:**
```python
async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([CurrentSceneSensor(coordinator, entry)])
```

### 4.2 Button entities

**File: `button.py`**

Update to use config entry and coordinator:

```python
class SceneToggleButton(ButtonEntity):
    _attr_has_entity_name = True
    
    def __init__(self, coordinator, entry, direction: str):
        self.coordinator = coordinator
        self._direction = direction
        self._attr_unique_id = f"{entry.entry_id}_{direction}_scene"
        self._attr_name = f"{direction.capitalize()} scene"
    
    async def async_press(self):
        if self._direction == "next":
            await self.coordinator.async_next_scene()
        else:
            await self.coordinator.async_previous_scene()
```

**Platform setup:**
```python
async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        SceneToggleButton(coordinator, entry, "next"),
        SceneToggleButton(coordinator, entry, "previous"),
    ])
```

---

## Phase 5: Testing & Polish

### 5.1 Manual testing checklist

- [ ] Config flow: can select scenes and reorder
- [ ] Config flow: wrap around option works
- [ ] Sensor shows correct scene on startup
- [ ] Sensor updates when lights change (with debounce)
- [ ] Next button advances to next scene
- [ ] Previous button goes to previous scene
- [ ] Wrap around works (and respects setting)
- [ ] Manual light adjustment → sensor updates → toggle works correctly
- [ ] Multiple config entries work independently
- [ ] Unloading config entry cleans up properly
- [ ] HA restart preserves config and works

### 5.2 Edge cases to test

- [ ] Scene is deleted from HA after being configured
- [ ] Light entity becomes unavailable
- [ ] All lights are off
- [ ] Single scene in list
- [ ] Scene with mix of RGB and color_temp lights

---

## Implementation Order

1. `const.py` - Add new constants
2. `manifest.json` - Enable config flow
3. `strings.json` + `translations/en.json` - UI strings
4. `config_flow.py` - Full config flow
5. `coordinator.py` - Core logic (biggest piece)
6. `__init__.py` - Entry setup, services
7. `sensor.py` - Current scene sensor
8. `button.py` - Update existing buttons
9. Test and iterate
