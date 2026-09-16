"use client";

import { useMemo } from "react";
import RadioFeed from "@/components/RadioFeed";
import TimingTower from "@/components/TimingTower";
import TrackMap from "@/components/TrackMap";
import { sendCommand, useRace } from "@/lib/race";

const SPEEDS = [1, 2, 4];

export default function RaceScreen() {
  const { track, state, feed, connected } = useRace();
  const teamColors = useMemo(
    () => Object.fromEntries((state?.cars ?? []).map((car) => [car.team, car.color])),
    [state?.cars],
  );

  let hint = "";
  if (!connected) hint = "Waiting for the race server. Start it with: python run.py";
  else if (state && !state.started) hint = "Type  start  in the terminal to begin the race";
  else if (state?.over) hint = "Race over. Type  restart  in the terminal for a new race";
  else if (state && !state.running) hint = "Paused. Type  resume  in the terminal";

  return (
    <div className="flex h-screen flex-col gap-3 bg-neutral-950 p-3 text-white">
      <header className="flex flex-wrap items-center gap-x-6 gap-y-2 rounded-xl border border-white/10 bg-neutral-900/70 px-5 py-3">
        <div className="mr-auto">
          <h1 className="text-xl font-black tracking-tight">F1 Strategy Agents · Silverstone</h1>
          <p className="text-sm text-neutral-400">
            12 AI agents race: in each of 4 teams a strategist plans the tyre stops and 2 drivers report back. Watch
            them change each other&apos;s decisions.
          </p>
          {hint && <p className="mt-1 text-sm font-semibold text-amber-300">{hint}</p>}
        </div>
        {state && (
          <span className="text-2xl font-black">
            Lap {state.lap}
            <span className="text-base text-neutral-400"> / {state.total_laps}</span>
          </span>
        )}
        <div className="flex items-center gap-1.5">
          <span className="mr-1 text-xs font-semibold uppercase text-neutral-400">Speed</span>
          {SPEEDS.map((speed) => (
            <button
              key={speed}
              onClick={() => sendCommand(`speed ${speed}`)}
              disabled={!connected}
              className={`rounded-lg px-4 py-2 text-base font-black transition ${
                state?.speed === speed ? "bg-red-600 text-white" : "bg-white/10 text-neutral-200 hover:bg-white/20"
              } disabled:opacity-40`}
            >
              ×{speed}
            </button>
          ))}
        </div>
      </header>

      <main className="grid min-h-0 flex-1 grid-cols-[360px_1fr_460px] gap-3">
        <TimingTower cars={state?.cars ?? []} />
        {track && state ? (
          <TrackMap track={track} state={state} />
        ) : (
          <section className="flex items-center justify-center rounded-xl border border-white/10 text-neutral-500">
            Loading the track…
          </section>
        )}
        <RadioFeed feed={feed} teamColors={teamColors} />
      </main>
    </div>
  );
}
