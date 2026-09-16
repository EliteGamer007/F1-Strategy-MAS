"""HTTP and WebSocket server used by the race page (web/)."""
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from server.engine import Engine

engine = Engine()


@asynccontextmanager
async def lifespan(app):
    engine.loop = asyncio.get_running_loop()
    task = asyncio.create_task(engine.run())
    yield
    task.cancel()


app = FastAPI(title="F1 Strategy Agents", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000"], allow_methods=["*"], allow_headers=["*"])


class Command(BaseModel):
    command: str


@app.post("/api/command")
async def command(body: Command):
    # async so it runs on the same thread as the race loop
    return {"output": engine.command(body.command)}


@app.websocket("/ws")
async def updates(ws: WebSocket):
    await ws.accept()
    client = asyncio.Queue()
    engine.clients.add(client)
    try:
        await ws.send_json(engine.hello())
        while True:
            await ws.send_json(await client.get())
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        engine.clients.discard(client)
