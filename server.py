import asyncio
import ctypes
import json
import logging
import mimetypes
import socket
import ssl
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import websockets

try:
	import vgamepad as vg
except Exception:  # pragma: no cover - graceful fallback when vgamepad is unavailable
	vg = None


HOST = "0.0.0.0"
HTTP_PORT = 8000
WS_PORT = 5005
HTTPS_PORT = 8443
WSS_PORT = 5443
WATCHDOG_TIMEOUT_S = 1.0

BUTTON_SOUTH = 1
BUTTON_EAST = 2
BUTTON_WEST = 4
BUTTON_NORTH = 8
BUTTON_LB = 16
BUTTON_RB = 32

PROJECT_ROOT = Path(__file__).resolve().parent
INDEX_FILE = PROJECT_ROOT / "index.html"
CERT_FILE = PROJECT_ROOT / "cert.pem"
KEY_FILE = PROJECT_ROOT / "key.pem"


def get_local_ip() -> str:
	"""Best-effort LAN IP detection for startup logs."""
	sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
	try:
		sock.connect(("8.8.8.8", 80))
		return sock.getsockname()[0]
	except OSError:
		return "127.0.0.1"
	finally:
		sock.close()


def clamp(value: float, low: float, high: float) -> float:
	return max(low, min(high, value))


def build_tls_context() -> Optional[ssl.SSLContext]:
	"""Enable TLS when local cert files are present."""
	if not CERT_FILE.exists() or not KEY_FILE.exists():
		return None

	context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
	context.load_cert_chain(certfile=str(CERT_FILE), keyfile=str(KEY_FILE))
	return context


class NullGamepad:
	"""No-op gamepad so UI and networking can be tested without ViGEm drivers."""

	def __init__(self, profile_name: str) -> None:
		self.profile_name = profile_name

	def left_joystick_float(self, x_value_float: float, y_value_float: float) -> None:
		_ = (x_value_float, y_value_float)

	def left_trigger_float(self, value_float: float) -> None:
		_ = value_float

	def right_trigger_float(self, value_float: float) -> None:
		_ = value_float

	def update(self) -> None:
		return

	def reset(self) -> None:
		return

	def press_button(self, button) -> None:
		_ = button

	def release_button(self, button) -> None:
		_ = button


class GamepadBridge:
	def __init__(self) -> None:
		self.profile = "xbox"
		self.gamepad = self._create_gamepad(self.profile)
		self.logical_pressed = {
			"south": False,
			"east": False,
			"west": False,
			"north": False,
			"lb": False,
			"rb": False,
		}

	def _create_gamepad(self, profile: str):
		if vg is None:
			logging.warning("vgamepad not found. Running in no-op mode.")
			return NullGamepad(profile)

		if profile in ("ps", "ps5"):
			logging.info("Using VDS4Gamepad profile")
			return vg.VDS4Gamepad()

		logging.info("Using VX360Gamepad profile")
		return vg.VX360Gamepad()

	def switch_profile(self, profile: str) -> None:
		if profile.lower().startswith("ps"):
			normalized = "ps5"
		elif profile.lower().startswith("ase"):
			normalized = "assetto"
		else:
			normalized = "xbox"
		if normalized == self.profile:
			return

		try:
			self.reset()
		except Exception:
			pass

		self.profile = normalized
		self.gamepad = self._create_gamepad(self.profile)
		logging.info("Controller profile switched to %s", self.profile)

	def apply(self, steering: float, gas: float, brake: float) -> None:
		steering = clamp(steering, -1.0, 1.0)
		gas = clamp(gas, 0.0, 1.0)
		brake = clamp(brake, 0.0, 1.0)

		self.gamepad.left_joystick_float(x_value_float=steering, y_value_float=0.0)
		self.gamepad.right_trigger_float(value_float=gas)
		self.gamepad.left_trigger_float(value_float=brake)
		self.gamepad.update()

	def _resolve_button_enum(self, logical_button: str):
		if vg is None:
			return None

		if self.profile == "ps5":
			enum_obj = getattr(vg, "DS4_BUTTONS", None)
			candidates = {
				"south": ["DS4_BUTTON_CROSS"],
				"east": ["DS4_BUTTON_CIRCLE"],
				"west": ["DS4_BUTTON_SQUARE"],
				"north": ["DS4_BUTTON_TRIANGLE"],
				"lb": ["DS4_BUTTON_SHOULDER_LEFT"],
				"rb": ["DS4_BUTTON_SHOULDER_RIGHT"],
			}
		else:
			enum_obj = getattr(vg, "XUSB_BUTTON", None)
			candidates = {
				"south": ["XUSB_GAMEPAD_A"],
				"east": ["XUSB_GAMEPAD_B"],
				"west": ["XUSB_GAMEPAD_X"],
				"north": ["XUSB_GAMEPAD_Y"],
				"lb": ["XUSB_GAMEPAD_LEFT_SHOULDER"],
				"rb": ["XUSB_GAMEPAD_RIGHT_SHOULDER"],
			}

		if enum_obj is None:
			return None

		for candidate in candidates.get(logical_button, []):
			value = getattr(enum_obj, candidate, None)
			if value is not None:
				return value
		return None

	def _set_logical_button(self, logical_button: str, should_press: bool) -> None:
		if self.logical_pressed.get(logical_button) == should_press:
			return

		button = self._resolve_button_enum(logical_button)
		if button is None:
			return

		if should_press:
			self.gamepad.press_button(button=button)
		else:
			self.gamepad.release_button(button=button)
		self.logical_pressed[logical_button] = should_press

	def apply_buttons(self, button_mask: int) -> None:
		mask = int(button_mask)
		self._set_logical_button("south", (mask & BUTTON_SOUTH) != 0)
		self._set_logical_button("east", (mask & BUTTON_EAST) != 0)
		self._set_logical_button("west", (mask & BUTTON_WEST) != 0)
		self._set_logical_button("north", (mask & BUTTON_NORTH) != 0)
		self._set_logical_button("lb", (mask & BUTTON_LB) != 0)
		self._set_logical_button("rb", (mask & BUTTON_RB) != 0)
		self.gamepad.update()

	def reset(self) -> None:
		self.gamepad.left_joystick_float(x_value_float=0.0, y_value_float=0.0)
		self.gamepad.right_trigger_float(value_float=0.0)
		self.gamepad.left_trigger_float(value_float=0.0)
		self.apply_buttons(0)
		self.gamepad.update()


class KeyboardBridge:
	"""Maps steering/pedals to arrow keys for games that use keyboard input."""

	VK_LEFT = 0x25
	VK_UP = 0x26
	VK_RIGHT = 0x27
	VK_DOWN = 0x28
	KEYEVENTF_KEYUP = 0x0002

	def __init__(self) -> None:
		self.user32 = ctypes.WinDLL("user32", use_last_error=True)
		self.pressed = {
			"left": False,
			"right": False,
			"up": False,
			"down": False,
		}
		self.steer_threshold = 0.20
		self.pedal_threshold = 0.05

	def _set_key(self, name: str, vk: int, should_press: bool) -> None:
		if self.pressed[name] == should_press:
			return

		flags = 0 if should_press else self.KEYEVENTF_KEYUP
		self.user32.keybd_event(vk, 0, flags, 0)
		self.pressed[name] = should_press

	def apply(self, steering: float, gas: float, brake: float) -> None:
		steering = clamp(steering, -1.0, 1.0)
		gas = clamp(gas, 0.0, 1.0)
		brake = clamp(brake, 0.0, 1.0)

		left = steering < -self.steer_threshold
		right = steering > self.steer_threshold
		up = gas > self.pedal_threshold
		down = brake > self.pedal_threshold

		self._set_key("left", self.VK_LEFT, left)
		self._set_key("right", self.VK_RIGHT, right)
		self._set_key("up", self.VK_UP, up)
		self._set_key("down", self.VK_DOWN, down)

	def reset(self) -> None:
		self._set_key("left", self.VK_LEFT, False)
		self._set_key("right", self.VK_RIGHT, False)
		self._set_key("up", self.VK_UP, False)
		self._set_key("down", self.VK_DOWN, False)


class ControlBridge:
	def __init__(self) -> None:
		self.output_mode = "gamepad"
		self.gamepad = GamepadBridge()
		self.keyboard = KeyboardBridge()

	def switch_profile(self, profile: str) -> None:
		self.gamepad.switch_profile(profile)

	def switch_output_mode(self, mode: str) -> None:
		normalized = "keyboard" if mode.lower().startswith("key") else "gamepad"
		if normalized == self.output_mode:
			return

		self.reset()
		self.output_mode = normalized
		logging.info("Output mode switched to %s", self.output_mode)

	def apply(self, steering: float, gas: float, brake: float) -> None:
		if self.output_mode == "keyboard":
			self.keyboard.apply(steering, gas, brake)
			self.gamepad.reset()
			return

		self.gamepad.apply(steering, gas, brake)
		self.keyboard.reset()

	def apply_buttons(self, button_mask: int) -> None:
		if self.output_mode == "keyboard":
			return
		self.gamepad.apply_buttons(button_mask)

	def reset(self) -> None:
		self.gamepad.reset()
		self.keyboard.reset()


@dataclass
class SharedState:
	bridge: ControlBridge
	last_input_ts: float = 0.0
	active_clients: int = 0


async def send_http_response(writer: asyncio.StreamWriter, status: str, content_type: str, body: bytes) -> None:
	headers = [
		f"HTTP/1.1 {status}",
		f"Content-Type: {content_type}",
		f"Content-Length: {len(body)}",
		"Cache-Control: no-cache, no-store, must-revalidate",
		"Pragma: no-cache",
		"Connection: close",
		"",
		"",
	]
	writer.write("\r\n".join(headers).encode("utf-8") + body)
	await writer.drain()


async def handle_http_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
	try:
		data = await reader.read(4096)
		if not data:
			return

		request_line = data.split(b"\r\n", 1)[0].decode("utf-8", errors="ignore")
		parts = request_line.split(" ")
		if len(parts) < 2:
			await send_http_response(writer, "400 Bad Request", "text/plain", b"Bad Request")
			return

		method, raw_path = parts[0], parts[1]
		if method.upper() != "GET":
			await send_http_response(writer, "405 Method Not Allowed", "text/plain", b"Method Not Allowed")
			return

		route = raw_path.split("?", 1)[0]

		if route == "/api/config":
			is_secure_request = writer.get_extra_info("ssl_object") is not None
			secure_available = getattr(handle_http_client, "secure_available", False)
			payload = {
				"ws_port": WSS_PORT if (is_secure_request and secure_available) else WS_PORT,
				"ws_protocol": "wss" if (is_secure_request and secure_available) else "ws",
				"http_port": HTTP_PORT,
				"https_port": HTTPS_PORT,
				"suggested_host": get_local_ip(),
				"output_modes": ["gamepad", "keyboard"],
				"default_output_mode": "gamepad",
				"secure_available": secure_available,
			}
			body = json.dumps(payload).encode("utf-8")
			await send_http_response(writer, "200 OK", "application/json", body)
			return

		if route == "/":
			route = "/index.html"

		safe_relative = route.lstrip("/")
		target_path = (PROJECT_ROOT / safe_relative).resolve()

		# Prevent directory traversal.
		if not str(target_path).startswith(str(PROJECT_ROOT.resolve())):
			await send_http_response(writer, "403 Forbidden", "text/plain", b"Forbidden")
			return

		if not target_path.exists() or not target_path.is_file():
			await send_http_response(writer, "404 Not Found", "text/plain", b"Not Found")
			return

		body = target_path.read_bytes()
		content_type = mimetypes.guess_type(target_path.name)[0] or "application/octet-stream"
		await send_http_response(writer, "200 OK", content_type, body)
	except Exception:
		logging.exception("HTTP request failed")
	finally:
		writer.close()
		await writer.wait_closed()


def parse_control_packet(payload: str) -> Optional[tuple[float, float, float]]:
	"""Parse steering,gas,brake CSV payload."""
	parts = payload.split(",")
	if len(parts) != 3:
		return None
	try:
		steering = float(parts[0])
		gas = float(parts[1])
		brake = float(parts[2])
	except ValueError:
		return None
	return steering, gas, brake


async def ws_handler(websocket: Any, state: SharedState) -> None:
	state.active_clients += 1
	logging.info("Phone connected (%s active)", state.active_clients)

	try:
		async for message in websocket:
			text = message.decode("utf-8") if isinstance(message, bytes) else message
			text = text.strip()
			if not text:
				continue

			if text.startswith("P:"):
				profile = text[2:].strip().lower()
				state.bridge.switch_profile(profile)
				continue

			if text.startswith("M:"):
				mode = text[2:].strip().lower()
				state.bridge.switch_output_mode(mode)
				continue

			if text.startswith("B:"):
				try:
					mask = int(text[2:].strip())
				except ValueError:
					continue
				state.bridge.apply_buttons(mask)
				continue

			parsed = parse_control_packet(text)
			if parsed is None:
				continue

			steering, gas, brake = parsed
			state.bridge.apply(steering, gas, brake)
			state.last_input_ts = time.perf_counter()
	except websockets.ConnectionClosed:
		pass
	except Exception:
		logging.exception("WebSocket handler error")
	finally:
		state.active_clients = max(0, state.active_clients - 1)
		logging.info("Phone disconnected (%s active)", state.active_clients)


async def ws_entrypoint(websocket: Any, state: SharedState, path: Optional[str] = None) -> None:
	_ = path
	await ws_handler(websocket, state)


async def watchdog_loop(state: SharedState) -> None:
	while True:
		await asyncio.sleep(0.1)
		now = time.perf_counter()
		if state.last_input_ts == 0:
			continue
		if (now - state.last_input_ts) > WATCHDOG_TIMEOUT_S:
			state.bridge.reset()
			state.last_input_ts = 0.0


async def main() -> None:
	logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s %(message)s")

	if not INDEX_FILE.exists():
		raise FileNotFoundError("index.html not found beside server.py")

	state = SharedState(bridge=ControlBridge())
	tls_context = build_tls_context()
	handle_http_client.secure_available = tls_context is not None  # type: ignore[attr-defined]

	http_servers = []
	ws_servers = []
	try:
		http_server = await asyncio.start_server(handle_http_client, HOST, HTTP_PORT)
		http_servers.append(http_server)
		ws_server = await websockets.serve(
			lambda ws, path=None: ws_entrypoint(ws, state, path),
			HOST,
			WS_PORT,
			max_size=2048,
		)
		ws_servers.append(ws_server)
	except OSError as exc:
		if getattr(exc, "winerror", None) == 10048:
			logging.error("Ports %s/%s are already in use. Stop previous server instances and retry.", HTTP_PORT, WS_PORT)
			logging.error("Tip: run 'netstat -ano | findstr :%s' to find the PID using that port.", HTTP_PORT)
			return
		raise

	if tls_context is not None:
		try:
			https_server = await asyncio.start_server(handle_http_client, HOST, HTTPS_PORT, ssl=tls_context)
			http_servers.append(https_server)
			wss_server = await websockets.serve(
				lambda ws, path=None: ws_entrypoint(ws, state, path),
				HOST,
				WSS_PORT,
				max_size=2048,
				ssl=tls_context,
			)
			ws_servers.append(wss_server)
		except OSError as exc:
			if getattr(exc, "winerror", None) == 10048:
				logging.error("Secure ports %s/%s are already in use. Stop previous instances and retry.", HTTPS_PORT, WSS_PORT)
				return
			raise
	else:
		logging.warning("TLS disabled. Add cert.pem and key.pem in project root to enable HTTPS/WSS.")

	watchdog_task = asyncio.create_task(watchdog_loop(state))

	ip = get_local_ip()
	logging.info("HTTP server: http://%s:%s", ip, HTTP_PORT)
	logging.info("WebSocket server: ws://%s:%s", ip, WS_PORT)
	if tls_context is not None:
		logging.info("HTTPS server: https://%s:%s", ip, HTTPS_PORT)
		logging.info("Secure WebSocket server: wss://%s:%s", ip, WSS_PORT)
		logging.info("For iOS motion permission, open the HTTPS URL and trust the certificate.")
	logging.info("Open the HTTP URL on your phone and connect using the same IP.")

	try:
		await asyncio.Future()
	except asyncio.CancelledError:
		pass
	finally:
		watchdog_task.cancel()
		for ws_instance in ws_servers:
			ws_instance.close()
		for ws_instance in ws_servers:
			await ws_instance.wait_closed()
		for http_instance in http_servers:
			http_instance.close()
		for http_instance in http_servers:
			await http_instance.wait_closed()
		state.bridge.reset()


if __name__ == "__main__":
	try:
		asyncio.run(main())
	except KeyboardInterrupt:
		pass
