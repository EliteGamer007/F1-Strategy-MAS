"""Strategist agent: plans tyre stops with A*, guesses rival tyre wear with belief states, decides close fights with minimax."""
import mesa
import numpy as np

from sim.driver import tyre_word
from sim.model import WEAR_LEVELS
from sim.search import PitState, minimax_duel, plan_stops, update_belief

ROUTINE_GAIN_S = 1.0    # a plan change without a new message or event must save at least this much time
TRIGGERED_GAIN_S = 0.05
DUEL_GAP_S = 3.0        # a rival this close makes the stop timing a two-player game
LAP_TIME_NOISE_S = 0.15


def describe(plan):
    return "no more tyre stops" if plan is None else f"change to {tyre_word(plan[1])} tyres at the end of lap {plan[0]}"


class StrategistAgent(mesa.Agent):
    def __init__(self, model, team, cars):
        super().__init__(model)
        self.team = team
        self.cars = cars
        self.name = f"{team} strategist"
        model.board.join(self.name, team)
        self.wear = {c.code: 1.0 for c in cars}             # own cars: NORMAL until a driver reports otherwise
        self.plan = {}                                      # next stop (lap, tyre) or None
        self.planned_lap = {}                               # (code, stops) -> first planned stop lap of that stint
        self.called_in = {}                                 # code -> lap we told the driver to come in
        self.stops_seen = {c.code: 0 for c in cars}
        self.laps_seen = {c.code: 0 for c in cars}
        self.belief = {}                                    # rival code -> possible wear levels
        self.rival_laps_seen = {}
        self.announced = False
        for car in cars:
            self.set_plan(car, self.best_plan(car).stops)

    # ------------------------------------------------------------------ planning
    def start_state(self, car):
        """Laps that can no longer change: the current one, and the next if the pit entry is already behind us."""
        race = self.model
        committed = car.laps_done + 1
        if car.dist % race.track.length >= race.pit_entry_m - 50:
            committed += 1
        committed = min(committed, race.total_laps)
        return PitState(committed, car.tyre, car.age + committed - car.laps_done, frozenset(car.used))

    def best_plan(self, car, use_heuristic=True):
        race = self.model
        return plan_stops(race.model, self.start_state(car), race.total_laps, race.stop_loss,
                          self.wear[car.code], car.pace, use_heuristic)

    def cost_keeping(self, car, stop):
        """Predicted time if we keep the current next stop instead of the new best plan."""
        race, model = self.model, self.model.model
        s = self.start_state(car)
        if stop is None or not s.lap <= stop[0] < race.total_laps:
            return float("inf")
        time = 0.0
        for lap in range(s.lap + 1, stop[0] + 1):
            s = PitState(lap, s.tyre, s.age + 1, s.used)
            time += model.lap_time(s.tyre, s.age, lap, self.wear[car.code], car.pace)
        lap = stop[0] + 1
        time += race.stop_loss(stop[0]) + model.lap_time(stop[1], 1, lap, self.wear[car.code], car.pace)
        s = PitState(lap, stop[1], 1, s.used | {stop[1]})
        try:
            return time + plan_stops(model, s, race.total_laps, race.stop_loss, self.wear[car.code], car.pace).cost
        except ValueError:
            return float("inf")

    def set_plan(self, car, stops):
        self.plan[car.code] = stops[0] if stops else None
        self.planned_lap.setdefault((car.code, car.stops), stops[0][0] if stops else None)

    def replan(self, car, because, cause, gain=TRIGGERED_GAIN_S):
        if car.state != "RUNNING" or car.pit_tyre or self.model.flag == "CHEQUERED":
            return
        try:
            best = self.best_plan(car)
        except ValueError:
            return
        new = best.stops[0] if best.stops else None
        old = self.plan[car.code]
        if new == old:
            return
        saving = self.cost_keeping(car, old) - best.cost
        if saving < gain:
            return
        detail = f"A* checked {best.expanded} plans in {best.ms:.0f} ms; the new plan is {saving:.1f} s faster."
        self.change_plan(car, new, because, cause, detail)

    def change_plan(self, car, new, because, cause, detail):
        race = self.model
        old = self.plan[car.code]
        self.plan[car.code] = new
        self.planned_lap.setdefault((car.code, car.stops), new[0] if new else None)
        race.board.record(race.lap, self.team, car.name, describe(old), describe(new), because, cause, detail)
        car.plan_changed_at = race.clock
        if new is None or new[0] > car.laps_done + 1:
            self.radio(car, f"Change of plan: {describe(new)}. {because}", action="plan")

    def radio(self, car, text, **data):
        self.model.board.post(self.model.lap, self.name, car.name, "INSTRUCTION", text, self.team, **data)

    # ------------------------------------------------------------------ each step
    def step(self):
        race = self.model
        if not self.announced:
            self.announced = True
            for car in self.cars:
                self.radio(car, f"Race plan: start on {tyre_word(car.tyre)} tyres, then {describe(self.plan[car.code])}.", action="plan")
        for msg in race.board.take(self.name):
            self.read(msg)
        for car in self.cars:
            if car.state in ("OUT", "FINISHED"):
                continue
            if car.stops != self.stops_seen[car.code]:
                self.stops_seen[car.code] = car.stops
                self.after_stop(car)
            if car.laps_done != self.laps_seen[car.code]:
                self.laps_seen[car.code] = car.laps_done
                self.lap_done(car)
            self.call_in(car)
        self.watch_rivals()

    def after_stop(self, car):
        try:
            self.set_plan(car, self.best_plan(car).stops)
        except ValueError:
            return
        self.radio(car, f"Good stop. Next: {describe(self.plan[car.code])}.", action="plan")

    def lap_done(self, car):
        self.replan(car, "New lap times show a faster plan.", "laps", ROUTINE_GAIN_S)
        for rival in (self.model.car_ahead(car), self.model.car_behind(car)):
            if rival:
                self.duel(car, rival, rival_pitted=False,
                          because=f"{rival.name} is close, so the timing of our stop decides who stays ahead.")

    def call_in(self, car):
        """Tell the driver to come in when the planned stop is at the end of the current lap."""
        race = self.model
        plan = self.plan[car.code]
        if (plan is None or plan[0] != car.laps_done + 1 or car.pit_tyre or car.in_pit
                or self.called_in.get(car.code) == plan[0] or car.dist % race.track.length >= race.pit_entry_m - 50):
            return
        self.called_in[car.code] = plan[0]
        first = self.planned_lap.get((car.code, car.stops))
        early = first is not None and first - plan[0] >= 2
        self.radio(car, f"Come in for new {tyre_word(plan[1])} tyres at the end of this lap.", action="pit", tyre=plan[1], early=early)

    # ------------------------------------------------------------------ reading messages
    def read(self, msg):
        race = self.model
        car = next((c for c in self.cars if c.name == msg.sender), None)
        if car is not None:
            self.read_driver(car, msg)
        elif msg.data.get("pit_entry"):
            rival = race.cars[msg.data["pit_entry"]]
            if rival.team != self.team:
                for own in self.cars:
                    self.duel(own, rival, rival_pitted=True, because=f"{rival.name} just came in for new tyres.")
        elif msg.data.get("safety_car") is not None:
            because = ("The safety car makes a tyre stop much cheaper." if msg.data["safety_car"]
                       else "The safety car has gone in, so tyre stops cost the normal time again.")
            for own in self.cars:
                self.replan(own, because, "incident")

    def read_driver(self, car, msg):
        race = self.model
        if msg.kind == "INFO" and "wear" in msg.data:
            self.learn_wear(car, msg.data)
            self.replan(car, f"{car.name} said his tyres are {msg.data['wear']:.0%} worn.", "driver")
        elif msg.kind == "INFO" and "rival" in msg.data:
            self.duel(car, race.cars[msg.data["rival"]], rival_pitted=False,
                      because=f"{car.name} is stuck behind {race.cars[msg.data['rival']].name}.")
        elif msg.kind == "REQUEST" and not car.pit_tyre:
            before = self.plan[car.code]
            self.replan(car, f"{car.name} asked to come in for new tyres.", "driver")
            plan = self.plan[car.code]
            if plan != before:
                return  # the change of plan was already radioed
            if plan is None:
                self.radio(car, "Stay out: no more stops needed, bring it home.", action="stay")
            elif plan[0] > car.laps_done + 1:
                self.radio(car, f"Not yet. Stay out: we plan to {describe(plan)}.", action="stay")
        elif msg.kind == "REPLY" and msg.data.get("push_back"):
            self.learn_wear(car, msg.data)
            self.called_in.pop(car.code, None)
            self.replan(car, f"{car.name} said his tyres still feel good.", "driver")
            plan = self.plan[car.code]
            if plan is not None and plan[0] == car.laps_done + 1:
                self.called_in[car.code] = plan[0]
                self.radio(car, "Understood, but come in now: stopping this lap is still faster overall.",
                           action="pit", tyre=plan[1], final=True)

    def learn_wear(self, car, data):
        if data["age"] > 0:
            measured = data["wear"] * self.model.model.tyres[data["tyre"]].life / data["age"]
            self.wear[car.code] = min(WEAR_LEVELS.values(), key=lambda level: abs(level - measured))

    # ------------------------------------------------------------------ rivals
    def watch_rivals(self):
        """Belief-state update from the public lap times: which wear levels still fit each rival's lap-time trend?"""
        model = self.model.model
        for rival in self.model.cars.values():
            if rival.team == self.team or len(rival.history) == self.rival_laps_seen.get(rival.code, 0):
                continue
            self.rival_laps_seen[rival.code] = len(rival.history)
            stint = [h for h in rival.history if h["stops"] == rival.stops and h["clean"]]
            if len(stint) < 4:
                continue
            ages = np.array([h["age"] for h in stint], dtype=float)
            times = np.array([h["time"] for h in stint])
            trend = float(np.polyfit(ages, times, 1)[0])
            tyre = stint[-1]["tyre"]
            predicted = {level: model.tyres[tyre].wear * mult + model.fuel for level, mult in WEAR_LEVELS.items()}
            tolerance = max(0.03, 2 * LAP_TIME_NOISE_S / np.sqrt(np.sum((ages - ages.mean()) ** 2)))
            self.belief[rival.code] = update_belief(self.belief.get(rival.code, set(WEAR_LEVELS)), trend, predicted, tolerance)

    def believed_wear(self, rival):
        levels = self.belief.get(rival.code, set(WEAR_LEVELS))
        return sum(WEAR_LEVELS[level] for level in levels) / len(levels)

    def duel(self, car, rival, rival_pitted, because):
        """Minimax over 'stop now' vs 'stop next lap' against a close rival (undercut / overcut)."""
        race = self.model
        plan = self.plan[car.code]
        if car.state != "RUNNING" or car.pit_tyre or plan is None or race.flag in ("SAFETY_CAR", "CHEQUERED"):
            return
        if rival.team == self.team or rival.state not in ("RUNNING", "PIT"):
            return
        start = self.start_state(car)
        now = start.lap
        gap = race.gap_between(car, rival)
        if now >= race.total_laps - 1 or plan[0] > now + 2 or gap is None or abs(gap) > DUEL_GAP_S:
            return
        if not rival_pitted and len(rival.used) >= 2:
            return  # the rival does not need to stop, so there is nothing to time against

        rival_next = "HARD" if "HARD" not in rival.used else "MEDIUM"
        rival_age = rival.age + now - rival.laps_done

        def window(tyre, age, wear, stop_lap, new_tyre):
            total = 0.0
            for lap in range(now + 1, now + 4):
                if lap == stop_lap + 1:
                    tyre, age = new_tyre, 0
                    total += race.stop_loss(stop_lap)
                age += 1
                total += race.model.lap_time(tyre, age, lap, wear)
            return total

        def evaluate(ours, theirs):
            our_time = window(car.tyre, start.age, self.wear[car.code], now if ours == "PIT" else now + 1, plan[1])
            their_time = window(rival.tyre, rival_age, self.believed_wear(rival), now if theirs == "PIT" else now + 1, rival_next)
            return gap + their_time - our_time

        move, value, leaves, pruned = minimax_duel(evaluate, rival_moves=("PIT",) if rival_pitted else ("PIT", "STAY"))
        stop_value = min(v for (ours, _), v in leaves.items() if ours == "PIT")
        detail = (f"Minimax against {rival.name}: stop now -> {stop_value:+.1f} s, "
                  f"wait a lap -> {min((v for (o, _), v in leaves.items() if o == 'STAY'), default=float('nan')):+.1f} s "
                  f"(+ means ahead of {rival.name}); {pruned} option(s) pruned by alpha-beta.")
        outcome = "keeps us ahead" if value >= 0 else "loses the least time to them"
        if move == "PIT" and plan[0] > now:
            self.change_plan(car, (now, plan[1]), f"{because} Stopping now {outcome}.", "rival", detail)
        elif move == "STAY" and plan[0] == now and rival_pitted:
            self.change_plan(car, (now + 1, plan[1]), f"{because} Staying out one more lap {outcome}.", "rival", detail)
