# SigenEnergy Modbus TCP — Home Assistant Integration

Enable and configure the **Modbus TCP server** built into your SigenEnergy gateway (SigenStor, ECS series) directly from Home Assistant — no phone app required.

---

## How it works

The SigenEnergy mobile app communicates with the gateway over a local **WebSocket** connection on port 8080. This integration reverse-engineers that same protocol to send the exact same "enable Modbus TCP" command the app would.

Once Modbus TCP is enabled, **any** Modbus TCP client (e.g. the popular [SigenEnergy HACS integration](https://github.com/TypQxQ/sigenergy-local-modbus), Node-RED, SolarAssistant, etc.) can connect to your gateway on **port 502** for live energy data.

### Reverse-engineering notes

The Flutter app source (`main.dart.js`) contains:

| Finding | Detail |
|---|---|
| Route `/modbus-tcp-server-enable` | class `A.aQO`, handler `cI8` |
| Route `/modbus-tcp-server-detail` | class `A.bEf`, handler `cIa` |
| Default port | `502` (confirmed in form field initialiser) |
| Parent route | `/general-setting` (alongside CSIP, IEC104, NTR-sync) |

The WebSocket protocol envelope is:

```json
// Outbound (HA → gateway)
{ "msgType": 3, "sn": "<serial>", "token": "<auth_token>",
  "data": { "service": "modbusTcpServer", "modbusEnable": 1, "modbusPort": 502 } }

// Inbound (gateway → HA)
{ "msgType": 4, "code": 0, "msg": "ok", "data": {} }
```

---

## Requirements

- Home Assistant 2024.1 or newer
- SigenEnergy gateway reachable on your local network (same subnet as HA)
- Your gateway's **local IP address**
- The **username and password** used to log into the SigenEnergy app

---

## Installation

### Option A — HACS (recommended)

1. Open HACS → **Integrations** → three-dot menu → **Custom repositories**
2. Add `https://github.com/yourusername/sigenergy-modbus-tcp-ha` as type **Integration**
3. Search for "SigenEnergy Modbus TCP" and install
4. Restart Home Assistant

### Option B — Manual

1. Download or clone this repository
2. Copy the `custom_components/sigenergy_modbus_tcp/` folder into your HA config directory:
   ```
   /config/custom_components/sigenergy_modbus_tcp/
   ```
3. Restart Home Assistant

---

## Setup

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **SigenEnergy Modbus TCP**
3. Fill in the form:

   | Field | Example | Notes |
   |---|---|---|
   | Gateway IP | `192.168.1.150` | Local IP of your gateway |
   | WebSocket Port | `8080` | Default — don't change unless you know otherwise |
   | Username | `admin` | Same as the app login |
   | Password | `••••••••` | Same as the app login |
   | Serial Number | *(leave blank)* | Auto-detected from gateway after login |

4. Click **Submit** — HA will test the connection before saving

---

## Entities created

| Entity | Type | What it does |
|---|---|---|
| `switch.modbus_tcp_server` | Switch | **Enable / disable** the Modbus TCP server |
| `number.modbus_tcp_port` | Number | Set the listening port (default 502, range 1–65535) |
| `sensor.modbus_tcp_status` | Sensor | Shows "Enabled" or "Disabled" (diagnostic) |
| `sensor.modbus_tcp_port` | Sensor | Shows current configured port (diagnostic) |

### Quick-enable automation example

```yaml
automation:
  - alias: "Keep Modbus TCP always enabled"
    trigger:
      - platform: state
        entity_id: switch.modbus_tcp_server
        to: "off"
    action:
      - service: switch.turn_on
        target:
          entity_id: switch.modbus_tcp_server
```

---

## Troubleshooting

### "Cannot connect" during setup

- Confirm the gateway IP is correct and reachable: `ping <gateway_ip>`
- Confirm port 8080 is accessible: `nc -zv <gateway_ip> 8080`
- Make sure your HA instance is on the same network/VLAN as the gateway

### Switch turns on but Modbus TCP still won't connect on port 502

The `msgType` or `service` key in the protocol may differ on your firmware version. Enable **debug logging** to capture raw WebSocket frames:

```yaml
# configuration.yaml
logger:
  logs:
    custom_components.sigenergy_modbus_tcp: debug
```

Then restart HA, flip the switch, and check **Settings → System → Logs**. You'll see lines like:

```
→ WS send: {"msgType": 3, "sn": "...", "token": "...", "data": {...}}
← WS recv: {"msgType": 4, "code": 0, ...}
```

If the gateway returns a non-zero `code`, open an issue and paste the raw frames.

### Authentication fails

- Double-check username/password (these are the **local gateway** credentials, not your cloud account)
- Some firmwares default to `admin` / `admin` — try that if you've never changed it
- Factory reset the gateway credentials if locked out (see your hardware manual)

---

## After enabling Modbus TCP

Install the full SigenEnergy energy monitoring integration:

- **[sigenergy-local-modbus](https://github.com/TypQxQ/sigenergy-local-modbus)** — reads battery SOC, power flows, grid import/export, PV generation, and more via Modbus TCP registers

---

## License

MIT
