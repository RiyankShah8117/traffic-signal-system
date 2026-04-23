"""
Traffic Signal Control System - Web Server
============================================
Flask + SocketIO server for real-time web visualization.
"""

from flask import Flask, render_template, send_from_directory, jsonify, request
from flask_socketio import SocketIO, emit
from flask_cors import CORS
import threading
import time
import os

from traffic_ai import TrafficSimulation, Direction

app = Flask(__name__, static_folder="static", template_folder=".")
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# Global simulation instance
simulation = TrafficSimulation()
sim_thread = None
sim_running = False


@app.route("/")
def index():
    """Serve the main visualization page."""
    return send_from_directory(".", "index.html")


@app.route("/static/<path:filename>")
def serve_static(filename):
    """Serve static files (CSS, JS)."""
    return send_from_directory("static", filename)


@app.route("/api/state")
def get_state():
    """REST endpoint: Get current simulation state."""
    return jsonify(simulation.get_state())


@app.route("/api/reset", methods=["POST"])
def reset_simulation():
    """REST endpoint: Reset the simulation."""
    global simulation
    simulation = TrafficSimulation()
    return jsonify({"status": "reset"})


def simulation_loop():
    """Background thread: Run the simulation and emit state updates."""
    global sim_running
    while sim_running:
        state = simulation.tick()
        socketio.emit("state_update", state)
        time.sleep(max(0.2, 1.0 / simulation.simulation_speed))


@socketio.on("connect")
def handle_connect():
    """Client connected."""
    print("[Server] Client connected")
    emit("state_update", simulation.get_state())


@socketio.on("start_simulation")
def handle_start():
    """Start the simulation loop."""
    global sim_thread, sim_running
    if not sim_running:
        sim_running = True
        sim_thread = threading.Thread(target=simulation_loop, daemon=True)
        sim_thread.start()
        emit("simulation_status", {"running": True})
        print("[Server] Simulation started")


@socketio.on("stop_simulation")
def handle_stop():
    """Stop the simulation loop."""
    global sim_running
    sim_running = False
    emit("simulation_status", {"running": False})
    print("[Server] Simulation stopped")


@socketio.on("reset_simulation")
def handle_reset():
    """Reset the simulation."""
    global simulation, sim_running
    sim_running = False
    time.sleep(0.3)
    simulation = TrafficSimulation()
    emit("state_update", simulation.get_state())
    emit("simulation_status", {"running": False})
    print("[Server] Simulation reset")


@socketio.on("set_speed")
def handle_speed(data):
    """Change simulation speed."""
    speed = data.get("speed", 1.0)
    simulation.simulation_speed = max(0.5, min(speed, 5.0))
    print(f"[Server] Speed set to {simulation.simulation_speed}x")


@socketio.on("set_arrival_rate")
def handle_arrival_rate(data):
    """Set arrival rate for a direction."""
    direction_str = data.get("direction", "")
    rate = data.get("rate", 0.3)
    try:
        direction = Direction(direction_str)
        simulation.set_arrival_rate(direction, rate)
        print(f"[Server] {direction.value} arrival rate set to {rate}")
    except ValueError:
        pass


if __name__ == "__main__":
    print("=" * 60)
    print("  AI Traffic Signal Control System")
    print("  Open http://localhost:5000 in your browser")
    print("=" * 60)
    socketio.run(app, host="0.0.0.0", port=5000, debug=False, allow_unsafe_werkzeug=True)
