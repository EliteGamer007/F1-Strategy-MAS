"""Stress tests: the race must survive nonsense commands and any order of shocks.

The demo is driven live from the terminal, so these tests fire commands at random moments
(crashes, rain, pauses, restarts, typos) and check the race never breaks and always finishes.
"""
import random

import pytest

from server.engine import Engine
from sim.race import Race

COMMANDS = [
    "", "   ", "help", "start", "start", "pause", "resume", "status", "speed 0.5", "speed 4",
    "speed", "speed 3", "speed x2", "rain start", "rain stop", "rain", "rain maybe",
    "crash VER", "crash piastri", "crash", "crash NOBODY", "plan NOR", "plan", "why HAM", "why VER",
    "restart", "restart 9", "restart abc", "fly to the moon", "STATUS", "Crash Ver",
]


def check(race):
    """Invariants that must hold at every moment of every race."""
    for car in race.cars.values():
        assert car.state in ("RUNNING", "PIT", "OUT", "FINISHED")
        assert car.dist <= (race.total_laps + 1) * race.track.length
        assert 0 <= car.laps_done <= race.total_laps
        assert car.tyre in ("SOFT", "MEDIUM", "HARD", "WET")
    assert 0.0 <= race.rain <= 1.0
    assert 1 <= race.lap <= race.total_laps
    positions = [row["position"] for row in race.standings()]
    assert positions == sorted(positions)


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_random_commands_never_break_the_race(seed):
    rng = random.Random(seed)
    engine = Engine(seed)
    engine.command("start")
    for _ in range(6000):
        if rng.random() < 0.01:
            assert isinstance(engine.command(rng.choice(COMMANDS)), str)
        if not engine.race.over:
            engine.race.step()
        check(engine.race)
        engine.publish()


def test_crashing_every_car_ends_the_race_cleanly():
    race = Race(1)
    race.start()
    while race.lap < 3:
        race.step()
    for code in list(race.cars):
        race.crash(code, manual=True)
        check(race)
    for _ in range(2000):
        race.step()
    assert race.over
    assert all(car.state == "OUT" for car in race.cars.values())


def test_shocks_can_be_stacked_in_any_order():
    race = Race(2)
    race.start()
    while race.lap < 4:
        race.step()
    race.start_rain()           # rain first
    race.crash("VER", manual=True)   # then the safety car, while it rains
    race.rain_target = 1.0
    for _ in range(3000):
        race.step()
        check(race)
    race.stop_rain()
    race.crash("NOR", manual=True)   # a second safety car, while the track dries
    while not race.over:
        race.step()
        check(race)
    finished = [car for car in race.cars.values() if car.state == "FINISHED"]
    assert finished and all(len(car.used) >= 2 for car in finished)
