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
WATCHDOG_TIMEOUT_S = 10.0
MAX_GAMEPADS = 4

BUTTON_SOUTH = 1
BUTTON_EAST = 2
BUTTON_WEST = 4
BUTTON_NORTH = 8
BUTTON_LB = 16
BUTTON_RB = 32
BUTTON_LT = 64
BUTTON_RT = 128
BUTTON_BACK = 256
BUTTON_START = 512
BUTTON_LS = 1024
BUTTON_RS = 2048
BUTTON_DPAD_UP = 4096
BUTTON_DPAD_DOWN = 8192
BUTTON_DPAD_LEFT = 16384
BUTTON_DPAD_RIGHT = 32768

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

	def right_joystick_float(self, x_value_float: float, y_value_float: float) -> None:
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
	def __init__(self, slot: int) -> None:
		self.slot = slot
		self.profile = "xbox"
		self.gamepad = self._create_gamepad(self.profile)
		self.logical_pressed = {
			"south": False,
			"east": False,
			"west": False,
			"north": False,
			"lb": False,
			"rb": False,
			"lt": False,
			"rt": False,
			"back": False,
			"start": False,
			"ls": False,
			"rs": False,
			"dpad_up": False,
			"dpad_down": False,
			"dpad_left": False,
			"dpad_right": False,
		}
		self.trigger_overrides = {"lt": False, "rt": False}

	def _create_gamepad(self, profile: str):
		if vg is None:
			logging.warning("vgamepad not found. Running in no-op mode for slot %s.", self.slot)
			return NullGamepad(profile)

		if profile in ("ps", "ps5"):
			logging.info("Using VDS4Gamepad profile for slot %s", self.slot)
			return vg.VDS4Gamepad()

		logging.info("Using VX360Gamepad profile for slot %s", self.slot)
		return vg.VX360Gamepad()

	def switch_profile(self, profile: str) -> None:
		if profile.lower().startswith("ps"):
			normalized = "ps5"
		elif profile.lower().startswith("rac") or profile.lower().startswith("ase"):
			normalized = "racing"
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
		logging.info("Controller profile switched to %s (slot %s)", self.profile, self.slot)

	def apply(
		self,
		left_x: float,
		left_y: float,
		right_x: float,
		right_y: float,
		left_trigger: float,
		right_trigger: float,
	) -> None:
		left_x = clamp(left_x, -1.0, 1.0)
		left_y = clamp(left_y, -1.0, 1.0)
		right_x = clamp(right_x, -1.0, 1.0)
		right_y = clamp(right_y, -1.0, 1.0)
		left_trigger = clamp(left_trigger, 0.0, 1.0)
		right_trigger = clamp(right_trigger, 0.0, 1.0)
		if self.trigger_overrides["rt"]:
			right_trigger = max(right_trigger, 1.0)
		if self.trigger_overrides["lt"]:
			left_trigger = max(left_trigger, 1.0)

		self.gamepad.left_joystick_float(x_value_float=left_x, y_value_float=left_y)
		self.gamepad.right_joystick_float(x_value_float=right_x, y_value_float=right_y)
		self.gamepad.right_trigger_float(value_float=right_trigger)
		self.gamepad.left_trigger_float(value_float=left_trigger)
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
				"back": ["DS4_BUTTON_SHARE"],
				"start": ["DS4_BUTTON_OPTIONS"],
				"ls": ["DS4_BUTTON_THUMB_LEFT"],
				"rs": ["DS4_BUTTON_THUMB_RIGHT"],
				"dpad_up": ["DS4_BUTTON_DPAD_NORTH"],
				"dpad_down": ["DS4_BUTTON_DPAD_SOUTH"],
				"dpad_left": ["DS4_BUTTON_DPAD_WEST"],
				"dpad_right": ["DS4_BUTTON_DPAD_EAST"],
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
				"back": ["XUSB_GAMEPAD_BACK"],
				"start": ["XUSB_GAMEPAD_START"],
				"ls": ["XUSB_GAMEPAD_LEFT_THUMB"],
				"rs": ["XUSB_GAMEPAD_RIGHT_THUMB"],
				"dpad_up": ["XUSB_GAMEPAD_DPAD_UP"],
				"dpad_down": ["XUSB_GAMEPAD_DPAD_DOWN"],
				"dpad_left": ["XUSB_GAMEPAD_DPAD_LEFT"],
				"dpad_right": ["XUSB_GAMEPAD_DPAD_RIGHT"],
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

		if logical_button in ("lt", "rt"):
			self.trigger_overrides[logical_button] = should_press
			self.logical_pressed[logical_button] = should_press
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
		self._set_logical_button("lt", (mask & BUTTON_LT) != 0)
		self._set_logical_button("rt", (mask & BUTTON_RT) != 0)
		self._set_logical_button("back", (mask & BUTTON_BACK) != 0)
		self._set_logical_button("start", (mask & BUTTON_START) != 0)
		self._set_logical_button("ls", (mask & BUTTON_LS) != 0)
		self._set_logical_button("rs", (mask & BUTTON_RS) != 0)
		self._set_logical_button("dpad_up", (mask & BUTTON_DPAD_UP) != 0)
		self._set_logical_button("dpad_down", (mask & BUTTON_DPAD_DOWN) != 0)
		self._set_logical_button("dpad_left", (mask & BUTTON_DPAD_LEFT) != 0)
		self._set_logical_button("dpad_right", (mask & BUTTON_DPAD_RIGHT) != 0)
		self.gamepad.update()

	def reset(self) -> None:
		self.trigger_overrides["lt"] = False
		self.trigger_overrides["rt"] = False
		self.gamepad.left_joystick_float(x_value_float=0.0, y_value_float=0.0)
		self.gamepad.right_joystick_float(x_value_float=0.0, y_value_float=0.0)
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

	def apply(
		self,
		left_x: float,
		left_y: float,
		right_x: float,
		right_y: float,
		left_trigger: float,
		right_trigger: float,
	) -> None:
		left_x = clamp(left_x, -1.0, 1.0)
		left_trigger = clamp(left_trigger, 0.0, 1.0)
		right_trigger = clamp(right_trigger, 0.0, 1.0)

		left = left_x < -self.steer_threshold
		right = left_x > self.steer_threshold
		up = right_trigger > self.pedal_threshold
		down = left_trigger > self.pedal_threshold

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
	def __init__(self, slot: int) -> None:
		self.output_mode = "gamepad"
		self.gamepad = GamepadBridge(slot)
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

	def apply(
		self,
		left_x: float,
		left_y: float,
		right_x: float,
		right_y: float,
		left_trigger: float,
		right_trigger: float,
	) -> None:
		if self.output_mode == "keyboard":
			self.keyboard.apply(left_x, left_y, right_x, right_y, left_trigger, right_trigger)
			self.gamepad.reset()
			return

		self.gamepad.apply(left_x, left_y, right_x, right_y, left_trigger, right_trigger)
		self.keyboard.reset()

	def apply_buttons(self, button_mask: int) -> None:
		if self.output_mode == "keyboard":
			return
		self.gamepad.apply_buttons(button_mask)

	def reset(self) -> None:
		self.gamepad.reset()
		self.keyboard.reset()


@dataclass
class ClientSession:
	slot: int
	bridge: ControlBridge
	last_input_ts: float = 0.0


class BridgePool:
	def __init__(self, max_slots: int = MAX_GAMEPADS) -> None:
		self.max_slots = max_slots
		self._available_slots = list(range(1, max_slots + 1))
		self._sessions: dict[int, ClientSession] = {}

	def acquire(self) -> Optional[ClientSession]:
		if not self._available_slots:
			return None

		slot = self._available_slots.pop(0)
		session = ClientSession(slot=slot, bridge=ControlBridge(slot))
		self._sessions[slot] = session
		return session

	def release(self, slot: int) -> None:
		session = self._sessions.pop(slot, None)
		if session is None:
			return
		try:
			session.bridge.reset()
		except Exception:
			logging.exception("Failed resetting controller slot %s", slot)
		if slot not in self._available_slots:
			self._available_slots.append(slot)
			self._available_slots.sort()

	def active_sessions(self) -> list[ClientSession]:
		return list(self._sessions.values())


@dataclass
class SharedState:
	pool: BridgePool
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


def parse_axis_packet(payload: str) -> Optional[tuple[float, float, float, float, float, float]]:
	"""Parse LX,LY,RX,RY,L2,R2 packet payload."""
	parts = payload.split(",")
	if len(parts) != 6:
		return None
	try:
		left_x = float(parts[0])
		left_y = float(parts[1])
		right_x = float(parts[2])
		right_y = float(parts[3])
		left_trigger = float(parts[4])
		right_trigger = float(parts[5])
	except ValueError:
		return None
	return left_x, left_y, right_x, right_y, left_trigger, right_trigger


def parse_legacy_control_packet(payload: str) -> Optional[tuple[float, float, float, float, float, float]]:
	"""Parse legacy steering,gas,brake CSV payload and map to modern axes/triggers."""
	parts = payload.split(",")
	if len(parts) != 3:
		return None
	try:
		steering = float(parts[0])
		gas = float(parts[1])
		brake = float(parts[2])
	except ValueError:
		return None
	return steering, 0.0, 0.0, 0.0, clamp(brake, 0.0, 1.0), clamp(gas, 0.0, 1.0)


async def ws_handler(websocket: Any, state: SharedState) -> None:
	session = state.pool.acquire()
	if session is None:
		logging.warning("Rejecting client: all %s virtual controller slots are in use", MAX_GAMEPADS)
		await websocket.close(code=1013, reason="No free controller slots")
		return

	state.active_clients += 1
	logging.info("Phone connected on slot %s (%s active)", session.slot, state.active_clients)
	await websocket.send(f"S:{session.slot}")

	try:
		async for message in websocket:
			text = message.decode("utf-8") if isinstance(message, bytes) else message
			text = text.strip()
			if not text:
				continue

			if text.startswith("P:"):
				profile = text[2:].strip().lower()
				session.bridge.switch_profile(profile)
				continue

			if text.startswith("M:"):
				mode = text[2:].strip().lower()
				session.bridge.switch_output_mode(mode)
				continue

			if text.startswith("B:"):
				try:
					mask = int(text[2:].strip())
				except ValueError:
					continue
				session.bridge.apply_buttons(mask)
				session.last_input_ts = time.perf_counter()
				continue

			if text.startswith("A:"):
				parsed = parse_axis_packet(text[2:].strip())
			else:
				parsed = parse_legacy_control_packet(text)
			if parsed is None:
				continue

			left_x, left_y, right_x, right_y, left_trigger, right_trigger = parsed
			session.bridge.apply(left_x, left_y, right_x, right_y, left_trigger, right_trigger)
			session.last_input_ts = time.perf_counter()
	except websockets.ConnectionClosed:
		pass
	except Exception:
		logging.exception("WebSocket handler error")
	finally:
		state.active_clients = max(0, state.active_clients - 1)
		state.pool.release(session.slot)
		logging.info("Phone disconnected from slot %s (%s active)", session.slot, state.active_clients)


async def ws_entrypoint(websocket: Any, state: SharedState, path: Optional[str] = None) -> None:
	_ = path
	await ws_handler(websocket, state)


async def watchdog_loop(state: SharedState) -> None:
	while True:
		await asyncio.sleep(0.1)
		now = time.perf_counter()
		for session in state.pool.active_sessions():
			if session.last_input_ts == 0:
				continue
			if (now - session.last_input_ts) > WATCHDOG_TIMEOUT_S:
				session.bridge.reset()
				session.last_input_ts = 0.0


async def main() -> None:
	logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s %(message)s")

	if not INDEX_FILE.exists():
		raise FileNotFoundError("index.html not found beside server.py")

	state = SharedState(pool=BridgePool())
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
		for session in state.pool.active_sessions():
			session.bridge.reset()


if __name__ == "__main__":
	try:
		asyncio.run(main())
	except KeyboardInterrupt:
		pass
