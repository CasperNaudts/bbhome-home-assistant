# B&B Home for Home Assistant

Custom Home Assistant integration for legacy B&B Home / Bits & Bites installations that communicate through the TCP socket protocol used by the original Android app.

This integration is intended for systems where the original B&B Home controller is still available on the local network.

[![Validate](https://github.com/CasperNaudts/bbhome-home-assistant/actions/workflows/validate.yml/badge.svg)](https://github.com/CasperNaudts/bbhome-home-assistant/actions/workflows/validate.yml)

## Features

- Local polling over TCP.
- Config flow setup from the Home Assistant UI.
- Light entities for discovered switch, function, and dimmer buttons.
- Climate entities for discovered controllable temperatures.
- Media player entities for discovered audio rooms and sources.
- Optional raw entities for numbered switches, inputs, functions, dimmers, and temperatures.

## Installation With HACS

This repository can be installed as a HACS custom repository. The repository root contains the integration files directly and uses HACS `content_in_root` mode.

1. Open HACS in Home Assistant.
2. Go to `Integrations`.
3. Open the three-dot menu and choose `Custom repositories`.
4. Add this repository URL: `https://github.com/CasperNaudts/bbhome-home-assistant`.
5. Select category `Integration`.
6. Install `B&B Home`.
7. Restart Home Assistant.
8. Go to `Settings > Devices & services > Add integration` and search for `B&B Home`.

## Manual Installation

1. Create `custom_components/bbhome` in your Home Assistant configuration folder.
2. Copy the Python files, `manifest.json`, `strings.json`, and `icon.png` from this repository into `custom_components/bbhome`.
3. Restart Home Assistant.
4. Go to `Settings > Devices & services > Add integration` and search for `B&B Home`.

## Configuration

The setup flow asks for the controller connection details.

| Field | Default | Description |
| --- | --- | --- |
| Host | none | IP address or hostname of the B&B Home controller. |
| Port | `2555` | TCP port used by the controller. |
| Init string | `001` | Login init string used by the original app. |
| Password | blank | Password value. Passworded login is currently not implemented beyond blank-password behavior. |

The setup flow also supports raw entity provisioning. These are useful when the discovered room/button mapping is incomplete or when you want direct access to numbered protocol addresses.

| Field | Entity type | Description |
| --- | --- | --- |
| Raw switch count | `light` | Creates `S 001`, `S 002`, etc. using switch commands and `OUTP` feedback. |
| Raw input count | `binary_sensor` | Creates `I 001`, `I 002`, etc. using `INPU` feedback. |
| Raw function count | `button` | Creates `F 001`, `F 002`, etc. using pulse/function commands. |
| Raw dimmer count | `light` | Creates `D 001`, `D 002`, etc. with brightness support. |
| Raw temperature count | `climate` | Creates `T 001`, `T 002`, etc. using temperature state frames and commands. |

If raw switch or dimmer counts are set, the light platform creates raw numbered entities instead of discovered named room buttons. If raw temperature count is set, the climate platform creates raw numbered temperature entities instead of discovered room thermostat entities.

## Supported Entities

| Platform | Description |
| --- | --- |
| `light` | Discovered room buttons with `S`, `F`, or `D` functions. Dimmer buttons expose brightness. |
| `binary_sensor` | Optional raw input entities. |
| `button` | Optional raw function entities. |
| `climate` | Discovered or raw thermostats with current temperature, target temperature, and mode cycling. |
| `media_player` | Discovered audio rooms with source selection and available power, volume, and mute controls. |

## Known Limitations

- Passworded login has not been implemented because the available test configuration uses a blank password.
- Thermostat mode changes follow the original app behavior and send a mode-cycle command (`SEL`). Home Assistant cannot directly select a specific target mode until the next state update confirms it.
- Audio source selection and media controls use the Android app's audio input mapping: `room_index * 368 + source_index * 46`, plus the button position for controls.
- This is a community integration and is not affiliated with Home Assistant, B&B Home, or Bits & Bites.

## Repository Setup Checklist

Before publishing the repository, verify these values:

- The repository URL is `https://github.com/CasperNaudts/bbhome-home-assistant`.
- The manifest `codeowners` entry is `@CasperNaudts`.
- The copyright holder in `LICENSE` is correct.
- The GitHub repository description is set, for example `Home Assistant integration for B&B Home / Bits & Bites controllers`.
- The GitHub repository topics include `home-assistant`, `hacs`, `integration`, and `bbhome`.

Do not commit local credentials or discovery files. The included `.gitignore` excludes `login.txt`, APK files, Python caches, Home Assistant local storage, and secrets.

## Development

Run the same lightweight checks used by GitHub Actions:

```bash
ruff check --line-length 120 --select E4,E7,E9,F,I .
python -m compileall .
```

The GitHub Actions workflow also runs HACS validation and Home Assistant Hassfest validation on pushes and pull requests.

## License

This project is released under the MIT License. See [`LICENSE`](LICENSE).
