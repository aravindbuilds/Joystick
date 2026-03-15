const WS_PORT = 5005;
const MAX_TILT_DEG = 35;
const STEERING_DEADZONE = 0.04;
const STEERING_ALPHA = 0.16;
const SEND_EPSILON = 0.002;
const AUTO_CONNECT_DELAY_MS = 220;
const BUTTON_BITS = {
  south: 1,
  east: 2,
  west: 4,
  north: 8,
  lb: 16,
  rb: 32,
};

const DRIVE_PROFILES = {
  balanced: {
    maxTiltDeg: 35,
    deadzone: 0.04,
    steerAlpha: 0.16,
    steerExpo: 1.2,
    gasExpo: 1.0,
    brakeExpo: 1.0,
  },
  assetto: {
    maxTiltDeg: 28,
    deadzone: 0.025,
    steerAlpha: 0.24,
    steerExpo: 1.45,
    gasExpo: 1.15,
    brakeExpo: 1.35,
  },
};

const state = {
  ws: null,
  connected: false,
  requestedProfile: "xbox",
  outputMode: "gamepad",
  driveProfile: "balanced",
  neutralTilt: 0,
  lastTiltRaw: 0,
  rawSteering: 0,
  smoothedSteering: 0,
  gas: 0,
  brake: 0,
  orientationAttached: false,
  wsPort: WS_PORT,
  wsProtocol: window.location.protocol === "https:" ? "wss" : "ws",
  serverSuggestedHost: null,
  autoConnectAttempted: false,
  lastSent: {
    steering: 999,
    gas: 999,
    brake: 999,
    buttonMask: 999,
  },
  buttonMask: 0,
  invertSteering: false,
  sensorsEnabled: false,
};

const el = {
  ipInput: document.getElementById("ipInput"),
  motionBtn: document.getElementById("motionBtn"),
  connectBtn: document.getElementById("connectBtn"),
  invertBtn: document.getElementById("invertBtn"),
  statusDot: document.getElementById("statusDot"),
  statusText: document.getElementById("statusText"),
  sensorText: document.getElementById("sensorText"),
  wheel: document.getElementById("wheel"),
  steeringValue: document.getElementById("steeringValue"),
  profileXbox: document.getElementById("profileXbox"),
  profilePs: document.getElementById("profilePs"),
  profileAssetto: document.getElementById("profileAssetto"),
  outputGamepad: document.getElementById("outputGamepad"),
  outputKeyboard: document.getElementById("outputKeyboard"),
  driveNormal: document.getElementById("driveNormal"),
  driveAssetto: document.getElementById("driveAssetto"),
  calibrateBtn: document.getElementById("calibrateBtn"),
  gasZone: document.getElementById("gasZone"),
  brakeZone: document.getElementById("brakeZone"),
  gasMeter: document.getElementById("gasMeter"),
  brakeMeter: document.getElementById("brakeMeter"),
  gasValue: document.getElementById("gasValue"),
  brakeValue: document.getElementById("brakeValue"),
  actionHint: document.getElementById("actionHint"),
  btnSouth: document.getElementById("btnSouth"),
  btnEast: document.getElementById("btnEast"),
  btnWest: document.getElementById("btnWest"),
  btnNorth: document.getElementById("btnNorth"),
  btnLb: document.getElementById("btnLb"),
  btnRb: document.getElementById("btnRb"),
};

const PROFILE_LABELS = {
  xbox: {
    hint: "Xbox layout",
    south: "A",
    east: "B",
    west: "X",
    north: "Y",
    lb: "LB",
    rb: "RB",
  },
  ps5: {
    hint: "PS5 layout",
    south: "Cross",
    east: "Circle",
    west: "Square",
    north: "Triangle",
    lb: "L1",
    rb: "R1",
  },
  assetto: {
    hint: "Assetto layout",
    south: "Shift+",
    east: "Handbrake",
    west: "Shift-",
    north: "LookBack",
    lb: "TC-",
    rb: "TC+",
  },
};

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function applyDeadzone(value, deadzone) {
  if (Math.abs(value) <= deadzone) {
    return 0;
  }
  const sign = Math.sign(value);
  const scaled = (Math.abs(value) - deadzone) / (1 - deadzone);
  return sign * clamp(scaled, 0, 1);
}

function applyExpo(value, exponent) {
  const sign = Math.sign(value);
  return sign * Math.pow(Math.abs(value), exponent);
}

function updateSensorUi() {
  if (state.sensorsEnabled) {
    el.sensorText.textContent = "Motion: Enabled";
    el.motionBtn.textContent = "Motion Enabled";
    el.motionBtn.classList.add("active");
    return;
  }
  el.sensorText.textContent = "Motion: Tap Enable Motion";
  el.motionBtn.textContent = "Enable Motion";
  el.motionBtn.classList.remove("active");
}

function updateInvertButton() {
  el.invertBtn.textContent = `Invert L/R: ${state.invertSteering ? "On" : "Off"}`;
  el.invertBtn.classList.toggle("active", state.invertSteering);
}

function activeDriveConfig() {
  return DRIVE_PROFILES[state.driveProfile] || DRIVE_PROFILES.balanced;
}

function updateDriveButtons() {
  const isAssetto = state.driveProfile === "assetto";
  el.driveAssetto.classList.toggle("active", isAssetto);
  el.driveNormal.classList.toggle("active", !isAssetto);
}

function updateStatus(text, isConnected) {
  state.connected = isConnected;
  el.statusText.textContent = text;
  el.statusDot.classList.toggle("connected", isConnected);
  el.connectBtn.textContent = isConnected ? "Disconnect" : "Connect";
}

function updateProfileButtons() {
  el.profileXbox.classList.toggle("active", state.requestedProfile === "xbox");
  el.profilePs.classList.toggle("active", state.requestedProfile === "ps5");
  el.profileAssetto.classList.toggle("active", state.requestedProfile === "assetto");
  const labels = PROFILE_LABELS[state.requestedProfile] || PROFILE_LABELS.xbox;
  el.actionHint.textContent = labels.hint;
  el.btnSouth.textContent = labels.south;
  el.btnEast.textContent = labels.east;
  el.btnWest.textContent = labels.west;
  el.btnNorth.textContent = labels.north;
  el.btnLb.textContent = labels.lb;
  el.btnRb.textContent = labels.rb;
}

function updateOutputButtons() {
  const keyboard = state.outputMode === "keyboard";
  el.outputKeyboard.classList.toggle("active", keyboard);
  el.outputGamepad.classList.toggle("active", !keyboard);
}

function loadSettings() {
  const savedIp = localStorage.getItem("wheel_host_ip");
  const savedOutput = localStorage.getItem("wheel_output_mode");
  const savedInvert = localStorage.getItem("wheel_invert_steering");
  if (savedOutput === "keyboard" || savedOutput === "gamepad") {
    state.outputMode = savedOutput;
  }
  if (savedInvert === "true") {
    state.invertSteering = true;
  }
  if (savedIp) {
    el.ipInput.value = savedIp;
    return;
  }

  // If the page is opened from the PC host, use that hostname automatically.
  if (window.location.hostname && window.location.hostname !== "localhost") {
    el.ipInput.value = window.location.hostname;
  }
}

function saveSettings() {
  localStorage.setItem("wheel_host_ip", el.ipInput.value.trim());
  localStorage.setItem("wheel_output_mode", state.outputMode);
  localStorage.setItem("wheel_invert_steering", String(state.invertSteering));
}

function currentHost() {
  const raw = el.ipInput.value.trim();
  if (raw) {
    return raw;
  }
  if (state.serverSuggestedHost) {
    return state.serverSuggestedHost;
  }
  if (window.location.hostname && window.location.hostname !== "localhost") {
    return window.location.hostname;
  }
  return null;
}

function closeSocket() {
  if (state.ws) {
    state.ws.onclose = null;
    state.ws.close();
    state.ws = null;
  }
  updateStatus("Disconnected", false);
}

function connectSocket() {
  if (state.connected) {
    closeSocket();
    return;
  }

  const host = currentHost();
  if (!host) {
    updateStatus("Enter PC IP first", false);
    return;
  }

  if (!el.ipInput.value.trim()) {
    el.ipInput.value = host;
  }

  saveSettings();
  updateStatus("Connecting...", false);

  const ws = new WebSocket(`${state.wsProtocol}://${host}:${state.wsPort}`);

  ws.onopen = () => {
    state.ws = ws;
    updateStatus("Connected", true);
    sendProfile();
    sendOutputMode();
  };

  ws.onclose = () => {
    state.ws = null;
    updateStatus("Disconnected", false);
  };

  ws.onerror = () => {
    updateStatus("Connection error", false);
  };
}

async function loadServerConfig() {
  try {
    const response = await fetch("/api/config", { cache: "no-store" });
    if (!response.ok) {
      return;
    }

    const config = await response.json();
    if (typeof config.ws_port === "number" && Number.isFinite(config.ws_port)) {
      state.wsPort = config.ws_port;
    }

    if (typeof config.ws_protocol === "string") {
      const normalized = config.ws_protocol.toLowerCase();
      if (normalized === "ws" || normalized === "wss") {
        state.wsProtocol = normalized;
      }
    }

    if (typeof config.default_output_mode === "string") {
      const normalizedMode = config.default_output_mode.toLowerCase();
      if ((normalizedMode === "gamepad" || normalizedMode === "keyboard") && !localStorage.getItem("wheel_output_mode")) {
        state.outputMode = normalizedMode;
      }
    }

    if (typeof config.suggested_host === "string" && config.suggested_host.trim()) {
      state.serverSuggestedHost = config.suggested_host.trim();
      if (!el.ipInput.value.trim()) {
        el.ipInput.value = state.serverSuggestedHost;
      }
    }
  } catch {
    // Keep defaults if config endpoint is not available.
  }
}

function maybeAutoConnect() {
  if (state.autoConnectAttempted || state.connected) {
    return;
  }

  const host = currentHost();
  if (!host || !state.sensorsEnabled) {
    return;
  }

  state.autoConnectAttempted = true;
  setTimeout(() => {
    if (!state.connected) {
      connectSocket();
    }
  }, AUTO_CONNECT_DELAY_MS);
}

function sendProfile() {
  if (!state.ws || state.ws.readyState !== WebSocket.OPEN) {
    return;
  }
  state.ws.send(`P:${state.requestedProfile}`);
}

function sendButtons() {
  if (!state.ws || state.ws.readyState !== WebSocket.OPEN) {
    return;
  }
  state.ws.send(`B:${state.buttonMask}`);
  state.lastSent.buttonMask = state.buttonMask;
}

function sendOutputMode() {
  if (!state.ws || state.ws.readyState !== WebSocket.OPEN) {
    return;
  }
  state.ws.send(`M:${state.outputMode}`);
}

function sendControlPacket(steering, gas, brake) {
  if (!state.ws || state.ws.readyState !== WebSocket.OPEN) {
    return;
  }

  const packet = `${steering.toFixed(4)},${gas.toFixed(4)},${brake.toFixed(4)}`;
  state.ws.send(packet);
  state.lastSent.steering = steering;
  state.lastSent.gas = gas;
  state.lastSent.brake = brake;
}

function maybeSendControlPacket() {
  const s = state.smoothedSteering;
  const g = state.gas;
  const b = state.brake;

  const changed =
    Math.abs(s - state.lastSent.steering) > SEND_EPSILON ||
    Math.abs(g - state.lastSent.gas) > SEND_EPSILON ||
    Math.abs(b - state.lastSent.brake) > SEND_EPSILON;

  const buttonChanged = state.buttonMask !== state.lastSent.buttonMask;

  if (changed) {
    sendControlPacket(s, g, b);
  }

  if (buttonChanged) {
    sendButtons();
  }
}

function updateWheelUi() {
  const degrees = state.smoothedSteering * 95;
  el.wheel.style.transform = `rotate(${degrees.toFixed(2)}deg)`;
  el.steeringValue.textContent = `Steering: ${state.smoothedSteering.toFixed(2)}`;

  const gasPct = Math.round(state.gas * 100);
  const brakePct = Math.round(state.brake * 100);
  el.gasMeter.style.height = `${gasPct}%`;
  el.brakeMeter.style.height = `${brakePct}%`;
  el.gasValue.textContent = `${gasPct}%`;
  el.brakeValue.textContent = `${brakePct}%`;
}

function readTiltFromOrientation(event) {
  const gamma = typeof event.gamma === "number" ? event.gamma : 0;
  const beta = typeof event.beta === "number" ? event.beta : 0;

  let angle = 0;
  if (screen.orientation && typeof screen.orientation.angle === "number") {
    angle = screen.orientation.angle;
  } else if (typeof window.orientation === "number") {
    angle = window.orientation;
  }

  const normalizedAngle = ((angle % 360) + 360) % 360;
  let tilt = gamma;

  if (normalizedAngle === 90 || normalizedAngle === 270) {
    // In landscape, gamma is usually the closest to intuitive left-right wheel tilt.
    tilt = gamma;

    // Some devices report weak gamma in landscape, so use beta as fallback.
    if (Math.abs(gamma) < 1.0 && Math.abs(beta) > Math.abs(gamma) * 1.5) {
      tilt = beta;
    }

    // Landscape-secondary needs sign flip to keep steering direction consistent.
    if (normalizedAngle === 270) {
      tilt = -tilt;
    }
  } else if (normalizedAngle === 180) {
    tilt = -gamma;
  }

  return state.invertSteering ? -tilt : tilt;
}

function handleOrientation(event) {
  if (typeof event.gamma !== "number" && typeof event.beta !== "number") {
    return;
  }

  state.sensorsEnabled = true;
  updateSensorUi();
  const tiltRaw = readTiltFromOrientation(event);
  state.lastTiltRaw = tiltRaw;
  const cfg = activeDriveConfig();
  const centeredTilt = tiltRaw - state.neutralTilt;
  const normalized = clamp(centeredTilt / cfg.maxTiltDeg, -1, 1);
  const dz = applyDeadzone(normalized, cfg.deadzone);
  state.rawSteering = applyExpo(dz, cfg.steerExpo);
}

function attachOrientationListener() {
  if (state.orientationAttached) {
    return;
  }
  window.addEventListener("deviceorientation", handleOrientation, { passive: true });
  state.orientationAttached = true;
}

async function ensureOrientationPermissionIfNeeded() {
  const iOSPermission =
    typeof DeviceOrientationEvent !== "undefined" &&
    typeof DeviceOrientationEvent.requestPermission === "function";

  if (!iOSPermission) {
    attachOrientationListener();
    updateStatus("Motion ready", state.connected);
    return;
  }

  try {
    const result = await DeviceOrientationEvent.requestPermission();
    if (result === "granted") {
      attachOrientationListener();
      updateStatus("Motion ready", state.connected);
      maybeAutoConnect();
    } else {
      updateStatus("Motion permission denied", state.connected);
    }
  } catch {
    updateStatus("Sensor permission failed", state.connected);
  }
}

function valueFromTouch(zoneElement, touchEvent) {
  const rect = zoneElement.getBoundingClientRect();
  const y = clamp(touchEvent.clientY - rect.top, 0, rect.height);
  const cfg = activeDriveConfig();
  const percent = 1 - y / rect.height;
  const curved = Math.pow(clamp(percent, 0, 1), keyFromZone(zoneElement) === "brake" ? cfg.brakeExpo : cfg.gasExpo);
  return clamp(curved, 0, 1);
}

function keyFromZone(zoneElement) {
  return zoneElement === el.brakeZone ? "brake" : "gas";
}

function setButtonPressed(name, pressed, buttonElement) {
  const bit = BUTTON_BITS[name];
  if (!bit) {
    return;
  }

  if (pressed) {
    state.buttonMask |= bit;
    buttonElement.classList.add("pressed");
  } else {
    state.buttonMask &= ~bit;
    buttonElement.classList.remove("pressed");
  }
}

function attachActionButton(element, logicalName) {
  const start = (event) => {
    event.preventDefault();
    setButtonPressed(logicalName, true, element);
  };
  const end = (event) => {
    event.preventDefault();
    setButtonPressed(logicalName, false, element);
  };

  element.addEventListener("pointerdown", start, { passive: false });
  element.addEventListener("pointerup", end, { passive: false });
  element.addEventListener("pointercancel", end, { passive: false });
  element.addEventListener("pointerleave", end, { passive: false });
}

function attachPedal(zoneElement, keyName) {
  const activeTouches = new Map();

  const updateFromTouches = () => {
    if (activeTouches.size === 0) {
      state[keyName] = 0;
      return;
    }

    // Use the highest pressure when multiple fingers touch the zone.
    let max = 0;
    for (const value of activeTouches.values()) {
      if (value > max) {
        max = value;
      }
    }
    state[keyName] = max;

    if (state[keyName] >= 0.9 && navigator.vibrate) {
      navigator.vibrate(14);
    }
  };

  zoneElement.addEventListener("touchstart", (event) => {
    event.preventDefault();
    for (const touch of event.changedTouches) {
      activeTouches.set(touch.identifier, valueFromTouch(zoneElement, touch));
    }
    updateFromTouches();
  }, { passive: false });

  zoneElement.addEventListener("touchmove", (event) => {
    event.preventDefault();
    for (const touch of event.changedTouches) {
      if (activeTouches.has(touch.identifier)) {
        activeTouches.set(touch.identifier, valueFromTouch(zoneElement, touch));
      }
    }
    updateFromTouches();
  }, { passive: false });

  const release = (event) => {
    event.preventDefault();
    for (const touch of event.changedTouches) {
      activeTouches.delete(touch.identifier);
    }
    updateFromTouches();
  };

  zoneElement.addEventListener("touchend", release, { passive: false });
  zoneElement.addEventListener("touchcancel", release, { passive: false });
}

function animationLoop() {
  const cfg = activeDriveConfig();
  state.smoothedSteering += cfg.steerAlpha * (state.rawSteering - state.smoothedSteering);
  state.smoothedSteering = clamp(state.smoothedSteering, -1, 1);

  updateWheelUi();
  maybeSendControlPacket();

  requestAnimationFrame(animationLoop);
}

function setupEvents() {
  el.motionBtn.addEventListener("click", async () => {
    await ensureOrientationPermissionIfNeeded();
  });

  el.connectBtn.addEventListener("click", () => {
    connectSocket();
  });

  el.invertBtn.addEventListener("click", () => {
    state.invertSteering = !state.invertSteering;
    updateInvertButton();
    saveSettings();
  });

  el.profileXbox.addEventListener("click", () => {
    state.requestedProfile = "xbox";
    updateProfileButtons();
    sendProfile();
  });

  el.profilePs.addEventListener("click", () => {
    state.requestedProfile = "ps5";
    updateProfileButtons();
    sendProfile();
  });

  el.profileAssetto.addEventListener("click", () => {
    state.requestedProfile = "assetto";
    updateProfileButtons();
    sendProfile();
  });

  el.outputGamepad.addEventListener("click", () => {
    state.outputMode = "gamepad";
    updateOutputButtons();
    saveSettings();
    sendOutputMode();
  });

  el.outputKeyboard.addEventListener("click", () => {
    state.outputMode = "keyboard";
    updateOutputButtons();
    saveSettings();
    sendOutputMode();
  });

  el.driveNormal.addEventListener("click", () => {
    state.driveProfile = "balanced";
    updateDriveButtons();
  });

  el.driveAssetto.addEventListener("click", () => {
    state.driveProfile = "assetto";
    updateDriveButtons();
  });

  el.calibrateBtn.addEventListener("click", () => {
    // Capture current tilt as neutral center.
    state.neutralTilt = state.lastTiltRaw;
    state.rawSteering = 0;
    state.smoothedSteering = 0;
    updateStatus("Steering calibrated", state.connected);
    if (navigator.vibrate) {
      navigator.vibrate([10, 30, 10]);
    }
  });

  attachPedal(el.gasZone, "gas");
  attachPedal(el.brakeZone, "brake");
  attachActionButton(el.btnSouth, "south");
  attachActionButton(el.btnEast, "east");
  attachActionButton(el.btnWest, "west");
  attachActionButton(el.btnNorth, "north");
  attachActionButton(el.btnLb, "lb");
  attachActionButton(el.btnRb, "rb");

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      state.gas = 0;
      state.brake = 0;
      state.rawSteering = 0;
      state.buttonMask = 0;
    }
  });
}

async function boot() {
  loadSettings();
  await loadServerConfig();
  updateProfileButtons();
  updateInvertButton();
  updateOutputButtons();
  updateDriveButtons();
  updateStatus("Disconnected", false);
  updateSensorUi();

  // On iOS, motion permission requires a user gesture.
  // We still auto-enable listener on platforms that do not require permission.
  const iOSPermission =
    typeof DeviceOrientationEvent !== "undefined" &&
    typeof DeviceOrientationEvent.requestPermission === "function";
  if (!iOSPermission) {
    await ensureOrientationPermissionIfNeeded();
    maybeAutoConnect();
  }

  setupEvents();
  requestAnimationFrame(animationLoop);
}

boot();
