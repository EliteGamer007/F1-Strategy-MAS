# Demo script

A 5–6 minute live demo. Every race is reproducible from its seed, so a rehearsed run behaves the
same way on the day. Full explanations are in [DOCUMENTATION.md](DOCUMENTATION.md).

## Before you start

Two terminals, from the project folder:

```bash
python run.py
```

```bash
cd web && npm run dev
```

Open <http://localhost:3000> and put the browser beside the terminal. You should see the grid,
"Lap 1 / 20" and the play button. If the page says it is not connected, the first terminal is not
running.

Useful: `restart 1` gives the race used in the examples below. `restart 42` is the default.

---

## The run

### 1. What the audience is looking at (30 s)

> "Twelve agents are racing: four teams, and each team has one strategist agent and two driver
> agents. The strategist plans the tyre stops, the drivers drive and report back. On the left is
> the running order, in the middle the track, and on the right every message the agents send each
> other and every decision they change."

Type:

```
start
```

The race starts. Press **×4** to get through the early laps, then **×1**.

### 2. Agents talking (1 min)

Point at the feed as the first messages arrive: the strategist radios each driver the plan, drivers
reply. Then a driver reports worn tyres and asks to come in, and the strategist answers.

Press **Pause** and read one aloud:

```
Lap 7  Instruction  McLaren strategist -> Piastri: Box this lap! Come in for Hard tyres ...
```

> "Nothing here is scripted. The driver noticed his own tyre wear, sent a message, and the
> strategist re-ran its search and answered."

Press **Play** again.

### 3. The algorithms, in the terminal (1½ min)

While the race runs:

```
plan NOR
```

Shows the current plan, **A\*** versus **uniform-cost search** (same answer, far fewer plans
checked), and the team's **Bayesian** estimate of every rival's tyre wear.

> "The plan is found with A\* search. The heuristic assumes the tyres never wear out, which can
> never overestimate the real time — so A\* is guaranteed to find the fastest plan. Running it
> without the heuristic is uniform-cost search: the same answer, but it checks three times as many
> plans."

```
why RUS
```

Shows the last plan change for that car: before, after, why, and the **minimax** numbers with how
many branches alpha–beta pruned.

> "When a rival is within three seconds, stopping becomes a two-player game — so the strategist
> runs minimax: we choose, the rival replies. It uses the Bayesian estimate of the rival's tyre
> wear, so two algorithms feed into each other."

### 4. Teams changing each other's decisions (1 min)

Watch for an **undercut**, **cover** or **overcut** in the feed — one team pits, and other teams
immediately pull their own stops forward. A few laps later the strategist reports the outcome:

```
The undercut worked: you are now ahead of Hadjar.
Covering Leclerc's undercut: it worked, you stayed ahead of Leclerc.
```

> "One team's pit stop just changed another team's plan, live. They cannot see each other's plans —
> only the public timing screen, exactly like the real thing."

### 5. Shock 1: a crash and the safety car (1 min)

The two Ferraris crash on their own at random laps — the first brings a yellow flag, the second the
safety car. To force it at the moment you want:

```
crash VER
```

> "I have just taken a car out of the race. The safety car comes out, everyone slows down, and a
> pit stop now costs half as much time — so every strategist re-plans at once."

Watch the feed: drivers ask "should I come in now?", strategists answer, and several plans change
with the cause *safety car*. Also watch for the **pit box conflict**: when both cars of a team want
the same lap, the strategist either double-stacks them or keeps one out for a lap, and says exactly
how many seconds each option costs.

### 6. Shock 2: rain (1 min)

```
rain start
```

> "How hard it rains is random. The teams decide for themselves whether to fit wet tyres now or
> wait a lap, and they switch back when the track dries."

Watch the weather chip at the top of the page and the tyres in the timing tower turning blue.

```
rain stop
```

### 7. Close (30 s)

Let it run to the finish (**×4**) and read the closing line:

```
Race over. Antonelli wins! The strategists changed a plan 7 times: 1 after a driver's message,
5 because of a rival team, 1 because of the safety car, 0 because of rain, 0 to avoid waiting in
the pit box, and 0 from new lap times.
```

> "Every one of those changes was caused by another agent's message or by an event — that is the
> multi-agent part. And the whole race is reproducible from its seed."

Optional, if you are asked about robustness:

```bash
python -m pytest -q
```

33 tests, including a fuzz test that fires random and invalid commands at random moments across
several races.

---

## If something goes wrong

| Problem | Fix |
|---|---|
| The page shows no cars | The first terminal (`python run.py`) is not running, or `start` has not been typed. |
| The race is going too fast to narrate | **Pause**, or **×0.5**. |
| You want the same race again | `restart 1` then `start`. Any seed works: `restart 7`. |
| A command is refused | `crash` and `rain` need a race in progress. Type `start` first. |
| You forget a command | `help`. |

## Commands worth having on a card

```
start / pause / resume      speed 0.5 | 1 | 2 | 4
crash <driver>              rain start | rain stop
status                      plan <driver>        why <driver>
restart [seed]              help                 quit
```
