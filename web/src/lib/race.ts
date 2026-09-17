"use client";

import { useEffect, useState } from "react";

// The Python race server started by `python run.py`.
export const API = "http://localhost:8000";

export type Car = {
  position: number;
  code: string;
  name: string;
  team: string;
  color: string;
  x: number;
  y: number;
  state: "RUNNING" | "PIT" | "OUT" | "FINISHED";
  in_pit: boolean;
  tyre: "SOFT" | "MEDIUM" | "HARD" | "WET";
  tyre_age: number;
  stops: number;
  gap: string;
  last_lap: number | null;
  plan: string | null;
  plan_changed: boolean;
};

export type RaceState = {
  lap: number;
  total_laps: number;
  flag: "GREEN" | "YELLOW" | "SAFETY_CAR" | "CHEQUERED";
  started: boolean;
  running: boolean;
  over: boolean;
  speed: number;
  seed: number;
  rain: { level: number; label: "dry" | "light" | "medium" | "heavy"; trend: string };
  cars: Car[];
  crashes: { code: string; x: number; y: number }[];
  safety_car: [number, number] | null;
};

export type Track = {
  x: number[];
  y: number[];
  corners: { number: number; x: number; y: number }[];
  pit_lane: [number, number][];
  pit_box: [number, number];
};

export type Message = {
  type: "message";
  id: number;
  lap: number;
  sender: string;
  to: string;
  kind: "INFO" | "REQUEST" | "INSTRUCTION" | "REPLY" | "EVENT";
  text: string;
  team: string | null;
};

export type Decision = {
  type: "decision";
  id: number;
  lap: number;
  team: string;
  driver: string;
  before: string;
  after: string;
  because: string;
  detail: string;
};

export type FeedItem = Message | Decision;

export function useRace() {
  const [track, setTrack] = useState<Track | null>(null);
  const [state, setState] = useState<RaceState | null>(null);
  const [feed, setFeed] = useState<FeedItem[]>([]);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    let socket: WebSocket;
    let retry: ReturnType<typeof setTimeout>;
    let closed = false;

    const connect = () => {
      socket = new WebSocket(API.replace("http", "ws") + "/ws");
      socket.onopen = () => setConnected(true);
      socket.onmessage = (event) => {
        const update = JSON.parse(event.data);
        if (update.type === "reset") {
          setTrack(update.track);
          setFeed(update.feed);
        } else if (update.feed.length) {
          setFeed((items) => [...items, ...update.feed]);
        }
        setState(update.state);
      };
      socket.onclose = () => {
        setConnected(false);
        if (!closed) retry = setTimeout(connect, 1000); // the server may not be started yet
      };
    };

    connect();
    return () => {
      closed = true;
      clearTimeout(retry);
      socket.close();
    };
  }, []);

  return { track, state, feed, connected };
}

export function sendCommand(command: string) {
  return fetch(`${API}/api/command`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ command }),
  });
}

export const TYRE_COLORS = { SOFT: "#E8002D", MEDIUM: "#FFF200", HARD: "#EDEDED", WET: "#0067FF" };
