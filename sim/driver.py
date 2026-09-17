"""Driver agent: a model-based reflex agent (condition-action rules) that drives and talks to its strategist."""
import mesa

STUCK_S = 20.0  # seconds held up behind a car before the driver complains


def tyre_word(tyre):
    return tyre.capitalize()


class DriverAgent(mesa.Agent):
    def __init__(self, model, car):
        super().__init__(model)
        self.car = car
        self.name = car.name
        self.strategist = f"{car.team} strategist"
        self.said = set()
        model.board.join(self.name, car.team)

    def say(self, kind, text, **data):
        return self.model.board.post(self.model.lap, self.name, self.strategist, kind, text, self.car.team, **data)

    def step(self):
        race, car = self.model, self.car
        for msg in race.board.take(self.name):
            if msg.kind == "INSTRUCTION":
                self.follow(msg)
        if car.state != "RUNNING":
            return

        wear = race.model.wear_pct(car.tyre, car.age, car.wear)
        if wear >= 0.7 and ("worn", car.stops) not in self.said:
            self.said.add(("worn", car.stops))
            self.say("INFO", f"My {tyre_word(car.tyre)} tyres are {wear:.0%} worn and I'm getting slower.",
                     wear=wear, age=car.age, tyre=car.tyre)
            if car.pit_tyre is None and race.flag != "CHEQUERED":
                self.say("REQUEST", "Should I come in for new tyres?")

        if race.rain_label != "dry" and car.tyre != "WET" and ("rain", race.rain_label) not in self.said and car.pit_tyre is None:
            self.said.add(("rain", race.rain_label))
            self.say("REQUEST", f"It's raining ({race.rain_label}) and I'm on dry tyres. Should I come in for wet tyres?")

        if car.tyre == "WET" and race.rain < 0.15 and not race.raining and ("drying", car.stops) not in self.said:
            self.said.add(("drying", car.stops))
            self.say("INFO", "The track is drying and my wet tyres are losing grip.", drying=True)

        if race.flag == "SAFETY_CAR" and ("safety car", race.safety_car_count) not in self.said and car.pit_tyre is None:
            self.said.add(("safety car", race.safety_car_count))
            self.say("REQUEST", "The safety car is out. Should I come in for new tyres now?")

        ahead = race.car_ahead(car)
        if car.stuck_s > STUCK_S and ahead and ("stuck", car.laps_done // 3) not in self.said:
            self.said.add(("stuck", car.laps_done // 3))
            self.say("INFO", f"I'm stuck behind {ahead.name} and can't get past.", rival=ahead.code)

    def follow(self, msg):
        race, car = self.model, self.car
        action = msg.data.get("action")
        if action == "pit":
            wear = race.model.wear_pct(car.tyre, car.age, car.wear)
            if msg.data.get("early") and not msg.data.get("final") and wear < 0.5 and ("push back", car.stops) not in self.said:
                self.said.add(("push back", car.stops))
                self.say("REPLY", f"My tyres still feel good ({wear:.0%} worn). I can stay out longer.",
                         wear=wear, age=car.age, tyre=car.tyre, push_back=True)
                return
            car.pit_tyre = msg.data["tyre"]
            self.say("REPLY", f"OK, coming in for new {tyre_word(car.pit_tyre)} tyres.")
        elif action == "stay" and not car.in_pit:
            car.pit_tyre = None
            self.say("REPLY", "OK, staying out.")

    def wants_to_attack(self, ahead, corner):
        """Attack only with a clear pace advantage and tyres that are not worn out."""
        race, car = self.model, self.car
        advantage = ahead.lap_target - car.lap_target
        wear = race.model.wear_pct(car.tyre, car.age, car.wear)
        if advantage < race.model.overtake_advantage or wear > 0.8:
            return False
        self.say("INFO", f"Attacking {ahead.name} into Turn {corner}: I'm {advantage:.1f} s a lap faster "
                         f"and my tyres are {wear:.0%} worn.", attack=ahead.code)
        return True

    def defends_against(self, attacker, corner):
        """Defend, unless it is a teammate or our tyres are worn out (defending would only cost more time)."""
        race, car = self.model, self.car
        wear = race.model.wear_pct(car.tyre, car.age, car.wear)
        if attacker.team == car.team:
            self.say("INFO", f"Letting my teammate {attacker.name} through, he is faster.", defend=False)
            return False
        if wear > 0.9:
            self.say("INFO", f"{attacker.name} is attacking, but my tyres are {wear:.0%} worn. Not fighting him.", defend=False)
            return False
        self.say("INFO", f"{attacker.name} is attacking me. Defending into Turn {corner}.", defend=True)
        return True

    def crashed(self, corner):
        self.say("INFO", f"I've crashed at Turn {corner}. I'm OK, but the car is out of the race.", crashed=True)
