# F1 Strategy Agents — Full Documentation

A multi-agent system that races a Formula 1 grand prix and decides the tyre strategy live.
**12 agents**: 4 teams, each with **1 strategist agent** and **2 driver agents**.

Everything here is explained in plain words first, then in AI terms, so it can be read by someone
who does not follow Formula 1.

**Contents**

1. [The problem](#1-the-problem)
2. [What the agents are (PEAS)](#2-what-the-agents-are-peas)
3. [What kind of environment this is](#3-what-kind-of-environment-this-is)
4. [Agent architecture](#4-agent-architecture)
5. [The algorithms and why we chose them](#5-the-algorithms-and-why-we-chose-them)
6. [Multi-agent interaction](#6-multi-agent-interaction)
7. [Tools and packages](#7-tools-and-packages)
8. [The data](#8-the-data)
9. [Code map](#9-code-map)
10. [Testing](#10-testing)
11. [Honest limitations](#11-honest-limitations)
12. [How this meets the marking criteria](#12-how-this-meets-the-marking-criteria)

---

## 1. The problem

In a Formula 1 race every car must stop at least once to change tyres, and each team must use
two different types of tyre. Tyres get slower the longer they are used, a pit stop costs about
21 seconds, and there are only a few laps where stopping is a good idea.

The hard part is that **the best moment to stop depends on what everyone else does**:

- Stop too early and the new tyres are worn out before the finish.
- Stop too late and a rival who stopped earlier is already past you on fresh tyres (an *undercut*).
- Both team cars share **one pit box**, so if they stop on the same lap the second one waits.
- The weather and crashes change everything in the middle of the race.

So each team is solving a **sequential decision problem under uncertainty, against other agents
who are solving the same problem at the same time**. That is what makes it a multi-agent search
problem rather than a formula.

**The goal of every team:** finish the race in the shortest total time, ahead of the other teams,
while obeying the two-tyre rule.

---

## 2. What the agents are (PEAS)

### Strategist agent (one per team, 4 in total) — `sim/strategist.py`

| PEAS | Description |
|---|---|
| **Performance measure** | Total race time of its two cars, finishing position, and obeying the two-tyre rule. Time lost waiting in the shared pit box counts against it. |
| **Environment** | The race: its own two cars, the six rival cars, the tyres, the weather, the flags (yellow / safety car), and the pit lane. |
| **Actuators** | Team radio to its own two drivers: a pit instruction ("Box this lap, Hard tyres"), a stay-out instruction, a change of plan, and tyre-wear information. |
| **Sensors** | Its drivers' radio messages (wear, "I'm stuck", requests), and the **public timing screen**: every car's lap times, tyre type, tyre age, gaps, pit entries, flags and the weather. It **cannot** see a rival's plan or how fast a rival's tyres really wear. |

### Driver agent (two per team, 8 in total) — `sim/driver.py`

| PEAS | Description |
|---|---|
| **Performance measure** | Own finishing position; keeping the car out of the wall; not wasting the tyres. |
| **Environment** | The track, the car ahead and behind, its own tyres, the weather and the flags. |
| **Actuators** | Radio to its own strategist (report, request, reply, push back), and driving actions: attack the car ahead, defend, or let a teammate through. |
| **Sensors** | Own tyre wear, own lap time, the gap to the car ahead, the corner it is approaching, the flag and the rain level. |

Only the strategist can order a pit stop; only the driver decides whether to attack or defend.
Neither can do the other's job — that is what makes them separate agents rather than one program.

---

## 3. What kind of environment this is

Using the standard properties from *Artificial Intelligence: A Modern Approach* (AIMA):

| Property | This race | Why |
|---|---|---|
| **Partially observable** | Yes | A team sees rival lap times but not rival plans, and not how quickly rival tyres wear. This is exactly what the Bayesian estimator is for. |
| **Stochastic** | Yes | Lap times carry random noise (±0.15 s), crashes happen at random points, rain intensity is random, and overtakes succeed with a probability. |
| **Sequential** | Yes | A stop on lap 9 changes every lap after it. Decisions cannot be judged one at a time. |
| **Dynamic** | Yes | The race keeps running while an agent thinks; the world changes between two decisions. |
| **Continuous** | Mostly | Positions and times are continuous; the search works on a discrete lap-by-lap abstraction of it. |
| **Multi-agent** | Yes — both competitive and cooperative | Teams compete with each other; the two drivers and the strategist inside a team cooperate and must share one pit box. |
| **Known** | Yes | The rules of the world (tyre wear, pit loss, fuel effect) are known to the agents; the *state* is what is hidden. |

This mix is why a fixed plan cannot work, and why the agents re-plan whenever something changes.

---

## 4. Agent architecture

| Agent | AIMA type | What it means here |
|---|---|---|
| **Driver** | Model-based **reflex agent** (condition–action rules) | "If my tyres are more than 70 % worn → tell the strategist and ask to come in." Simple, fast rules on top of a small internal model (what it has already said, its own tyre state). |
| **Strategist** | **Goal-based / utility-based agent** with search | It has a model of how the race evolves and searches over possible pit-stop plans, choosing the one with the lowest predicted time. It also keeps **beliefs** (probabilities) about hidden rival information. |

The strategist has the final say. A driver can push back once ("my tyres still feel good"), and the
strategist re-plans and either agrees or insists. This is a deliberate, visible negotiation.

**One step of the simulation** (`Race.step()` in `sim/race.py`, 0.2 s of race time):

1. Race control: update the weather, the flags, the safety car, trigger any crash.
2. Move every car; cars in the pit lane are served by the single pit box.
3. Drivers attack, defend or fall back into line behind the car ahead.
4. Every driver agent runs its rules and may radio its strategist.
5. Every strategist reads its radio, re-plans (A*), runs duels (minimax), updates its beliefs (Bayes),
   and radios its drivers.

Mesa's scheduler runs the agents: `agents_by_type[DriverAgent].do("step")` then
`agents_by_type[StrategistAgent].do("step")`, so all drivers report before any strategist decides.

---

## 5. The algorithms and why we chose them

All four are standard AIMA material. Nothing is a black box, and every number the agents use can
be printed in the terminal with `plan <driver>` and `why <driver>`.

### 5.1 A* search — planning the pit stops (`sim/search.py`, `plan_stops`)

The strategist has to answer: *on which laps do we stop, and for which tyres?*

| Search element | Definition in this project |
|---|---|
| **State** | `(lap, tyre on the car, age of that tyre, set of tyre types already used)` |
| **Initial state** | Where the car is now (laps that can no longer be changed are locked in) |
| **Actions** | "Drive the next lap on the current tyres", or "Stop at the end of this lap and fit SOFT / MEDIUM / HARD (and WET if rain is forecast)" |
| **Step cost** | Predicted lap time in seconds, plus 21 s if a stop happens (about 10 s under the safety car) |
| **Goal test** | Reached the last lap **and** used two different dry tyres (or wets at some point) — the sporting rule |
| **Solution** | The list of stops with the lowest total predicted time |

**The heuristic** (`h`) is the cost of a **relaxed problem**: assume the tyres never wear out, so
every remaining lap is driven at the fastest possible lap time for the forecast weather, and add
one cheapest pit stop only if the two-tyre rule has not been satisfied yet.

*Why it is admissible:* removing tyre wear can only make laps faster, the fastest tyre is a lower
bound for any tyre choice, and the car provably still has to make at least one more stop when the
rule is unmet. So `h` can never be larger than the true remaining cost, and A* returns the optimal
plan. It is also consistent (each lap's estimate drops by at most that lap's true cost), so no state
needs to be re-expanded.

*Proof by experiment:* the same search with `h = 0` is **uniform-cost search**, and the app runs both
side by side. From a real race (`plan NOR` on lap 2):

```
A* checked 314 plans in 4.4 ms. Uniform-cost search checked 1143 plans in 14.6 ms for the same answer.
```

Same answer, about **3.6× fewer nodes** — the classic demonstration that a good admissible heuristic
speeds up search without losing optimality.

**Why not the alternatives?**

| Alternative | Why not |
|---|---|
| Breadth-first search | Ignores cost; here the cost (seconds) is the whole point. |
| Depth-first search | Not optimal, and can dive down a hopeless branch. |
| Greedy best-first | Fast but not optimal — it would happily pick a plan that is cheap now and terrible later. |
| Hill climbing / local search | Gets stuck: the plan "stop on lap 11" and "stop on lap 12" look almost identical, but a one-lap change can flip who is ahead. No optimality guarantee. |
| Reinforcement learning / genetic algorithms | Needs training runs, gives no explanation, and cannot be defended line by line in a viva. The model here is known, so search is the right tool. |

The search runs in milliseconds, so it is re-run **every time something changes** — that is the
"dynamic re-planning" you see in the message feed.

### 5.2 Minimax with alpha–beta pruning — the stop-timing duel (`minimax_duel`)

When a rival is within 3 seconds, the timing of the stop stops being a one-player problem: whoever
stops first gets fresh tyres first (the *undercut*), but also spends 21 s in the pit lane first.

| Game element | Definition |
|---|---|
| **Players** | Us (MAX) and the closest rival (MIN) |
| **Moves** | `PIT` (stop at the end of this lap) or `STAY` (one more lap) |
| **Depth** | 2 — we choose, the rival replies |
| **Utility** | Our predicted gap to the rival in seconds three laps later (positive = we are ahead) |

The utility comes from the same lap-time model used by A*, using the **believed** tyre wear of the
rival from the Bayesian estimator — so the two algorithms feed into each other.

*Why depth 2?* The whole decision is "this lap or next lap"; a deeper tree would model laps that the
next event (rain, safety car, a driver's message) is very likely to invalidate anyway. Depth 2 is the
honest depth for this question, and it keeps the explanation readable.

*Alpha–beta* prunes branches the rival can already make no better than an option we hold. Because
the tree is small the saving is small, but it is real and is reported in the app:

```
why RUS
Lap 5: the Mercedes strategist changed Russell's plan.
  before:  change to Hard tyres at the end of lap 7
  after:   change to Hard tyres at the end of lap 5
  because: Leclerc is close, so the timing of our stop decides who stays ahead.
           Cover Leclerc's undercut: pit now to stay ahead.
  how:     Minimax against Leclerc: stop now -> +0.2 s, wait a lap -> -0.1 s
           (+ means ahead of Leclerc); 1 option(s) pruned by alpha-beta.
```

The result is named in plain F1 language — **undercut** (stop first to jump ahead), **cover** (stop
to stop a rival's undercut working), **overcut** (stay out while the rival is in the pit lane) — and
a few laps later the strategist reports whether it actually worked.

### 5.3 Bayesian estimation — how worn are the rival's tyres? (`bayes_update`, `watch_rivals`)

A strategist cannot see how fast a rival's tyres wear, but minimax needs exactly that number.
Only the rival's **lap times** are public, and lap times are noisy and also depend on the driver's
own pace, which is hidden too.

| Bayes element | This project |
|---|---|
| **Hypotheses** | The rival's tyre wear is `LOW` (×0.75), `NORMAL` (×1.0) or `HIGH` (×1.5) |
| **Prior** | Uniform: 1/3 each, at the start of the race |
| **Evidence** | The clean laps of the rival's current stint (no in-laps, out-laps, traffic, yellow flags, safety car or rain — so no lap is counted twice or distorted) |
| **Likelihood** | Gaussian on the *trend* of the lap times: the residual from the model under each hypothesis, with the mean residual subtracted so the driver's unknown constant pace is fitted out. Noise = the race model's lap-to-lap noise. |
| **Posterior** | `prior × likelihood`, normalised (Bayes' rule). Recomputed after every lap; when the rival stops, the posterior becomes the **prior for the next stint**. |

Computed in log space and shifted by the maximum so the numbers cannot underflow.

**Why Bayesian and not a single estimate?** A point estimate ("his tyres wear 1.2× as fast") would
hide how sure we are. With a distribution the strategist can (a) use the **expected** wear in
minimax, so an uncertain guess pulls the answer only slightly, and (b) only tell its drivers when it
is at least 80 % sure. The belief is printed live:

```
McLaren's Bayesian estimate of rival tyre wear:
  ANT: low 55%, normal 42%, high 3%;  HAM: low 15%, normal 30%, high 55%;  RUS: low 26%, normal 64%, high 9%
```

Piastri is the driver actually given HIGH tyre wear in `data/teams.json`. Rival teams identify this
from lap times alone with 86–99 % confidence by mid-race, and never confidently call a wrong level —
that is the estimator working, checked in `tests/test_search.py`.

### 5.4 Condition–action rules — the drivers

The drivers are deliberately simple reflex agents. Their rules:

| Condition | Action |
|---|---|
| Tyres ≥ 70 % worn | Report the wear, then request a stop |
| It is raining and I am on dry tyres | Request wet tyres (once per rain level) |
| On wet tyres and the track is drying | Report it |
| The safety car is out | Ask whether to come in now |
| Stuck > 20 s behind the same car | Report who is blocking me |
| Told to pit early and my tyres feel fine (< 50 % worn) | Push back once |
| Pace advantage over the car ahead (≥ 0.1 s, `overtake_min_advantage_s`) and tyres < 80 % worn, on a long straight | Attack the car ahead |
| Being attacked: teammate | Let him through |
| Being attacked: tyres > 90 % worn | Do not fight (defending would cost more than it gains) |
| Being attacked otherwise | Defend (costs 0.3 s of lap time) |

Simple rules here are the *right* design: a driver has no time to run a search in a corner, and the
contrast between reflex drivers and searching strategists is itself part of the case study.

---

## 6. Multi-agent interaction

This is the core of the project: agents that **change each other's decisions**, visibly.

### 6.1 The message protocol (`sim/messages.py`)

Every agent has an inbox. Five message kinds:

| Kind | From → to | Example |
|---|---|---|
| `INFO` | driver → strategist, or strategist → driver | "My Medium tyres are 74 % worn and I'm getting slower." |
| `REQUEST` | driver → strategist | "The safety car is out. Should I come in for new tyres now?" |
| `INSTRUCTION` | strategist → driver | "Box this lap! Come in for Hard tyres at the end of lap 11." |
| `REPLY` | driver → strategist | "My tyres still feel good (41 % worn). I can stay out longer." |
| `EVENT` | race control → everyone | "Safety car deployed." / "Rain is getting heavier: medium." |

**Team radio is private.** The message board refuses any message sent to another team and raises an
error (`test_team_radio_stays_inside_the_team`). Teams learn about each other only through the
public timing screen — which is what forces the Bayesian estimation instead of simply reading the
rival's plan.

Every plan change is also written to a **decision record** with `before`, `after`, `because` and the
numbers behind it (`detail`), tagged with a cause: `driver`, `rival`, `incident`, `weather`, `team`
or `laps`. The page shows these in the feed, and the terminal prints one with `why <driver>`.

### 6.2 The five interaction patterns

**1. Request → reply → changed decision (cooperation inside a team).**
A driver reports worn tyres → the strategist re-runs A* → the plan changes → the driver is told.
The feed shows the cause `driver`, so it is clear that *another agent's message* changed the plan.

**2. Negotiation / push-back (conflict inside a team).**
The strategist calls a car in early; the driver disagrees because the tyres feel fine. The
strategist re-plans with the driver's measurement and either changes the plan or insists:
"Understood, but box now anyway — stopping this lap is still the fastest option." The driver obeys.
The strategist has the final say, but only after taking the new evidence into account.

**3. Competition between teams (undercut / cover / overcut).**
A rival pits → every other strategist is woken by the public pit-entry event → each runs a minimax
duel and may pull its own stop forward (cover), jump first (undercut), or stay out while the rival
is in the pit lane (overcut). A few laps later the strategist reports whether it worked. This is
one team's action directly changing another team's plan in real time.

**4. Resource conflict inside a team — the shared pit box (deadlock avoidance).**
Both cars of a team can want the same lap for their stop, but a team has **one pit box**: the second
car would sit waiting for the first to be released (2.5 s stop + 3.0 s box reset). The strategist
compares the two options with the same cost model:

```
McLaren changed Norris's plan
  before:  change to Wet tyres at the end of lap 4
  after:   change to Wet tyres at the end of lap 5
  because: Piastri stops just ahead of us in the same pit box, and one more lap costs less
           than waiting behind him.
  how:     Waiting in the box behind Piastri: about 5.3 s.
           Staying out one more lap instead: about +1.8 s.
```

It then either sends the second car out for **one more lap** (above), or **double-stacks** both cars
on the same lap and tells the second driver exactly what it will cost him:

```
Mercedes strategist -> Russell: Box this lap! Come in for Hard tyres at the end of lap 5.
  Double stack: you come in right behind Antonelli (about 4 s wait), still better than
  another lap out.
``` The lap it rejected is remembered, so
A* and the duels cannot immediately propose it again — that is the deadlock/livelock guard
(`skipped_for_box`), and a test checks the same box decision is never repeated.

**5. Driver-level competition (overtaking).**
The attacking driver decides to attack (pace advantage + tyre wear), the defending driver decides
independently whether to defend, let a teammate through, or not fight on worn tyres. Defending
costs the defender lap time, so the choice matters. All of it is announced on the radio and the
timing screen.

### 6.3 A real exchange from the app

Copied from a real race (seed 1). Two teams watch the same close rival and react differently:

```
Lap 2  EVENT        Timing screen -> everyone: Russell overtakes Leclerc into Turn 15.
Lap 2  INFO         Hadjar -> Red Bull strategist: Attacking Hamilton into Turn 15:
                    I'm 0.4 s a lap faster and my tyres are 8% worn.
Lap 2  INFO         Hamilton -> Ferrari strategist: Hadjar is attacking me. Defending into Turn 15.
Lap 2  EVENT        Timing screen -> everyone: Hadjar overtakes Hamilton into Turn 15.

Lap 5  DECISION     Mercedes changed Russell's plan
       before:  change to Hard tyres at the end of lap 7
       after:   change to Hard tyres at the end of lap 5
       because: Leclerc is close, so the timing of our stop decides who stays ahead.
                Cover Leclerc's undercut: pit now to stay ahead.
       how:     Minimax against Leclerc: stop now -> +0.2 s, wait a lap -> -0.1 s;
                1 option(s) pruned by alpha-beta.
Lap 5  INSTRUCTION  Mercedes strategist -> Russell: Box this lap! Come in for Hard tyres
                    at the end of lap 5.
Lap 5  REPLY        Russell -> Mercedes strategist: OK, coming in for new Hard tyres.

Lap 5  DECISION     Red Bull changed Verstappen's plan
       before:  change to Hard tyres at the end of lap 7
       after:   change to Hard tyres at the end of lap 5
       because: Leclerc is close, so the timing of our stop decides who stays ahead.
                Undercut Leclerc: pit now - fresh tyres will get us ahead of them.
       how:     Minimax against Leclerc: stop now -> -0.2 s, wait a lap -> -0.5 s;
                1 option(s) pruned by alpha-beta.
Lap 5  INSTRUCTION  Red Bull strategist -> Verstappen: Box this lap! ...
Lap 5  EVENT        Timing screen -> everyone: Russell came into the pit lane for new tyres.
Lap 6  INSTRUCTION  Mercedes strategist -> Russell: Good stop. New plan: no more tyre stops.
```

Six agents, three teams: two drivers fight on track, and one rival's position makes two different
teams pull their stops forward on the same lap — one to *cover*, one to *undercut*.

---

## 7. Tools and packages

| Package | Used for | Why this one |
|---|---|---|
| **Mesa 3.5** | The agent framework: `Model`, `Agent`, seeded randomness, scheduling agents by type | The standard Python framework for agent-based models, and the one named in the brief. It gives agent registration, per-type activation (`agents_by_type[...].do("step")`) and reproducible seeding for free — the whole race is deterministic from one seed, which is what makes the demo repeatable. |
| **FastAPI + WebSockets** | The server: commands over HTTP, race state pushed to the page 10×/second | Async by design, so the race loop, the terminal and the browser share one event loop with no threads to manage. |
| **uvicorn** | Runs the server | Standard ASGI server for FastAPI. |
| **prompt_toolkit + rich** | The terminal console | Lets you keep typing while the race prints messages (`patch_stdout`), with colour. Falls back to plain `input()` when there is no real console (e.g. Git Bash on Windows). |
| **NumPy** | The track geometry and the Bayesian likelihood | Vector maths for resampling the racing line and for the sum-of-squares in the likelihood. |
| **pandas** | Reading the track and corner CSVs | The data comes from real telemetry in CSV form. |
| **Next.js 16 + React 19 + Tailwind 4** | The page: timing tower, track map, message feed | React re-renders the tower and feed cleanly from a stream of state updates; the track map is drawn on a canvas for smooth movement. |
| **pytest** | 33 automated tests | Including the stress/fuzz tests. |
| **FastF1** (`tools/requirements.txt` only) | Extracting the real race data, once | Standard library for official F1 timing data. It is **not** needed to run the app — the extracted data is committed in `data/`. |

**Considered and rejected:** *CrewAI / LangChain / AutoGen* — built around LLM agents, which would
make every decision unexplainable and non-reproducible, the opposite of what this case study needs.
*ROS* — robotics middleware, far too heavy. *SPADE* — needs an XMPP server for messaging, when a
message board of 60 lines does the job and can be read in full by the examiner.

**Modularity.** The simulation (`sim/`) knows nothing about the server, and the server knows nothing
about the browser. `sim/` can be imported and run on its own — every test does exactly that, and the
whole race can be run headless in a few lines. The UI is one consumer of the state; the terminal is
another.

---

## 8. The data

The race is the **2026 British Grand Prix at Silverstone** (a dry race, so tyre strategy is the
whole story), extracted once with FastF1 by `tools/extract_race_data.py` and fitted by
`tools/fit_model.py` into `data/race_model.json`.

| Value | Where it comes from |
|---|---|
| Base lap time 94.97 s, fuel effect −0.167 s per lap, per-driver pace offsets | Measured from the real race's clean laps |
| Tyre offsets and wear rates (Soft −0.6 s but 0.264 s/lap of wear; Medium 0; Hard +0.4 s, 0.079 s/lap) | Fitted to the real stints |
| Pit loss 21.0 s | Measured from the real race |
| Track and corner positions | Real telemetry of the fastest lap |
| Rain effects, safety-car pit loss (10 s), lap noise (0.15 s) | Set by hand, documented in the JSON, because the real race was dry |
| Piastri's HIGH tyre wear, the starting tyres, HAD in place of TSU | Set by hand for the demo, in `data/teams.json` |

Driver pace differences are scaled down to a quarter (`PACE_SPREAD = 0.25`) so the cars stay close
enough to actually race each other — a realistic spread of tens of seconds would make a boring demo.
The safety car runs for 2 laps and a car will attack for a pace advantage of 0.1 s, both tuned so
that a 20-lap demo has enough happening in it.

The app **never** connects to the internet or to any other project: everything it needs is in `data/`.

---

## 9. Code map

```
run.py                 starts the server and the terminal together
sim/
  model.py     58 ln   lap-time rules: tyres, fuel, wear, rain (all numbers from data/)
  track.py    130 ln   Silverstone geometry: positions, overtaking straights, the pit lane
  search.py   124 ln   THE ALGORITHMS: A*/UCS, minimax with alpha-beta, Bayes' rule
  messages.py  65 ln   team radio, public announcements, the record of every decision change
  driver.py    97 ln   driver agent: condition-action rules, attacking and defending
  strategist.py 374 ln strategist agent: planning, duels, beliefs, the pit-box decision
  race.py     458 ln   the world: cars, laps, pit stops, crashes, safety car, rain, overtakes
server/
  engine.py   175 ln   real-time loop, terminal commands, state for the page
  api.py       48 ln   FastAPI routes and the WebSocket
  console.py   56 ln   the terminal itself
web/src/               Next.js page: timing tower, track map, message feed
tools/                 one-off scripts that produced data/ (not needed to run the app)
tests/                 33 tests
docs/
  DOCUMENTATION.md     this file
  DEMO.md              the demo script
```

Every file starts with a one-line docstring saying what it is for, and every non-obvious number is a
named constant with a comment (`STUCK_S`, `DUEL_GAP_S`, `SHARE_CONFIDENCE`, `OVERTAKE_ROOM_M`, …).

---

## 10. Testing

```bash
python -m pytest -q
```

33 tests, about 35 seconds.

| File | What it checks |
|---|---|
| `tests/test_search.py` | A* returns the optimal plan and the **same cost as uniform-cost search** while expanding fewer nodes; the heuristic never overestimates; the tyre rule is always met; wet tyres are only considered when rain is forecast; minimax picks the better move and alpha-beta prunes; Bayes converges on the right wear level and stays uncertain when the evidence is weak. |
| `tests/test_race.py` | Races finish with valid results from several seeds; the two-tyre rule holds; crashes produce a yellow flag then the safety car; nobody overtakes behind the safety car; cars in the pit lane are drawn on the pit lane; every plan change names a cause; rain makes teams fit wets and go back to slicks; teammates double-stack or stay out and never repeat a rejected box decision; every attack gets an answer and a result; undercuts are announced and their outcome reported. |
| `tests/test_server.py` | Every terminal command and the API/WebSocket, including bad input. |
| `tests/test_stress.py` | **Stress / fuzz**: 5 seeds × 6000 steps with random commands fired at random moments (including typos, `speed 3`, `crash NOBODY`, `restart abc`, restarts mid-race) — the race must never break and the invariants must hold at **every** step; crashing all 8 cars ends the race cleanly; rain, a safety car, more rain and a second safety car can be stacked in any order. |

The invariants checked at every single step: every car is in a valid state, no car exceeds the race
distance, lap counts stay in range, tyres are real tyres, the rain level stays in 0–1, and the
standings are always correctly ordered.

---

## 11. Honest limitations

These are deliberate simplifications, not bugs:

- **Fixed grid of 8 cars, 20 laps.** Enough for a 3-minute demo; the code has no hard-coded limit.
- **No fuel or engine management, no tyre temperature, no DRS.** Tyres, time and position only.
- **Overtaking is probabilistic**, not a physical model of the corner.
- **Rain is a single number 0–1** that drifts towards a random target — not a weather map.
- **Minimax is depth 2 against one rival**, not a full 8-player game tree. Modelling every car's
  reply to every car would be exponential and would be invalidated by the next event anyway.
- **The lap-time model is the agents' model of the world and also the world itself.** Rival wear
  and pace are still hidden and must be estimated, but there is no model error beyond the noise.

---

## 12. How this meets the marking criteria

| Criterion | Where it is in this project |
|---|---|
| **Tool / package selection & setup** | Mesa for the agents, FastAPI + WebSocket for the live server, Next.js for the page, pytest for the tests (§7), each with a justification and rejected alternatives. `sim/` is independent of the server, and the server is independent of the browser, so the simulation runs headless on its own. Setup is two commands per side and everything needed is committed. |
| **Multi-agent execution & interaction** | 12 agents, private team radio, public timing screen (§6). Five interaction patterns: request→reply, **renegotiation** (driver push-back), **competition** (undercut / cover / overcut between teams), **shared-resource conflict resolution** (one pit box, double-stack vs one more lap, with a guard so the rejected decision is never re-proposed), and driver-level attack/defend. **Predictive planning**: A* over the rest of the race, minimax over the rival's reply, and Bayesian belief about hidden rival wear feeding into that minimax. Every changed decision records what changed it. |
| **Demo quality & testing scenarios** | Live race with a timing tower, track map and message feed, plus a terminal with `status`, `plan`, `why`. Scenarios on demand: `crash <driver>` (safety car), `rain start` / `rain stop` (random intensity), `pause` to read the decisions, `speed 0.5–4`, `restart <seed>` for a different race. Shocks can be combined in any order, and the fuzz tests fire random and invalid commands at random moments (§10). Every race is reproducible from its seed. |
| **Code structure & scalability** | ~1 400 lines of simulation and server code, split by responsibility (§9), documented, no dead code, 33 tests. The algorithms live in one file (`sim/search.py`) and are used by the agents, not buried in them. |

---

*Run it: see [../README.md](../README.md). Demo script: [DEMO.md](DEMO.md).*
