"""The algorithms the agents use (AIMA): A* / uniform-cost search, minimax with alpha-beta, and Bayes' rule."""
import heapq
import itertools
import math
import time
from dataclasses import dataclass

from sim.model import TYRES


@dataclass(frozen=True)
class PitState:
    lap: int          # laps already covered
    tyre: str         # tyre on the car
    age: int          # laps done on this tyre
    used: frozenset   # tyre types used so far in the race


@dataclass
class Plan:
    stops: list       # [(lap, tyre)]: come in at the end of `lap`, leave on `tyre`
    cost: float       # predicted time for the remaining laps (seconds)
    expanded: int     # nodes taken off the frontier
    ms: float


def plan_stops(model, start, total_laps, pit_loss, wear=1.0, pace=0.0, use_heuristic=True):
    """Cheapest pit-stop plan from `start` to the finish.

    `pit_loss` is seconds per stop, or a function of the lap the stop happens at (stops are cheaper
    under the safety car). A* when use_heuristic is True, uniform-cost search when False. The heuristic
    is the cost of a relaxed problem (no tyre wear, fastest tyre, one cheapest stop only if the tyre rule
    still needs it), so it never overestimates and A* returns the same cost as UCS.
    """
    began = time.perf_counter()
    stop_cost = pit_loss if callable(pit_loss) else (lambda lap: pit_loss)
    cheapest_stop = min(stop_cost(lap) for lap in range(start.lap, total_laps + 1))
    # fastest_rest[k] = sum of the fastest possible laps from lap k+1 to the finish
    fastest_rest = [0.0] * (total_laps + 2)
    for lap in range(total_laps, 0, -1):
        fastest_rest[lap - 1] = fastest_rest[lap] + model.fastest_lap(lap, pace)

    def h(s):
        if not use_heuristic:
            return 0.0
        return fastest_rest[s.lap] + (cheapest_stop if len(s.used) < 2 and s.lap < total_laps else 0.0)

    counter = itertools.count()
    frontier = [(h(start), 0.0, next(counter), start)]
    best_g = {start: 0.0}
    parent = {start: None}
    expanded = 0
    while frontier:
        _, g, _, state = heapq.heappop(frontier)
        if g > best_g[state]:
            continue
        expanded += 1
        if state.lap == total_laps:
            if len(state.used) >= 2:
                return Plan(_stops(parent, state), g, expanded, (time.perf_counter() - began) * 1000)
            continue
        lap = state.lap + 1
        moves = [(PitState(lap, state.tyre, state.age + 1, state.used), model.lap_time(state.tyre, state.age + 1, lap, wear, pace), False)]
        for tyre in TYRES:
            moves.append((PitState(lap, tyre, 1, state.used | {tyre}), stop_cost(state.lap) + model.lap_time(tyre, 1, lap, wear, pace), True))
        for child, step_cost, pitted in moves:
            g_child = g + step_cost
            if g_child < best_g.get(child, float("inf")):
                best_g[child] = g_child
                parent[child] = (state, pitted)
                heapq.heappush(frontier, (g_child + h(child), g_child, next(counter), child))
    raise ValueError("no plan satisfies the tyre rule")


def _stops(parent, state):
    stops = []
    while parent[state] is not None:
        previous, pitted = parent[state]
        if pitted:
            stops.append((previous.lap, state.tyre))
        state = previous
    return stops[::-1]


def minimax_duel(evaluate, our_moves=("PIT", "STAY"), rival_moves=("PIT", "STAY")):
    """Depth-2 minimax with alpha-beta pruning.

    We (MAX) choose first, the rival (MIN) replies. evaluate(ours, theirs) returns our predicted gap to the
    rival in seconds (positive = we are ahead). Returns (best move, its value, leaf values, leaves pruned).
    """
    alpha, best_move, leaves, pruned = float("-inf"), None, {}, 0
    for ours in our_moves:
        worst = float("inf")
        for i, theirs in enumerate(rival_moves):
            leaves[(ours, theirs)] = evaluate(ours, theirs)
            worst = min(worst, leaves[(ours, theirs)])
            if worst <= alpha:  # the rival can already make this branch no better than one we have
                pruned += len(rival_moves) - i - 1
                break
        if worst > alpha:
            alpha, best_move = worst, ours
    return best_move, alpha, leaves, pruned


def bayes_update(prior, log_likelihood):
    """Bayes' rule over a few hypotheses: posterior is proportional to prior x likelihood.

    Likelihoods are passed as logarithms and shifted by their maximum so tiny numbers do not underflow.
    """
    best = max(log_likelihood.values())
    weights = {h: prior[h] * math.exp(log_likelihood[h] - best) for h in prior}
    total = sum(weights.values())
    return {h: w / total for h, w in weights.items()}
