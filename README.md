# Scene Toggle for Home Assistant

A custom component that intelligently tracks and cycles through scenes for a group of lights.

## The Problem

You have multiple scenes for a room—"Dim", "Bright", "Movie", "Night"—that gradually adjust brightness and color temperature. You want to cycle through them with a simple button press (physical remote, dashboard button, or automation).

But here's the catch: if you manually adjust a light, traditional scene cycling breaks. You're on "Dim", you tweak the brightness slightly, and now pressing "Next" has no idea where you are in the sequence.

## The Solution

Scene Toggle solves this by continuously tracking which scene best matches the current state of your lights. When you press Next or Previous, it figures out where you are and moves to the logical next scene—even if lights have been manually adjusted.

### How It Works

1. **Configure scenes** - Select which scenes to track and their order
2. **Automatic matching** - The component monitors all lights in those scenes and calculates which scene is the "closest match" based on brightness, color temperature, and RGB values
3. **Smart cycling** - Next/Previous buttons use the matched scene as the starting point

### Example

You have three scenes: Dim (30%), Medium (60%), Bright (100%).

- Lights are at 60% → Sensor shows "Medium"
- Press Next → Activates "Bright"
- Manually dim to 45% → Sensor updates to "Medium" (closest match)
- Press Next → Activates "Bright" (not "Medium" again)

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click the three dots in the top right corner
3. Select "Custom repositories"
4. Add this repository URL: `https://github.com/nikita2206/ha-scene-tracker`
5. Select "Integration" as the category
6. Click "Add"
7. Find "Scene Toggle" in the HACS integrations list and click "Download"
8. Restart Home Assistant
9. Go to Settings → Devices & Services → Add Integration → Scene Toggle
10. Enter a name for this scene group, select your scenes, and set the order

### Manual Installation

1. Copy `custom_components/scene_toggle` to your Home Assistant `config/custom_components/` directory
2. Restart Home Assistant
3. Go to Settings → Devices & Services → Add Integration → Scene Toggle
4. Enter a name for this scene group, select your scenes, and set the order

## Entities Created

For each Scene Toggle instance (where `{name}` is the name you provided during setup):

| Entity | Description |
|--------|-------------|
| `sensor.scene_toggle_{name}_current_scene` | Shows the best-matching scene name |
| `button.scene_toggle_{name}_next_scene` | Activates the next scene in the list |
| `button.scene_toggle_{name}_previous_scene` | Activates the previous scene in the list |

## Configuration Options

- **Name** - A unique name for this scene group (lowercase letters, numbers, and underscores only)
- **Scenes** - Select and order the scenes to track
- **Wrap around** - Whether cycling wraps from last→first and first→last (default: enabled)

## Services

- `scene_toggle.next_scene` - Activate the next scene (for automations)
- `scene_toggle.previous_scene` - Activate the previous scene

## Use Cases

- **Physical remotes** - Map a button to cycle through room scenes
- **Dashboard** - Add Next/Previous buttons for quick scene control
- **Automations** - Cycle scenes based on triggers (time, motion, etc.)
- **Adaptive lighting** - Gradually step through brightness levels throughout the day

## Technical Details

The component calculates a "distance score" for each scene based on:
- Brightness difference (normalized)
- Color temperature difference (in mireds)
- RGB color difference (Euclidean distance)

Off lights are treated as brightness=0. The scene with the lowest total distance across all its lights is considered the current scene.

A 500ms debounce prevents excessive recalculation when multiple lights change simultaneously (e.g., when a scene is activated).
