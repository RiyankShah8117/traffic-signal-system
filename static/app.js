/**
 * AI Traffic Signal Control System - Frontend Application
 * ========================================================
 * Real-time visualization and control interface.
 * Connects to the Python Flask-SocketIO backend.
 */

// --- State ---
let isRunning = false;
let lastState = null;
let previousGreen = null;
let logCount = 0;
const MAX_LOG_ENTRIES = 50;

// --- SocketIO Connection ---
const socket = io();

socket.on('connect', () => {
    addLog('Connected to server', 'info');
});

socket.on('disconnect', () => {
    addLog('Disconnected from server', 'warning');
    updateStatus(false);
});

socket.on('state_update', (state) => {
    lastState = state;
    updateUI(state);
});

socket.on('simulation_status', (data) => {
    updateStatus(data.running);
});

// --- Control Functions ---
function startSimulation() {
    socket.emit('start_simulation');
    updateStatus(true);
    addLog('Simulation started', 'info');
}

function stopSimulation() {
    socket.emit('stop_simulation');
    updateStatus(false);
    addLog('Simulation paused', 'warning');
}

function resetSimulation() {
    socket.emit('reset_simulation');
    updateStatus(false);
    previousGreen = null;
    addLog('Simulation reset', 'info');
    // Clear vehicle dots
    ['north', 'south', 'east', 'west'].forEach(dir => {
        document.getElementById(`queue-${dir}`).innerHTML = '';
    });
}

function setSpeed(value) {
    document.getElementById('speed-value').textContent = parseFloat(value).toFixed(1);
    socket.emit('set_speed', { speed: parseFloat(value) });
}

function setRate(direction, value) {
    const val = parseFloat(value).toFixed(2);
    document.getElementById(`rate-${direction}`).textContent = val;
    socket.emit('set_arrival_rate', { direction: direction, rate: parseFloat(value) });
}

// --- UI Update ---
function updateStatus(running) {
    isRunning = running;
    const badge = document.getElementById('status-badge');
    const statusText = badge.querySelector('.status-text');
    const btnStart = document.getElementById('btn-start');
    const btnStop = document.getElementById('btn-stop');

    if (running) {
        badge.classList.add('running');
        statusText.textContent = 'Running';
        btnStart.disabled = true;
        btnStop.disabled = false;
    } else {
        badge.classList.remove('running');
        statusText.textContent = 'Idle';
        btnStart.disabled = false;
        btnStop.disabled = true;
    }
}

function updateUI(state) {
    if (!state) return;

    // Elapsed time
    const elapsed = state.time_elapsed;
    const mins = Math.floor(elapsed / 60);
    const secs = Math.floor(elapsed % 60);
    document.getElementById('elapsed-time').textContent =
        `${mins}:${secs.toString().padStart(2, '0')}`;

    // Stats
    document.getElementById('total-throughput').textContent = state.stats.total_throughput;
    document.getElementById('total-cycles').textContent = state.stats.cycles_completed;

    let totalWaiting = 0;
    let totalPassed = 0;

    // Update each lane
    const directions = ['north', 'south', 'east', 'west'];
    directions.forEach(dir => {
        const lane = state.lanes[dir];
        if (!lane) return;

        totalWaiting += lane.vehicle_count;
        totalPassed += lane.vehicles_passed;

        // Signal lights
        updateSignalLight(dir, lane.signal);

        // Vehicle count on intersection
        const infoEl = document.getElementById(`info-${dir}`);
        infoEl.querySelector('.count').textContent = lane.vehicle_count;

        // Timer badge
        const timerBadge = document.getElementById(`timer-${dir}`);
        if (dir === state.current_green) {
            timerBadge.textContent = `${state.phase_time_remaining}s`;
            timerBadge.style.color = state.is_yellow ? 'var(--signal-yellow)' : 'var(--signal-green)';
        } else {
            timerBadge.textContent = '';
        }

        // Vehicle queue dots
        updateVehicleQueue(dir, lane.vehicle_count);

        // Analytics panel
        document.getElementById(`metric-${dir}-waiting`).textContent = lane.vehicle_count;
        document.getElementById(`metric-${dir}-passed`).textContent = lane.vehicles_passed;
        document.getElementById(`metric-${dir}-wait`).textContent = `${lane.avg_wait_time}s`;
        document.getElementById(`metric-${dir}-priority`).textContent = lane.priority_score.toFixed(3);

        // Density bar
        document.getElementById(`density-${dir}`).style.width = `${lane.density * 100}%`;

        // Congestion badge
        const congBadge = document.getElementById(`cong-${dir}`);
        congBadge.textContent = lane.congestion;
        congBadge.className = `congestion-badge ${lane.congestion.toLowerCase()}`;

        // Lane card active state
        const laneCard = document.getElementById(`lane-card-${dir}`);
        if (dir === state.current_green) {
            laneCard.classList.add('active-green');
        } else {
            laneCard.classList.remove('active-green');
        }
    });

    document.getElementById('total-waiting').textContent = totalWaiting;

    // Efficiency score
    if (totalPassed + totalWaiting > 0) {
        const eff = Math.round((totalPassed / (totalPassed + totalWaiting)) * 100);
        document.getElementById('efficiency-score').textContent = `${eff}%`;
    }

    // Phase bar
    document.getElementById('phase-direction').textContent = state.current_green
        ? state.current_green.toUpperCase()
        : '--';

    const signalEmoji = state.is_yellow ? '🟡 YELLOW' : '🟢 GREEN';
    document.getElementById('phase-signal').textContent = signalEmoji;
    document.getElementById('phase-seconds').textContent = `${state.phase_time_remaining}s`;

    // Timer bar fill
    const currentLane = state.lanes[state.current_green];
    if (currentLane) {
        const maxTime = currentLane.green_time || 30;
        const pct = Math.max(0, Math.min(100, (state.phase_time_remaining / maxTime) * 100));
        const fillEl = document.getElementById('timer-bar-fill');
        fillEl.style.width = `${pct}%`;

        if (state.is_yellow) {
            fillEl.style.background = 'linear-gradient(90deg, var(--signal-yellow), #f59e0b)';
        } else if (pct < 25) {
            fillEl.style.background = 'linear-gradient(90deg, var(--signal-red), #f97316)';
        } else {
            fillEl.style.background = 'linear-gradient(90deg, var(--signal-green), var(--accent-cyan))';
        }
    }

    // Log signal changes
    if (previousGreen !== null && previousGreen !== state.current_green) {
        addLog(
            `Signal changed: ${state.current_green.toUpperCase()} is now GREEN ` +
            `(${currentLane ? currentLane.green_time + 's' : ''} allocated)`,
            'signal-change'
        );
    }
    previousGreen = state.current_green;
}

function updateSignalLight(direction, signalState) {
    const signalEl = document.getElementById(`signal-${direction}`);
    if (!signalEl) return;

    const lights = signalEl.querySelectorAll('.light');
    lights.forEach(l => l.classList.remove('active'));

    if (signalState === 'red') {
        lights[0].classList.add('active');
    } else if (signalState === 'yellow') {
        lights[1].classList.add('active');
    } else if (signalState === 'green') {
        lights[2].classList.add('active');
    }
}

function updateVehicleQueue(direction, count) {
    const queueEl = document.getElementById(`queue-${direction}`);
    const maxDots = 12;
    const displayCount = Math.min(count, maxDots);

    // Only update if count changed
    if (queueEl.children.length === displayCount) return;

    queueEl.innerHTML = '';
    for (let i = 0; i < displayCount; i++) {
        const dot = document.createElement('div');
        dot.className = 'vehicle-dot';
        dot.style.animationDelay = `${i * 0.05}s`;

        // Color based on density
        if (count > 15) {
            dot.style.background = 'var(--signal-red)';
        } else if (count > 8) {
            dot.style.background = 'var(--signal-yellow)';
        }

        queueEl.appendChild(dot);
    }
}

function addLog(message, type = '') {
    const container = document.getElementById('log-container');
    const entry = document.createElement('div');
    entry.className = `log-entry ${type}`;

    const time = lastState ? formatTime(lastState.time_elapsed) : '0:00';
    entry.textContent = `[${time}] ${message}`;

    container.insertBefore(entry, container.firstChild);
    logCount++;

    // Limit log entries
    while (container.children.length > MAX_LOG_ENTRIES) {
        container.removeChild(container.lastChild);
    }
}

function formatTime(seconds) {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
}

// --- Initialize ---
document.addEventListener('DOMContentLoaded', () => {
    // Set initial slider values display
    document.getElementById('speed-value').textContent = '1.0';
});
