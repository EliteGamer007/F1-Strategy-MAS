"""The terminal: prints every radio message and plan change as it happens, and sends typed commands to the race."""
import asyncio
import queue
import sys
import threading
from contextlib import nullcontext

from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout
from rich.console import Console
from rich.markup import escape

from server.engine import HELP
from sim.messages import DecisionChange

LABELS = {"INFO": ("REPORT", "cyan"), "REQUEST": ("QUESTION", "magenta"), "INSTRUCTION": ("INSTRUCTION", "blue"),
          "REPLY": ("REPLY", "green"), "EVENT": ("NEWS", "yellow")}


def show(out, item):
    if isinstance(item, DecisionChange):
        out.print(f"[dim]lap {item.lap:>2}[/]  [bold red]PLAN CHANGED[/] {escape(item.team)} / {escape(item.driver)}: "
                  f"{escape(item.before)} [bold]->[/] {escape(item.after)}\n          why: {escape(item.because)}")
    else:
        label, colour = LABELS[item.kind]
        out.print(f"[dim]lap {item.lap:>2}[/]  [{colour}]{label:<12}[/][bold]{escape(item.sender)}[/] -> {escape(item.to)}: {escape(item.text)}")


def run(engine):
    # A real console keeps the '>' prompt below the scrolling messages. Terminals such as Git Bash on
    # Windows are not real consoles for prompt_toolkit, so they get a plain input() prompt instead.
    interactive = sys.stdin.isatty() and sys.stdout.isatty()
    with patch_stdout(raw=True) if interactive else nullcontext():
        out = Console(force_terminal=interactive, highlight=False)
        prompt = PromptSession().prompt if interactive else input
        stop = threading.Event()

        def printer():
            while not stop.is_set():
                try:
                    show(out, engine.console.get(timeout=0.2))
                except queue.Empty:
                    pass

        threading.Thread(target=printer, daemon=True).start()
        out.print("[bold]F1 Strategy Agents[/]  - open http://localhost:3000 to watch the race.\n" + escape(HELP))
        while True:
            try:
                text = prompt("> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if text.lower() in ("quit", "exit"):
                break
            if text:
                out.print(escape(asyncio.run_coroutine_threadsafe(engine.run_command(text), engine.loop).result()))
        stop.set()
