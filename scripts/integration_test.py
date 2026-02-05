#!/usr/bin/env -S uv run --script
"""
Integration test for scene_toggle custom component.

Starts Home Assistant in Docker, verifies the custom component loads successfully,
and tests scene detection with a simple light toggle scenario.

Usage:
    ./scripts/integration_test.py [--stop]

Options:
    --stop    Stop Home Assistant container after testing
"""
# /// script
# requires-python = ">=3.12"
# ///

import argparse
import json
import shutil
import subprocess
import sys
import time
import urllib.parse
from http.client import RemoteDisconnected
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


# =============================================================================
# Configuration
# =============================================================================

BASE_URL = "http://localhost:8123"
PROJECT_ROOT = Path(__file__).parent.parent
TEST_CONFIG_DIR = PROJECT_ROOT / "test_config"
CONTAINER_NAME = "ha-scene-toggle-test"

# Onboarding user credentials
TEST_USER = "test"
TEST_PASSWORD = "testtest123"


# =============================================================================
# Terminal Output
# =============================================================================

class Colors:
    """Terminal color codes for output formatting."""
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    RESET = "\033[0m"
    BOLD = "\033[1m"


def print_ok(msg: str) -> None:
    """Print a success message."""
    print(f"{Colors.GREEN}[✓]{Colors.RESET} {msg}")


def print_fail(msg: str) -> None:
    """Print a failure message."""
    print(f"{Colors.RED}[✗]{Colors.RESET} {msg}")


def print_info(msg: str) -> None:
    """Print an info message."""
    print(f"{Colors.YELLOW}[i]{Colors.RESET} {msg}")


def print_step(msg: str) -> None:
    """Print a step header."""
    print(f"\n{Colors.CYAN}▶{Colors.RESET} {Colors.BOLD}{msg}{Colors.RESET}")


def print_header(msg: str) -> None:
    """Print a section header."""
    print(f"\n{Colors.BOLD}{'='*50}{Colors.RESET}")
    print(f"{Colors.BOLD}  {msg}{Colors.RESET}")
    print(f"{Colors.BOLD}{'='*50}{Colors.RESET}")


# =============================================================================
# HTTP Requests
# =============================================================================

def http_request(
    url: str,
    method: str = "GET",
    data: dict | None = None,
    headers: dict | None = None,
    timeout: int = 10,
) -> tuple[int, dict | str | None]:
    """Make an HTTP request.

    Returns:
        Tuple of (status_code, response_data)
        status_code is 0 if request failed to connect
    """
    headers = headers or {}
    if data:
        headers["Content-Type"] = "application/json"

    body = json.dumps(data).encode() if data else None
    req = Request(url, data=body, headers=headers, method=method)

    try:
        with urlopen(req, timeout=timeout) as resp:
            content = resp.read().decode()
            try:
                return resp.status, json.loads(content)
            except json.JSONDecodeError:
                return resp.status, content
    except HTTPError as e:
        try:
            content = e.read().decode()
            return e.code, json.loads(content) if content else None
        except Exception:
            return e.code, None
    except (URLError, TimeoutError, RemoteDisconnected, ConnectionError, OSError):
        return 0, None


def ha_api_request(
    method: str,
    endpoint: str,
    token: str,
    data: dict | None = None,
) -> tuple[int, dict | str | None]:
    """Make an authenticated API request to Home Assistant."""
    return http_request(
        f"{BASE_URL}{endpoint}",
        method=method,
        data=data,
        headers={"Authorization": f"Bearer {token}"},
    )


# =============================================================================
# Docker / Container Management
# =============================================================================

def docker_compose(*args: str) -> subprocess.CompletedProcess:
    """Run docker compose command."""
    return subprocess.run(
        ["docker", "compose", *args],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )


def get_container_logs(lines: int = 30) -> str:
    """Get the last N lines of container logs."""
    result = subprocess.run(
        ["docker", "logs", "--tail", str(lines), CONTAINER_NAME],
        capture_output=True,
        text=True,
    )
    # Docker logs go to stderr
    return result.stderr or result.stdout


def is_ha_running() -> bool:
    """Check if Home Assistant is responding."""
    status, _ = http_request(BASE_URL, timeout=5)
    return status in (200, 401)


def wait_for_ha(timeout: int = 180) -> bool:
    """Wait for Home Assistant to be ready."""
    print_info(f"Waiting for Home Assistant to start (timeout: {timeout}s)...")
    start = time.time()
    dots = 0
    while time.time() - start < timeout:
        if is_ha_running():
            print()  # newline after dots
            print_ok(f"Home Assistant is running (took {int(time.time() - start)}s)")
            return True
        print(".", end="", flush=True)
        dots += 1
        if dots % 60 == 0:
            print()  # newline every 60 dots
        time.sleep(2)
    print()
    print_fail("Home Assistant failed to start")
    return False


def reset_test_environment() -> None:
    """Reset test environment by removing .storage."""
    print_step("Resetting test environment")

    # Stop HA if running
    if is_ha_running():
        print_info("Stopping Home Assistant...")
        docker_compose("down")

    # Remove .storage directory
    storage_dir = TEST_CONFIG_DIR / ".storage"
    if storage_dir.exists():
        print_info("Removing .storage directory...")
        shutil.rmtree(storage_dir)

    print_ok("Test environment reset")


def start_ha() -> bool:
    """Start Home Assistant using docker compose."""
    print_step("Starting Home Assistant")

    if is_ha_running():
        print_ok("Home Assistant is already running")
        return True

    print_info("Starting container...")
    result = docker_compose("up", "-d")
    if result.returncode != 0:
        print_fail(f"Failed to start: {result.stderr}")
        return False

    return wait_for_ha()


def stop_ha() -> None:
    """Stop Home Assistant container."""
    print_step("Stopping Home Assistant")
    docker_compose("down")
    print_ok("Container stopped")


# =============================================================================
# Onboarding & Authentication
# =============================================================================

def complete_onboarding() -> str | None:
    """Complete the Home Assistant onboarding process.

    Returns the auth code if successful, None otherwise.
    """
    print_step("Completing Home Assistant onboarding")

    # Step 1: Create owner user
    print_info("Creating owner user...")
    status, data = http_request(
        f"{BASE_URL}/api/onboarding/users",
        method="POST",
        data={
            "client_id": BASE_URL,
            "name": TEST_USER,
            "username": TEST_USER,
            "password": TEST_PASSWORD,
            "language": "en",
        },
    )

    if status != 200:
        print_fail(f"Failed to create user: {status} - {data}")
        return None

    auth_code = data.get("auth_code") if isinstance(data, dict) else None
    if not auth_code:
        print_fail("No auth_code in response")
        return None
    print_ok("User created")

    # Step 2: Set core config (minimal)
    print_info("Setting core config...")
    status, _ = http_request(
        f"{BASE_URL}/api/onboarding/core_config",
        method="POST",
        data={},
    )
    if status == 200:
        print_ok("Core config set")

    # Step 3: Set analytics (opt out)
    print_info("Setting analytics preferences...")
    http_request(
        f"{BASE_URL}/api/onboarding/analytics",
        method="POST",
        data={},
    )

    # Step 4: Complete integration step
    print_info("Completing integration step...")
    http_request(
        f"{BASE_URL}/api/onboarding/integration",
        method="POST",
        data={"client_id": BASE_URL, "redirect_uri": f"{BASE_URL}/?auth_callback=1"},
    )

    return auth_code


def exchange_auth_code(auth_code: str) -> str | None:
    """Exchange auth code for access token."""
    print_info("Exchanging auth code for access token...")

    data = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "code": auth_code,
        "client_id": BASE_URL,
    }).encode()

    req = Request(
        f"{BASE_URL}/auth/token",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )

    try:
        with urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode())
            access_token = result.get("access_token")
            if access_token:
                print_ok("Got access token")
                return access_token
    except Exception as e:
        print_fail(f"Token exchange failed: {e}")

    return None


# =============================================================================
# Test Functions
# =============================================================================

def check_component_loaded() -> bool:
    """Check if the scene_toggle component loaded without errors."""
    print_step("Checking component loaded")

    logs = get_container_logs(200)

    # Look for errors related to our component
    has_errors = False
    for line in logs.split("\n"):
        line_lower = line.lower()
        if "error" in line_lower and "scene_toggle" in line_lower:
            print_fail(f"Error found: {line.strip()}")
            has_errors = True
        if "exception" in line_lower and "scene_toggle" in line_lower:
            print_fail(f"Exception found: {line.strip()}")
            has_errors = True
        if "unable to set up" in line_lower and "scene_toggle" in line_lower:
            print_fail(f"Setup failed: {line.strip()}")
            has_errors = True

    if has_errors:
        return False

    # Check that HA detected our custom component
    if "custom integration scene_toggle" in logs:
        print_ok("Custom component scene_toggle detected by Home Assistant")
    elif "scene_toggle" in logs:
        print_ok("Component scene_toggle mentioned in logs")
    else:
        print_info("Component scene_toggle not found in recent logs (may need more time)")

    # Check for successful startup indicators
    if "Home Assistant initialized" in logs or "Waiting for startup" in logs:
        print_ok("Home Assistant initialized")

    return True


def verify_component_manifest() -> bool:
    """Verify the component manifest is valid."""
    print_step("Verifying component manifest")

    manifest_path = PROJECT_ROOT / "custom_components" / "scene_toggle" / "manifest.json"
    if not manifest_path.exists():
        print_fail("manifest.json not found")
        return False

    try:
        with open(manifest_path) as f:
            manifest = json.load(f)

        required_fields = ["domain", "name", "version"]
        for field in required_fields:
            if field not in manifest:
                print_fail(f"Missing required field: {field}")
                return False
            print_ok(f"Has {field}: {manifest[field]}")

        return True
    except json.JSONDecodeError as e:
        print_fail(f"Invalid JSON in manifest: {e}")
        return False


def create_scene_toggle_config_entry(token: str) -> str | None:
    """Create a config entry for scene_toggle via the API.
    
    Returns the entry_id if successful, None otherwise.
    """
    print_step("Creating scene_toggle config entry")

    scene_ids = ["scene.light_on", "scene.light_off"]
    print_info(f"Using scenes: {', '.join(scene_ids)}")

    # Initialize the config flow
    print_info("Starting config flow...")
    status, data = ha_api_request(
        "POST",
        "/api/config/config_entries/flow",
        token,
        data={"handler": "scene_toggle"},
    )

    if status != 200:
        print_fail(f"Failed to start config flow: {status} - {data}")
        return None

    flow_id = data.get("flow_id")
    if not flow_id:
        print_fail("No flow_id in response")
        return None

    print_ok(f"Config flow started: {flow_id}")

    # Submit the form with scene selection
    print_info("Submitting scene selection...")
    status, data = ha_api_request(
        "POST",
        f"/api/config/config_entries/flow/{flow_id}",
        token,
        data={
            "name": "basic_test",
            "scenes": scene_ids,
            "wrap_around": True,
        },
    )

    if status != 200:
        print_fail(f"Failed to submit config flow: {status} - {data}")
        return None

    if data.get("type") == "create_entry":
        entry_id = data.get("result", {}).get("entry_id")
        print_ok(f"Config entry created: {entry_id}")
        return entry_id

    print_fail(f"Unexpected flow result: {data}")
    return None


def create_unavailable_edge_case_config_entry(token: str) -> str | None:
    """Create a config entry for the unavailable entity edge case test."""
    print_step("Creating unavailable edge case config entry")

    scene_ids = ["scene.off_lights", "scene.night"]
    print_info(f"Using scenes: {', '.join(scene_ids)}")

    status, data = ha_api_request(
        "POST",
        "/api/config/config_entries/flow",
        token,
        data={"handler": "scene_toggle"},
    )

    if status != 200:
        print_fail(f"Failed to start config flow: {status} - {data}")
        return None

    flow_id = data.get("flow_id")
    if not flow_id:
        print_fail("No flow_id in response")
        return None

    print_ok(f"Config flow started: {flow_id}")

    status, data = ha_api_request(
        "POST",
        f"/api/config/config_entries/flow/{flow_id}",
        token,
        data={
            "name": "unavailable_edge_case",
            "scenes": scene_ids,
            "wrap_around": True,
        },
    )

    if status != 200:
        print_fail(f"Failed to submit config flow: {status} - {data}")
        return None

    if data.get("type") == "create_entry":
        entry_id = data.get("result", {}).get("entry_id")
        print_ok(f"Config entry created: {entry_id}")
        return entry_id

    print_fail(f"Unexpected flow result: {data}")
    return None


def set_entity_state(token: str, entity_id: str, state: str, attributes: dict | None = None) -> bool:
    """Set an entity state directly via the states API."""
    payload = {"state": state}
    if attributes:
        payload["attributes"] = attributes

    status, _ = ha_api_request("POST", f"/api/states/{entity_id}", token, data=payload)
    if status not in (200, 201):
        print_fail(f"Failed to set state for {entity_id}: {status}")
        return False
    return True


def wait_for_entity(token: str, entity_id: str, timeout: int = 30) -> bool:
    """Wait for an entity to appear in Home Assistant."""
    start = time.time()
    while time.time() - start < timeout:
        status, data = ha_api_request("GET", f"/api/states/{entity_id}", token)
        if status == 200:
            return True
        time.sleep(1)
    return False


def test_scene_detection(token: str) -> bool:
    """Test that scene detection works correctly."""
    print_step("Testing scene detection")

    # Wait for the sensor to appear
    print_info("Waiting for scene_toggle sensor...")
    
    # Find the sensor entity
    status, data = ha_api_request("GET", "/api/states", token)
    if status != 200:
        print_fail(f"Failed to get states: {status}")
        return False

    sensor_entity = None
    for state in data:
        entity_id = state["entity_id"]
        if entity_id.startswith("sensor.") and "current_scene" in entity_id:
            attrs = state.get("attributes", {})
            all_scores = attrs.get("all_scores", {})
            has_basic = "scene.light_on" in all_scores and "scene.light_off" in all_scores
            has_color = "scene.color_test_off" in all_scores
            has_edge = "scene.off_lights" in all_scores
            if has_basic and not has_color and not has_edge:
                sensor_entity = entity_id
                break

    if not sensor_entity:
        print_fail("Scene toggle sensor not found")
        return False

    print_ok(f"Found sensor: {sensor_entity}")

    # Give HA a moment to settle
    time.sleep(2)

    # Test 1: Turn light OFF and verify "Light Off" scene is detected
    print_info("Test 1: Turning light OFF...")
    status, _ = ha_api_request(
        "POST",
        "/api/services/light/turn_off",
        token,
        data={"entity_id": "light.test_light"},
    )
    if status != 200:
        print_fail(f"Failed to turn off light: {status}")
        return False

    # Wait for debounce (0.5s) + some buffer
    time.sleep(1.5)

    # Check sensor state
    status, data = ha_api_request("GET", f"/api/states/{sensor_entity}", token)
    if status != 200:
        print_fail(f"Failed to get sensor state: {status}")
        return False

    current_scene = data.get("state")
    scene_entity_id = data.get("attributes", {}).get("scene_entity_id")
    
    if scene_entity_id == "scene.light_off" or current_scene == "Light Off":
        print_ok(f"Light OFF -> Scene detected: {current_scene} ({scene_entity_id})")
    else:
        print_fail(f"Expected 'Light Off' scene, got: {current_scene} ({scene_entity_id})")
        return False

    # Test 2: Turn light ON and verify "Light On" scene is detected
    print_info("Test 2: Turning light ON...")
    status, _ = ha_api_request(
        "POST",
        "/api/services/light/turn_on",
        token,
        data={"entity_id": "light.test_light"},
    )
    if status != 200:
        print_fail(f"Failed to turn on light: {status}")
        return False

    # Wait for debounce + buffer
    time.sleep(1.5)

    # Check sensor state
    status, data = ha_api_request("GET", f"/api/states/{sensor_entity}", token)
    if status != 200:
        print_fail(f"Failed to get sensor state: {status}")
        return False

    current_scene = data.get("state")
    scene_entity_id = data.get("attributes", {}).get("scene_entity_id")

    if scene_entity_id == "scene.light_on" or current_scene == "Light On":
        print_ok(f"Light ON -> Scene detected: {current_scene} ({scene_entity_id})")
    else:
        print_fail(f"Expected 'Light On' scene, got: {current_scene} ({scene_entity_id})")
        return False

    # Test 3: Turn light OFF again to verify it changes back
    print_info("Test 3: Turning light OFF again...")
    status, _ = ha_api_request(
        "POST",
        "/api/services/light/turn_off",
        token,
        data={"entity_id": "light.test_light"},
    )
    if status != 200:
        print_fail(f"Failed to turn off light: {status}")
        return False

    time.sleep(1.5)

    status, data = ha_api_request("GET", f"/api/states/{sensor_entity}", token)
    if status != 200:
        print_fail(f"Failed to get sensor state: {status}")
        return False

    current_scene = data.get("state")
    scene_entity_id = data.get("attributes", {}).get("scene_entity_id")

    if scene_entity_id == "scene.light_off" or current_scene == "Light Off":
        print_ok(f"Light OFF again -> Scene detected: {current_scene} ({scene_entity_id})")
    else:
        print_fail(f"Expected 'Light Off' scene, got: {current_scene} ({scene_entity_id})")
        return False

    return True


def create_color_mode_config_entry(token: str) -> str | None:
    """Create a config entry for color mode test scenes.
    
    Returns the entry_id if successful, None otherwise.
    """
    print_step("Creating color mode test config entry")

    # Get the color test scenes
    scene_ids = [
        "scene.color_test_off",
        "scene.color_test_two",
        "scene.color_test_three",
        "scene.color_test_four",
    ]
    print_info(f"Using scenes: {', '.join(scene_ids)}")

    # Initialize the config flow
    print_info("Starting config flow...")
    status, data = ha_api_request(
        "POST",
        "/api/config/config_entries/flow",
        token,
        data={"handler": "scene_toggle"},
    )

    if status != 200:
        print_fail(f"Failed to start config flow: {status} - {data}")
        return None

    flow_id = data.get("flow_id")
    if not flow_id:
        print_fail("No flow_id in response")
        return None

    print_ok(f"Config flow started: {flow_id}")

    # Submit the form with scene selection
    print_info("Submitting scene selection...")
    status, data = ha_api_request(
        "POST",
        f"/api/config/config_entries/flow/{flow_id}",
        token,
        data={
            "name": "color_test",
            "scenes": scene_ids,
            "wrap_around": True,
        },
    )

    if status != 200:
        print_fail(f"Failed to submit config flow: {status} - {data}")
        return None

    if data.get("type") == "create_entry":
        entry_id = data.get("result", {}).get("entry_id")
        print_ok(f"Config entry created: {entry_id}")
        return entry_id

    print_fail(f"Unexpected flow result: {data}")
    return None


def test_color_mode_scene_detection(token: str) -> bool:
    """Test scene detection with brightness, RGB, and color_temp modes.
    
    Tests a light (demo ceiling_lights) with four scenes:
    - off: light off
    - two: on, brightness=20, rgb=200,100,80
    - three: on, brightness=20, color_temp=2400K (417 mireds)
    - four: on, brightness=50, color_temp=2700K (370 mireds)
    """
    print_step("Testing color mode scene detection")

    # Wait for entities to settle
    time.sleep(2)

    # Find the sensor entity for color test
    status, data = ha_api_request("GET", "/api/states", token)
    if status != 200:
        print_fail(f"Failed to get states: {status}")
        return False

    # Find the sensor that tracks ONLY our color test scenes (not light_on/light_off)
    sensor_entity = None
    for state in data:
        entity_id = state["entity_id"]
        if entity_id.startswith("sensor.") and "current_scene" in entity_id:
            attrs = state.get("attributes", {})
            all_scores = attrs.get("all_scores", {})
            # Must have color_test scenes and NOT have light_on/light_off scenes
            has_color_test = "scene.color_test_off" in all_scores
            has_basic_test = "scene.light_on" in all_scores or "scene.light_off" in all_scores
            if has_color_test and not has_basic_test:
                sensor_entity = entity_id
                break

    if not sensor_entity:
        print_fail("Color test scene toggle sensor not found")
        # Debug: print all sensors and their scores
        for state in data:
            entity_id = state["entity_id"]
            if entity_id.startswith("sensor.") and "current_scene" in entity_id:
                attrs = state.get("attributes", {})
                all_scores = attrs.get("all_scores", {})
                print_info(f"  Found sensor: {entity_id} with scenes: {list(all_scores.keys())}")
        return False

    print_ok(f"Found sensor: {sensor_entity}")

    # Helper to set light state and check detected scene
    def set_light_and_check(description: str, light_data: dict, expected_scenes: list[str]) -> bool:
        """Set light state and verify detected scene matches one of expected scenes."""
        print_info(f"Test: {description}")

        # Determine service based on state
        if light_data.get("state") == "off":
            # Turn off the light
            status, _ = ha_api_request(
                "POST",
                "/api/services/light/turn_off",
                token,
                data={"entity_id": "light.ceiling_lights"},
            )
        else:
            # Turn on with attributes
            service_data = {"entity_id": "light.ceiling_lights"}
            if "brightness" in light_data:
                service_data["brightness"] = light_data["brightness"]
            if "rgb_color" in light_data:
                service_data["rgb_color"] = light_data["rgb_color"]
            if "color_temp" in light_data:
                service_data["color_temp"] = light_data["color_temp"]

            status, _ = ha_api_request(
                "POST",
                "/api/services/light/turn_on",
                token,
                data=service_data,
            )

        if status != 200:
            print_fail(f"  Failed to set light state: {status}")
            return False

        # Wait for debounce (0.5s) + buffer
        time.sleep(1.5)

        # Check sensor state
        status, data = ha_api_request("GET", f"/api/states/{sensor_entity}", token)
        if status != 200:
            print_fail(f"  Failed to get sensor state: {status}")
            return False

        scene_entity_id = data.get("attributes", {}).get("scene_entity_id")
        current_scene = data.get("state")
        all_scores = data.get("attributes", {}).get("all_scores", {})

        # Print all distances for debugging
        print_info(f"  Detected: {current_scene} ({scene_entity_id})")
        print_info(f"  Distances: {json.dumps({k.split('.')[-1]: round(v, 4) for k, v in all_scores.items()}, indent=None)}")

        if scene_entity_id in expected_scenes:
            print_ok(f"  ✓ Matched expected: {scene_entity_id}")
            return True
        else:
            print_fail(f"  ✗ Expected one of {expected_scenes}, got {scene_entity_id}")
            return False

    results = []

    # Test 1: Light OFF -> should detect "Color Test Off" scene
    results.append(set_light_and_check(
        "Light OFF",
        {"state": "off"},
        ["scene.color_test_off"],
    ))

    # Test 2: on, brightness=5, temp=2700K -> should detect "off" scene
    # (brightness=5 is very far from any "on" scene with brightness 20+)
    results.append(set_light_and_check(
        "ON, brightness=5, color_temp=370 (2700K)",
        {"brightness": 5, "color_temp": 370},
        ["scene.color_test_off"],
    ))

    # Test 3: on, brightness=20, temp=2700K -> closest to which scene?
    # Both scene_two (rgb) and scene_three (temp=2400K) have brightness=20
    # scene_three wins because same color mode (color_temp) avoids cross-mode penalty
    results.append(set_light_and_check(
        "ON, brightness=20, color_temp=370 (2700K)",
        {"brightness": 20, "color_temp": 370},
        ["scene.color_test_two", "scene.color_test_three"],
    ))

    # Test 4: on, brightness=30, rgb=210,120,120 -> two or three
    results.append(set_light_and_check(
        "ON, brightness=30, rgb=[210,120,120]",
        {"brightness": 30, "rgb_color": [210, 120, 120]},
        ["scene.color_test_two", "scene.color_test_three"],
    ))

    # Test 5: on, brightness=100, rgb=200,120,120 -> four
    results.append(set_light_and_check(
        "ON, brightness=100, rgb=[200,120,120]",
        {"brightness": 100, "rgb_color": [200, 120, 120]},
        ["scene.color_test_four"],
    ))

    # Summary
    passed = sum(results)
    total = len(results)
    print_info(f"Color mode tests: {passed}/{total} passed")

    return all(results)


def test_scene_toggle_buttons(token: str) -> bool:
    """Test next/previous scene buttons and wraparound behavior.
    
    Uses the color mode config entry with scenes in order:
    - color_test_off (index 0)
    - color_test_two (index 1)
    - color_test_three (index 2)
    - color_test_four (index 3)
    """
    print_step("Testing scene toggle buttons (next/prev/wraparound)")

    # Find the sensor and button entities for color test
    status, data = ha_api_request("GET", "/api/states", token)
    if status != 200:
        print_fail(f"Failed to get states: {status}")
        return False

    # Find entities for color test config entry
    sensor_entity = None
    next_button = None
    prev_button = None
    
    for state in data:
        entity_id = state["entity_id"]
        # Find sensor that tracks color test scenes (not the basic light_on/light_off ones)
        if entity_id.startswith("sensor.") and "current_scene" in entity_id:
            attrs = state.get("attributes", {})
            all_scores = attrs.get("all_scores", {})
            has_color_test = "scene.color_test_off" in all_scores
            has_basic_test = "scene.light_on" in all_scores
            if has_color_test and not has_basic_test:
                sensor_entity = entity_id
                # Derive button names from sensor name
                base_name = entity_id.replace("sensor.", "").replace("_current_scene", "")
                next_button = f"button.{base_name}_next_scene"
                prev_button = f"button.{base_name}_previous_scene"
                break

    if not sensor_entity:
        print_fail("Color test sensor not found")
        return False

    print_ok(f"Found sensor: {sensor_entity}")
    print_ok(f"Found next button: {next_button}")
    print_ok(f"Found prev button: {prev_button}")

    # Helper to press a button and check the resulting scene
    def press_and_check(button: str, expected_scene: str, description: str) -> bool:
        print_info(f"Test: {description}")
        
        # Press the button
        status, _ = ha_api_request(
            "POST",
            "/api/services/button/press",
            token,
            data={"entity_id": button},
        )
        if status != 200:
            print_fail(f"  Failed to press button: {status}")
            return False

        # Wait for scene to activate and debounce
        time.sleep(2.0)

        # Check sensor state
        status, data = ha_api_request("GET", f"/api/states/{sensor_entity}", token)
        if status != 200:
            print_fail(f"  Failed to get sensor state: {status}")
            return False

        scene_entity_id = data.get("attributes", {}).get("scene_entity_id")
        current_scene = data.get("state")

        if scene_entity_id == expected_scene:
            print_ok(f"  ✓ {current_scene} ({scene_entity_id})")
            return True
        else:
            print_fail(f"  ✗ Expected {expected_scene}, got {scene_entity_id}")
            return False

    # Helper to set light to a known state (off) to start from a known scene
    def reset_to_off():
        print_info("Resetting light to OFF state...")
        ha_api_request(
            "POST",
            "/api/services/light/turn_off",
            token,
            data={"entity_id": "light.ceiling_lights"},
        )
        time.sleep(1.5)

    results = []

    # Start from a known state: light off -> scene.color_test_off
    reset_to_off()

    # Verify we're at color_test_off
    status, data = ha_api_request("GET", f"/api/states/{sensor_entity}", token)
    if data.get("attributes", {}).get("scene_entity_id") != "scene.color_test_off":
        print_fail("Could not reset to color_test_off")
        return False
    print_ok("Starting at: color_test_off (index 0)")

    # Test next button cycling
    # off(0) -> two(1) -> three(2) -> four(3)
    results.append(press_and_check(
        next_button, "scene.color_test_two",
        "Next: off(0) -> two(1)"
    ))
    results.append(press_and_check(
        next_button, "scene.color_test_three",
        "Next: two(1) -> three(2)"
    ))
    results.append(press_and_check(
        next_button, "scene.color_test_four",
        "Next: three(2) -> four(3)"
    ))

    # Test wraparound: four(3) -> off(0)
    results.append(press_and_check(
        next_button, "scene.color_test_off",
        "Next (wraparound): four(3) -> off(0)"
    ))

    # Test previous button cycling
    # off(0) -> four(3) via wraparound
    results.append(press_and_check(
        prev_button, "scene.color_test_four",
        "Prev (wraparound): off(0) -> four(3)"
    ))
    
    # four(3) -> three(2)
    results.append(press_and_check(
        prev_button, "scene.color_test_three",
        "Prev: four(3) -> three(2)"
    ))
    
    # three(2) -> two(1)
    results.append(press_and_check(
        prev_button, "scene.color_test_two",
        "Prev: three(2) -> two(1)"
    ))
    
    # two(1) -> off(0)
    results.append(press_and_check(
        prev_button, "scene.color_test_off",
        "Prev: two(1) -> off(0)"
    ))

    # Summary
    passed = sum(results)
    total = len(results)
    print_info(f"Toggle button tests: {passed}/{total} passed")

    return all(results)


def test_unavailable_entity_edge_case(token: str) -> bool:
    """Reproduce the Night vs Off lights misidentification with unavailable entities."""
    print_step("Testing unavailable entity edge case (Night vs Off lights)")

    status, data = ha_api_request("GET", "/api/states", token)
    if status != 200:
        print_fail(f"Failed to get states: {status}")
        return False

    sensor_entity = None
    for state in data:
        entity_id = state["entity_id"]
        if entity_id.startswith("sensor.") and "current_scene" in entity_id:
            attrs = state.get("attributes", {})
            all_scores = attrs.get("all_scores", {})
            has_edge = "scene.off_lights" in all_scores and "scene.night" in all_scores
            has_other = "scene.light_on" in all_scores or "scene.color_test_off" in all_scores
            if has_edge and not has_other:
                sensor_entity = entity_id
                break

    if not sensor_entity:
        print_fail("Edge case scene toggle sensor not found")
        return False

    print_ok(f"Found sensor: {sensor_entity}")

    # Set current states to mirror the reported scenario.
    ok = True
    ok &= set_entity_state(
        token,
        "light.sphere_lamp",
        "on",
        {"brightness": 125, "rgb_color": [255, 53, 31]},
    )
    ok &= set_entity_state(
        token,
        "light.synthia_lamp",
        "on",
        {"brightness": 156, "color_temp": 500},
    )
    ok &= set_entity_state(token, "light.egg_lamp", "off")
    ok &= set_entity_state(token, "light.gorinych_group", "off")
    ok &= set_entity_state(token, "light.gorinych_1", "unavailable")
    ok &= set_entity_state(token, "light.gorinych_2", "unavailable")
    ok &= set_entity_state(token, "light.gorinych_3", "unavailable")

    if not ok:
        return False

    # Wait for debounce (0.5s) + buffer
    time.sleep(1.5)

    status, data = ha_api_request("GET", f"/api/states/{sensor_entity}", token)
    if status != 200:
        print_fail(f"Failed to get sensor state: {status}")
        return False

    scene_entity_id = data.get("attributes", {}).get("scene_entity_id")
    current_scene = data.get("state")
    all_scores = data.get("attributes", {}).get("all_scores", {})

    print_info(f"Detected: {current_scene} ({scene_entity_id})")
    if all_scores:
        print_info(
            f"Distances: {json.dumps({k.split('.')[-1]: round(v, 4) for k, v in all_scores.items()}, indent=None)}"
        )

    if scene_entity_id == "scene.night":
        print_ok("Night scene detected as current")
        return True

    print_fail(f"Expected scene.night, got {scene_entity_id}")
    return False


def run_tests(token: str) -> bool:
    """Run all integration tests."""
    results = []

    # Test 1: Verify manifest is valid
    results.append(verify_component_manifest())

    # Test 2: Check component loaded without errors
    results.append(check_component_loaded())

    # Test 3: Create config entry
    entry_id = create_scene_toggle_config_entry(token)
    results.append(entry_id is not None)

    if entry_id:
        # Test 4: Test scene detection
        time.sleep(2)  # Give HA time to set up the entities
        results.append(test_scene_detection(token))

    # Test 5: Create color mode config entry and test
    color_entry_id = create_color_mode_config_entry(token)
    results.append(color_entry_id is not None)

    if color_entry_id:
        # Test 6: Test color mode scene detection
        time.sleep(2)  # Give HA time to set up the entities
        results.append(test_color_mode_scene_detection(token))

        # Test 7: Test scene toggle buttons (next/prev/wraparound)
        results.append(test_scene_toggle_buttons(token))

    # Test 8: Create edge case config entry and test unavailable entities
    edge_entry_id = create_unavailable_edge_case_config_entry(token)
    results.append(edge_entry_id is not None)

    if edge_entry_id:
        time.sleep(2)
        results.append(test_unavailable_entity_edge_case(token))

    return all(results)


def print_logs_on_failure() -> None:
    """Print the last 30 lines of container logs."""
    print_step("Container Logs (last 30 lines)")
    print("-" * 50)
    logs = get_container_logs(30)
    print(logs)
    print("-" * 50)


# =============================================================================
# Main Entry Point
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Integration test for scene_toggle component",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  ./scripts/integration_test.py          # Start HA, test, keep running
  ./scripts/integration_test.py --stop   # Same, but stop HA after testing
        """,
    )
    parser.add_argument("--stop", action="store_true", help="Stop HA container after testing")
    args = parser.parse_args()

    print_header("Scene Toggle Integration Test")

    success = False
    try:
        # Always start fresh
        reset_test_environment()

        # Start Home Assistant
        if not start_ha():
            print_logs_on_failure()
            sys.exit(1)

        # Complete onboarding
        auth_code = complete_onboarding()
        if not auth_code:
            print_fail("Onboarding failed")
            print_logs_on_failure()
            sys.exit(1)

        # Get access token
        token = exchange_auth_code(auth_code)
        if not token:
            print_fail("Failed to get access token")
            print_logs_on_failure()
            sys.exit(1)

        # Give HA time to fully initialize
        time.sleep(3)

        # Run tests
        success = run_tests(token)

        # Summary
        print_header("Summary")
        if success:
            print_ok("All tests passed!")
        else:
            print_fail("Some tests failed")
            print_logs_on_failure()

        if not args.stop:
            print()
            print("Container kept running. Useful commands:")
            print(f"  docker compose logs -f homeassistant  # View logs")
            print(f"  docker compose down                   # Stop container")
            print(f"  Open http://localhost:8123 in browser")

    finally:
        if args.stop:
            stop_ha()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
