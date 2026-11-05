from concurrent.futures import ThreadPoolExecutor

import pytest

from chaosusers.llm.budget import Budget, BudgetExceeded, Pricing


def test_commit_uses_exact_price():
    budget = Budget(max_usd=1.0, max_tokens=10_000, price_in=0.40, price_out=1.60)
    rid = budget.reserve(1000, 500)
    assert budget.commit(rid, 1000, 500) == 0.0012
    assert budget.spent_usd == 0.0012
    assert budget.spent_in == 1000
    assert budget.spent_out == 500
    assert budget.calls == 1


def test_reserve_rejects_before_spend():
    budget = Budget(max_usd=0.001, max_tokens=10_000, price_in=0.40, price_out=1.60)
    with pytest.raises(BudgetExceeded):
        budget.reserve(1000, 500)
    assert budget.spent_usd == 0.0
    assert budget.calls == 0


def test_outstanding_reservations_count():
    budget = Budget(max_usd=1.0, max_tokens=10_000_000, price_in=1.0, price_out=0.0)
    budget.reserve(600_000, 0)
    with pytest.raises(BudgetExceeded):
        budget.reserve(600_000, 0)
    assert budget.spent_usd == 0.0


def test_release_frees_reservation():
    budget = Budget(max_usd=1.0, max_tokens=10_000_000, price_in=1.0, price_out=0.0)
    rid = budget.reserve(600_000, 0)
    budget.release(rid)
    budget.reserve(600_000, 0)


def test_unpriced_enforces_tokens_only():
    budget = Budget(max_usd=0.0001, max_tokens=100, price_in=None, price_out=None)
    rid = budget.reserve(40, 10)
    assert budget.commit(rid, 40, 10) == 0.0
    with pytest.raises(BudgetExceeded):
        budget.reserve(90, 20)
    assert budget.spent_usd == 0.0
    assert budget.spent_tokens == 50


def test_concurrent_reserves_stay_inside_cap():
    cap = 0.012
    budget = Budget(max_usd=cap, max_tokens=10_000_000, price_in=0.40, price_out=1.60)

    def once(_n: int) -> None:
        try:
            rid = budget.reserve(1000, 500)
        except BudgetExceeded:
            return
        budget.commit(rid, 1000, 500)

    with ThreadPoolExecutor(max_workers=50) as pool:
        list(pool.map(once, range(50)))
    assert budget.spent_usd <= cap
    assert budget.calls == 10
    assert budget.spent_usd == 0.012


def test_pricing_table():
    pricing = Pricing.load()
    assert pricing.price("unknown") is None
    assert pricing.default_model("openai") == "gpt-4.1-mini"
    assert pricing.price("gpt-4.1-mini") == (0.40, 1.60)


def test_max_usd_must_be_positive():
    with pytest.raises(ValueError):
        Budget(max_usd=0, max_tokens=10, price_in=None, price_out=None)
