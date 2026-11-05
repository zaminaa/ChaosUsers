from pydantic import BaseModel

from chaosusers.packs.schema import EventName, Mood, PatienceSpec


class PatienceState(BaseModel):
    spec: PatienceSpec
    value: float
    mood: Mood = "calm"
    abandoned: bool = False

    def apply(self, events: list[EventName]) -> None:
        self.value -= sum(self.spec.costs.get(event, 0) for event in events)
        self.value += sum(self.spec.recovery.get(event, 0) for event in events)
        self.value = min(self.value, self.spec.start)
        if self.value < self.spec.angry_below:
            self.mood = "angry"
        elif self.value < self.spec.frustrated_below:
            self.mood = "frustrated"
        else:
            self.mood = "calm"
        self.abandoned = self.value <= self.spec.abandon_at
