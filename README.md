# Joystick - Phone Joystick Pad for PC

Use your smartphone browser as a dual-stick joystick pad with face buttons and send inputs to a virtual controller on your PC.

## Features

- Left virtual stick for steering (X axis)
- Right virtual stick for throttle and brake (Y axis)
- Gamepad-style face buttons and shoulder buttons
- Full Xbox-style action set (face, shoulders, triggers, start/back, stick clicks, d-pad)
- Assetto Corsa drive profile curves
- Real-time WebSocket input streaming
- Output modes: Virtual Gamepad or Keyboard mapper
- Automatic host detection from page URL and server config endpoint
- Xbox and PlayStation virtual controller profiles
- Multi-joystick sessions (up to 4 simultaneous phone clients)
- Watchdog safety reset on connection/input timeout
- Mobile-first joystick dashboard UI

## Project Structure

- [server.py](server.py): Python host app (HTTP + WebSocket + vgamepad bridge)
- [index.html](index.html): Mobile UI layout
- [style.css](style.css): Dashboard styling
- [app.js](app.js): Virtual stick, button, networking, and UI logic

## Requirements

- Windows PC (recommended for virtual gamepad support)
- Python 3.10+
- Smartphone connected to the same local network as the PC
- ViGEmBus driver (required by vgamepad for virtual controller output)

## Install

```bash
python -m pip install -r requirements.txt
```

## Run

```bash
python server.py
```

On startup the server logs your local IP and ports:

- HTTP app: port 8000
- WebSocket: port 5005

If `cert.pem` and `key.pem` exist in the project root, it also starts:

- HTTPS app: port 8443
- Secure WebSocket: port 5443

Open on phone:

- `http://PC_IP:8000`

Example:

- `http://192.168.1.10:8000`

## How to Use

1. Start [server.py](server.py) on your PC.
2. Open the HTTP URL on your phone.
3. Host IP auto-fills and app auto-attempts connect.
4. If needed, edit IP manually and tap Connect.
5. Use left stick for steering.
6. Use right stick vertically:
  - Up for gas
  - Down for brake
7. Pick profile: Xbox, PlayStation, or Assetto.
  - Xbox: A/B/X/Y + LB/RB layout
  - PS5: Cross/Circle/Square/Triangle + L1/R1 layout
  - Assetto: Shift/handbrake/assist quick actions
8. Pick output mode:
  - Gamepad: virtual controller via vgamepad
  - Keyboard: sends arrow keys (Left/Right/Up/Down) for games like older NFS titles
9. Pick driving profile: Balanced or Assetto Corsa.

## Hotspot / Wi-Fi Direct Mode

Use this when phone connects directly to your PC hotspot.

1. Enable Windows Mobile Hotspot on PC.
2. Connect phone to that hotspot.
3. Start [server.py](server.py).
4. Open `http://PC_HOTSPOT_IP:8000` once on phone.
5. App reuses detected host automatically on next launches.

Common hotspot IP on Windows is `192.168.137.1`.

## HTTPS / WSS Access

Use HTTPS mode when you want encrypted local-network traffic.

1. Create local certificate files in project root:
  - `cert.pem`
  - `key.pem`
2. Restart [server.py](server.py).
3. Open `https://PC_IP:8443` on your phone.
4. Trust the certificate warning for local testing.
5. Connect from the app as usual.

The app automatically switches to secure WebSocket (`wss://`) when opened over HTTPS.

### Generate Local Certs (Automated)

No OpenSSL required. The script auto-falls back to Python generation and installs required package automatically.

One command (recommended):

```powershell
powershell -ExecutionPolicy Bypass -File .\generate-certs.ps1
```

Manual OpenSSL command:

```bash
openssl req -x509 -newkey rsa:2048 -sha256 -days 365 -nodes -keyout key.pem -out cert.pem -subj "/CN=JoystickLocal"
```

Then restart [server.py](server.py).

## Input Mapping

- Steering -> Left joystick X axis
- Gas -> Right trigger
- Brake -> Left trigger

Keyboard mapper mode:

- Steering left -> Left Arrow
- Steering right -> Right Arrow
- Gas -> Up Arrow
- Brake -> Down Arrow

Controller action buttons in app:

- South / East / West / North face buttons
- LB1 / RB1 shoulder buttons
- LB2 / RB2 trigger buttons
- Back and Start
- Left-stick click and Right-stick click
- D-pad Up / Down / Left / Right

Each connected phone gets its own virtual controller slot automatically (up to 4 active at the same time).

## Data Packet Format

Client sends CSV packets over WebSocket:

- `steering,gas,brake`
- Example: `0.32,0.80,0.00`

Profile switch packet:

- `P:xbox`
- `P:ps`

## Performance Notes

- Sends only changed values to reduce network traffic
- Applies deadzone and curve shaping for smoother stick feel
- Intended for local Wi-Fi use (low-latency LAN)

## Safety Behavior

If no input is received for about 10 seconds, the server watchdog resets controller state:

- Steering centered
- Gas released
- Brake released

## Troubleshooting

### Import errors for websockets or vgamepad

Install dependencies again:

```bash
python -m pip install -r requirements.txt
```

### Connected but no controller appears in game

- Ensure ViGEmBus is installed properly.
- Restart [server.py](server.py).
- Test with Xbox profile first.
- Try Output Mode = Keyboard for games that do not detect virtual gamepads.
- Run both [server.py](server.py) and the game with same privilege level (both normal user or both admin).

### Phone cannot connect

- Verify phone and PC are on same Wi-Fi
- Confirm Windows firewall allows Python on ports 8000 and 5005
- Use PC LAN IP, not `localhost`
- In hotspot mode, try `192.168.137.1`

### Sticks or buttons feel unresponsive

- Ensure you are touching inside the stick pads or button circles
- Reconnect from the app if packets seem delayed
- Keep phone and PC on the same Wi-Fi band when possible

## Security Note

This project is intended for trusted local networks only. It does not include authentication or encryption by default.
