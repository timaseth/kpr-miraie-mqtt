<img src="https://raw.githubusercontent.com/hareeshmu/kpr-miraie-mqtt/main/icon.png" alt="KPR MirAIe" width="80">

# KPR MirAIe Local MQTT — Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

Home Assistant custom integration for Panasonic MirAIe smart air conditioners via local MQTT.

![Device Page](https://raw.githubusercontent.com/hareeshmu/kpr-miraie-mqtt/main/images/device-page.png)

## Features

- **Zero YAML** — UI-based setup, auto-discovers all your ACs
- **Full climate control** — temperature, HVAC mode, fan speed
- **Positional swing** — vertical and horizontal vane positions (Auto, 1-5)
- **Extra controls** — Eco, Powerful, Nanoe, Display, Buzzer switches
- **Converti mode** — compressor capacity select (0/50/100%)
- **Diagnostics** — room temperature, WiFi signal, online status
- **Auto token refresh** — no manual re-authentication needed

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant → **Integrations**
2. Click the three dots menu (top right) → **Custom repositories**
3. URL: `https://github.com/hareeshmu/kpr-miraie-mqtt`
4. Category: **Integration** → Click **Add**
5. Search for "KPR MirAIe" and click **Install**
6. Restart Home Assistant

### Manual

1. Download this repository
2. Copy `custom_components/kpr_miraie_mqtt/` to your HA `config/custom_components/` directory
3. Restart Home Assistant

## Setup

### Prerequisites

- Home Assistant with [MQTT integration](https://www.home-assistant.io/integrations/mqtt/) configured and connected to a broker
- A Panasonic MirAIe app account

### Steps

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **KPR MirAIe**

![Search](https://raw.githubusercontent.com/hareeshmu/kpr-miraie-mqtt/main/images/search.png)

3. Enter your MirAIe app credentials (email or mobile number + password)

![Login](https://raw.githubusercontent.com/hareeshmu/kpr-miraie-mqtt/main/images/login.png)

4. All your ACs appear automatically under the integration

![Integration](https://raw.githubusercontent.com/hareeshmu/kpr-miraie-mqtt/main/images/integration.png)

5. View and control your AC devices under **MQTT** integration

![MQTT Devices](https://raw.githubusercontent.com/hareeshmu/kpr-miraie-mqtt/main/images/mqtt-devices.png)

## Entities

Each AC device gets these entities:

| Entity | Type | Description |
|--------|------|-------------|
| Climate | `climate` | Temperature, HVAC mode (cool/heat/auto/dry/fan), fan speed |
| Vertical Swing | `select` | Vane position: Auto, 1 (up) to 5 (down) |
| Horizontal Swing | `select` | Vane position: Auto, 1 (left) to 5 (right) |
| Eco Mode | `switch` | Energy saving mode |
| Powerful Mode | `switch` | Boost cooling/heating |
| Nanoe | `switch` | Air purification |
| Display | `switch` | LED panel on/off |
| Buzzer | `switch` | Beep on/off |
| Converti Mode | `select` | Compressor capacity: 0%, 50%, 100% |
| Room Temperature | `sensor` | Current room temperature |
| WiFi Signal | `sensor` | Signal strength in dBm (diagnostic) |
| Online | `binary_sensor` | Device connectivity (diagnostic) |

## How It Works

The integration bridges MirAIe's cloud MQTT to your local MQTT broker:

1. Logs into MirAIe cloud API with your credentials
2. Discovers your home and all AC devices
3. Connects to MirAIe's cloud MQTT broker
4. Relays device status to your local MQTT broker
5. Forwards control commands from HA through cloud MQTT to your ACs
6. Auto-refreshes the auth token before it expires (~84 days)

Your Home Assistant only communicates with your local MQTT broker — it never talks to the cloud directly.

## Troubleshooting

**Integration not found after install:**
- Restart Home Assistant after installing
- Check that `custom_components/miraie_mqtt/` exists in your HA config directory

**Login fails:**
- Verify your credentials work in the MirAIe mobile app
- Try both email and mobile number formats

**Entities show unavailable:**
- Check that your MQTT broker is running and HA's MQTT integration is connected
- Verify the AC is online in the MirAIe app

**Controls not responding:**
- Check HA logs for `miraie_mqtt` errors
- The AC must be online (check the Online binary sensor)

## License

MIT
