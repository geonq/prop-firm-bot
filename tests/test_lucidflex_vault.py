import json
from dataclasses import replace

import pytest

from src.data.lucidflex_vault import LucidFlexVaultCycle, load_lucidflex_vault_cycle
from src.rules.lucidflex import LucidFlex50K


def test_lucidflex_eval_fee_from_discount() -> None:
    rules = LucidFlex50K()

    assert rules.eval_fee_from_discount(0.30) == 98
    assert rules.eval_fee_from_discount(0.40) == 84
    assert rules.eval_fee_from_discount(0.50) == 70


def test_lucidflex_vault_discount_applies_only_to_first_five_accounts() -> None:
    rules = LucidFlex50K()

    assert rules.eval_fee_for_vault_account(accounts_used_in_cycle=0, realized_discount=0.50) == 70
    assert rules.eval_fee_for_vault_account(accounts_used_in_cycle=4, realized_discount=0.40) == 84
    assert rules.eval_fee_for_vault_account(accounts_used_in_cycle=5, realized_discount=0.50) == 98


def test_lucidflex_vault_cycle_can_create_priced_ruleset() -> None:
    cycle = LucidFlexVaultCycle(accounts_used=2, realized_discount=0.40, cycle_id="vault-1")
    rules = cycle.ruleset_for_next_account()

    assert rules.eval_fee == 84
    assert rules.reset_cost_estimate == 95


def test_lucidflex_vault_cycle_falls_back_to_standard_coupon_fee() -> None:
    cycle = LucidFlexVaultCycle(accounts_used=0, realized_discount=None)

    assert cycle.current_eval_fee() == 98


def test_lucidflex_vault_cycle_loader(tmp_path) -> None:
    path = tmp_path / "vault.json"
    path.write_text(json.dumps({"accounts_used": 1, "realized_discount": 0.5, "cycle_id": "v2"}))

    cycle = load_lucidflex_vault_cycle(path)

    assert cycle.accounts_used == 1
    assert cycle.realized_discount == 0.5
    assert cycle.cycle_id == "v2"
    assert cycle.current_eval_fee() == 70


def test_lucidflex_vault_rejects_invalid_discount() -> None:
    with pytest.raises(ValueError, match="realized_discount"):
        LucidFlexVaultCycle(accounts_used=0, realized_discount=1.0).validate()


def test_lucidflex_vault_respects_custom_base_price() -> None:
    rules = replace(LucidFlex50K(), base_eval_fee=150, eval_fee=105)
    cycle = LucidFlexVaultCycle(accounts_used=0, realized_discount=0.40)

    assert cycle.current_eval_fee(rules) == 90
