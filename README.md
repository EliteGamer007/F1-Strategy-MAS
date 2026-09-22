# F1 Strategy Agents

A multi-agent F1 race strategy demo for the AI Search Methods case study.
4 teams race 20 laps of Silverstone. Each team has **3 agents**: a **strategist** that plans tyre stops and **2 drivers** that race and report back (12 agents in total).
You control the race from a terminal and watch it on a web page.

See **[docs/DOCUMENTATION.md](docs/DOCUMENTATION.md)** for the full write-up and **[docs/DEMO.md](docs/DEMO.md)** for the demo script.

## Objectives

1. **Show the problem as an AI problem**: PEAS, and an environment that is partially observable, stochastic, dynamic and multi-agent.
2. **Show search algorithms doing real work** (AI: A Modern Approach):
   - **A\*** plans each car's tyre stops (uniform-cost search is shown alongside for comparison).
   - A **Bayesian estimator** (Bayes' rule) works out the hidden tyre wear of rival cars from their lap times.
   - **Minimax with alpha-beta pruning** decides "stop now or wait a lap" when a rival is close (undercut / overcut).
   - **Condition-action rules** drive each driver agent.
3. **Show agents changing each other's decisions**: every message appears on screen, and every changed plan says which agent or event caused it.

## Running it

```bash
pip install -r requirements.txt
python run.py                    # race server + terminal for commands
```

In a second terminal:

```bash
cd web
npm install                      # first time only
npm run dev                      # open http://localhost:3000
```

Type `start` in the first terminal. The page shows:

- **Timing tower**: position, tyres and their age, gap to the leader, stops, next planned stop. Cars in the pit lane are highlighted in amber, crashed cars in red.
- **Track map**: cars move on the real 2026 Silverstone layout; cars changing tyres are drawn on the pit lane beside the main straight.
- **Team radio & decisions**: a scrolling list of every message and every plan change (before, after and why).
- **Play / pause button** to freeze the race and read the decisions, and **×0.5 / ×1 / ×2 / ×4 buttons** for race speed.
- **Weather chip**: dry, or light / medium / heavy rain and whether it is getting heavier or lighter.

Tests:

```bash
python -m pytest -q                # 33 tests, about 35 s
```

## Terminal commands

| Command | What it does |
|---|---|
| `start` | Start the race |
| `pause` / `resume` | Freeze or continue the race |
| `speed 0.5`, `speed 1`, `speed 2`, `speed 4` | Race speed (same as the buttons on the page) |
| `rain start` / `rain stop` | Start or stop rain; how heavy it gets is random (set by the seed) |
| `crash <driver>` | Crash a car out of the race; the safety car comes out automatically |
| `status` | Running order, tyres, gaps and each car's next tyre stop |
| `plan <driver>` | The strategist's plan for that car, how many plans A* and UCS checked, and the team's guesses of rival tyre wear |
| `why <driver>` | Why that car's plan last changed (with the minimax numbers for close fights) |
| `restart [seed]` | Back to the grid; the same seed gives the same race |
| `help` / `quit` | Show the commands / close the app |

Drivers can be named by code or surname, e.g. `crash VER` or `plan piastri`.

## What happens in a race

- Every car must use two different tyre types, so every car stops at least once. Strategists announce a plan at the start and change it when something happens.
- **Driver reports change plans**: when a driver says his tyres are worn, or that they still feel good, the strategist re-plans with A*.
- **Rival teams change plans**: when a rival is within 3 seconds, or stops for tyres, the strategist runs minimax to decide whether to stop now or wait. The message names the move: **undercut** (stop first to get ahead), **cover** (stop to stay ahead of a rival's undercut) or **overcut** (stay out while the rival is in the pits). A few laps later the strategist tells the driver whether it worked.
- **Overtakes are decided by the drivers**: a driver attacks on a long straight only if clearly faster and the tyres are not worn out, and says so on the radio. The driver ahead defends (costs a little lap time), lets a teammate through, or does not fight on worn-out tyres. The timing screen reports the result.
- **Rain** (`rain start`): the rain level drifts towards a random target. Dry tyres get slower as it rains harder; wet tyres are faster above light rain. Teams decide to stop for wet tyres now, or wait a lap if the rain is light and not getting heavier, and switch back to dry tyres when it dries.
- **Double stack or stay out**: if both cars of a team want to stop on the same lap, the second car would wait in the pit box. The strategist compares that wait with the time lost by staying out one more lap and picks the cheaper one (also under the safety car).
- **Crashes**: both Ferraris crash at random points in every race. The first crash brings a yellow flag (drivers slow down near it); the second brings out the **safety car**. `crash <driver>` always brings out the safety car. Behind the safety car nobody can overtake and a tyre stop is much cheaper, so every strategist re-plans at once.
- The race ends with a summary of how many plans were changed by drivers, rivals, incidents, the weather and the pit box.

## Documentation

| Document | What is in it |
|---|---|
| **[docs/DOCUMENTATION.md](docs/DOCUMENTATION.md)** | The full case study: the problem, PEAS for both agent types, the environment analysis, the four algorithms with the reasoning behind each choice, how the agents interact, the tools, the data, the tests and the limitations. |

## Project structure

```
run.py              starts the race server and the terminal
sim/                the race and the agents (no web code)
  race.py           the environment (Mesa model): cars, pit stops, crashes, safety car
  driver.py         driver agent: condition-action rules
  strategist.py     strategist agent: A* plans, Bayesian tyre estimates, minimax duels
  search.py         A* / UCS, minimax with alpha-beta, Bayes rule
  messages.py       team radio (private) and public announcements, plan-change records
  model.py          lap-time rules read from data/race_model.json
  track.py          Silverstone geometry, overtaking straights, pit lane
server/             FastAPI + WebSocket server, commands, terminal
web/                Next.js page: timing tower, track map, radio feed
data/               race data (see below)
tools/              one-off scripts that produced data/
tests/              python -m pytest  (33 tests, including a fuzz/stress test)
docs/               DOCUMENTATION.md
```

## Data (already in this folder, nothing to download)

| File | What it holds |
|---|---|
| `data/silverstone_2026_track.csv` | Racing line x, y, distance (5,817 m), from the fastest race lap |
| `data/silverstone_2026_corners.csv` | 18 corners with label positions |
| `data/silverstone_2026_laps.csv` | Every lap of the real 2026 British GP: driver, team, lap time, tyre, tyre age, pit in/out, flag status |
| `data/silverstone_2026_summary.json` | Race facts: 52 laps, dry, 24.8 °C air, safety car and VSC laps |
| `data/teams.json` | McLaren (NOR, PIA), Ferrari (LEC, HAM), Red Bull (HAD, VER), Mercedes (ANT, RUS): 2026 colours, real grid, demo settings |
| `data/race_model.json` | Lap-time numbers used by the simulator, each marked `data` (measured) or `hand` (set by us) |

The app only reads `data/`. It does not use FastF1, the internet, or the F1-Telemetry-Analysis project.

The demo does not copy the real race exactly: the race is 20 laps (tyre wear and fuel effect are scaled by 52/20), cars start on different tyres, Piastri has worse tyre wear than everyone else, and the real pace differences between drivers are scaled down to a quarter so the cars race closely.

### How the data was made (only needed to regenerate it)

```bash
pip install -r tools/requirements.txt
python tools/extract_race_data.py   # downloads the race through FastF1 and writes the CSV/JSON files
python tools/fit_model.py           # fits tyre wear, fuel effect, pit loss and driver pace into race_model.json
```

`extract_race_data.py` reuses `../F1-Telemetry-Analysis/cache` if it exists, otherwise it creates `.fastf1_cache/`.
If the MultiViewer circuit API is unreachable, it lines up the lap with a saved Silverstone layout to place the corners.
