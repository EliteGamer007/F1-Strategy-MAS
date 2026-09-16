import { Car, TYRE_COLORS } from "@/lib/race";

function TyreBadge({ tyre, age }: { tyre: Car["tyre"]; age: number }) {
  return (
    <span className="flex items-center gap-1.5">
      <span
        className="flex h-6 w-6 items-center justify-center rounded-full border-[3px] bg-neutral-900 text-[11px] font-black"
        style={{ borderColor: TYRE_COLORS[tyre], color: TYRE_COLORS[tyre] }}
        title={`${tyre.toLowerCase()} tyres`}
      >
        {tyre[0]}
      </span>
      <span className="text-sm text-neutral-400">
        {age} {age === 1 ? "lap" : "laps"}
      </span>
    </span>
  );
}

function Status({ car }: { car: Car }) {
  if (car.state === "OUT") return <span className="rounded bg-red-600 px-1.5 py-0.5 text-[11px] font-bold">CRASHED</span>;
  if (car.in_pit) return <span className="rounded bg-amber-400 px-1.5 py-0.5 text-[11px] font-bold text-black">IN PIT</span>;
  if (car.state === "FINISHED") return <span className="rounded bg-white px-1.5 py-0.5 text-[11px] font-bold text-black">FINISHED</span>;
  return null;
}

export default function TimingTower({ cars }: { cars: Car[] }) {
  return (
    <section className="flex min-h-0 flex-col rounded-xl border border-white/10 bg-neutral-900/70">
      <h2 className="border-b border-white/10 px-4 py-2.5 text-sm font-bold tracking-wide text-neutral-300">TIMING TOWER</h2>
      <div className="grid grid-cols-[28px_1fr_92px_74px] gap-x-2 px-3 pt-2 text-[11px] font-semibold uppercase text-neutral-500">
        <span>Pos</span>
        <span>Driver</span>
        <span>Tyres</span>
        <span className="text-right">Gap</span>
      </div>
      <ol className="flex-1 overflow-y-auto px-2 pb-2">
        {cars.map((car) => (
          <li
            key={car.code}
            className={`mt-1.5 rounded-lg border px-2 py-2 transition-colors ${
              car.in_pit
                ? "border-amber-400 bg-amber-400/15"
                : car.plan_changed
                  ? "border-red-500/70 bg-red-500/10"
                  : "border-transparent bg-white/[0.03]"
            } ${car.state === "OUT" ? "opacity-50" : ""}`}
          >
            <div className="grid grid-cols-[28px_1fr_92px_74px] items-center gap-x-2">
              <span className="text-center text-base font-black">{car.position}</span>
              <span className="flex min-w-0 items-center gap-2">
                <span className="h-7 w-1.5 shrink-0 rounded" style={{ background: car.color }} />
                <span className="min-w-0">
                  <span className="block text-base font-bold leading-tight">{car.code}</span>
                  <span className="block truncate text-xs text-neutral-400">{car.name}</span>
                </span>
              </span>
              <TyreBadge tyre={car.tyre} age={car.tyre_age} />
              <span className="text-right font-mono text-sm">{car.gap}</span>
            </div>
            <div className="mt-1.5 flex items-center justify-between gap-2 pl-9 text-xs text-neutral-400">
              <span>
                {car.stops} {car.stops === 1 ? "stop" : "stops"}
                {car.plan && <> · next stop: <span className="text-neutral-200">{car.plan}</span></>}
              </span>
              <Status car={car} />
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
