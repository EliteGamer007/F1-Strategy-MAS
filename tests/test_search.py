import math
import random

import pytest

from sim.model import LapModel
from sim.search import PitState, bayes_update, minimax_duel, plan_stops
from sim.strategist import UNIFORM, wear_log_likelihood


@pytest.fixture(scope="module")
def model():
    return LapModel()


def test_worked_example_matches_the_plan_document():
    """3 laps left on 8-lap-old Mediums, a second tyre type still needed (fuel effect removed, as in the document)."""
    model = LapModel()
    model.fuel = 0.0
    start = PitState(0, "MEDIUM", 8, frozenset({"MEDIUM"}))
    astar = plan_stops(model, start, 3, pit_loss=21.0)
    ucs = plan_stops(model, start, 3, pit_loss=21.0, use_heuristic=False)
    assert astar.stops == ucs.stops == [(0, "SOFT")]
    assert round(astar.cost, 2) == round(ucs.cost, 2) == 305.69
    assert (astar.expanded, ucs.expanded) == (5, 18)


def test_astar_is_optimal_and_expands_fewer_nodes():
    model = LapModel()
    rng = random.Random(7)
    for _ in range(20):
        tyre = rng.choice(["SOFT", "MEDIUM", "HARD"])
        lap = rng.randint(0, 12)
        start = PitState(lap, tyre, rng.randint(0, lap), frozenset({tyre}))
        wear = rng.choice([0.8, 1.0, 1.25])
        astar = plan_stops(model, start, 20, 21.0, wear)
        ucs = plan_stops(model, start, 20, 21.0, wear, use_heuristic=False)
        assert astar.cost == pytest.approx(ucs.cost)
        assert astar.expanded <= ucs.expanded


def test_heuristic_never_overestimates(model):
    for laps in (3, 4):
        for tyre in ("SOFT", "MEDIUM", "HARD"):
            for age in (0, 5, 10):
                start = PitState(0, tyre, age, frozenset({tyre}))
                true_cost = plan_stops(model, start, laps, 21.0, use_heuristic=False).cost
                relaxed = sum(model.fastest_lap(lap) for lap in range(1, laps + 1)) + 21.0
                assert relaxed <= true_cost + 1e-9


def test_plan_from_new_tyres_lists_only_real_stops(model):
    plan = plan_stops(model, PitState(0, "MEDIUM", 0, frozenset({"MEDIUM"})), 20, 21.0)
    assert 1 <= len(plan.stops) <= 2
    assert all(0 < lap < 20 for lap, _ in plan.stops)
    assert {tyre for _, tyre in plan.stops} - {"MEDIUM"}


def test_minimax_example_from_the_plan_document():
    values = {("PIT", "PIT"): 0.6, ("PIT", "STAY"): 1.8, ("STAY", "PIT"): -1.2, ("STAY", "STAY"): 5.0}
    move, value, leaves, pruned = minimax_duel(lambda ours, theirs: values[(ours, theirs)])
    assert (move, value, pruned) == ("PIT", 0.6, 1)
    assert ("STAY", "STAY") not in leaves


def test_minimax_when_the_rival_has_already_stopped():
    values = {("PIT", "PIT"): -0.3, ("STAY", "PIT"): 0.4}
    move, value, _, _ = minimax_duel(lambda ours, theirs: values[(ours, theirs)], rival_moves=("PIT",))
    assert (move, value) == ("STAY", 0.4)


def test_bayes_update_is_prior_times_likelihood_normalised():
    prior = {"LOW": 1 / 3, "NORMAL": 1 / 3, "HIGH": 1 / 3}
    posterior = bayes_update(prior, {"LOW": -10.0, "NORMAL": -2.0, "HIGH": 0.0})
    assert sum(posterior.values()) == pytest.approx(1.0)
    assert posterior["HIGH"] == pytest.approx(1 / (1 + math.exp(-2) + math.exp(-10)))
    # a strong prior can outweigh weak evidence
    assert bayes_update({"A": 0.99, "B": 0.01}, {"A": -1.0, "B": 0.0})["A"] > 0.9


def test_wear_estimate_prefers_the_level_that_produced_the_lap_times(model):
    rng = random.Random(3)
    laps = [{"lap": lap, "tyre": "MEDIUM", "age": lap, "time": model.lap_time("MEDIUM", lap, lap, 1.5, pace=0.4) + rng.gauss(0, model.noise)}
            for lap in range(2, 12)]
    posterior = bayes_update(UNIFORM, {level: wear_log_likelihood(model, laps, level) for level in UNIFORM})
    assert max(posterior, key=posterior.get) == "HIGH"
