import pytest

from src.sizing.dynamic import AdaptiveSizing, BufferAwareSizing, FixedSizing, SizingContext


def ctx(phase="eval", balance=50_000.0, mll=48_000.0, payout_count=0, starting=50_000.0):
    return SizingContext(
        phase=phase,
        balance=balance,
        mll=mll,
        starting_balance=starting,
        payout_count=payout_count,
    )


class TestSizingContext:
    def test_buffer_is_distance_to_mll(self):
        c = ctx(balance=50_500.0, mll=48_000.0)
        assert c.buffer == pytest.approx(2_500.0)

    def test_buffer_floors_at_zero(self):
        c = ctx(balance=47_500.0, mll=48_000.0)
        assert c.buffer == 0.0

    def test_buffer_fraction_normalized_by_starting_balance(self):
        c = ctx(balance=50_500.0, mll=48_000.0, starting=50_000.0)
        assert c.buffer_fraction == pytest.approx(0.05)


class TestFixedSizing:
    def test_picks_eval_or_funded_size(self):
        s = FixedSizing(eval_size=200.0, funded_size=125.0)
        assert s(ctx(phase="eval")) == 200.0
        assert s(ctx(phase="funded")) == 125.0

    def test_constant_regardless_of_buffer(self):
        s = FixedSizing(eval_size=200.0, funded_size=125.0)
        assert s(ctx(phase="eval", balance=48_001.0)) == 200.0
        assert s(ctx(phase="eval", balance=53_000.0)) == 200.0

    def test_rejects_nonpositive_sizes(self):
        with pytest.raises(ValueError):
            FixedSizing(eval_size=0.0, funded_size=125.0)
        with pytest.raises(ValueError):
            FixedSizing(eval_size=200.0, funded_size=-1.0)


class TestBufferAwareSizing:
    def test_full_buffer_returns_base(self):
        s = BufferAwareSizing(eval_base=200.0, funded_base=125.0, full_buffer_fraction=0.04)
        # buffer fraction = 0.04 → ratio = 1 → scale = 1
        result = s(ctx(phase="eval", balance=52_000.0, mll=48_000.0))
        assert result == pytest.approx(200.0)

    def test_at_mll_returns_floor(self):
        s = BufferAwareSizing(eval_base=200.0, funded_base=125.0, min_scale=0.25)
        result = s(ctx(phase="eval", balance=48_000.0, mll=48_000.0))
        assert result == pytest.approx(50.0)  # 200 * 0.25

    def test_phase_differentiation(self):
        s = BufferAwareSizing(eval_base=200.0, funded_base=125.0, full_buffer_fraction=0.04)
        eval_size = s(ctx(phase="eval", balance=52_000.0, mll=48_000.0))
        funded_size = s(ctx(phase="funded", balance=52_000.0, mll=48_000.0))
        assert eval_size == pytest.approx(200.0)
        assert funded_size == pytest.approx(125.0)

    def test_monotonic_in_buffer(self):
        s = BufferAwareSizing(eval_base=200.0, funded_base=125.0, full_buffer_fraction=0.04, min_scale=0.25)
        sizes = [
            s(ctx(phase="eval", balance=b, mll=48_000.0))
            for b in (48_100.0, 48_500.0, 49_000.0, 50_000.0, 52_000.0)
        ]
        assert sizes == sorted(sizes)


class TestAdaptiveSizing:
    def test_post_payout_shrink_only_after_payout(self):
        s = AdaptiveSizing(
            eval_base=200.0,
            funded_base=125.0,
            buffer_full_frac=0.04,
            buffer_floor=0.25,
            post_payout_shrink=0.5,
        )
        before = s(ctx(phase="funded", balance=52_000.0, mll=48_000.0, payout_count=0))
        after = s(ctx(phase="funded", balance=52_000.0, mll=48_000.0, payout_count=1))
        assert before == pytest.approx(125.0)
        assert after == pytest.approx(62.5)

    def test_post_payout_shrink_does_not_apply_to_eval(self):
        s = AdaptiveSizing(
            eval_base=200.0,
            funded_base=125.0,
            post_payout_shrink=0.5,
        )
        result = s(ctx(phase="eval", balance=52_000.0, mll=48_000.0, payout_count=2))
        assert result == pytest.approx(200.0)

    def test_rejects_invalid_params(self):
        with pytest.raises(ValueError):
            AdaptiveSizing(eval_base=200, funded_base=125, buffer_full_frac=0)
        with pytest.raises(ValueError):
            AdaptiveSizing(eval_base=200, funded_base=125, buffer_floor=1.5)
        with pytest.raises(ValueError):
            AdaptiveSizing(eval_base=200, funded_base=125, post_payout_shrink=0)
