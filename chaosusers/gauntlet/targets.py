from typing import Protocol

from pydantic import BaseModel


class TargetReply(BaseModel):
    text: str
    latency_ms: int = 0
    raw: dict | None = None


class Target(Protocol):
    name: str
    has_state: bool

    def start(self, session_id: str) -> None: ...

    def send(self, session_id: str, message: str, history: list) -> TargetReply: ...

    def state(self, session_id: str) -> dict | None: ...


class PythonTarget:
    def __init__(self, name: str, bot, has_state: bool = True):
        self.name = name
        self.bot = bot
        self.has_state = has_state

    def start(self, session_id: str) -> None:
        return None

    def send(self, session_id: str, message: str, history: list) -> TargetReply:
        result = self.bot.handle(session_id, message)
        return TargetReply(text=result["reply"], latency_ms=0, raw=result)

    def state(self, session_id: str) -> dict | None:
        return self.bot.state(session_id)
