"""The race environment (a Mesa model): cars moving round Silverstone, pit stops, crashes, the safety car, and the 12 agents."""
import json
import math
from dataclasses import dataclass, field

import mesa

from sim.driver import DriverAgent, tyre_word
from sim.messages import EVERYONE, MessageBoard
from sim.model import DATA, PACE_SPREAD, WEAR_LEVELS, LapModel
from sim.strategist import StrategistAgent
from sim.track import PIT_BOX_M, PIT_ENTRY_M, PIT_EXIT_M, Track

DT = 0.2                  # simulated seconds per step
GRID_GAP_M = 8.0
FOLLOW_GAP_M = 12.0       # closest a car can follow another when it cannot pass
SAFETY_CAR_GAP_M = 40.0   # cars line up this far apart behind the safety car
STOP_S = 2.5              # time stationary in the pit box
FIRST_LAP_EXTRA_S = 3.0   # standing start
CHECKPOINT_M = 100.0      # timing points used for the gaps
YELLOW_ZONE_M = 400.0
PLAN_HIGHLIGHT_S = 30.0   # how long a car is highlighted after its plan changed


@dataclass
class Car:
    code: str
    name: str
    team: str
    color: str
    pace: float               # seconds per lap compared with the average car (hidden from rivals)
    wear: float                # tyre wear multiplier (hidden from rivals)
    tyre: str
    dist: float                # metres from the start line, over the whole race
    used: set = field(default_factory=set)
    age: int = 0               # laps done on the current tyres
    stops: int = 0
    laps_done: int = 0
    state: str = "RUNNING"     # RUNNING, PIT, OUT or FINISHED
    in_pit: bool = False
    pit_tyre: str | None = None
    pit_speed: float = 0.0
    stop_left: float = 0.0
    stopped_in_box: bool = False
    lap_target: float = 0.0
    lap_start: float = 0.0
    lap_clean: bool = True
    last_lap: float | None = None
    finish_time: float | None = None
    stuck_s: float = 0.0
    crash_at: float | None = None
    plan_changed_at: float = -1e9
    history: list = field(default_factory=list)   # public lap times (the timing screen)
    checkpoints: dict = field(default_factory=dict)


class Race(mesa.Model):
    def __init__(self, seed=42):
        super().__init__(rng=seed)
        self.seed = seed
        self.model = LapModel()
        self.track = Track()
        self.board = MessageBoard()
        self.total_laps = self.model.laps
        self.pit_entry_m = PIT_ENTRY_M
        self.clock = 0.0
        self.started = False
        self.over = False
        self.flag = "GREEN"          # GREEN, YELLOW, SAFETY_CAR or CHEQUERED
        self.yellow = None
        self.safety_car_until = 0
        self.safety_car_count = 0
        self.crash_marks = []
        self.box_free_at = {}
        self.first_checkpoint = {}
        self.pass_attempts = {}
        self.track_order = {}

        teams = json.loads((DATA / "teams.json").read_text())
        drivers = [(team, d) for team in teams for d in team["drivers"]]
        mean_offset = sum(self.model.driver_offsets[d["code"]] for _, d in drivers) / len(drivers)
        self.cars = {}
        for team, d in sorted(drivers, key=lambda td: td[1]["real_grid"]):
            car = Car(d["code"], d["name"], team["name"], team["color"],
                      pace=PACE_SPREAD * (self.model.driver_offsets[d["code"]] - mean_offset),
                      wear=WEAR_LEVELS[d["wear_level"]], tyre=d["start_tyre"],
                      dist=-GRID_GAP_M * (len(self.cars) + 1), used={d["start_tyre"]})
            car.lap_target = self.target_lap_time(car, 1)
            self.cars[car.code] = car
        self.drivers = {code: DriverAgent(self, car) for code, car in self.cars.items()}
        self.strategists = {team["name"]: StrategistAgent(self, team["name"], [self.cars[d["code"]] for d in team["drivers"]])
                            for team in teams}

        # Both Ferraris crash at random points: the first brings a yellow flag, the second the safety car.
        ferraris = [car for car in self.cars.values() if car.team == "Ferrari"]
        self.random.shuffle(ferraris)
        for car, (low, high) in zip(ferraris, [(3, 6), (7, 10)]):
            car.crash_at = (self.random.randint(low, high) - 1 + self.random.uniform(0.15, 0.85)) * self.track.length

    # ------------------------------------------------------------------ helpers used by the agents
    @property
    def lap(self):
        leader = self.leader()
        return min(self.total_laps, leader.laps_done + 1) if leader else self.total_laps

    def leader(self):
        racing = [c for c in self.cars.values() if c.state in ("RUNNING", "PIT")]
        return max(racing, key=lambda c: c.dist, default=None)

    def stop_loss(self, lap):
        """Seconds lost by a stop at the end of `lap`: cheaper while the safety car is out."""
        if self.flag == "SAFETY_CAR" and lap < self.safety_car_until:
            return self.model.safety_car_pit_loss
        return self.model.pit_loss

    def target_lap_time(self, car, lap):
        t = self.model.lap_time(car.tyre, car.age + 1, lap, car.wear, car.pace) + self.random.gauss(0.0, self.model.noise)
        return t + (FIRST_LAP_EXTRA_S if lap == 1 else 0.0)

    def racing_order(self):
        return sorted((c for c in self.cars.values() if c.state in ("RUNNING", "PIT")), key=lambda c: -c.dist)

    def car_ahead(self, car):
        order = self.racing_order()
        i = order.index(car) if car in order else 0
        return order[i - 1] if i > 0 else None

    def car_behind(self, car):
        order = self.racing_order()
        i = order.index(car) if car in order else len(order)
        return order[i + 1] if i + 1 < len(order) else None

    def gap_to_leader(self, car):
        """Seconds behind the first car to pass the same timing point."""
        if not car.checkpoints:
            return 0.0
        index = max(car.checkpoints)
        return car.checkpoints[index] - self.first_checkpoint[index]

    def gap_between(self, car, rival):
        """Positive when `car` is ahead of `rival`, in seconds."""
        if abs(car.dist - rival.dist) > self.track.length / 2:
            return None
        return self.gap_to_leader(rival) - self.gap_to_leader(car)

    def post(self, sender, text, **data):
        return self.board.post(self.lap, sender, EVERYONE, "EVENT", text, **data)

    # ------------------------------------------------------------------ race control
    def start(self):
        self.started = True
        self.post("Race control", "Lights out! The race has started.")

    def crash(self, code, manual):
        car = self.cars[code]
        if car.state in ("OUT", "FINISHED"):
            return f"{car.name} is not racing."
        car.state, car.in_pit, car.pit_tyre, car.crash_at = "OUT", False, None, None
        corner = self.track.nearest_corner(car.dist)
        x, y = self.track.xy(car.dist)
        self.crash_marks.append({"code": code, "x": x, "y": y})
        self.post("Race control", f"{car.name} has crashed near Turn {corner} and is out of the race.")
        self.drivers[code].crashed(corner)
        if self.flag == "CHEQUERED":
            return f"{car.name} crashed after the finish flag."
        if manual or len(self.crash_marks) >= 2:
            self.deploy_safety_car()
            return f"{car.name} crashed. " + ("Safety car deployed." if self.flag == "SAFETY_CAR" else "No cars are left racing.")
        self.flag = "YELLOW"
        self.yellow = {"at": car.dist % self.track.length, "until": self.clock + self.model.base}
        self.post("Race control", f"Yellow flag near Turn {corner}: drivers must slow down there.")
        return f"{car.name} crashed. Yellow flag near Turn {corner}."

    def deploy_safety_car(self):
        leader = self.leader()
        if leader is None:
            return  # nobody left on track
        self.yellow = None
        self.safety_car_count += 1
        self.safety_car_until = leader.laps_done + 1 + self.model.safety_car_laps
        if self.flag != "SAFETY_CAR":
            self.flag = "SAFETY_CAR"
            self.post("Race control", "Safety car is out: everyone slows down and follows in a line. No overtaking.", safety_car=True)

    def race_control(self):
        for car in self.cars.values():
            if car.crash_at is not None and car.state == "RUNNING" and car.dist >= car.crash_at:
                self.crash(car.code, manual=False)
            if self.flag != "GREEN":
                car.lap_clean = False  # lap times under yellow or the safety car say nothing about tyre wear
        if self.flag == "YELLOW" and self.clock > self.yellow["until"]:
            self.flag, self.yellow = "GREEN", None
            self.post("Race control", "Track clear: green flag, racing as normal.")
        leader = self.leader()
        if self.flag == "SAFETY_CAR" and leader and leader.laps_done >= self.safety_car_until:
            self.flag = "GREEN"
            self.post("Race control", "The safety car is coming in. Racing starts again!", safety_car=False)
        if not any(c.state in ("RUNNING", "PIT") for c in self.cars.values()):
            self.over = True
            self.post("Race control", self.summary())

    def summary(self):
        winner = min((c for c in self.cars.values() if c.finish_time is not None), key=lambda c: c.finish_time, default=None)
        changes = [item for item in self.board.feed if hasattr(item, "cause")]
        count = {cause: sum(1 for c in changes if c.cause == cause) for cause in ("driver", "rival", "incident", "laps")}
        return (f"Race over. {winner.name if winner else 'Nobody'} wins! The strategists changed a plan {len(changes)} times: "
                f"{count['driver']} after a driver's message, {count['rival']} because of a rival team, "
                f"{count['incident']} because of the safety car, and {count['laps']} from new lap times.")

    # ------------------------------------------------------------------ physics
    def step(self):
        if not self.started or self.over:
            return
        self.clock += DT
        self.race_control()
        before = {code: car.dist for code, car in self.cars.items()}
        for car in self.cars.values():
            if car.state in ("RUNNING", "PIT"):
                self.move(car)
        self.keep_order(before)
        for car in self.cars.values():
            self.record_checkpoints(car, before[car.code])
        self.agents_by_type[DriverAgent].do("step")
        self.agents_by_type[StrategistAgent].do("step")

    def speed(self, car):
        if car.in_pit:
            return car.pit_speed
        d = car.dist % self.track.length
        speed = self.track.lap_integral / car.lap_target * self.track.speed_weight_at(d)
        if self.flag == "SAFETY_CAR":
            ahead = self.car_ahead(car)
            catching_up = ahead is not None and not ahead.in_pit and ahead.dist - car.dist > SAFETY_CAR_GAP_M + 20
            return speed if catching_up else speed / self.model.safety_car_factor
        if self.yellow and abs((d - self.yellow["at"] + self.track.length / 2) % self.track.length - self.track.length / 2) < YELLOW_ZONE_M:
            return speed * 0.85
        return speed

    def passes(self, car, before, after, mark):
        L = self.track.length
        return math.floor((after - mark) / L) > math.floor((before - mark) / L)

    def move(self, car):
        if car.in_pit:
            car.lap_clean = False  # in-laps and out-laps include the stop, so they say nothing about tyre wear
        if car.stop_left > 0:
            car.stop_left -= DT
            if car.stop_left <= 0:
                self.change_tyres(car)
            return
        before = car.dist
        after = before + self.speed(car) * DT
        if not car.in_pit and car.pit_tyre and self.passes(car, before, after, PIT_ENTRY_M):
            car.in_pit, car.state, car.lap_clean = True, "PIT", False
            lap_time = car.lap_target * (self.model.safety_car_factor if self.flag == "SAFETY_CAR" else 1.0)
            normal = self.track.segment_time(PIT_ENTRY_M, self.track.pit_length, lap_time)
            car.pit_speed = self.track.pit_length / (normal + self.stop_loss(car.laps_done + 1) - STOP_S)
            self.post("Timing screen", f"{car.name} came into the pit lane for new tyres.", pit_entry=car.code)
        elif car.in_pit and not car.stopped_in_box and self.passes(car, before, after, PIT_BOX_M):
            after = math.floor((after - PIT_BOX_M) / self.track.length) * self.track.length + PIT_BOX_M
            wait = max(0.0, self.box_free_at.get(car.team, 0.0) - self.clock)
            car.stop_left = wait + STOP_S
            car.stopped_in_box = True
            self.box_free_at[car.team] = self.clock + car.stop_left
        elif car.in_pit and car.stopped_in_box and self.passes(car, before, after, PIT_EXIT_M):
            car.in_pit, car.state, car.stopped_in_box = False, "RUNNING", False
        car.dist = after
        if math.floor(after / self.track.length) > math.floor(before / self.track.length) and before >= 0:
            self.complete_lap(car)  # leaving the grid (before < 0) starts lap 1 instead of finishing a lap

    def change_tyres(self, car):
        old = car.tyre
        car.tyre, car.age, car.pit_tyre = car.pit_tyre, 0, None
        car.used.add(car.tyre)
        car.stops += 1
        car.lap_target = self.target_lap_time(car, car.laps_done + 1)
        self.post("Timing screen", f"{car.name} changed from {tyre_word(old)} to {tyre_word(car.tyre)} tyres.")

    def complete_lap(self, car):
        lap_time = self.clock - car.lap_start
        car.laps_done += 1
        car.age += 1
        car.history.append({"lap": car.laps_done, "time": lap_time, "tyre": car.tyre, "age": car.age,
                            "stops": car.stops, "clean": car.lap_clean and car.laps_done > 1})
        car.last_lap, car.lap_start, car.lap_clean = lap_time, self.clock, True
        if car.laps_done >= self.total_laps and self.flag != "CHEQUERED":
            self.flag, self.yellow = "CHEQUERED", None
            self.post("Race control", f"Chequered flag! {car.name} wins the race.")
        if self.flag == "CHEQUERED":
            car.state, car.in_pit, car.finish_time = "FINISHED", False, self.clock
        else:
            car.lap_target = self.target_lap_time(car, car.laps_done + 1)

    def keep_order(self, before):
        """No passing through each other: a car stays behind unless it overtakes on a long straight."""
        on_track = sorted((c for c in self.cars.values() if c.state == "RUNNING" and c.stop_left <= 0), key=lambda c: -c.dist)
        safety_car = self.flag == "SAFETY_CAR"
        gap_needed = SAFETY_CAR_GAP_M if safety_car else FOLLOW_GAP_M
        for ahead, car in zip(on_track, on_track[1:]):
            gap = ahead.dist - car.dist
            if gap >= gap_needed:
                if gap > 3 * FOLLOW_GAP_M:
                    car.stuck_s = 0.0
                continue
            if not safety_car and self.may_pass(car, ahead):
                continue
            car.dist = max(before[car.code], ahead.dist - gap_needed)
            car.stuck_s += DT
            car.lap_clean = False
        self.announce_overtakes()

    def may_pass(self, car, ahead):
        """One overtaking attempt per straight, only for a car that is clearly faster (50% chance)."""
        straight = self.track.straight_at(car.dist)
        if straight is None or ahead.lap_target - car.lap_target < self.model.overtake_advantage:
            return False
        key = (car.code, ahead.code, car.laps_done, straight)
        if key not in self.pass_attempts:
            self.pass_attempts[key] = self.random.random() < 0.5
        return self.pass_attempts[key]

    def announce_overtakes(self):
        order = [c for c in sorted(self.cars.values(), key=lambda c: -c.dist) if c.state == "RUNNING" and not c.in_pit]
        previous, self.track_order = self.track_order, {c.code: i for i, c in enumerate(order)}
        for ahead, car in zip(order, order[1:]):
            if ahead.code in previous and car.code in previous and previous[ahead.code] > previous[car.code]:
                ahead.stuck_s = 0.0
                self.post("Timing screen", f"{ahead.name} overtook {car.name}.")

    def record_checkpoints(self, car, before):
        for index in range(math.floor(before / CHECKPOINT_M) + 1, math.floor(car.dist / CHECKPOINT_M) + 1):
            car.checkpoints[index] = self.clock
            self.first_checkpoint.setdefault(index, self.clock)

    # ------------------------------------------------------------------ what the screen shows
    def standings(self):
        def key(car):
            if car.state == "OUT":
                return (1, -car.dist)
            return (0, -car.laps_done, car.finish_time if car.state == "FINISHED" else -car.dist)
        order = sorted(self.cars.values(), key=key)
        leader = order[0]
        rows = []
        for position, car in enumerate(order, start=1):
            x, y = self.track.pit_xy(car.dist) if car.in_pit else self.track.xy(car.dist)
            if car.state == "OUT":
                gap = "Out"
            elif position == 1:
                gap = "Leader"
            elif leader.laps_done - car.laps_done >= 1 and (car.state == "FINISHED" or leader.dist - car.dist > self.track.length):
                laps = leader.laps_done - car.laps_done
                gap = f"+{laps} lap" + ("s" if laps > 1 else "")
            elif car.state == "FINISHED":
                gap = f"+{car.finish_time - leader.finish_time:.1f}s"
            else:
                gap = f"+{self.gap_to_leader(car):.1f}s"
            strategist_plan = self.strategists[car.team].plan[car.code]
            rows.append({
                "position": position, "code": car.code, "name": car.name, "team": car.team, "color": car.color,
                "x": round(x, 1), "y": round(y, 1), "state": car.state, "in_pit": car.in_pit,
                "tyre": car.tyre, "tyre_age": car.age, "stops": car.stops, "gap": gap,
                "last_lap": round(car.last_lap, 2) if car.last_lap else None,
                "plan": None if car.state in ("OUT", "FINISHED") else
                        ("No more stops" if strategist_plan is None else f"Lap {strategist_plan[0]}: {tyre_word(strategist_plan[1])}"),
                "plan_changed": self.clock - car.plan_changed_at < PLAN_HIGHLIGHT_S,
            })
        return rows

    def safety_car_xy(self):
        leader = self.leader()
        if self.flag != "SAFETY_CAR" or leader is None:
            return None
        return self.track.xy(leader.dist + 150.0)
