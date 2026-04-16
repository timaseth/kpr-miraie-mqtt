#!/usr/bin/env python3
"""
MirAIe Cloud ↔ Local MQTT Bridge with HA MQTT Discovery.

Single cloud MQTT client bridges all devices to local EMQX.
Publishes HA climate entities via MQTT Discovery.

Usage:
  python3 miraie_bridge.py                  # run bridge + publish discovery
  python3 miraie_bridge.py --discover-only  # publish HA discovery configs only
  python3 miraie_bridge.py --unpublish      # remove all HA entities
  python3 miraie_bridge.py --dry-run        # print discovery payloads
"""

import argparse
import json
import ssl
import time
import threading
import requests
import yaml
import paho.mqtt.client as mqtt

# ── Constants ───────────────────────────────────────────────────────

CLIENT_ID_API = "PBcMcfG19njNCL8AOgvRzIC8AjQa"
USER_AGENT = "okhttp/3.13.1"
SCOPE = "an_14214235325"
LOCAL_TOPIC_PREFIX = "miraie"
TOKEN_REFRESH_MARGIN = 3600  # refresh 1h before expiry

# MirAIe status field mappings
HVAC_MODES = ["off", "cool", "heat", "auto", "dry", "fan_only"]
FAN_MODES = ["auto", "quiet", "low", "medium", "high"]
SWING_MODES = ["off", "1", "2", "3", "4", "5"]

HVAC_MODE_MAP = {
    "off": "off", "cool": "cool", "heat": "heat",
    "auto": "auto", "dry": "dry", "fan_only": "fan",
}
HVAC_MODE_REV = {v: k for k, v in HVAC_MODE_MAP.items()}
HVAC_MODE_REV["fan"] = "fan_only"

FAN_MODE_MAP = {
    "auto": "auto", "quiet": "quiet", "low": "low",
    "medium": "medium", "high": "high",
}

# ── Cloud Auth ──────────────────────────────────────────────────────

class CloudAuth:
    def __init__(self, credentials_file):
        with open(credentials_file) as f:
            creds = json.load(f)
        self.username = creds.get("mobile", creds.get("email", ""))
        self.password = creds["password"]
        self.user_id = None
        self.access_token = None
        self.home_id = None
        self.expires_at = 0

    def login(self):
        data = {
            "clientId": CLIENT_ID_API,
            "password": self.password,
            "scope": SCOPE,
        }
        if "@" in self.username:
            data["email"] = self.username
        else:
            data["mobile"] = self.username

        r = requests.post(
            "https://auth.miraie.in/simplifi/v1/userManagement/login",
            json=data,
            headers={"User-Agent": USER_AGENT},
            timeout=15,
        )
        r.raise_for_status()
        resp = r.json()

        self.user_id = resp["userId"]
        self.access_token = resp["accessToken"]
        self.expires_at = time.time() + resp.get("expiresIn", 86400)
        print(f"[auth] logged in as {self.user_id}, expires in {resp.get('expiresIn', '?')}s")
        return resp

    def get_homes(self):
        r = requests.get(
            "https://app.miraie.in/simplifi/v1/homeManagement/homes",
            headers=self._headers(),
            timeout=15,
        )
        r.raise_for_status()
        homes = r.json()
        if homes:
            self.home_id = homes[0]["homeId"]
            print(f"[auth] home: {homes[0].get('homeName', self.home_id)}")
        return homes

    def get_device_status(self, device_id):
        r = requests.get(
            f"https://app.miraie.in/simplifi/v1/deviceManagement/devices/{device_id}/mobile/status",
            headers=self._headers(),
            timeout=15,
        )
        r.raise_for_status()
        return r.json()

    def ensure_token(self):
        if time.time() > (self.expires_at - TOKEN_REFRESH_MARGIN):
            print("[auth] token expiring, refreshing...")
            self.login()
            return True
        return False

    def _headers(self):
        return {
            "User-Agent": USER_AGENT,
            "Authorization": f"Bearer {self.access_token}",
        }


# ── HA MQTT Discovery ──────────────────────────────────────────────

def build_climate_discovery(dev, prefix, local_prefix):
    """Build HA MQTT Discovery config for a climate entity."""
    device_id = dev["device_id"]
    slug = dev["slug"]
    status_topic = f"{local_prefix}/{device_id}/status"
    control_topic = f"{local_prefix}/{device_id}/control"
    connection_topic = f"{local_prefix}/{device_id}/connection"

    device_block = {
        "identifiers": [f"miraie_{device_id}"],
        "name": dev["name"],
        "manufacturer": dev.get("manufacturer", "KPR"),
        "model": dev.get("model", "Panasonic MirAIe Smart AC"),
    }

    entities = []

    # --- Climate entity ---
    climate_config = {
        "name": None,  # use device name
        "unique_id": f"miraie_{device_id}_climate",
        "object_id": slug,
        "device": device_block,

        # State
        "current_temperature_topic": status_topic,
        "current_temperature_template": "{{ value_json.rmtmp | float }}",

        "temperature_state_topic": status_topic,
        "temperature_state_template": "{{ value_json.actmp | float }}",

        "mode_state_topic": status_topic,
        "mode_state_template": (
            "{% if value_json.ps == 'off' %}off"
            "{% elif value_json.acmd == 'fan' %}fan_only"
            "{% else %}{{ value_json.acmd }}{% endif %}"
        ),

        "fan_mode_state_topic": status_topic,
        "fan_mode_state_template": "{{ value_json.acfs }}",

        "swing_mode_state_topic": status_topic,
        "swing_mode_state_template": (
            "{% if value_json.acvs == 0 %}auto{% else %}{{ value_json.acvs }}{% endif %}"
        ),

        # Commands
        "temperature_command_topic": control_topic,
        "temperature_command_template": (
            '{"actmp":"{{ value }}","ki":0,"cnt":"an","sid":"0"}'
        ),

        "mode_command_topic": control_topic,
        "mode_command_template": (
            '{% if value == "off" %}'
            '{"ps":"off","ki":0,"cnt":"an","sid":"0"}'
            '{% elif value == "fan_only" %}'
            '{"ps":"on","acmd":"fan","ki":0,"cnt":"an","sid":"0"}'
            '{% else %}'
            '{"ps":"on","acmd":"{{ value }}","ki":0,"cnt":"an","sid":"0"}'
            '{% endif %}'
        ),

        "fan_mode_command_topic": control_topic,
        "fan_mode_command_template": (
            '{"acfs":"{{ value }}","ki":0,"cnt":"an","sid":"0"}'
        ),

        "swing_mode_command_topic": control_topic,
        "swing_mode_command_template": (
            '{% if value == "auto" %}'
            '{"acvs":0,"ki":0,"cnt":"an","sid":"0"}'
            '{% else %}'
            '{"acvs":{{ value }},"ki":0,"cnt":"an","sid":"0"}'
            '{% endif %}'
        ),

        # Modes
        "modes": ["off", "cool", "heat", "auto", "dry", "fan_only"],
        "fan_modes": ["auto", "quiet", "low", "medium", "high"],
        "swing_modes": ["auto", "1", "2", "3", "4", "5"],

        # Temp range
        "min_temp": 16,
        "max_temp": 30,
        "temp_step": 0.5,
        "temperature_unit": "C",

        # Availability
        "availability_topic": connection_topic,
        "availability_template": (
            "{% if value_json.onlineStatus == 'true' %}online{% else %}offline{% endif %}"
        ),
    }
    entities.append(("climate", slug, climate_config))

    # --- Room temperature sensor ---
    entities.append(("sensor", f"{slug}_room_temp", {
        "name": "Room Temperature",
        "unique_id": f"miraie_{device_id}_room_temp",
        "object_id": f"{slug}_room_temp",
        "device": device_block,
        "state_topic": status_topic,
        "value_template": "{{ value_json.rmtmp }}",
        "unit_of_measurement": "°C",
        "device_class": "temperature",
        "state_class": "measurement",
    }))

    # --- RSSI sensor ---
    entities.append(("sensor", f"{slug}_rssi", {
        "name": "WiFi Signal",
        "unique_id": f"miraie_{device_id}_rssi",
        "object_id": f"{slug}_rssi",
        "device": device_block,
        "state_topic": status_topic,
        "value_template": "{{ value_json.rssi }}",
        "unit_of_measurement": "dBm",
        "device_class": "signal_strength",
        "state_class": "measurement",
        "entity_category": "diagnostic",
    }))

    # --- Online status binary sensor ---
    entities.append(("binary_sensor", f"{slug}_online", {
        "name": "Online",
        "unique_id": f"miraie_{device_id}_online",
        "object_id": f"{slug}_online",
        "device": device_block,
        "state_topic": connection_topic,
        "value_template": "{{ value_json.onlineStatus }}",
        "payload_on": "true",
        "payload_off": "false",
        "device_class": "connectivity",
        "entity_category": "diagnostic",
    }))

    # --- Eco mode switch ---
    entities.append(("switch", f"{slug}_eco", {
        "name": "Eco Mode",
        "unique_id": f"miraie_{device_id}_eco",
        "object_id": f"{slug}_eco",
        "device": device_block,
        "state_topic": status_topic,
        "value_template": "{{ value_json.acec }}",
        "state_on": "on",
        "state_off": "off",
        "command_topic": control_topic,
        "payload_on": '{"acec":"on","ki":0,"cnt":"an","sid":"0"}',
        "payload_off": '{"acec":"off","ki":0,"cnt":"an","sid":"0"}',
        "icon": "mdi:leaf",
    }))

    # --- Powerful mode switch ---
    entities.append(("switch", f"{slug}_powerful", {
        "name": "Powerful Mode",
        "unique_id": f"miraie_{device_id}_powerful",
        "object_id": f"{slug}_powerful",
        "device": device_block,
        "state_topic": status_topic,
        "value_template": "{{ value_json.acpm }}",
        "state_on": "on",
        "state_off": "off",
        "command_topic": control_topic,
        "payload_on": '{"acpm":"on","ki":0,"cnt":"an","sid":"0"}',
        "payload_off": '{"acpm":"off","ki":0,"cnt":"an","sid":"0"}',
        "icon": "mdi:flash",
    }))

    # --- Nanoe switch ---
    entities.append(("switch", f"{slug}_nanoe", {
        "name": "Nanoe",
        "unique_id": f"miraie_{device_id}_nanoe",
        "object_id": f"{slug}_nanoe",
        "device": device_block,
        "state_topic": status_topic,
        "value_template": "{{ value_json.acng }}",
        "state_on": "on",
        "state_off": "off",
        "command_topic": control_topic,
        "payload_on": '{"acng":"on","ki":0,"cnt":"an","sid":"0"}',
        "payload_off": '{"acng":"off","ki":0,"cnt":"an","sid":"0"}',
        "icon": "mdi:air-purifier",
    }))

    # --- Display switch ---
    entities.append(("switch", f"{slug}_display", {
        "name": "Display",
        "unique_id": f"miraie_{device_id}_display",
        "object_id": f"{slug}_display",
        "device": device_block,
        "state_topic": status_topic,
        "value_template": "{{ value_json.acdc }}",
        "state_on": "on",
        "state_off": "off",
        "command_topic": control_topic,
        "payload_on": '{"acdc":"on","ki":0,"cnt":"an","sid":"0"}',
        "payload_off": '{"acdc":"off","ki":0,"cnt":"an","sid":"0"}',
        "icon": "mdi:monitor",
    }))

    # --- Buzzer switch ---
    entities.append(("switch", f"{slug}_buzzer", {
        "name": "Buzzer",
        "unique_id": f"miraie_{device_id}_buzzer",
        "object_id": f"{slug}_buzzer",
        "device": device_block,
        "state_topic": status_topic,
        "value_template": "{{ value_json.bzr }}",
        "state_on": "on",
        "state_off": "off",
        "command_topic": control_topic,
        "payload_on": '{"bzr":"on","ki":0,"cnt":"an","sid":"0"}',
        "payload_off": '{"bzr":"off","ki":0,"cnt":"an","sid":"0"}',
        "icon": "mdi:volume-high",
    }))

    # --- Vertical swing select ---
    entities.append(("select", f"{slug}_v_swing", {
        "name": "Vertical Swing",
        "unique_id": f"miraie_{device_id}_v_swing",
        "object_id": f"{slug}_v_swing",
        "device": device_block,
        "state_topic": status_topic,
        "value_template": "{% if value_json.acvs == 0 %}Auto{% else %}{{ value_json.acvs }}{% endif %}",
        "command_topic": control_topic,
        "command_template": (
            '{% if value == "Auto" %}'
            '{"acvs":0,"ki":0,"cnt":"an","sid":"0"}'
            '{% else %}'
            '{"acvs":{{ value }},"ki":0,"cnt":"an","sid":"0"}'
            '{% endif %}'
        ),
        "options": ["Auto", "1", "2", "3", "4", "5"],
        "icon": "mdi:arrow-up-down",
    }))

    # --- Horizontal swing select ---
    entities.append(("select", f"{slug}_h_swing", {
        "name": "Horizontal Swing",
        "unique_id": f"miraie_{device_id}_h_swing",
        "object_id": f"{slug}_h_swing",
        "device": device_block,
        "state_topic": status_topic,
        "value_template": "{% if value_json.achs == 0 %}Auto{% else %}{{ value_json.achs }}{% endif %}",
        "command_topic": control_topic,
        "command_template": (
            '{% if value == "Auto" %}'
            '{"achs":0,"ki":0,"cnt":"an","sid":"0"}'
            '{% else %}'
            '{"achs":{{ value }},"ki":0,"cnt":"an","sid":"0"}'
            '{% endif %}'
        ),
        "options": ["Auto", "1", "2", "3", "4", "5"],
        "icon": "mdi:arrow-left-right",
    }))

    # --- Converti mode select ---
    entities.append(("select", f"{slug}_converti", {
        "name": "Converti Mode",
        "unique_id": f"miraie_{device_id}_converti",
        "object_id": f"{slug}_converti",
        "device": device_block,
        "state_topic": status_topic,
        "value_template": "{{ value_json.cnv }}",
        "command_topic": control_topic,
        "command_template": '{"cnv":{{ value }},"ki":0,"cnt":"an","sid":"0"}',
        "options": ["0", "50", "100"],
        "icon": "mdi:percent",
    }))

    return entities


# ── Bridge ──────────────────────────────────────────────────────────

class MirAIeBridge:
    def __init__(self, auth, config):
        self.auth = auth
        self.config = config

        mqtt_cfg = config["mqtt"]
        self.local_host = mqtt_cfg["host"]
        self.local_port = mqtt_cfg["port"]
        self.local_user = mqtt_cfg.get("username", "")
        self.local_pass = mqtt_cfg.get("password", "")

        cloud_cfg = config.get("cloud", {})
        self.cloud_host = cloud_cfg.get("broker", "mqtt.miraie.in")
        self.cloud_port = cloud_cfg.get("port", 8883)

        self.devices = {d["device_id"]: d for d in config["devices"]}
        self.cloud_sub = f"{auth.user_id}/{auth.home_id}/#"

        self.cloud_client = None
        self.local_client = None
        self._token_timer = None

    def start(self):
        self._connect_local()
        self._connect_cloud()
        self._schedule_token_refresh()
        print(f"\n[bridge] running with {len(self.devices)} device(s)")
        print(f"[bridge] local topics: {LOCAL_TOPIC_PREFIX}/{{deviceId}}/status|control|connection")

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n[bridge] shutting down")
            if self._token_timer:
                self._token_timer.cancel()
            self.cloud_client.disconnect()
            self.local_client.disconnect()

    def _connect_cloud(self):
        client = mqtt.Client(client_id=f"miraie-bridge-cloud-{self.auth.user_id[:8]}")
        client.tls_set(tls_version=ssl.PROTOCOL_TLSv1_2)
        client.tls_insecure_set(True)
        client.username_pw_set(self.auth.home_id, self.auth.access_token)
        client.on_connect = self._on_cloud_connect
        client.on_message = self._on_cloud_message
        client.on_disconnect = self._on_cloud_disconnect

        print(f"[cloud] connecting to {self.cloud_host}:{self.cloud_port}...")
        client.connect_async(self.cloud_host, self.cloud_port, 60)
        client.loop_start()
        self.cloud_client = client

    def _connect_local(self):
        client = mqtt.Client(client_id="miraie-bridge-local")
        if self.local_user:
            client.username_pw_set(self.local_user, self.local_pass)
        client.on_connect = self._on_local_connect
        client.on_message = self._on_local_message
        client.on_disconnect = self._on_local_disconnect

        print(f"[local] connecting to {self.local_host}:{self.local_port}...")
        client.connect(self.local_host, self.local_port, 60)
        client.loop_start()
        self.local_client = client

    def _schedule_token_refresh(self):
        """Refresh token before expiry and reconnect cloud client."""
        wait = max(self.auth.expires_at - time.time() - TOKEN_REFRESH_MARGIN, 60)
        self._token_timer = threading.Timer(wait, self._refresh_token)
        self._token_timer.daemon = True
        self._token_timer.start()
        print(f"[auth] token refresh scheduled in {int(wait)}s")

    def _refresh_token(self):
        try:
            self.auth.login()
            self.cloud_client.username_pw_set(self.auth.home_id, self.auth.access_token)
            self.cloud_client.reconnect()
            print("[auth] token refreshed, cloud reconnected")
        except Exception as e:
            print(f"[auth] refresh failed: {e}, retrying in 60s")
        self._schedule_token_refresh()

    # ── Cloud callbacks ──

    def _on_cloud_connect(self, client, userdata, flags, rc):
        if rc != 0:
            print(f"[cloud] connection failed: rc={rc}")
            return
        print(f"[cloud] connected, subscribing to {self.cloud_sub}")
        client.subscribe(self.cloud_sub)

    def _on_cloud_message(self, client, userdata, msg):
        topic = msg.topic
        payload = msg.payload.decode(errors="replace")
        parts = topic.split("/")

        # Topic format: userId/homeId/deviceId/type
        if len(parts) < 4:
            return

        device_id = parts[2]
        msg_type = "/".join(parts[3:])

        # Only bridge known devices
        if device_id not in self.devices:
            return

        # Don't bridge control messages back from cloud (prevents loop)
        if msg_type == "control":
            return

        local_topic = f"{LOCAL_TOPIC_PREFIX}/{device_id}/{msg_type}"
        self.local_client.publish(local_topic, payload, retain=True)

        # Log status updates with key fields
        if msg_type == "status":
            try:
                d = json.loads(payload)
                dev_name = self.devices[device_id].get("name", device_id)
                print(f"[cloud→local] {dev_name}: ps={d.get('ps')} acmd={d.get('acmd')} actmp={d.get('actmp')} acfs={d.get('acfs')} acvs={d.get('acvs')} achs={d.get('achs')}")
            except Exception:
                pass

    def _on_cloud_disconnect(self, client, userdata, rc):
        if rc != 0:
            print(f"[cloud] disconnected (rc={rc}), auto-reconnecting...")

    # ── Local callbacks ──

    def _on_local_connect(self, client, userdata, flags, rc):
        if rc != 0:
            print(f"[local] connection failed: rc={rc}")
            return
        print("[local] connected")
        # Subscribe to control topics for all devices
        for device_id in self.devices:
            topic = f"{LOCAL_TOPIC_PREFIX}/{device_id}/control"
            client.subscribe(topic)
            print(f"[local] subscribed: {topic}")

    def _on_local_message(self, client, userdata, msg):
        if not self.cloud_client or not self.cloud_client.is_connected():
            return

        # Extract device_id from topic: miraie/{deviceId}/control
        parts = msg.topic.split("/")
        if len(parts) < 3:
            return
        device_id = parts[1]

        if device_id not in self.devices:
            return

        payload = msg.payload.decode(errors="replace")
        cloud_topic = f"{self.auth.user_id}/{self.auth.home_id}/{device_id}/control"
        self.cloud_client.publish(cloud_topic, payload)
        dev_name = self.devices[device_id].get("name", device_id)
        print(f"[local→cloud] {dev_name}: {payload[:150]}")

    def _on_local_disconnect(self, client, userdata, rc):
        if rc != 0:
            print(f"[local] disconnected (rc={rc}), auto-reconnecting...")


# ── Discovery Publisher ─────────────────────────────────────────────

def publish_discovery(config, dry_run=False, unpublish=False):
    """Publish HA MQTT Discovery configs for all devices."""
    mqtt_cfg = config["mqtt"]
    prefix = config.get("ha_discovery_prefix", "homeassistant")

    if not dry_run:
        client = mqtt.Client(client_id="miraie-discovery")
        if mqtt_cfg.get("username"):
            client.username_pw_set(mqtt_cfg["username"], mqtt_cfg.get("password", ""))
        client.connect(mqtt_cfg["host"], mqtt_cfg["port"], 60)
        client.loop_start()
        time.sleep(1)

    for dev in config["devices"]:
        entities = build_climate_discovery(dev, prefix, LOCAL_TOPIC_PREFIX)
        print(f"\n[discovery] {dev['name']} — {len(entities)} entities")

        for component, object_id, entity_config in entities:
            topic = f"{prefix}/{component}/{object_id}/config"
            if unpublish:
                payload = ""
            else:
                payload = json.dumps(entity_config)

            if dry_run:
                print(f"  {topic}")
                print(f"    {payload[:300]}")
            else:
                client.publish(topic, payload, retain=True, qos=1)
                action = "unpublished" if unpublish else "published"
                print(f"  {action}: {topic}")

    if not dry_run:
        time.sleep(1)
        client.disconnect()

    action = "Unpublished" if unpublish else "Published"
    print(f"\n[discovery] {action} all entities")


# ── Main ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="MirAIe MQTT Bridge for Home Assistant")
    parser.add_argument("--config", default="devices.yaml", help="Device config file")
    parser.add_argument("--credentials", default="credentials.json", help="Cloud credentials")
    parser.add_argument("--discover-only", action="store_true", help="Publish HA discovery only")
    parser.add_argument("--unpublish", action="store_true", help="Remove all HA entities")
    parser.add_argument("--dry-run", action="store_true", help="Print discovery payloads")
    args = parser.parse_args()

    with open(args.config) as f:
        config = yaml.safe_load(f)

    # Discovery-only modes don't need cloud auth
    if args.discover_only or args.unpublish or args.dry_run:
        publish_discovery(config, dry_run=args.dry_run, unpublish=args.unpublish)
        return

    # Full bridge mode
    auth = CloudAuth(args.credentials)
    auth.login()
    homes = auth.get_homes()

    # Auto-discover and populate devices if none configured
    if not config.get("devices"):
        print("\n[discovery] No devices in devices.yaml — discovering...")
        discovered = []
        for home in homes:
            for space in home.get("spaces", []):
                for dev in space.get("devices", []):
                    device_id = dev.get("deviceId", "")
                    name = dev.get("deviceName", "AC")
                    space_name = space.get("spaceName", "")
                    discovered.append({
                        "name": name,
                        "slug": f"kpr_{device_id}",
                        "space": space_name,
                        "device_id": device_id,
                        "manufacturer": "KPR",
                        "model": "Panasonic MirAIe Smart AC",
                    })
                    print(f"  Found: {name} ({device_id}) in {space_name}")

        if discovered:
            config["devices"] = discovered
            with open(args.config, "w") as f:
                yaml.dump(config, f, default_flow_style=False, sort_keys=False)
            print(f"\n[discovery] Saved {len(discovered)} device(s) to {args.config}")
            print("[discovery] Restarting bridge with discovered devices...\n")
        else:
            print("[discovery] No devices found in your MirAIe home.")
            return

    # Print device status
    for dev in config["devices"]:
        try:
            status = auth.get_device_status(dev["device_id"])
            ps = status.get("ps", "?")
            temp = status.get("actmp", "?")
            room = status.get("rmtmp", "?")
            mode = status.get("acmd", "?")
            online = status.get("onlineStatus", "?")
            print(f"  {dev['name']}: power={ps} mode={mode} set={temp} room={room} online={online}")
        except Exception as e:
            print(f"  {dev['name']}: {e}")

    # HA component handles MQTT Discovery — bridge only relays.
    # To publish discovery manually, use: --discover-only

    # Start bridge
    bridge = MirAIeBridge(auth, config)
    bridge.start()


if __name__ == "__main__":
    main()
