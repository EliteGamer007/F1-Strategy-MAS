"""Runs the race in real time and handles commands from the terminal and the page's buttons."""
import asyncio
import queue

from sim.driver import tyre_word
from sim.messages import DecisionChange, to_json
from sim.race import DT, Race
from sim.strategist import describe

REAL_TIME_SCALE = 8   # at speed x1, 8 race seconds pass every real second (a lap takes about 12 s)
TICK_S = 0.1
SPEEDS = ("0.5", "1", "2", "4")

HELP = """Commands:
  start             start the race
  pause / resume    freeze or continue the race
  speed 0.5|1|2|4   race speed (same as the buttons on the page)
  crash <driver>    crash a car out of the race: the safety car comes out
  rain start|stop   start or stop rain (how hard it rains is random)
  status            running order, tyres, gaps and each car's next tyre stop
  plan <driver>     the strategist's plan for that car, and how A* and UCS found it
  why <driver>      why that car's plan last changed
  restart [seed]    start again from the grid (same seed = same race)
  help              this list
  quit              close the app"""


class Engine:
    def __init__(self, seed=42):
        self.clients = set()            # one asyncio queue per open page
        self.console = queue.Queue()    # messages for the terminal (read from another thread)
        self.loop = None
        self.restart(seed)

    def restart(self, seed):
        self.seed = seed
        self.race = Race(seed)
        self.running = False
        self.speed = 1
        self.sent = 0
        for client in self.clients:
            client.put_nowait(self.hello())

    # ------------------------------------------------------------------ real-time loop and updates
    async def run(self):
        while True:
            await asyncio.sleep(TICK_S)
            if self.running:
                for _ in range(round(TICK_S * REAL_TIME_SCALE * self.speed / DT)):
                    self.race.step()
                    if self.race.over:
                        self.running = False
                        break
            self.publish()

    def publish(self):
        new = self.race.board.feed[self.sent:]
        self.sent = len(self.race.board.feed)
        for item in new:
            self.console.put(item)
        update = {"type": "update", "state": self.state(), "feed": [to_json(item) for item in new]}
        for client in self.clients:
            client.put_nowait(update)

    def hello(self):
        return {"type": "reset", "track": self.race.track.to_json(), "state": self.state(),
                "feed": [to_json(item) for item in self.race.board.feed[:self.sent]]}

    def state(self):
        race = self.race
        return {"lap": race.lap, "total_laps": race.total_laps, "flag": race.flag, "started": race.started,
                "running": self.running, "over": race.over, "speed": self.speed, "seed": self.seed,
                "rain": {"level": round(race.rain, 2), "label": race.rain_label, "trend": race.rain_trend()},
                "cars": race.standings(), "crashes": race.crash_marks, "safety_car": race.safety_car_xy()}

    # ------------------------------------------------------------------ commands
    async def run_command(self, text):
        return self.command(text)

    def command(self, text):
        words = text.split()
        if not words:
            return ""
        name, args = words[0].lower(), words[1:]
        if name == "help":
            return HELP
        if name == "start":
            if self.race.started:
                return "The race has already started."
            self.race.start()
            self.running = True
            return "Lights out! The race has started."
        if name in ("pause", "resume"):
            if not self.race.started or self.race.over:
                return "The race is not running. Type 'start' or 'restart'."
            self.running = name == "resume"
            return "Race paused." if name == "pause" else "Race resumed."
        if name == "speed":
            value = args[0].lower().lstrip("x") if len(args) == 1 else ""
            if value not in SPEEDS:
                return "Usage: speed 0.5, speed 1, speed 2 or speed 4"
            self.speed = float(value)
            return f"Race speed is now x{value}."
        if name == "restart":
            if args and not args[0].isdigit():
                return "Usage: restart [seed], for example: restart 7"
            self.restart(int(args[0]) if args else self.seed)
            return f"New race on the grid (seed {self.seed}). Type 'start' when ready."
        if name == "status":
            return self.status()
        if name == "rain":
            if len(args) != 1 or args[0].lower() not in ("start", "stop"):
                return "Usage: rain start  or  rain stop"
            if not self.race.started or self.race.over:
                return "The race is not running. Type 'start' first."
            return self.race.start_rain() if args[0].lower() == "start" else self.race.stop_rain()
        if name in ("crash", "plan", "why"):
            car = self.find_car(args)
            if isinstance(car, str):
                return car
            return getattr(self, name)(car)
        return f"Unknown command '{name}'. Type 'help' to see the commands."

    def find_car(self, args):
        codes = ", ".join(self.race.cars)
        if len(args) != 1:
            return f"Name one driver, for example: plan NOR. Drivers: {codes}"
        word = args[0].lower()
        for car in self.race.cars.values():
            if word == car.code.lower() or (len(word) >= 3 and car.name.lower().startswith(word)):
                return car
        return f"No driver called '{args[0]}'. Drivers: {codes}"

    def crash(self, car):
        if not self.race.started or self.race.over:
            return "The race is not running. Type 'start' first."
        return self.race.crash(car.code, manual=True)

    def status(self):
        race = self.race
        lines = [f"Lap {race.lap}/{race.total_laps}  flag: {race.flag.replace('_', ' ').lower()}  weather: {race.rain_label}  speed: x{self.speed:g}",
                 f"{'Pos':<4}{'Driver':<12}{'Team':<10}{'Tyre':<19}{'Stops':<7}{'Gap':<10}Next tyre stop"]
        for row in race.standings():
            tyre = f"{tyre_word(row['tyre'])} ({row['tyre_age']} lap{'' if row['tyre_age'] == 1 else 's'})"
            where = " IN PIT" if row["in_pit"] else ""
            lines.append(f"{row['position']:<4}{row['name']:<12}{row['team']:<10}{tyre:<19}{row['stops']:<7}"
                         f"{row['gap']:<10}{row['plan'] or '-'}{where}")
        return "\n".join(lines)

    def plan(self, car):
        if car.state in ("OUT", "FINISHED"):
            return f"{car.name} is not racing."
        strategist = self.race.strategists[car.team]
        astar = strategist.best_plan(car)
        ucs = strategist.best_plan(car, use_heuristic=False)
        stops = " then ".join(describe(stop) for stop in astar.stops) or describe(None)
        minutes, seconds = divmod(astar.cost, 60)
        beliefs = "; ".join(f"{code}: " + ", ".join(f"{level.lower()} {p:.0%}" for level, p in belief.items())
                            for code, belief in sorted(strategist.belief.items())) or "not enough clean laps yet"
        return "\n".join([
            f"{car.name} ({car.team}) on lap {self.race.lap}: {tyre_word(car.tyre)} tyres, {car.age} laps old, {car.stops} stop(s) so far.",
            f"Current plan: {describe(strategist.plan[car.code])}.",
            f"A* best plan now: {stops}. Predicted time for the rest of the race: {int(minutes)}:{seconds:04.1f}.",
            f"A* checked {astar.expanded} plans in {astar.ms:.1f} ms. Uniform-cost search checked {ucs.expanded} plans "
            f"in {ucs.ms:.1f} ms for the same answer.",
            f"{car.team}'s Bayesian estimate of rival tyre wear: {beliefs}.",
        ])

    def why(self, car):
        changes = [i for i in self.race.board.feed if isinstance(i, DecisionChange) and i.driver == car.name]
        if not changes:
            return f"{car.name}'s plan has not changed yet."
        c = changes[-1]
        return "\n".join([f"Lap {c.lap}: the {c.team} strategist changed {c.driver}'s plan.",
                          f"  before:  {c.before}", f"  after:   {c.after}", f"  because: {c.because}", f"  how:     {c.detail}"])
