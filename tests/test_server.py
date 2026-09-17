from fastapi.testclient import TestClient

from server.api import app, engine
from server.engine import Engine


def test_page_receives_the_track_then_live_race_updates():
    engine.restart(42)
    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "reset"
        assert len(hello["state"]["cars"]) == 8
        assert len(hello["track"]["pit_lane"]) > 10

        assert client.post("/api/command", json={"command": "start"}).json()["output"].startswith("Lights out")
        texts = []
        for _ in range(50):
            update = ws.receive_json()
            texts += [item["text"] for item in update["feed"] if item["type"] == "message"]
            if any(text.startswith("Race plan") for text in texts):
                break
        assert "Lights out! The race has started." in texts
        assert update["state"]["running"] is True


def test_commands_explain_mistakes_instead_of_failing():
    e = Engine(42)
    assert "Unknown command" in e.command("fly")
    assert "Usage" in e.command("speed 3")
    assert e.command("speed x4") == "Race speed is now x4."
    assert e.command("speed 0.5") == "Race speed is now x0.5." and e.speed == 0.5
    assert "not running" in e.command("crash NOR")
    assert "not running" in e.command("rain start")
    assert "Usage" in e.command("rain maybe")
    assert "No driver called" in e.command("plan XYZ")
    assert "Name one driver" in e.command("why")
    assert "has not changed yet" in e.command("why PIA")

    assert e.command("start").startswith("Lights out")
    assert e.command("start") == "The race has already started."
    assert e.command("rain start").startswith("Rain started")
    assert e.command("rain stop").startswith("Rain stopped")
    assert "Safety car deployed" in e.command("crash norris")
    assert "not racing" in e.command("plan NOR")
    assert "A* checked" in e.command("plan pia")
    assert "Piastri" in e.command("status")
    assert e.command("restart 7").startswith("New race on the grid (seed 7)")
    assert not e.race.started and e.speed == 1
