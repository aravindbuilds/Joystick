// State Variables
let ws;
let wsPort = 5005; // Fallback, will be fetched from server
let wsProtocol = 'ws';
let isConnected = false;
let isEditMode = false;

// Hardware & Controls Settings
let activeKeys = new Set();
let activeProfile = "default";
let activeTheme = "xbox";
let uiScale = 1.0;
let joystickSens = 1.0;
let useGyro = false;
let gyroOffset = { gamma: 0, beta: 0 };
let currentTouches = {}; 

// Elements
const connectBtn = document.getElementById('connect-btn');
const editBtn = document.getElementById('edit-layout-btn');
const settingsToggleBtn = document.getElementById('settings-toggle-btn');
const settingsBar = document.getElementById('settings-bar');

// UI Scalable Container Elements (Wrappers we drag around)
const scalableElements = [
    document.getElementById('shoulder-left'),
    document.getElementById('shoulder-right'),
    document.getElementById('dpad-grid'),
    document.getElementById('action-grid'),
    document.getElementById('base-left'),
    document.getElementById('base-right'),
    document.getElementById('middle-buttons')
];

// Profile Manager
const profileSel = document.getElementById('profile-sel');
const sizeSlider = document.getElementById('size-slider');
const sensSlider = document.getElementById('sens-slider');

// Gyro Manager
const gyroToggle = document.getElementById('gyro-toggle');
const gyroIndicator = document.getElementById('gyro-indicator');
const calibrateBtn = document.getElementById('calibrate-btn');

const btnMap = {
    'A': 'BTN_SOUTH', 'B': 'BTN_EAST', 'X': 'BTN_WEST', 'Y': 'BTN_NORTH',
    'Up': 'ABS_HAT0Y:-1', 'Down': 'ABS_HAT0Y:1', 'Left': 'ABS_HAT0X:-1', 'Right': 'ABS_HAT0X:1',
    'L1': 'BTN_TL', 'R1': 'BTN_TR', 'L2': 'ABS_Z:255', 'R2': 'ABS_RZ:255',
    'L3': 'BTN_THUMBL', 'R3': 'BTN_THUMBR',
    'Share': 'BTN_SELECT', 'Menu': 'BTN_START', 'Home': 'BTN_MODE'
};


// --- INITIALIZATION ---
function setupZoomPrevention() {
    // Prevent pinch zoom and double-tap zoom on iOS
    document.addEventListener('gesturestart', function(e) { e.preventDefault(); });
    document.addEventListener('gesturechange', function(e) { e.preventDefault(); });
    document.addEventListener('gestureend', function(e) { e.preventDefault(); });

    let lastTouchEnd = 0;
    document.addEventListener('touchend', function (event) {
        if (!isEditMode) {
            const now = (new Date()).getTime();
            if (now - lastTouchEnd <= 300) {
                event.preventDefault();
            }
            lastTouchEnd = now;
        }
    }, { passive: false });
}

function init() {
    setupZoomPrevention();
    loadProfile(activeProfile);
    setTheme(activeTheme);
    setupWebSocket();
    setupControls();
    setupEditMode();
    setupGyro();

    sizeSlider.addEventListener('input', (e) => {
        uiScale = e.target.value;
        document.documentElement.style.setProperty('--btn-scale', uiScale);
        if(isEditMode) saveProfile();
    });

    sensSlider.addEventListener('input', (e) => {
        joystickSens = e.target.value;
        if(isEditMode) saveProfile();
    });

    profileSel.addEventListener('change', (e) => {
        activeProfile = e.target.value;
        loadProfile(activeProfile);
    });

    settingsToggleBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        if(settingsBar.classList.contains('hidden')) {
            settingsBar.classList.remove('hidden');
        } else {
            settingsBar.classList.add('hidden');
            if(isEditMode) toggleEditMode(); // Force exit edit mode if settings close
        }
    });

    // Close settings bar when clicking outside
    document.addEventListener('click', (e) => {
        if (!settingsBar.classList.contains('hidden') && 
            !settingsBar.contains(e.target) && 
            !settingsToggleBtn.contains(e.target)) {
            
            // Ignore outside clicks if we are currently dragging UI elements in edit mode
            if (isEditMode) return; 

            settingsBar.classList.add('hidden');
        }
    });

    document.addEventListener('touchstart', (e) => {
        // Because touch events might be used for controls, we check specifically 
        // to avoid closing if we touch inside settings
        if (!settingsBar.classList.contains('hidden') && 
            !settingsBar.contains(e.target) && 
            !settingsToggleBtn.contains(e.target)) {
            
            if (isEditMode) return;

            settingsBar.classList.add('hidden');
        }
    }, { passive: true });
}


// --- PROFILES & THEMES ---
function setTheme(theme) {
    document.body.classList.remove('theme-ps5');
    if (theme === 'ps5') {
        document.body.classList.add('theme-ps5');
        document.getElementById('btn-a').querySelector('span').innerText = '✕';
        document.getElementById('btn-b').querySelector('span').innerText = '○';
        document.getElementById('btn-x').querySelector('span').innerText = '□';
        document.getElementById('btn-y').querySelector('span').innerText = '△';
        document.getElementById('home-icon').innerText = 'PS';
        document.getElementById('home-icon').className = 'font-bold text-xl text-blue-400';
    } else {
        document.getElementById('btn-a').querySelector('span').innerText = 'A';
        document.getElementById('btn-b').querySelector('span').innerText = 'B';
        document.getElementById('btn-x').querySelector('span').innerText = 'X';
        document.getElementById('btn-y').querySelector('span').innerText = 'Y';
        document.getElementById('home-icon').innerText = 'X';
        document.getElementById('home-icon').className = 'font-bold text-2xl text-emerald-400';
    }
}

function saveProfile() {
    const layout = {};
    scalableElements.forEach(el => {
        if(el) {
            layout[el.id] = { left: el.style.left, top: el.style.top, right: el.style.right, bottom: el.style.bottom };
        }
    });
    
    const profileData = {
        layout,
        scale: uiScale,
        sens: joystickSens,
        gyro: useGyro
    };
    
    localStorage.setItem(`gamepad_${activeProfile}`, JSON.stringify(profileData));
}

function loadProfile(profileName) {
    const data = localStorage.getItem(`gamepad_${profileName}`);
    if (data) {
        try {
            const profile = JSON.parse(data);
            
            // Apply Layout
            if(profile.layout) {
                Object.keys(profile.layout).forEach(id => {
                    const el = document.getElementById(id);
                    if (el) {
                        if(profile.layout[id].left) el.style.left = profile.layout[id].left;
                        if(profile.layout[id].top) el.style.top = profile.layout[id].top;
                        if(profile.layout[id].right) el.style.right = profile.layout[id].right;
                        if(profile.layout[id].bottom) el.style.bottom = profile.layout[id].bottom;
                    }
                });
            }

            // Apply Settings
            if(profile.scale) {
                uiScale = profile.scale;
                sizeSlider.value = uiScale;
                document.documentElement.style.setProperty('--btn-scale', uiScale);
            }
            if(profile.sens) {
                joystickSens = profile.sens;
                sensSlider.value = joystickSens;
            }
            if(profile.gyro !== undefined) {
                useGyro = profile.gyro;
                gyroToggle.checked = useGyro;
                updateGyroUI();
            }
        } catch(e) { console.error("Profile load failed", e); }
    }
}


// --- EDIT MODE (DRAG & DROP) ---
let draggedEl = null;
let dragOffset = { x: 0, y: 0 };

function toggleEditMode() {
    isEditMode = !isEditMode;
    editBtn.textContent = isEditMode ? "Save Layout" : "Edit Layout";
    
    if (isEditMode) {
        editBtn.classList.replace('text-yellow-400', 'text-white');
        editBtn.classList.replace('bg-yellow-500/20', 'bg-red-500/80');
        editBtn.classList.replace('border-yellow-500/50', 'border-red-500');
        
        scalableElements.forEach(el => {
            if(el) {
                el.classList.add('edit-mode-active');
            }
        });
        
        // Setup Drag Listeners globally while in edit mode
        document.addEventListener('touchstart', handleDragStart, {passive: false});
        document.addEventListener('touchmove', handleDragMove, {passive: false});
        document.addEventListener('touchend', handleDragEnd);
        
        // For Mouse users testing locally
        document.addEventListener('mousedown', handleDragStart);
        document.addEventListener('mousemove', handleDragMove);
        document.addEventListener('mouseup', handleDragEnd);

    } else {
        editBtn.classList.replace('text-white', 'text-yellow-400');
        editBtn.classList.replace('bg-red-500/80', 'bg-yellow-500/20');
        editBtn.classList.replace('border-red-500', 'border-yellow-500/50');
        
        scalableElements.forEach(el => {
            if(el) {
                el.classList.remove('edit-mode-active');
            }
        });
        
        document.removeEventListener('touchstart', handleDragStart);
        document.removeEventListener('touchmove', handleDragMove);
        document.removeEventListener('touchend', handleDragEnd);
        document.removeEventListener('mousedown', handleDragStart);
        document.removeEventListener('mousemove', handleDragMove);
        document.removeEventListener('mouseup', handleDragEnd);
        
        saveProfile();
    }
}

function handleDragStart(e) {
    if (!isEditMode) return;
    
    const target = e.target.closest('.scalable-control');
    if (!target) return;
    
    e.preventDefault(); // Prevent scrolling while dragging wrappers
    draggedEl = target;
    
    const clientX = e.touches ? e.touches[0].clientX : e.clientX;
    const clientY = e.touches ? e.touches[0].clientY : e.clientY;
    
    const rect = draggedEl.getBoundingClientRect();
    
    // We calculate offset relative to left/top explicitly
    dragOffset.x = clientX - rect.left;
    dragOffset.y = clientY - rect.top;
    
    // Clear right/bottom to avoid CSS conflicts when forcing left/top
    draggedEl.style.right = 'auto';
    draggedEl.style.bottom = 'auto';
}

function handleDragMove(e) {
    if (!isEditMode || !draggedEl) return;
    e.preventDefault();
    
    const clientX = e.touches ? e.touches[0].clientX : e.clientX;
    const clientY = e.touches ? e.touches[0].clientY : e.clientY;
    
    // Convert to absolute px positioning dynamically
    const newLeft = clientX - dragOffset.x;
    const newTop = clientY - dragOffset.y;
    
    draggedEl.style.left = `${newLeft}px`;
    draggedEl.style.top = `${newTop}px`;
}

function handleDragEnd() {
    draggedEl = null;
}

function setupEditMode() {
    editBtn.addEventListener('click', toggleEditMode);
}


// --- HARDWARE / INPUT HANDLING  ---

function setupControls() {
    // Buttons setup
    document.querySelectorAll('[data-btn]').forEach(btn => {
        btn.addEventListener('touchstart', (e) => {
            if (isEditMode) return;
            e.preventDefault(); // crucial to stop context menus / selections
            for (let i = 0; i < e.changedTouches.length; i++) {
                currentTouches[e.changedTouches[i].identifier] = btn;
            }
            pressButton(btn);
        }, { passive: false });

        btn.addEventListener('touchend', (e) => {
            if (isEditMode) return;
            e.preventDefault();
            for (let i = 0; i < e.changedTouches.length; i++) {
                delete currentTouches[e.changedTouches[i].identifier];
            }
            releaseButton(btn);
        }, { passive: false });
        
        btn.addEventListener('touchcancel', (e) => releaseButton(btn));
        
        // Mouse fallback
        btn.addEventListener('mousedown', (e) => { if(!isEditMode) pressButton(btn); });
        btn.addEventListener('mouseup', (e) => { if(!isEditMode) releaseButton(btn); });
        btn.addEventListener('mouseleave', (e) => { if(!isEditMode) releaseButton(btn); });
    });

    // Left Stick (Physical)
    const baseL = document.getElementById('base-left');
    const stickL = document.getElementById('stick-left');
    setupJoystick(baseL, stickL, 'ABS_X', 'ABS_Y');

    // Right Stick (Physical - Only active if Gyro is OFF)
    const baseR = document.getElementById('base-right');
    const stickR = document.getElementById('stick-right');
    setupJoystick(baseR, stickR, 'ABS_RX', 'ABS_RY', () => !useGyro);
}

function hapticPulse() {
    if (navigator.vibrate) {
        navigator.vibrate(15);
    }
}

function pressButton(el) {
    if (!el.classList.contains('active')) {
        el.classList.add('active');
        const key = el.getAttribute('data-btn');
        if (key && btnMap[key]) {
            sendUpdate(btnMap[key]);
            hapticPulse();
        }
    }
}

function releaseButton(el) {
    el.classList.remove('active');
    const key = el.getAttribute('data-btn');
    if (key && btnMap[key]) {
        // Special logic for DPAD/Triggers
        if (btnMap[key].includes(':')) {
            const axisName = btnMap[key].split(':')[0];
            // Send 0 to reset axis
            sendUpdate(`${axisName}:0`);
        } else {
            sendUpdate(`!${btnMap[key]}`);
        }
    }
}

function setupJoystick(base, stick, axisX, axisY, conditionCallback = null) {
    let joystickState = { active: false, id: null };
    const maxDistance = 70; // Pixel deadzone constraint

    base.addEventListener('touchstart', handleStart, {passive: false});
    document.addEventListener('touchmove', handleMove, {passive: false});
    document.addEventListener('touchend', handleEnd);
    document.addEventListener('touchcancel', handleEnd);
    
    // Mouse
    base.addEventListener('mousedown', handleStart);
    document.addEventListener('mousemove', handleMove);
    document.addEventListener('mouseup', handleEnd);

    function handleStart(e) {
        if (isEditMode) return;
        if (conditionCallback && conditionCallback() === false) return;
        
        // Find if any of the new touches are on this specific base
        if (e.changedTouches) {
            let foundTouch = null;
            for (let i = 0; i < e.changedTouches.length; i++) {
                const touch = e.changedTouches[i];
                // Prevent multi-binding the same touch by checking element boundaries loosely
                // or just relying on the fact that the touchstart fired on *our* base element
                if (e.target === base || base.contains(e.target)) {
                    foundTouch = touch;
                    break;
                }
            }
            if (!foundTouch) return;
            joystickState.id = foundTouch.identifier;
        } else {
            joystickState.id = 'mouse';
        }

        e.preventDefault();
        joystickState.active = true;
        stick.classList.add('stick-active');
        stick.style.transition = 'none';
        
        updateJoystickPosition(e);
    }

    function handleMove(e) {
        if (!joystickState.active || isEditMode) return;
        if (conditionCallback && conditionCallback() === false) return;
        
        let clientX, clientY;
        if (e.touches) {
            for (let i = 0; i < e.touches.length; i++) {
                if (e.touches[i].identifier === joystickState.id) {
                    clientX = e.touches[i].clientX;
                    clientY = e.touches[i].clientY;
                    break;
                }
            }
            if(clientX === undefined) return;
        } else {
            clientX = e.clientX;
            clientY = e.clientY;
        }

        const rect = base.getBoundingClientRect();
        // Calculate center of base relative to viewport
        const centerX = rect.left + rect.width / 2;
        const centerY = rect.top + rect.height / 2;

        let deltaX = clientX - centerX;
        let deltaY = clientY - centerY;

        const distance = Math.min(Math.sqrt(deltaX*deltaX + deltaY*deltaY), maxDistance);
        const angle = Math.atan2(deltaY, deltaX);

        const x = distance * Math.cos(angle);
        const y = distance * Math.sin(angle);

        stick.style.transform = `translate(${x}px, ${y}px)`;

        // Normalize -1 to 1, apply sensitivity
        let nx = (x / maxDistance) * joystickSens;
        let ny = (y / maxDistance) * joystickSens;
        
        // Clamp
        nx = Math.max(-1, Math.min(1, nx));
        ny = Math.max(-1, Math.min(1, ny));

        // Scale to 16bit integer (-32768 to 32767)
        const iX = Math.round(nx * 32767);
        const iY = Math.round(ny * 32767);

        sendUpdate(`${axisX}:${iX}`);
        sendUpdate(`${axisY}:${iY}`);
    }

    function handleEnd(e) {
        if (!joystickState.active) return;
        
        if (e.changedTouches) {
            let found = false;
            for (let i = 0; i < e.changedTouches.length; i++) {
                if (e.changedTouches[i].identifier === joystickState.id) {
                    found = true; break;
                }
            }
            if(!found) return;
        }

        joystickState.active = false;
        joystickState.id = null;
        stick.classList.remove('stick-active');
        stick.style.transition = 'transform 0.2s cubic-bezier(0.4, 0, 0.2, 1)';
        stick.style.transform = 'translate(0px, 0px)';
        
        sendUpdate(`${axisX}:0`);
        sendUpdate(`${axisY}:0`);
    }
    
    // Initial Helper
    function updateJoystickPosition(e) { 
        // Create a synthetic event that looks like touchmove to reuse logic 
        let tempEvent = { touches: e.touches || e.changedTouches, clientX: e.clientX, clientY: e.clientY };
        handleMove(tempEvent); 
    }
}

// --- GYROSCOPE (Phone Steering) ---
function setupGyro() {
    gyroToggle.addEventListener('change', (e) => {
        useGyro = e.target.checked;
        saveProfile();
        updateGyroUI();
        
        if (useGyro && typeof DeviceOrientationEvent !== 'undefined') {
            if (typeof DeviceOrientationEvent.requestPermission === 'function') {
                DeviceOrientationEvent.requestPermission()
                    .then(state => {
                        if (state === 'granted') {
                            window.addEventListener('deviceorientation', handleGyro);
                            calibrateGyro();
                        } else {
                            alert("Gyroscope permission denied.");
                            useGyro = false;
                            gyroToggle.checked = false;
                            updateGyroUI();
                        }
                    })
                    .catch(console.error);
            } else {
                window.addEventListener('deviceorientation', handleGyro);
                calibrateGyro();
            }
        } else {
            window.removeEventListener('deviceorientation', handleGyro);
            sendUpdate(`ABS_RX:0`);
            sendUpdate(`ABS_RY:0`);
        }
    });

    calibrateBtn.addEventListener('click', calibrateGyro);
}

function updateGyroUI() {
    if (useGyro) {
        gyroIndicator.classList.replace('bg-white/10', 'bg-emerald-500');
        gyroIndicator.firstElementChild.classList.add('translate-x-4');
        calibrateBtn.classList.remove('hidden');
        document.getElementById('base-right').style.opacity = '0.3';
    } else {
        gyroIndicator.classList.replace('bg-emerald-500', 'bg-white/10');
        gyroIndicator.firstElementChild.classList.remove('translate-x-4');
        calibrateBtn.classList.add('hidden');
        document.getElementById('base-right').style.opacity = '1';
    }
}

let latestGyro = { beta: 0, gamma: 0 };
function handleGyro(e) {
    if (!useGyro || !isConnected) return;
    latestGyro.beta = e.beta;
    latestGyro.gamma = e.gamma;
    
    // Landscape Mode Assumption (Top of phone is Right or Left)
    // Map phone tilt directly to Right Stick X/Y
    
    // Sensitivity Multiplier
    const multi = joystickSens * 2;
    
    // Calculate difference from calibrated center
    let steerX = (latestGyro.beta - gyroOffset.beta) * multi;
    let steerY = (latestGyro.gamma - gyroOffset.gamma) * multi;

    // Normalize roughly (e.g., 45 degrees tilt = max)
    let nx = steerX / 45.0;
    let ny = steerY / 45.0;

    nx = Math.max(-1, Math.min(1, nx));
    ny = Math.max(-1, Math.min(1, ny));

    const iX = Math.round(nx * 32767);
    const iY = Math.round(ny * 32767);

    // Send to Right Stick
    sendUpdate(`ABS_RX:${iX}`);
    // sendUpdate(`ABS_RY:${iY}`); // Usually steering only needs X in racing 
}

function calibrateGyro() {
    gyroOffset.beta = latestGyro.beta;
    gyroOffset.gamma = latestGyro.gamma;
    calibrateBtn.textContent = "Done";
    calibrateBtn.classList.replace('border-emerald-500/50', 'border-white');
    setTimeout(() => {
        calibrateBtn.textContent = "Calibrate";
        calibrateBtn.classList.replace('border-white', 'border-emerald-500/50');
    }, 1000);
}


// --- WEBSOCKETS ---
function setupWebSocket() {
    connectBtn.addEventListener('click', () => {
        if (!isConnected) {
            connect();
        } else {
            ws.close();
        }
    });

    // Auto-fetch config from server then connect
    fetch('/api/config')
        .then(res => res.json())
        .then(config => {
            if (config.ws_port) wsPort = config.ws_port;
            if (config.ws_protocol) wsProtocol = config.ws_protocol;
            connect();
        })
        .catch(e => {
            console.error("Config fetch failed, using fallback ports.");
            wsProtocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
            wsPort = window.location.protocol === 'https:' ? 5443 : 5005;
            connect();
        });
}

function connect() {
    const wsUrl = `${wsProtocol}://${window.location.hostname}:${wsPort}`;
    connectBtn.textContent = "Connecting...";
    
    try {
        ws = new WebSocket(wsUrl);
        
        ws.onopen = () => {
            isConnected = true;
            connectBtn.textContent = "Connected";
            connectBtn.classList.replace('bg-blue-500/20', 'bg-emerald-500/20');
            connectBtn.classList.replace('text-blue-400', 'text-emerald-400');
            connectBtn.classList.replace('border-blue-500/50', 'border-emerald-500/50');
        };

        ws.onclose = () => {
            isConnected = false;
            connectBtn.textContent = "Connect PC";
            connectBtn.classList.replace('bg-emerald-500/20', 'bg-red-500/20');
            connectBtn.classList.replace('text-emerald-400', 'text-red-400');
            connectBtn.classList.replace('border-emerald-500/50', 'border-red-500/50');
            
            // Retry
            setTimeout(connect, 3000);
        };

        ws.onmessage = (e) => {
            // Handle server messages (slot id)
            if(e.data.startsWith('S:')) {
                console.log("Gamepad Slot:", e.data.substring(2));
            }
        };

        ws.onerror = (e) => {
            console.error("WebSocket Error:", e);
        };
        
    } catch (e) {
        console.error("WebSocket Exception", e);
    }
}

function sendUpdate(data) {
    if (isConnected && ws.readyState === WebSocket.OPEN) {
        ws.send(data);
    }
}

// Kickoff
window.onload = init;
