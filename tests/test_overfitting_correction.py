"""Unit tests for src/optimizer/overfitting_stats.py (DSR/PSR math) and an
end-to-end smoke test of Analysis/scripts/orb_overfitting_correction.py
against the real saved walk-forward CSV/JSON outputs.

Toy cases are checked against hand-derivable reductions of the published
Bailey & Lopez de Prado (2014) formulas rather than against scipy's own
implementations of unrelated statistics (scipy has no built-in PSR/DSR to
compare against) -- see each test's docstring for the specific reduction
used and why it is a valid sanity check.
"""

from __future__ import annotations

import math
import subprocess
import sys
from pathlib import Path

import pytest
from scipy import stats

from src.optimizer.overfitting_stats import (
    DeflatedSharpeResult,
    ReturnSeriesStats,
    bonferroni_check,
    deflated_sharpe_ratio,
    expected_max_sharpe_under_null,
    one_sample_bootstrap_p_value,
    probabilistic_sharpe_ratio,
    summarize_return_series,
)

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "Analysis" / "scripts" / "orb_overfitting_correction.py"
PARQUET = ROOT / "DataLocal" / "nq_ohlcv_1m_2020-01-01_2026-07-16.parquet"
ROUND1_CSV = ROOT / "Analysis" / "output" / "orb" / "walk_forward_results.csv"
ROUND2_JSON = ROOT / "Analysis" / "output" / "orb" / "round2_search.json"


# ---------------------------------------------------------------------------
# PSR toy cases
# ---------------------------------------------------------------------------


def test_psr_at_sr_hat_equals_benchmark_is_exactly_half() -> None:
    """Universal, skew/kurtosis-independent reduction: when SR_hat == SR*,
    the PSR z-score numerator is exactly 0 regardless of skew/kurtosis/T
    (since (SR_hat - SR*) = 0 makes the whole z-score 0), so PSR = Phi(0) =
    0.5 exactly. This holds even for extreme, non-Normal skew/kurtosis
    values, which is what makes it a strong, formula-implementation-level
    sanity check (verified by hand: numerator is literally zero times
    anything)."""
    for skew, kurt, n in [(0.0, 3.0, 50), (2.5, 9.0, 10), (-1.3, 5.5, 500)]:
        psr = probabilistic_sharpe_ratio(sr_hat=0.7, sr_benchmark=0.7, n=n, skew=skew, kurtosis=kurt)
        assert psr == pytest.approx(0.5, abs=1e-12)


def test_psr_matches_scipy_norm_cdf_direct_computation() -> None:
    """Cross-check against a hand-computed z-score fed directly into
    scipy.stats.norm.cdf -- verifies the implementation matches the
    documented formula term-for-term (denominator = 1 - skew*SR_hat +
    ((kurt-1)/4)*SR_hat^2, numerator = (SR_hat-SR*)*sqrt(n-1))."""
    sr_hat, sr_star, n, skew, kurt = 0.42, 0.1, 120, 0.8, 4.2
    denom = 1 - skew * sr_hat + ((kurt - 1) / 4) * sr_hat**2
    expected_z = (sr_hat - sr_star) * math.sqrt(n - 1) / math.sqrt(denom)
    expected_psr = stats.norm.cdf(expected_z)
    actual = probabilistic_sharpe_ratio(sr_hat, sr_star, n, skew, kurt)
    assert actual == pytest.approx(expected_psr, abs=1e-12)


def test_psr_increases_with_more_observations_all_else_equal() -> None:
    """A higher T (more observations behind the same SR_hat) should increase
    confidence that the true SR exceeds a lower benchmark -- PSR should be
    monotonically increasing in n when SR_hat > SR*."""
    psr_small_n = probabilistic_sharpe_ratio(0.5, 0.0, 10, 0.0, 3.0)
    psr_large_n = probabilistic_sharpe_ratio(0.5, 0.0, 1000, 0.0, 3.0)
    assert psr_large_n > psr_small_n


def test_psr_requires_at_least_two_observations() -> None:
    with pytest.raises(ValueError):
        probabilistic_sharpe_ratio(0.5, 0.0, 1, 0.0, 3.0)


def test_psr_raises_on_non_positive_denominator() -> None:
    """An extreme skew/kurtosis + SR_hat combination can make the
    non-Normality adjustment term collapse the denominator to <= 0, where
    PSR is mathematically undefined; the function must raise rather than
    silently return nan or a wrong value. Verified by hand: denom =
    1 - 20*2 + ((1-1)/4)*2^2 = 1 - 40 + 0 = -39 <= 0."""
    with pytest.raises(ValueError):
        probabilistic_sharpe_ratio(sr_hat=2.0, sr_benchmark=0.0, n=50, skew=20.0, kurtosis=1.0)


# ---------------------------------------------------------------------------
# summarize_return_series toy cases
# ---------------------------------------------------------------------------


def test_summarize_return_series_matches_scipy_skew_kurtosis() -> None:
    returns = [0.5, -0.2, 1.3, 0.1, -0.8, 0.4, 0.9, -0.3, 0.2, 0.6]
    result = summarize_return_series(returns)
    assert result.n == len(returns)
    assert result.mean == pytest.approx(sum(returns) / len(returns))
    assert result.skew == pytest.approx(float(stats.skew(returns, bias=True)))
    assert result.kurtosis == pytest.approx(float(stats.kurtosis(returns, fisher=False, bias=True)))
    # Normal-ish random data should NOT show raw kurtosis near 0 (that would
    # indicate an accidental excess-kurtosis convention leak).
    assert result.kurtosis > 1.0


def test_summarize_return_series_rejects_too_few_observations() -> None:
    with pytest.raises(ValueError):
        summarize_return_series([1.0, 2.0, 3.0])


def test_summarize_return_series_rejects_zero_variance() -> None:
    with pytest.raises(ValueError):
        summarize_return_series([1.0, 1.0, 1.0, 1.0])


# ---------------------------------------------------------------------------
# expected_max_sharpe_under_null toy cases
# ---------------------------------------------------------------------------


def test_expected_max_sharpe_under_null_matches_hand_computed_toy_case() -> None:
    """Small-N (N=2) hand-computable case: trial_sharpes=[1.0, -1.0] has
    sample mean 0, sample variance ((1-0)^2 + (-1-0)^2)/(2-1) = 2.0. Verify
    the closed-form formula matches a direct hand-computation using
    scipy.stats.norm.ppf, and that the magnitude is sane (0 < E[max SR] <
    max(trial_sharpes), since the EXPECTED max of random noise draws should
    sit below the single best OBSERVED draw)."""
    trial_sharpes = [1.0, -1.0]
    gamma = 0.5772156649015329
    n = 2
    var_expected = 2.0
    std_expected = math.sqrt(var_expected)
    term1 = (1 - gamma) * stats.norm.ppf(1 - 1 / n)
    term2 = gamma * stats.norm.ppf(1 - 1 / (n * math.e))
    e_max_expected = std_expected * (term1 + term2)

    e_max, var_across = expected_max_sharpe_under_null(trial_sharpes)
    assert var_across == pytest.approx(var_expected)
    assert e_max == pytest.approx(e_max_expected, abs=1e-9)
    assert 0.0 < e_max < max(trial_sharpes)


def test_expected_max_sharpe_under_null_increases_with_more_trials() -> None:
    """More trials searched under the same null (same cross-trial variance)
    should raise the expected maximum -- the more lottery tickets, the
    luckier the best one looks by chance."""
    trial_sharpes_small = [0.1, 0.3, -0.2, 0.0, 0.15]
    e_max_small, var_small = expected_max_sharpe_under_null(trial_sharpes_small)
    e_max_large, var_same = expected_max_sharpe_under_null(trial_sharpes_small, n_trials=100)
    assert e_max_large > e_max_small
    # n_trials override must not change the variance estimate itself (only
    # the N inside the two Phi^-1 terms) -- the variance is always estimated
    # from the actual trial_sharpes sample, independent of the n_trials arg.
    assert var_same == pytest.approx(var_small, rel=1e-12)


def test_expected_max_sharpe_under_null_requires_at_least_two_trials() -> None:
    with pytest.raises(ValueError):
        expected_max_sharpe_under_null([1.0])


def test_expected_max_sharpe_under_null_zero_variance_gives_zero() -> None:
    """If every trial scored identically (zero cross-trial variance), there
    is no 'luck spread' to inflate the best one -- E[max SR] should be
    exactly 0."""
    e_max, var_across = expected_max_sharpe_under_null([0.5, 0.5, 0.5, 0.5])
    assert e_max == 0.0
    assert var_across == 0.0


# ---------------------------------------------------------------------------
# deflated_sharpe_ratio + bonferroni_check + bootstrap p-value
# ---------------------------------------------------------------------------


def test_deflated_sharpe_ratio_end_to_end_toy_case() -> None:
    """DSR should be strictly less than PSR(0) whenever E[max SR under null]
    > 0 (i.e. whenever there was genuine multiple-testing to correct for) --
    the trial correction can only make the bar harder to clear, never
    easier."""
    winner_returns = [0.5, 0.3, -0.1, 0.8, 0.2, -0.3, 0.6, 0.1, 0.4, -0.2, 0.7, 0.15]
    trial_sharpes = [0.1, -0.2, 0.3, 0.05, -0.1, 0.15, 0.25, -0.05]
    result = deflated_sharpe_ratio(winner_returns, trial_sharpes)
    assert isinstance(result, DeflatedSharpeResult)
    assert isinstance(result.winner_stats, ReturnSeriesStats)
    assert result.expected_max_sr_null > 0.0
    assert result.dsr < result.psr_zero
    assert 0.0 <= result.dsr <= 1.0
    assert 0.0 <= result.psr_zero <= 1.0


def test_deflated_sharpe_ratio_accepts_explicit_n_trials_override() -> None:
    """A larger true N (more trials searched than scores available) should
    raise the E[max SR] benchmark and thus lower DSR, all else equal."""
    winner_returns = [0.5, 0.3, -0.1, 0.8, 0.2, -0.3, 0.6, 0.1, 0.4, -0.2, 0.7, 0.15]
    trial_sharpes = [0.1, -0.2, 0.3, 0.05, -0.1, 0.15, 0.25, -0.05]
    result_default = deflated_sharpe_ratio(winner_returns, trial_sharpes)
    result_more_trials = deflated_sharpe_ratio(winner_returns, trial_sharpes, n_trials=500)
    assert result_more_trials.n_trials == 500
    assert result_more_trials.expected_max_sr_null > result_default.expected_max_sr_null
    assert result_more_trials.dsr <= result_default.dsr


def test_bonferroni_check_toy_case() -> None:
    result = bonferroni_check(p_value=0.001, n_trials=10, alpha=0.05)
    assert result["bonferroni_adjusted_p"] == pytest.approx(0.01)
    assert result["bonferroni_corrected_alpha"] == pytest.approx(0.005)
    assert result["passes_bonferroni"] is True

    result_fail = bonferroni_check(p_value=0.01, n_trials=10, alpha=0.05)
    assert result_fail["bonferroni_adjusted_p"] == pytest.approx(0.1)
    assert result_fail["passes_bonferroni"] is False


def test_bonferroni_check_caps_adjusted_p_at_one() -> None:
    result = bonferroni_check(p_value=0.5, n_trials=10, alpha=0.05)
    assert result["bonferroni_adjusted_p"] == 1.0


def test_bonferroni_check_rejects_invalid_inputs() -> None:
    with pytest.raises(ValueError):
        bonferroni_check(p_value=1.5, n_trials=10)
    with pytest.raises(ValueError):
        bonferroni_check(p_value=0.05, n_trials=0)


def test_bootstrap_p_value_clearly_positive_mean_is_near_zero() -> None:
    """A sample with a strongly, unambiguously positive mean and low
    variance should produce a bootstrap p-value near 0 for H0: mean <= 0."""
    sample = [1.0, 1.1, 0.9, 1.2, 0.95, 1.05, 1.0, 1.1, 0.9, 1.0]
    p = one_sample_bootstrap_p_value(sample, n_boot=2000, seed=1)
    assert p < 0.05


def test_bootstrap_p_value_zero_mean_noise_is_near_half() -> None:
    """A symmetric-around-zero sample should produce a bootstrap p-value
    near 0.5 (no evidence the true mean is positive)."""
    sample = [1.0, -1.0, 2.0, -2.0, 0.5, -0.5, 1.5, -1.5, 0.0, 0.2, -0.2]
    p = one_sample_bootstrap_p_value(sample, n_boot=5000, seed=2)
    assert 0.3 < p < 0.7


def test_bootstrap_p_value_is_deterministic_given_seed() -> None:
    sample = [0.3, -0.1, 0.5, 0.2, -0.4, 0.6, 0.1]
    p1 = one_sample_bootstrap_p_value(sample, n_boot=500, seed=7)
    p2 = one_sample_bootstrap_p_value(sample, n_boot=500, seed=7)
    assert p1 == p2


# ---------------------------------------------------------------------------
# End-to-end pipeline smoke test on real saved data
# ---------------------------------------------------------------------------

_missing_data_reason = None
if not PARQUET.exists():
    _missing_data_reason = f"parquet not found at {PARQUET}"
elif not ROUND1_CSV.exists():
    _missing_data_reason = f"round1 CSV not found at {ROUND1_CSV}"
elif not ROUND2_JSON.exists():
    _missing_data_reason = f"round2 JSON not found at {ROUND2_JSON}"


@pytest.mark.skipif(_missing_data_reason is not None, reason=str(_missing_data_reason))
def test_orb_overfitting_correction_script_runs_end_to_end_on_real_data() -> None:
    """Runs the actual script as a subprocess against the real saved
    walk-forward CSV/JSON and the real parquet bar data, and checks it
    completes successfully and prints/writes a coherent DSR verdict. This is
    a slow test (reads ~2.3M bars and re-runs the ORB backtest over the full
    pre-holdout window) but is the only way to verify the real pipeline
    doesn't crash and produces sane numbers on the actual data it will be
    judged against."""
    proc = subprocess.run(
        [sys.executable, str(SCRIPT_PATH)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert proc.returncode == 0, f"script failed:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    assert "DSR" in proc.stdout
    assert "wrote" in proc.stdout

    import json

    out_path = ROOT / "Analysis" / "output" / "orb" / "overfitting_correction.json"
    assert out_path.exists()
    data = json.loads(out_path.read_text())

    assert data["n_trials_total"] == 234
    assert data["n_trials_round1_grid"] == 216
    assert data["n_trials_round2_grid"] == 18
    assert 0.0 <= data["dsr_proxy_scale"] <= 1.0
    assert 0.0 <= data["psr_zero_proxy_scale"] <= 1.0
    assert data["winner_return_series_stats_r_multiple"]["n_trades"] > 0
    assert "verdict" in data and "DSR" in data["verdict"]
    assert isinstance(data["caveats"], list) and len(data["caveats"]) > 0
    # Trial correction must never be MORE generous than the uncorrected PSR(0)
    # on the same scale.
    assert data["dsr_proxy_scale"] <= data["psr_zero_proxy_scale"] + 1e-9


def test_overfitting_stats_module_is_importable_standalone() -> None:
    """Sanity check that src/optimizer/overfitting_stats.py has no hidden
    dependency on pandas or the rest of the ORB pipeline (per its docstring
    claim of being reusable outside this project). Checked by inspecting
    its own import statements directly (avoids exec()'ing the module under
    a synthetic module name, which trips a dataclasses/sys.modules quirk
    unrelated to what this test actually needs to verify)."""
    source = (ROOT / "src" / "optimizer" / "overfitting_stats.py").read_text()
    assert "import pandas" not in source
    assert "from src." not in source  # no dependency on the rest of this project's src tree

    # Also verify it's actually importable and exposes the documented API
    # (via the normal package import path, which is already exercised by
    # every other test in this file, but asserted explicitly here).
    import src.optimizer.overfitting_stats as mod

    assert hasattr(mod, "probabilistic_sharpe_ratio")
    assert hasattr(mod, "deflated_sharpe_ratio")
