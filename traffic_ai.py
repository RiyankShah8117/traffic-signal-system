"""
AI-Based Traffic Signal Control System
=======================================
Core simulation engine with adaptive signal timing.

This module implements:
- Vehicle generation and counting using simulated sensors
- Adaptive AI logic that adjusts green signal duration based on traffic density
- A 4-way intersection model (North, South, East, West)
- Real-time traffic flow metrics and analytics
"""

import random
import time
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Optional


class SignalState(Enum):
    """Traffic signal states."""
    RED = "red"
    YELLOW = "yellow"
    GREEN = "green"


class Direction(Enum):
    """Intersection directions."""
    NORTH = "north"
    SOUTH = "south"
    EAST = "east"
    WEST = "west"


@dataclass
class Vehicle:
    """Represents a vehicle in the simulation."""
    id: int
    direction: Direction
    arrival_time: float
    wait_time: float = 0.0
    has_passed: bool = False
    speed: float = 0.0  # 0 = stopped, 1 = moving
    position: float = 0.0  # 0 to 1, where 1 = through intersection


@dataclass
class TrafficLane:
    """Represents a single lane/direction at the intersection."""
    direction: Direction
    signal: SignalState = SignalState.RED
    vehicles_waiting: List[Vehicle] = field(default_factory=list)
    vehicles_passed: int = 0
    total_vehicles_arrived: int = 0
    green_time: float = 30.0  # Current allocated green time in seconds
    min_green_time: float = 10.0
    max_green_time: float = 60.0
    default_green_time: float = 30.0
    density_history: List[int] = field(default_factory=list)
    avg_wait_time: float = 0.0
    total_wait_time: float = 0.0

    @property
    def vehicle_count(self) -> int:
        """Simulated sensor: count vehicles waiting."""
        return len(self.vehicles_waiting)

    @property
    def density(self) -> float:
        """Traffic density score (0.0 to 1.0)."""
        max_capacity = 20  # Max vehicles before congestion
        return min(self.vehicle_count / max_capacity, 1.0)

    @property
    def congestion_level(self) -> str:
        """Human-readable congestion level."""
        d = self.density
        if d < 0.25:
            return "Low"
        elif d < 0.5:
            return "Moderate"
        elif d < 0.75:
            return "High"
        else:
            return "Critical"


class AdaptiveSignalController:
    """
    AI-based Adaptive Traffic Signal Controller.
    
    Uses a weighted scoring algorithm to dynamically allocate green time
    based on multiple factors:
    - Current vehicle count (density)
    - Historical traffic patterns
    - Average wait time per direction
    - Emergency vehicle priority (future)
    
    The algorithm mimics reinforcement learning by adjusting signal timing
    to minimize overall intersection wait time.
    """

    # Weights for the scoring function
    WEIGHT_DENSITY = 0.40
    WEIGHT_WAIT_TIME = 0.35
    WEIGHT_TREND = 0.25

    def __init__(self):
        self.cycle_count = 0
        self.total_throughput = 0
        self.optimization_history: List[Dict] = []

    def calculate_priority_score(self, lane: TrafficLane) -> float:
        """
        Calculate a priority score for a lane using multiple factors.
        Higher score = more urgently needs green time.
        """
        # Factor 1: Current density (0 to 1)
        density_score = lane.density

        # Factor 2: Normalized wait time
        max_acceptable_wait = 90.0  # seconds
        wait_score = min(lane.avg_wait_time / max_acceptable_wait, 1.0)

        # Factor 3: Trend analysis - is traffic increasing?
        trend_score = 0.0
        if len(lane.density_history) >= 3:
            recent = lane.density_history[-3:]
            if recent[-1] > recent[0]:
                trend_score = min((recent[-1] - recent[0]) / 10.0, 1.0)

        # Weighted combination
        score = (
            self.WEIGHT_DENSITY * density_score +
            self.WEIGHT_WAIT_TIME * wait_score +
            self.WEIGHT_TREND * trend_score
        )

        return round(score, 4)

    def calculate_optimal_green_time(self, lane: TrafficLane, total_cycle_time: float = 120.0) -> float:
        """
        Dynamically calculate optimal green time for a lane.
        Uses a proportional allocation strategy with bounds.
        """
        score = self.calculate_priority_score(lane)

        # Base allocation proportional to score
        allocated = lane.default_green_time * (1 + score)

        # Apply bounds
        allocated = max(lane.min_green_time, min(allocated, lane.max_green_time))

        # Ensure vehicles have enough time to clear
        # Assume ~2 seconds per vehicle to pass
        min_needed = lane.vehicle_count * 2.0
        allocated = max(allocated, min(min_needed, lane.max_green_time))

        return round(allocated, 1)

    def determine_next_phase(self, lanes: Dict[Direction, TrafficLane]) -> Direction:
        """
        Determine which direction should get the next green signal.
        Selects the lane with the highest priority score.
        """
        scores = {}
        for direction, lane in lanes.items():
            if lane.signal != SignalState.GREEN:
                scores[direction] = self.calculate_priority_score(lane)

        if not scores:
            # All lanes are green (shouldn't happen), pick first non-green
            return Direction.NORTH

        # Select direction with highest score
        best_direction = max(scores, key=scores.get)
        return best_direction

    def get_optimization_stats(self) -> Dict:
        """Return current optimization metrics."""
        return {
            "cycles_completed": self.cycle_count,
            "total_throughput": self.total_throughput,
            "algorithm": "Adaptive Weighted Scoring",
            "weights": {
                "density": self.WEIGHT_DENSITY,
                "wait_time": self.WEIGHT_WAIT_TIME,
                "trend": self.WEIGHT_TREND
            }
        }


class TrafficSimulation:
    """
    Main traffic intersection simulation.
    
    Simulates a 4-way intersection with:
    - Random vehicle arrivals following Poisson distribution
    - AI-controlled adaptive signal timing
    - Real-time metrics and analytics
    """

    def __init__(self):
        self.lanes: Dict[Direction, TrafficLane] = {
            d: TrafficLane(direction=d) for d in Direction
        }
        self.controller = AdaptiveSignalController()
        self.current_green: Optional[Direction] = Direction.NORTH
        self.time_elapsed: float = 0.0
        self.phase_time_remaining: float = 30.0
        self.yellow_duration: float = 3.0
        self.is_yellow_phase: bool = False
        self.vehicle_id_counter: int = 0
        self.tick_rate: float = 1.0  # seconds per tick
        self.is_running: bool = False
        self.simulation_speed: float = 1.0

        # Traffic generation parameters per direction
        self.arrival_rates: Dict[Direction, float] = {
            Direction.NORTH: 0.3,
            Direction.SOUTH: 0.25,
            Direction.EAST: 0.4,
            Direction.WEST: 0.2,
        }

        # Initialize: North starts green
        self.lanes[Direction.NORTH].signal = SignalState.GREEN

    def set_arrival_rate(self, direction: Direction, rate: float):
        """Set vehicle arrival rate for a direction (vehicles per second)."""
        self.arrival_rates[direction] = max(0, min(rate, 1.0))

    def _generate_vehicles(self):
        """
        Generate vehicles using Poisson-like arrival process.
        Each direction has an independent arrival rate.
        """
        for direction in Direction:
            rate = self.arrival_rates[direction]
            # Poisson arrival: probability of at least one vehicle
            if random.random() < rate:
                num_vehicles = 1
                # Small chance of burst arrival
                if random.random() < 0.1:
                    num_vehicles = random.randint(2, 4)

                for _ in range(num_vehicles):
                    self.vehicle_id_counter += 1
                    vehicle = Vehicle(
                        id=self.vehicle_id_counter,
                        direction=direction,
                        arrival_time=self.time_elapsed,
                    )
                    self.lanes[direction].vehicles_waiting.append(vehicle)
                    self.lanes[direction].total_vehicles_arrived += 1

    def _process_green_lane(self):
        """Process vehicles through the currently green lane."""
        if self.current_green is None or self.is_yellow_phase:
            return

        lane = self.lanes[self.current_green]
        # Vehicles pass through at ~1 vehicle per 2 seconds
        vehicles_to_pass = min(len(lane.vehicles_waiting), max(1, int(self.tick_rate / 2)))

        for _ in range(vehicles_to_pass):
            if lane.vehicles_waiting:
                vehicle = lane.vehicles_waiting.pop(0)
                vehicle.has_passed = True
                vehicle.wait_time = self.time_elapsed - vehicle.arrival_time
                lane.vehicles_passed += 1
                lane.total_wait_time += vehicle.wait_time
                self.controller.total_throughput += 1

    def _update_wait_times(self):
        """Update average wait times for all lanes."""
        for direction, lane in self.lanes.items():
            if lane.vehicles_waiting:
                current_waits = [
                    self.time_elapsed - v.arrival_time for v in lane.vehicles_waiting
                ]
                lane.avg_wait_time = sum(current_waits) / len(current_waits)
            else:
                lane.avg_wait_time = max(0, lane.avg_wait_time - 0.5)

    def _update_density_history(self):
        """Record density data for trend analysis."""
        for lane in self.lanes.values():
            lane.density_history.append(lane.vehicle_count)
            # Keep last 20 data points
            if len(lane.density_history) > 20:
                lane.density_history.pop(0)

    def _switch_signal(self):
        """Handle signal switching with yellow phase."""
        if self.is_yellow_phase:
            # Yellow phase complete, switch to next green
            self.is_yellow_phase = False

            # Set current green to red
            if self.current_green:
                self.lanes[self.current_green].signal = SignalState.RED

            # AI determines next green
            next_green = self.controller.determine_next_phase(self.lanes)
            self.current_green = next_green
            self.lanes[next_green].signal = SignalState.GREEN

            # AI calculates optimal green time
            optimal_time = self.controller.calculate_optimal_green_time(
                self.lanes[next_green]
            )
            self.lanes[next_green].green_time = optimal_time
            self.phase_time_remaining = optimal_time

            self.controller.cycle_count += 1
        else:
            # Start yellow phase
            self.is_yellow_phase = True
            if self.current_green:
                self.lanes[self.current_green].signal = SignalState.YELLOW
            self.phase_time_remaining = self.yellow_duration

    def tick(self) -> Dict:
        """
        Advance simulation by one tick.
        Returns current state for the web UI.
        """
        # Generate new vehicles
        self._generate_vehicles()

        # Process green lane
        self._process_green_lane()

        # Update metrics
        self._update_wait_times()
        self._update_density_history()

        # Count down phase timer
        self.phase_time_remaining -= self.tick_rate
        if self.phase_time_remaining <= 0:
            self._switch_signal()

        self.time_elapsed += self.tick_rate

        return self.get_state()

    def get_state(self) -> Dict:
        """Get complete simulation state for the web UI."""
        lanes_data = {}
        for direction, lane in self.lanes.items():
            priority = self.controller.calculate_priority_score(lane)
            lanes_data[direction.value] = {
                "signal": lane.signal.value,
                "vehicle_count": lane.vehicle_count,
                "vehicles_passed": lane.vehicles_passed,
                "total_arrived": lane.total_vehicles_arrived,
                "density": round(lane.density, 3),
                "congestion": lane.congestion_level,
                "green_time": lane.green_time,
                "avg_wait_time": round(lane.avg_wait_time, 1),
                "priority_score": priority,
                "arrival_rate": self.arrival_rates[direction],
            }

        return {
            "time_elapsed": round(self.time_elapsed, 1),
            "current_green": self.current_green.value if self.current_green else None,
            "phase_time_remaining": round(max(0, self.phase_time_remaining), 1),
            "is_yellow": self.is_yellow_phase,
            "lanes": lanes_data,
            "stats": self.controller.get_optimization_stats(),
        }

    def reset(self):
        """Reset the simulation."""
        self.__init__()


# ============================================================
# Standalone console simulation (for testing without web UI)
# ============================================================
def run_console_simulation(duration: int = 60):
    """Run the simulation in console mode for testing."""
    sim = TrafficSimulation()
    print("=" * 70)
    print("  AI-Based Traffic Signal Control System - Console Mode")
    print("=" * 70)

    for tick in range(duration):
        state = sim.tick()
        if tick % 5 == 0:  # Print every 5 seconds
            print(f"\n--- Time: {state['time_elapsed']}s ---")
            print(f"Current Green: {state['current_green'].upper()} "
                  f"(Remaining: {state['phase_time_remaining']}s)")
            for d, data in state['lanes'].items():
                signal_icon = {"red": "🔴", "yellow": "🟡", "green": "🟢"}
                icon = signal_icon.get(data['signal'], "⚪")
                print(f"  {icon} {d.upper():6s} | Waiting: {data['vehicle_count']:3d} | "
                      f"Passed: {data['vehicles_passed']:3d} | "
                      f"Density: {data['density']:.2f} | "
                      f"Avg Wait: {data['avg_wait_time']:.1f}s | "
                      f"Priority: {data['priority_score']:.3f}")
        time.sleep(0.05)

    print("\n" + "=" * 70)
    print("  Simulation Complete")
    print(f"  Total vehicles processed: {state['stats']['total_throughput']}")
    print(f"  Cycles completed: {state['stats']['cycles_completed']}")
    print("=" * 70)


if __name__ == "__main__":
    run_console_simulation(120)
