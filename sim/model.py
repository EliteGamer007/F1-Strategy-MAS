"""Lap-time rules. All numbers come from data/race_model.json (measured from the 2026 British GP or set by hand)."""
import json
from dataclasses import dataclass
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data"
TYRES = ("SOFT", "MEDIUM", "HARD")
WEAR_LEVELS = {"LOW": 0.75, "NORMAL": 1.0, "HIGH": 1.5}
PACE_SPREAD = 0.5         # real pace differences are halved so the cars stay close enough to race each other
WORN_OUT_S_PER_LAP = 1.0  # extra time for every lap a tyre is used past its life


@dataclass(frozen=True)
class Tyre:
    offset: float  # seconds faster (-) or slower (+) than Medium
    wear: float    # seconds lost per lap of age
    life: int      # laps before the tyre is worn out (normal wear)


class LapModel:
    def __init__(self, path=DATA / "race_model.json"):
        m = json.loads(Path(path).read_text())
        self.laps = m["race"]["laps"]
        self.base = m["base_lap_s"]["value"]
        self.fuel = m["fuel_s_per_lap"]["value"]
        self.tyres = {t: Tyre(m["tyres"][t]["offset_s"], m["tyres"][t]["wear_s_per_lap"], m["tyres"][t]["life_laps"]) for t in TYRES}
        self.pit_loss = m["pit_loss_s"]["value"]
        self.safety_car_pit_loss = m["safety_car"]["pit_loss_s"]
        self.safety_car_laps = m["safety_car"]["laps"]
        self.safety_car_factor = m["safety_car"]["lap_time_factor"]
        self.overtake_advantage = m["traffic"]["overtake_min_advantage_s"]
        self.noise = m["lap_noise_s"]["value"]
        self.driver_offsets = m["driver_pace_offset_s"]["value"]

    def lap_time(self, tyre, age, lap, wear=1.0, pace=0.0):
        """Predicted time for lap number `lap` on a tyre that is `age` laps old (counting this lap)."""
        t = self.tyres[tyre]
        worn_laps = age * wear
        past_life = max(0.0, worn_laps - t.life)
        return self.base + pace + t.offset + t.wear * worn_laps + self.fuel * lap + WORN_OUT_S_PER_LAP * past_life

    def fastest_lap(self, lap, pace=0.0):
        """Lower bound for any lap: best tyre, no wear. Used by the A* heuristic."""
        return self.base + pace + min(t.offset for t in self.tyres.values()) + self.fuel * lap

    def wear_pct(self, tyre, age, wear=1.0):
        return age * wear / self.tyres[tyre].life
