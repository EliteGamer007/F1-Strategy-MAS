"""Team radio, public announcements, and the record of every changed decision."""
from dataclasses import asdict, dataclass, field

EVERYONE = "everyone"


@dataclass
class Message:
    id: int
    lap: int
    sender: str
    to: str
    kind: str          # INFO, REQUEST, INSTRUCTION, REPLY or EVENT
    text: str
    team: str | None
    data: dict = field(default_factory=dict)


@dataclass
class DecisionChange:
    id: int
    lap: int
    team: str
    driver: str
    before: str
    after: str
    because: str
    cause: str         # driver, rival, incident or laps
    detail: str = ""


class MessageBoard:
    """Team radio is delivered only inside the team; messages to EVERYONE reach every agent."""

    def __init__(self):
        self.feed = []       # messages and decision changes, in order (what the screen shows)
        self._inbox = {}
        self._team = {}

    def join(self, name, team):
        self._inbox[name] = []
        self._team[name] = team

    def post(self, lap, sender, to, kind, text, team=None, **data):
        if to != EVERYONE and self._team.get(sender) not in (None, self._team[to]):
            raise ValueError(f"{sender} cannot radio {to}: team radio stays inside the team")
        msg = Message(len(self.feed) + 1, lap, sender, to, kind, text, team, data)
        self.feed.append(msg)
        for name in (self._inbox if to == EVERYONE else [to]):
            if name != sender:
                self._inbox[name].append(msg)
        return msg

    def take(self, name):
        messages, self._inbox[name] = self._inbox[name], []
        return messages

    def record(self, lap, team, driver, before, after, because, cause, detail=""):
        change = DecisionChange(len(self.feed) + 1, lap, team, driver, before, after, because, cause, detail)
        self.feed.append(change)
        return change


def to_json(item):
    return {"type": "decision" if isinstance(item, DecisionChange) else "message", **asdict(item)}
