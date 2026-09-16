"use client";

import { useEffect, useRef } from "react";
import { Decision, FeedItem, Message } from "@/lib/race";

const KIND_LABEL: Record<Message["kind"], string> = {
  INFO: "Report",
  REQUEST: "Question",
  INSTRUCTION: "Instruction",
  REPLY: "Reply",
  EVENT: "News",
};

const KIND_STYLE: Record<Message["kind"], string> = {
  INFO: "bg-sky-500/20 text-sky-300",
  REQUEST: "bg-fuchsia-500/20 text-fuchsia-300",
  INSTRUCTION: "bg-blue-500/20 text-blue-300",
  REPLY: "bg-emerald-500/20 text-emerald-300",
  EVENT: "bg-yellow-500/20 text-yellow-300",
};

function MessageRow({ msg, teamColors }: { msg: Message; teamColors: Record<string, string> }) {
  const color = msg.team ? teamColors[msg.team] : "#facc15";
  return (
    <li className="rounded-lg border-l-4 bg-white/[0.04] px-3 py-2" style={{ borderColor: color }}>
      <div className="flex flex-wrap items-center gap-2 text-xs text-neutral-400">
        <span className="font-mono">Lap {msg.lap}</span>
        <span className={`rounded px-1.5 py-0.5 font-bold ${KIND_STYLE[msg.kind]}`}>{KIND_LABEL[msg.kind]}</span>
        <span>
          <span className="font-semibold text-neutral-200">{msg.sender}</span> → {msg.to}
        </span>
      </div>
      <p className="mt-1 text-[15px] leading-snug">{msg.text}</p>
    </li>
  );
}

function DecisionRow({ change, color }: { change: Decision; color: string }) {
  return (
    <li className="rounded-lg border-2 border-red-500 bg-red-950/60 px-3 py-2.5">
      <div className="flex items-center gap-2 text-xs">
        <span className="font-mono text-neutral-400">Lap {change.lap}</span>
        <span className="rounded bg-red-600 px-1.5 py-0.5 font-bold">PLAN CHANGED</span>
        <span className="font-semibold" style={{ color }}>
          {change.team} · {change.driver}
        </span>
      </div>
      <dl className="mt-1.5 grid grid-cols-[62px_1fr] gap-x-2 gap-y-1 text-[15px] leading-snug">
        <dt className="text-neutral-400">Before</dt>
        <dd className="text-neutral-300 line-through decoration-red-400/60">{change.before}</dd>
        <dt className="text-neutral-400">After</dt>
        <dd className="font-bold">{change.after}</dd>
        <dt className="text-neutral-400">Why</dt>
        <dd className="text-amber-200">{change.because}</dd>
      </dl>
      <p className="mt-1.5 text-xs text-neutral-400">{change.detail}</p>
    </li>
  );
}

export default function RadioFeed({ feed, teamColors }: { feed: FeedItem[]; teamColors: Record<string, string> }) {
  const list = useRef<HTMLOListElement>(null);
  const followNewest = useRef(true);

  // Keep showing the newest message unless the viewer has scrolled up to read older ones.
  useEffect(() => {
    if (followNewest.current && list.current) list.current.scrollTop = list.current.scrollHeight;
  }, [feed]);

  return (
    <section className="flex min-h-0 flex-col rounded-xl border border-white/10 bg-neutral-900/70">
      <h2 className="border-b border-white/10 px-4 py-2.5 text-sm font-bold tracking-wide text-neutral-300">
        TEAM RADIO &amp; DECISIONS
      </h2>
      <ol
        ref={list}
        onScroll={(e) => {
          const el = e.currentTarget;
          followNewest.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
        }}
        className="flex flex-1 flex-col gap-2 overflow-y-auto p-3"
      >
        {feed.length === 0 && <li className="text-neutral-500">Messages between the agents will appear here.</li>}
        {feed.map((item) =>
          item.type === "decision" ? (
            <DecisionRow key={item.id} change={item} color={teamColors[item.team]} />
          ) : (
            <MessageRow key={item.id} msg={item} teamColors={teamColors} />
          ),
        )}
      </ol>
    </section>
  );
}
