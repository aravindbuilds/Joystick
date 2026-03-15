# Joystick - Phone Motion Racing Wheel for PC

Use your smartphone browser as a steering wheel + pedals and forward inputs to a virtual controller on your PC.

## Features

- Motion steering from phone tilt (DeviceOrientation gamma)
- Landscape-aware gyro steering (works in portrait and landscape)
- Steering normalization to -1.0 to 1.0 with clamping
- Low-pass filtering and center deadzone for smooth control
- Assetto Corsa drive profile (tighter steering + pedal curves)
- Touch pedals:
  - Left zone = brake
  - Right zone = gas
- Real-time WebSocket input streaming
- Output modes: Virtual Gamepad or Keyboard mapper
- Automatic host detection from page URL and server config endpoint
- Xbox and PlayStation virtual controller profiles
- Watchdog safety reset on connection/input timeout
- Steering calibration button
- Mobile-first neon racing dashboard UI

## Project Structure

- [server.py](server.py): Python host app (HTTP + WebSocket + vgamepad bridge)
- [index.html](index.html): Mobile UI layout
- [style.css](style.css): Dashboard styling
- [app.js](app.js): Motion, touch, networking, and UI logic

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
4. Tap Enable Motion and allow motion sensor permission.
5. If needed, edit IP manually and tap Connect.
6. Hold phone like a steering wheel and tilt left/right.
7. Use pedal zones:
   - Left side touch/drag up for brake
   - Right side touch/drag up for gas
8. Pick profile: Xbox or PlayStation.
  - Xbox: A/B/X/Y + LB/RB layout
  - PS5: Cross/Circle/Square/Triangle + L1/R1 layout
  - Assetto: Shift/handbrake/assist quick actions while keeping gyro steering
9. Pick output mode:
  - Gamepad: virtual controller via vgamepad
  - Keyboard: sends arrow keys (Left/Right/Up/Down) for games like older NFS titles
10. Pick driving profile: Balanced or Assetto Corsa.
11. If center feels off, tap Calibrate Steering.

## Hotspot / Wi-Fi Direct Mode

Use this when phone connects directly to your PC hotspot.

1. Enable Windows Mobile Hotspot on PC.
2. Connect phone to that hotspot.
3. Start [server.py](server.py).
4. Open `http://PC_HOTSPOT_IP:8000` once on phone.
5. App reuses detected host automatically on next launches.

Common hotspot IP on Windows is `192.168.137.1`.

## HTTPS / WSS for iPhone Motion Access

iOS Safari often denies motion sensors on insecure pages. Use HTTPS mode.

1. Create local certificate files in project root:
  - `cert.pem`
  - `key.pem`
2. Restart [server.py](server.py).
3. Open `https://PC_IP:8443` on your phone.
4. Trust the certificate warning for local testing.
5. Tap Enable Motion, then Connect.

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
- LB and RB shoulder buttons

## Data Packet Format

Client sends CSV packets over WebSocket:

- `steering,gas,brake`
- Example: `0.32,0.80,0.00`

Profile switch packet:

- `P:xbox`
- `P:ps`

## Performance Notes

- Uses requestAnimationFrame loop on client for smooth updates
- Sends only changed values to reduce network traffic
- Applies low-pass smoothing and deadzone correction
- Intended for local Wi-Fi use (low-latency LAN)

## Safety Behavior

If no input is received for about 1 second, the server watchdog resets controller state:

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

### Motion permission denied (iPhone/Safari)

- Open the HTTPS URL: `https://PC_IP:8443`
- Ensure Safari setting is ON: Motion & Orientation Access
- Tap Enable Motion only after page fully loads

### Steering is noisy or drifts

- Recalibrate while holding neutral position
- Keep phone away from magnetic interference

## Security Note

This project is intended for trusted local networks only. It does not include authentication or encryption by default.
