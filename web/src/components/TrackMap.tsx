"use client";

import { useEffect, useRef } from "react";
import { Car, RaceState, Track } from "@/lib/race";

type Point = { x: number; y: number };
type Motion = { from: Point; to: Point; at: number };

const UPDATE_MS = 100; // the server sends new positions 10 times a second
const PAD = 40;

function glide(m: Motion, now: number): Point {
  const t = Math.min(1, (now - m.at) / UPDATE_MS);
  return { x: m.from.x + (m.to.x - m.from.x) * t, y: m.from.y + (m.to.y - m.from.y) * t };
}

function bounds(track: Track) {
  const xs = [...track.x, ...track.pit_lane.map((p) => p[0])];
  const ys = [...track.y, ...track.pit_lane.map((p) => p[1])];
  return { minX: Math.min(...xs), maxX: Math.max(...xs), minY: Math.min(...ys), maxY: Math.max(...ys) };
}

function draw(canvas: HTMLCanvasElement, track: Track, box: ReturnType<typeof bounds>, state: RaceState, motion: Record<string, Motion>) {
  const dpr = window.devicePixelRatio || 1;
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  if (canvas.width !== Math.round(width * dpr) || canvas.height !== Math.round(height * dpr)) {
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
  }
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.fillStyle = "#000";
  ctx.fillRect(0, 0, width, height);

  // Fit the circuit into the panel, keeping its shape (map y points up, canvas y points down).
  const scale = Math.min((width - 2 * PAD) / (box.maxX - box.minX), (height - 2 * PAD) / (box.maxY - box.minY));
  const ox = (width - (box.maxX - box.minX) * scale) / 2;
  const oy = (height - (box.maxY - box.minY) * scale) / 2;
  const map = (x: number, y: number): Point => ({ x: ox + (x - box.minX) * scale, y: oy + (box.maxY - y) * scale });

  const stroke = (points: Point[], closed: boolean, color: string, lineWidth: number, dash: number[] = []) => {
    ctx.beginPath();
    points.forEach((p, i) => (i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y)));
    if (closed) ctx.closePath();
    ctx.setLineDash(dash);
    ctx.strokeStyle = color;
    ctx.lineWidth = lineWidth;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.stroke();
    ctx.setLineDash([]);
  };

  const circuit = track.x.map((x, i) => map(x, track.y[i]));
  const pitLane = track.pit_lane.map(([x, y]) => map(x, y));

  // Pit lane (drawn first so the track sits on top where they join)
  stroke(pitLane, false, "rgba(245,158,11,0.35)", 14);
  stroke(pitLane, false, "#3a2a0a", 7);
  const middle = pitLane[Math.floor(pitLane.length / 2)];
  ctx.fillStyle = "#f59e0b";
  ctx.font = "bold 12px system-ui, sans-serif";
  ctx.textAlign = "center";
  ctx.fillText("PIT LANE", middle.x, middle.y + 24);
  const garage = map(...track.pit_box);
  ctx.fillRect(garage.x - 5, garage.y - 5, 10, 10);

  // Track surface, in the style of the F1-Telemetry-Analysis track map
  if (state.flag === "SAFETY_CAR") stroke(circuit, true, "rgba(250,204,21,0.25)", 34);
  stroke(circuit, true, "#1c1c1c", 22);
  stroke(circuit, true, "#2e2e2e", 16);
  stroke(circuit, true, "#3c3c3c", 10);
  stroke(circuit, true, "rgba(255,255,255,0.18)", 1, [8, 10]);

  ctx.fillStyle = "rgba(255,255,255,0.45)";
  ctx.font = "bold 11px system-ui, sans-serif";
  for (const corner of track.corners) {
    const p = map(corner.x, corner.y);
    ctx.fillText(String(corner.number), p.x, p.y + 4);
  }

  // Finish line
  const [a, b] = [circuit[0], circuit[2]];
  const length = Math.hypot(b.x - a.x, b.y - a.y) || 1;
  const [nx, ny] = [(-(b.y - a.y) / length) * 12, ((b.x - a.x) / length) * 12];
  stroke([{ x: a.x + nx, y: a.y + ny }, { x: a.x - nx, y: a.y - ny }], false, "#fff", 3);

  // Crashed cars
  for (const crash of state.crashes) {
    const p = map(crash.x, crash.y);
    stroke([{ x: p.x - 8, y: p.y - 8 }, { x: p.x + 8, y: p.y + 8 }], false, "#ef4444", 4);
    stroke([{ x: p.x + 8, y: p.y - 8 }, { x: p.x - 8, y: p.y + 8 }], false, "#ef4444", 4);
    ctx.fillStyle = "#fca5a5";
    ctx.fillText(crash.code, p.x, p.y + 22);
  }

  // Safety car
  if (state.safety_car) {
    const p = map(...state.safety_car);
    ctx.fillStyle = "#facc15";
    ctx.fillRect(p.x - 16, p.y - 9, 32, 18);
    ctx.fillStyle = "#000";
    ctx.font = "bold 11px system-ui, sans-serif";
    ctx.fillText("SC", p.x, p.y + 4);
  }

  // Cars, leader drawn last so it stays on top
  const now = performance.now();
  const cars = state.cars.filter((car: Car) => car.state !== "OUT").reverse();
  for (const car of cars) {
    const m = motion[car.code];
    const at = m ? glide(m, now) : { x: car.x, y: car.y };
    const p = map(at.x, at.y);
    if (car.in_pit) {
      ctx.beginPath();
      ctx.arc(p.x, p.y, 15, 0, Math.PI * 2);
      ctx.strokeStyle = "#f59e0b";
      ctx.lineWidth = 3;
      ctx.stroke();
    }
    if (car.plan_changed) {
      ctx.beginPath();
      ctx.arc(p.x, p.y, 20 + 3 * Math.sin(now / 150), 0, Math.PI * 2);
      ctx.strokeStyle = "rgba(239,68,68,0.9)";
      ctx.lineWidth = 2.5;
      ctx.stroke();
    }
    ctx.globalAlpha = car.state === "FINISHED" ? 0.5 : 1;
    ctx.shadowColor = car.color;
    ctx.shadowBlur = 12;
    ctx.beginPath();
    ctx.arc(p.x, p.y, 8, 0, Math.PI * 2);
    ctx.fillStyle = car.color;
    ctx.fill();
    ctx.shadowBlur = 0;
    ctx.lineWidth = 1.5;
    ctx.strokeStyle = "rgba(0,0,0,0.7)";
    ctx.stroke();
    ctx.font = "bold 13px system-ui, sans-serif";
    ctx.lineWidth = 3;
    ctx.strokeText(car.code, p.x, p.y - 13);
    ctx.fillStyle = "#fff";
    ctx.fillText(car.code, p.x, p.y - 13);
    ctx.globalAlpha = 1;
  }
}

function Legend() {
  const item = "flex items-center gap-2";
  return (
    <div className="absolute bottom-3 left-3 flex flex-col gap-1 rounded-lg bg-black/70 px-3 py-2 text-xs text-neutral-300">
      <span className={item}>
        <span className="h-3.5 w-3.5 rounded-full border-[3px] border-amber-400" /> In the pit lane, changing tyres
      </span>
      <span className={item}>
        <span className="h-3.5 w-3.5 rounded-full border-2 border-red-500" /> Strategist just changed this car&apos;s plan
      </span>
      <span className={item}>
        <span className="w-3.5 text-center font-black text-red-500">✕</span> Crashed car
      </span>
      <span className={item}>
        <span className="rounded-sm bg-yellow-400 px-1 text-[10px] font-bold text-black">SC</span> Safety car
      </span>
    </div>
  );
}

const BANNERS: Partial<Record<RaceState["flag"], [string, string]>> = {
  YELLOW: ["YELLOW FLAG", "A car has crashed: drivers slow down near it"],
  SAFETY_CAR: ["SAFETY CAR", "Everyone slows down and follows in a line. No overtaking."],
  CHEQUERED: ["FINISH FLAG", "The race is ending"],
};

export default function TrackMap({ track, state }: { track: Track; state: RaceState }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const latest = useRef(state);
  const motion = useRef<Record<string, Motion>>({});

  // Remember where each car was drawn so it glides to its new position instead of jumping.
  useEffect(() => {
    const now = performance.now();
    for (const car of state.cars) {
      const m = motion.current[car.code];
      motion.current[car.code] = { from: m ? glide(m, now) : { x: car.x, y: car.y }, to: { x: car.x, y: car.y }, at: now };
    }
    latest.current = state;
  }, [state]);

  useEffect(() => {
    const box = bounds(track);
    let frame = requestAnimationFrame(function loop() {
      if (canvas.current) draw(canvas.current, track, box, latest.current, motion.current);
      frame = requestAnimationFrame(loop);
    });
    return () => cancelAnimationFrame(frame);
  }, [track]);

  const banner = state.over ? ["RACE OVER", "The final order is in the timing tower"] : BANNERS[state.flag];
  return (
    <section className="relative min-h-0 overflow-hidden rounded-xl border border-white/10 bg-black">
      <canvas ref={canvas} className="absolute inset-0 h-full w-full" />
      {banner && (
        <div className="absolute left-1/2 top-3 -translate-x-1/2 rounded-full border border-yellow-400/60 bg-yellow-400/15 px-5 py-2 text-center text-yellow-200 backdrop-blur">
          <span className="font-black tracking-widest">{banner[0]}</span>
          <span className="ml-3 text-sm">{banner[1]}</span>
        </div>
      )}
      <Legend />
    </section>
  );
}
