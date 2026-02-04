# Integration Testing

This project uses a Docker-based integration test that runs against a real Home Assistant instance.

## Running Tests

```bash
# Run tests, keep container running for manual inspection
./scripts/integration_test.py

# Run tests, stop container when done
./scripts/integration_test.py --stop
```

## Test Environment

The test environment consists of:

- **Docker Compose** (`docker-compose.yml`) - Runs Home Assistant with the custom component mounted
- **Test config** (`test_config/configuration.yaml`) - Minimal HA config with a template light
- **Scenes** (`test_config/scenes.yaml`) - Test scenes (gitignored, can be modified)

## Adding New Tests

### 1. Add Test Fixtures (if needed)

Edit `test_config/configuration.yaml` to add new entities:

```yaml
# Example: Add a second light
light:
  - platform: template
    lights:
      test_light_2:
        friendly_name: "Test Light 2"
        value_template: "{{ states('input_boolean.test_light_2_state') }}"
        turn_on:
          service: input_boolean.turn_on
          target:
            entity_id: input_boolean.test_light_2_state
        turn_off:
          service: input_boolean.turn_off
          target:
            entity_id: input_boolean.test_light_2_state

input_boolean:
  test_light_2_state:
    name: "Test Light 2 State"
```

Edit `test_config/scenes.yaml` to add scenes:

```yaml
- name: "Both Lights On"
  entities:
    light.test_light:
      state: "on"
    light.test_light_2:
      state: "on"
```

### 2. Add Test Function

In `scripts/integration_test.py`, add a new test function:

```python
def test_my_feature(token: str) -> bool:
    """Test description."""
    print_step("Testing my feature")
    
    # Use ha_api_request() for HA API calls
    status, data = ha_api_request("GET", "/api/states/light.test_light", token)
    
    if status != 200:
        print_fail(f"Failed to get state: {status}")
        return False
    
    # Your test logic here
    print_ok("Test passed")
    return True
```

### 3. Register Test in run_tests()

Add your test to the `run_tests()` function:

```python
def run_tests(token: str) -> bool:
    results = []
    
    # Existing tests...
    results.append(verify_component_manifest())
    results.append(check_component_loaded())
    
    # Your new test
    results.append(test_my_feature(token))
    
    return all(results)
```

## Useful API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/states` | GET | List all entity states |
| `/api/states/{entity_id}` | GET | Get single entity state |
| `/api/services/{domain}/{service}` | POST | Call a service |
| `/api/config/config_entries/flow` | POST | Start config flow |

## Debugging

- View logs: `docker compose logs -f homeassistant`
- Access UI: http://localhost:8123 (user: `test`, password: `testtest123`)
- Stop container: `docker compose down`

On test failure, the last 30 lines of container logs are printed automatically.
