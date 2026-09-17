import pytest

from sim.messages import EVERYONE, DecisionChange, MessageBoard
from sim.race import Race


def run(race, until=lambda race: race.over, max_steps=40000):
    for _ in range(max_steps):
        if until(race):
            return race
        race.step()
    raise AssertionError("race did not reach the expected point")


@pytest.mark.parametrize("seed", [1, 2, 42])
def test_race_finishes_with_valid_results(seed):
    race = Race(seed)
    race.start()
    run(race)
    finished = [c for c in race.cars.values() if c.state == "FINISHED"]
    assert {c.code for c in race.cars.values() if c.state == "OUT"} == {"LEC", "HAM"}
    assert len(finished) == 6
    for car in finished:
        assert car.laps_done == race.total_laps
        assert len(car.used) >= 2, f"{car.code} broke the tyre rule"
    positions = [row["position"] for row in race.standings()]
    assert positions == list(range(1, 9))
    assert race.safety_car_count == 1


def test_first_ferrari_crash_is_a_yellow_flag_and_the_second_brings_the_safety_car():
    race = Race(42)
    race.start()
    run(race, lambda r: len(r.crash_marks) == 1)
    assert race.flag == "YELLOW"
    run(race, lambda r: len(r.crash_marks) == 2)
    assert race.flag == "SAFETY_CAR"


def test_manual_crash_brings_out_the_safety_car_and_teams_react():
    race = Race(3)
    race.start()
    run(race, lambda r: r.lap == 4)
    assert "Safety car deployed" in race.crash("NOR", manual=True)
    assert race.cars["NOR"].state == "OUT" and race.flag == "SAFETY_CAR"
    assert race.crash("NOR", manual=True) == "Norris is not racing."
    run(race)
    assert any(isinstance(i, DecisionChange) and i.cause == "incident" for i in race.board.feed)


def test_no_overtaking_behind_the_safety_car():
    race = Race(42)
    race.start()
    run(race, lambda r: r.flag == "SAFETY_CAR")
    seen = len(race.board.feed)
    run(race, lambda r: r.flag != "SAFETY_CAR")
    assert not any(" overtakes " in getattr(i, "text", "") for i in race.board.feed[seen:])


def test_cars_in_the_pit_lane_are_drawn_on_the_pit_lane():
    race = Race(1)
    race.start()
    checked = 0
    while not race.over:
        race.step()
        for row in race.standings():
            car = race.cars[row["code"]]
            if car.in_pit:
                assert race.track.in_pit_zone(car.dist)
                assert (row["x"], row["y"]) == (round(race.track.pit_xy(car.dist)[0], 1), round(race.track.pit_xy(car.dist)[1], 1))
                checked += 1
    assert checked > 0


def test_every_plan_change_names_its_cause():
    race = Race(6)
    race.start()
    run(race)
    changes = [i for i in race.board.feed if isinstance(i, DecisionChange)]
    assert changes
    for change in changes:
        assert change.cause in {"driver", "rival", "incident", "weather", "laps", "team"}
        assert change.before != change.after and change.because


def test_rain_makes_teams_switch_to_wet_tyres_and_back():
    race = Race(42)
    race.start()
    run(race, lambda r: r.lap == 4)
    assert race.start_rain().startswith("Rain started") and race.start_rain() == "It is already raining."
    race.rain_target = 0.9
    run(race, lambda r: r.lap == 9)
    running = [c for c in race.cars.values() if c.state == "RUNNING"]
    assert sum(c.tyre == "WET" for c in running) >= len(running) - 1
    assert any(isinstance(i, DecisionChange) and i.cause == "weather" for i in race.board.feed)
    assert race.stop_rain().startswith("Rain stopped")
    run(race)
    assert race.rain == 0.0
    assert all(c.used & {"SOFT", "MEDIUM", "HARD"} for c in race.cars.values())


@pytest.mark.parametrize("scenario", ["safety car", "rain"])
def test_teammates_sharing_the_pit_box_double_stack_or_stay_out_a_lap(scenario):
    race = Race(1)
    race.start()
    run(race, lambda r: r.lap == 4)
    if scenario == "safety car":
        race.crash("NOR", manual=True)
    else:
        race.start_rain()
        race.rain_target = 0.8
    seen = len(race.board.feed)
    run(race, lambda r: r.lap == 9)
    new = race.board.feed[seen:]
    stayed_out = [i for i in new if isinstance(i, DecisionChange) and i.cause == "team"]
    doubled = [i for i in new if "Double stack" in getattr(i, "text", "")]
    assert stayed_out or doubled
    for change in stayed_out:
        assert "Waiting in the box" in change.detail
    assert len({(c.driver, c.before) for c in stayed_out}) == len(stayed_out), "the same box decision was repeated"


@pytest.mark.parametrize("seed", [1, 42])
def test_every_attack_has_a_defence_answer_and_an_announced_result(seed):
    race = Race(seed)
    race.start()
    run(race)
    texts = [i.text for i in race.board.feed if hasattr(i, "text")]
    attacks = [t for t in texts if t.startswith("Attacking")]
    answers = [t for t in texts if "is attacking" in t or t.startswith("Letting my teammate")]
    results = [t for t in texts if " overtakes " in t or "behind into Turn" in t or "could not get past" in t or "holds on" in t]
    assert attacks and len(attacks) == len(answers) == len(results)


def test_team_radio_stays_inside_the_team():
    board = MessageBoard()
    board.join("Norris", "McLaren")
    board.join("McLaren strategist", "McLaren")
    board.join("Russell", "Mercedes")
    board.post(1, "Norris", "McLaren strategist", "INFO", "hello", "McLaren")
    with pytest.raises(ValueError):
        board.post(1, "Norris", "Russell", "INFO", "hello", "McLaren")
    board.post(1, "Race control", EVERYONE, "EVENT", "Lights out")
    assert [m.text for m in board.take("McLaren strategist")] == ["hello", "Lights out"]
    assert [m.text for m in board.take("Russell")] == ["Lights out"]
