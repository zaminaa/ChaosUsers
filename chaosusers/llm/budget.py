import threading
from decimal import Decimal
from pathlib import Path

import yaml


def estimate_tokens(text: str) -> int:
    return len(text.encode("utf-8")) // 3 + 1


class BudgetExceeded(Exception):
    pass


class Pricing:
    def __init__(self, models: dict[str, tuple[float, float]], defaults: dict[str, str]):
        self._models = models
        self._defaults = defaults

    @classmethod
    def load(cls, path: Path | None = None) -> "Pricing":
        if path is None:
            path = Path(__file__).resolve().parents[1] / "pricing.yaml"
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        models = {name: (float(row["in"]), float(row["out"])) for name, row in data["models"].items()}
        return cls(models, dict(data["defaults"]))

    def price(self, model: str) -> tuple[float, float] | None:
        return self._models.get(model)

    def default_model(self, provider: str) -> str:
        return self._defaults[provider]


class Budget:
    def __init__(self, max_usd: float, max_tokens: int, price_in: float | None, price_out: float | None):
        if max_usd <= 0:
            raise ValueError("max_usd must be > 0")
        self.max_usd = max_usd
        self.max_tokens = max_tokens
        self.price_in = price_in
        self.price_out = price_out
        self.spent_usd = 0.0
        self.spent_tokens = 0
        self.spent_in = 0
        self.spent_out = 0
        self.calls = 0
        self._lock = threading.Lock()
        self._next = 1
        self._held: dict[int, tuple[int, Decimal]] = {}

    def reserve(self, est_in: int, max_out: int) -> int:
        tokens = est_in + max_out
        usd = self._usd(est_in, max_out)
        with self._lock:
            held_tokens = sum(item[0] for item in self._held.values())
            held_usd = sum((item[1] for item in self._held.values()), Decimal(0))
            if self.spent_tokens + held_tokens + tokens > self.max_tokens:
                raise BudgetExceeded("token cap")
            if self._priced() and self._spent_decimal() + held_usd + usd > Decimal(str(self.max_usd)):
                raise BudgetExceeded("usd cap")
            rid = self._next
            self._next += 1
            self._held[rid] = (tokens, usd)
            return rid

    def commit(self, rid: int, tokens_in: int, tokens_out: int) -> float:
        actual = self._usd(tokens_in, tokens_out)
        with self._lock:
            self._held.pop(rid)
            self.spent_usd = float(self._spent_decimal() + actual)
            self.spent_in += tokens_in
            self.spent_out += tokens_out
            self.spent_tokens += tokens_in + tokens_out
            self.calls += 1
            return float(actual)

    def release(self, rid: int) -> None:
        with self._lock:
            self._held.pop(rid)

    def worst_case_usd(self, calls: int, est_in_per_call: int, max_out: int) -> float | None:
        if not self._priced():
            return None
        return float(self._usd(est_in_per_call, max_out) * calls)

    def _priced(self) -> bool:
        return self.price_in is not None and self.price_out is not None

    def _spent_decimal(self) -> Decimal:
        return Decimal(str(self.spent_usd))

    def _usd(self, tokens_in: int, tokens_out: int) -> Decimal:
        if not self._priced():
            return Decimal(0)
        return (
            Decimal(tokens_in) * Decimal(str(self.price_in)) + Decimal(tokens_out) * Decimal(str(self.price_out))
        ) / Decimal(1_000_000)
