# MirAIe MQTT Bridge — Add-on Documentation

## Overview

This add-on runs the MirAIe MQTT bridge directly inside Home Assistant OS,
eliminating the need for a separate Docker container or LXC host. It logs into
the Panasonic MirAIe cloud, auto-discovers all your AC units, and relays their
status and control messages to your local MQTT broker so Home Assistant can
manage them entirely locally at runtime.

```
MirAIe Cloud MQTT <-> [this add-on] <-> Local MQTT Broker <-> HA entities
```

---

## Prerequisites

Before installing this add-on, make sure you have:

- Home Assistant OS or Supervised installation
- **Mosquitto broker** add-on installed and running _(recommended — credentials
  are injected automatically)_, **or** an external MQTT broker you can connect to
- The **KPR MirAIe Local MQTT** custom component installed via HACS
  (see [main README](https://github.com/hareeshmu/kpr-miraie-mqtt))
- A Panasonic MirAIe account (the same login you use in the MirAIe mobile app)

---

## Installation

### Step 1 — Add the custom repository

Click the button below to open your Home Assistant instance and jump straight
to the add-on:

[![Open your Home Assistant instance and show the dashboard of an app.](https://my.home-assistant.io/badges/supervisor_addon.svg)](https://my.home-assistant.io/redirect/supervisor_addon/?addon=miraie-mqtt-bridge&repository_url=https%3A%2F%2Fgithub.com%2Fhareeshmu%2Fkpr-miraie-mqtt)

Or add the repository manually:

1. In Home Assistant go to **Settings → Add-ons → Add-on Store**
2. Click **⋮ (three dots)** in the top-right corner → **Repositories**
3. Paste `https://github.com/hareeshmu/kpr-miraie-mqtt` and click **Add**
4. Close the dialog — the store will reload

### Step 2 — Install the add-on

1. Find **MirAIe MQTT Bridge** in the add-on store (scroll down or search)
2. Click it, then click **Install**
3. Wait for the build to complete (first install takes 3–10 min depending on hardware)

### Step 3 — Configure

Go to the **Configuration** tab of the add-on.

**Minimal setup (using the Mosquitto add-on):**

Leave all `mqtt_*` fields empty. The Supervisor injects the Mosquitto broker
credentials automatically.

```yaml
login_type: email         # or "mobile"
username: your@email.com  # MirAIe app login
password: your_password
cloud_broker: mqtt.miraie.in
cloud_port: 8883
ha_discovery_prefix: homeassistant
mqtt_host: ""
mqtt_port: 1883
mqtt_username: ""
mqtt_password: ""
devices: []
```

> **Mobile login:** set `login_type: mobile` and `username: "+91XXXXXXXXXX"`

> **External broker:** fill in `mqtt_host`, `mqtt_port`, `mqtt_username`,
> `mqtt_password` with your broker details.

### Step 4 — Start the add-on

1. Click **Start**
2. Open the **Log** tab immediately — on the first run the bridge will:
   - Log into the MirAIe cloud
   - Discover all ACs registered to your account
   - Print each device's name and ID
   - Save them to `/data/devices.yaml` (persists across restarts)
   - Begin relaying MQTT messages

### Step 5 — Restart once

After the first successful discovery, **restart the add-on once** from the
**Info** tab. This ensures all MQTT Discovery messages are re-published cleanly
and HA picks up all entities.

### Step 6 — Verify entities

In Home Assistant go to **Settings → Devices & Services → MQTT**. You should
see one device per AC, each with a full set of entities (see list below).

---

## Configuration Reference

| Option | Default | Description |
|---|---|---|
| `login_type` | `email` | `email` or `mobile` |
| `username` | — | MirAIe app email or `+91...` mobile |
| `password` | — | MirAIe app password |
| `cloud_broker` | `mqtt.miraie.in` | MirAIe cloud MQTT host (do not change) |
| `cloud_port` | `8883` | MirAIe cloud MQTT port (do not change) |
| `ha_discovery_prefix` | `homeassistant` | HA MQTT Discovery prefix |
| `mqtt_host` | _(empty)_ | Local broker IP — leave empty to use Mosquitto add-on |
| `mqtt_port` | `1883` | Local broker port |
| `mqtt_username` | _(empty)_ | Local broker username |
| `mqtt_password` | _(empty)_ | Local broker password |
| `devices` | `[]` | Manual device overrides (see below) |

### Manual device overrides

Leave `devices` empty on the first run — devices are auto-discovered and saved.
To rename or override after the first run:

```yaml
devices:
  - device_id: "XXXXXXXXXXXX"
    name: Living Room AC
    slug: kpr_XXXXXXXXXXXX
    space: Living Room
    manufacturer: KPR
    model: Panasonic MirAIe Smart AC
```

---

## Entities Created

Each AC automatically gets the following entities via MQTT Discovery:

| Entity | Type | Description |
|---|---|---|
| `climate.kpr_{id}` | Climate | Main thermostat — temp, HVAC mode, fan speed |
| `sensor.kpr_{id}_room_temp` | Sensor | Current room temperature |
| `sensor.kpr_{id}_rssi` | Sensor | WiFi signal strength (dBm) |
| `binary_sensor.kpr_{id}_online` | Binary sensor | Cloud connectivity |
| `switch.kpr_{id}_eco` | Switch | Clean mode (`acec`) |
| `switch.kpr_{id}_eco_mode` | Switch | Eco mode (`acem`) |
| `switch.kpr_{id}_powerful` | Switch | Powerful / boost mode |
| `switch.kpr_{id}_nanoe` | Switch | Nanoe air purification |
| `switch.kpr_{id}_display` | Switch | LED panel on/off |
| `switch.kpr_{id}_buzzer` | Switch | Beep on command |
| `select.kpr_{id}_v_swing` | Select | Vertical vane position (Auto / 1–5) |
| `select.kpr_{id}_h_swing` | Select | Horizontal vane position (Auto / 1–5) |
| `select.kpr_{id}_converti` | Select | Converti8 capacity (Off / 40–90% / FC / HC) |

---

## MQTT Topics

| Topic | Direction | Description |
|---|---|---|
| `miraie/{deviceId}/status` | Cloud → local | Full AC state JSON (retained) |
| `miraie/{deviceId}/connection` | Cloud → local | Online status JSON (retained) |
| `miraie/{deviceId}/control` | local → Cloud | Command JSON sent from HA |

---

## Troubleshooting

**Add-on fails to start — MQTT connection error**
Ensure the Mosquitto add-on is running, or fill in the `mqtt_host` / `mqtt_port`
/ `mqtt_username` / `mqtt_password` options for your external broker.

**No devices discovered / empty device list**
Open the **Log** tab. Verify your MirAIe credentials work in the MirAIe mobile
app. Check that your ACs appear in the app under the same account.

**Entities appear but show "Unavailable"**
The AC may be offline or the first cloud status message hasn't arrived yet.
Wait 10–30 seconds or toggle the AC in the MirAIe app to trigger a status push.

**Token expiry after ~84 days**
The bridge automatically refreshes the MirAIe token 1 hour before it expires
and reconnects. No manual action is needed.

**Want to rename a device?**
Fill in the `devices` list in the Configuration tab with the desired `name` and
`slug`. Then restart the add-on.

---

## Credits

- **Add-on** developed by [@pranjal-joshi](https://github.com/pranjal-joshi)
- **Integration & bridge** by [@hareeshmu](https://github.com/hareeshmu)
- **Custom Lovelace card**: [kpr-miraie-card](https://github.com/hareeshmu/kpr-miraie-card)

---

## Support

- Issues & discussions: https://github.com/hareeshmu/kpr-miraie-mqtt/issues
- Custom Lovelace card: https://github.com/hareeshmu/kpr-miraie-card
