"""Local LucidFlex vault-cycle economics inputs.

This module deliberately does not scrape or log into LucidFlex. The current
cycle state is a commercial input Georg can provide from the dashboard, and
the simulator turns that realized discount into the effective next eval fee.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path

from src.rules.lucidflex import LucidFlex50K


@dataclass(frozen=True)
class LucidFlexVaultCycle:
    """Current LucidFlex vault-cycle pricing state.

    ``accounts_used`` counts how many discounted accounts have already been
    bought in the active cycle. ``realized_discount`` is a fraction: 0.40 means
    40% off the base eval price.
    """

    accounts_used: int
    realized_discount: float | None
    cycle_id: str = ""

    @classmethod
    def from_mapping(cls, data: dict[str, object]) -> "LucidFlexVaultCycle":
        accounts_used = int(data.get("accounts_used", 0))
        raw_discount = data.get("realized_discount")
        realized_discount = None if raw_discount in (None, "") else float(raw_discount)
        cycle_id = str(data.get("cycle_id", ""))
        cycle = cls(
            accounts_used=accounts_used,
            realized_discount=realized_discount,
            cycle_id=cycle_id,
        )
        cycle.validate()
        return cycle

    def validate(self) -> None:
        if self.accounts_used < 0:
            raise ValueError("accounts_used must be non-negative")
        if self.realized_discount is not None and not 0 <= self.realized_discount < 1:
            raise ValueError("realized_discount must be in [0, 1)")

    def current_eval_fee(self, ruleset: LucidFlex50K | None = None) -> int:
        rules = ruleset or LucidFlex50K()
        return rules.eval_fee_for_vault_account(
            accounts_used_in_cycle=self.accounts_used,
            realized_discount=self.realized_discount,
        )

    def ruleset_for_next_account(self, ruleset: LucidFlex50K | None = None) -> LucidFlex50K:
        rules = ruleset or LucidFlex50K()
        return replace(rules, eval_fee=self.current_eval_fee(rules))


def load_lucidflex_vault_cycle(path: str | Path) -> LucidFlexVaultCycle:
    """Load a local JSON vault-cycle file.

    Expected shape:

    ``{"accounts_used": 0, "realized_discount": 0.40, "cycle_id": "optional"}``
    """
    with Path(path).expanduser().open() as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("vault cycle JSON must contain an object")
    return LucidFlexVaultCycle.from_mapping(data)
