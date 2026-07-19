"""Tests for the trade journal's additive net_pnl_usd/net_r columns.

Reviewer commission adjudication (2026-07-18): PaperBroker's gross fills
stay exactly as-is (parity depends on it -- see src/live/broker.py and
tests/test_live_parity.py). The journal ADDS net_pnl_usd/net_r columns
computed with MNQ_COMMISSION_USD_PER_SIDE (a config placeholder, NOT the
backtest's NQ-scaled commission constant), without altering the gross
pnl_usd/r_multiple columns already there.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from src.live.broker import FilledTrade
from src.live.config import MNQ, MNQ_COMMISSION_USD_PER_SIDE
from src.live.runner import TRADE_CSV_FIELDS, TradeJournal, _net_economics


def _make_trade(*, pnl_usd_gross_points: float, contracts: int, risk_points: float, direction: str = "long") -> FilledTrade:
    entry_price = 100.0
    exit_price = entry_price + pnl_usd_gross_points if direction == "long" else entry_price - pnl_usd_gross_points
    return FilledTrade(
        session_date=date(2025, 7, 2),
        direction=direction,
        entry_ts="2025-07-02 09:35:00-04:00",
        entry_price=entry_price,
        exit_ts="2025-07-02 10:00:00-04:00",
        exit_price=exit_price,
        exit_reason="target",
        contracts=contracts,
        risk_points=risk_points,
        point_value=MNQ.point_value,
    )


def test_net_economics_subtracts_commission_both_sides():
    trade = _make_trade(pnl_usd_gross_points=10.0, contracts=5, risk_points=5.0)
    # gross pnl_usd = 10.0 points * 2.0 (point_value) * 5 (contracts) = 100.0
    assert trade.pnl_usd == pytest.approx(100.0)

    net_pnl_usd, net_r = _net_economics(trade)
    expected_commission = 2 * MNQ_COMMISSION_USD_PER_SIDE * 5  # 2 sides, 5 contracts
    assert net_pnl_usd == pytest.approx(100.0 - expected_commission)
    risk_usd = 5.0 * MNQ.point_value * 5  # 50.0
    assert net_r == pytest.approx((100.0 - expected_commission) / risk_usd)


def test_net_economics_never_mutates_gross_fields():
    """The gross pnl_usd/r_multiple on FilledTrade itself must be untouched --
    net economics are computed on the side, never written back.
    """
    trade = _make_trade(pnl_usd_gross_points=-10.0, contracts=3, risk_points=10.0)
    gross_pnl_before = trade.pnl_usd
    gross_r_before = trade.r_multiple
    _net_economics(trade)
    assert trade.pnl_usd == gross_pnl_before
    assert trade.r_multiple == gross_r_before


def test_net_economics_scales_with_contract_count():
    """Commission is charged on the ACTUAL contract count, not per-trade flat --
    a 20-contract trade pays 4x the commission of a 5-contract trade with the
    same per-point P&L.
    """
    small = _make_trade(pnl_usd_gross_points=5.0, contracts=5, risk_points=5.0)
    large = _make_trade(pnl_usd_gross_points=5.0, contracts=20, risk_points=5.0)

    net_small, _ = _net_economics(small)
    net_large, _ = _net_economics(large)

    commission_small = small.pnl_usd - net_small
    commission_large = large.pnl_usd - net_large
    assert commission_large == pytest.approx(commission_small * 4)


def test_journal_writes_both_gross_and_net_columns(tmp_path):
    journal = TradeJournal(tmp_path)
    trade = _make_trade(pnl_usd_gross_points=10.0, contracts=5, risk_points=5.0)
    journal.record_trade(trade)

    df = pd.read_csv(journal.csv_path)
    assert list(df.columns) == TRADE_CSV_FIELDS
    assert "net_pnl_usd" in df.columns
    assert "net_r" in df.columns
    row = df.iloc[0]
    # gross columns unchanged from the FilledTrade's own values
    assert row["pnl_usd"] == pytest.approx(trade.pnl_usd)
    assert row["r_multiple"] == pytest.approx(trade.r_multiple)
    # net columns present and strictly less favorable than gross for a winner
    assert row["net_pnl_usd"] < row["pnl_usd"]
    assert row["net_r"] < row["r_multiple"]


def test_zero_risk_net_r_is_nan_not_a_crash():
    """Defensive: a trade with risk_points/contracts such that risk_usd would
    be zero must not raise a ZeroDivisionError -- net_r degrades to NaN.
    """
    trade = _make_trade(pnl_usd_gross_points=0.0, contracts=0, risk_points=5.0)
    net_pnl_usd, net_r = _net_economics(trade)
    assert net_pnl_usd == pytest.approx(-2 * MNQ_COMMISSION_USD_PER_SIDE * 0)
    import math

    assert math.isnan(net_r)
