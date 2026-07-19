"""Deflated Sharpe Ratio (DSR) / Probabilistic Sharpe Ratio (PSR) math.

Implements Bailey & Lopez de Prado, "The Deflated Sharpe Ratio: Correcting
for Selection Bias, Backtest Overfitting, and Non-Normality" (Journal of
Portfolio Management, 2014), plus the trial-correction term from the
companion literature on the expected maximum Sharpe ratio under a null of
zero true skill ("Probability of Backtest Overfitting", Bailey, Borwein,
Lopez de Prado, Zhu).

Kurtosis convention: this module uses RAW (Pearson) kurtosis throughout,
i.e. a normal distribution has kurtosis = 3.0 (scipy's `fisher=False`
convention), NOT excess kurtosis (normal = 0.0). This matches the
`(gamma4 - 1) / 4` term in the PSR formula as published in Bailey &
Lopez de Prado (2012, "The Sharpe Ratio Efficient Frontier") and (2014).
Callers must pass raw kurtosis (e.g. `scipy.stats.kurtosis(x, fisher=False)`)
into `probabilistic_sharpe_ratio`; passing excess kurtosis will silently
produce a wrong (too-generous) PSR.

No dependency on pandas — pure-Python/scipy math on flat sequences, so this
module is reusable outside the ORB walk-forward pipeline.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from scipy import stats

EULER_MASCHERONI = 0.5772156649015329


@dataclass(frozen=True)
class ReturnSeriesStats:
    """Summary statistics of one return/R-multiple series, as consumed by PSR/DSR."""

    n: int
    mean: float
    std: float
    sharpe: float  # mean / std, same convention as the input series (not annualized unless caller annualizes first)
    skew: float  # sample skewness (gamma3)
    kurtosis: float  # sample RAW kurtosis (gamma4; normal = 3.0), NOT excess


def summarize_return_series(returns: list[float]) -> ReturnSeriesStats:
    """Compute (n, mean, std, Sharpe, skew, raw kurtosis) for a return series.

    `returns` must have at least 4 observations (skew/kurtosis are undefined,
    or numerically degenerate, below that). Std uses the sample (ddof=1)
    convention, matching the T-1 term in the PSR formula.
    """
    n = len(returns)
    if n < 4:
        raise ValueError(f"need at least 4 observations to compute skew/kurtosis, got {n}")
    mean = sum(returns) / n
    variance = sum((r - mean) ** 2 for r in returns) / (n - 1)
    std = math.sqrt(variance)
    if std == 0.0:
        raise ValueError("return series has zero variance; Sharpe/skew/kurtosis are undefined")
    sharpe = mean / std
    skew = float(stats.skew(returns, bias=True))
    kurt = float(stats.kurtosis(returns, fisher=False, bias=True))
    return ReturnSeriesStats(n=n, mean=mean, std=std, sharpe=sharpe, skew=skew, kurtosis=kurt)


def probabilistic_sharpe_ratio(
    sr_hat: float,
    sr_benchmark: float,
    n: int,
    skew: float,
    kurtosis: float,
) -> float:
    """PSR(SR*): probability the TRUE Sharpe ratio exceeds `sr_benchmark`, given an
    observed Sharpe `sr_hat` estimated from `n` observations with sample skew
    `skew` (gamma3) and RAW kurtosis `kurtosis` (gamma4; normal = 3.0).

    PSR(SR*) = Phi( (SR_hat - SR*) * sqrt(n-1) / sqrt(1 - skew*SR_hat + ((kurtosis-1)/4)*SR_hat^2) )

    Bailey & Lopez de Prado (2012/2014). Requires n >= 2 (needs sqrt(n-1) > 0)
    and a strictly positive value under the inner sqrt (i.e. the
    non-Normality adjustment must not make the denominator non-positive;
    raises ValueError if so, since PSR is undefined there).
    """
    if n < 2:
        raise ValueError(f"PSR requires n >= 2, got {n}")
    denom_inner = 1.0 - skew * sr_hat + ((kurtosis - 1.0) / 4.0) * sr_hat**2
    if denom_inner <= 0.0:
        raise ValueError(
            f"PSR denominator non-positive ({denom_inner!r}) for sr_hat={sr_hat}, "
            f"skew={skew}, kurtosis={kurtosis}; non-Normality adjustment invalid here"
        )
    z = (sr_hat - sr_benchmark) * math.sqrt(n - 1) / math.sqrt(denom_inner)
    return float(stats.norm.cdf(z))


def expected_max_sharpe_under_null(
    trial_sharpes: list[float],
    n_trials: int | None = None,
) -> tuple[float, float]:
    """E[max SR] across N independent trials under a null of zero true skill.

    E[max SR] ~= sqrt(Var[{SR_n}]) * [ (1-gamma)*Phi^-1(1 - 1/N) + gamma*Phi^-1(1 - 1/(N*e)) ]

    where Var[{SR_n}] is the variance of the Sharpe-like scores observed
    ACROSS the N trials (cross-sectional variance of the trial scores
    themselves, not the within-trial return variance), gamma is the
    Euler-Mascheroni constant, and Phi^-1 is the inverse standard normal CDF.

    Bailey, Borwein, Lopez de Prado, Zhu, "Probability of Backtest
    Overfitting" (formula for the expected maximum of N Normal draws with
    the observed cross-trial variance, used as a benchmark Sharpe under the
    "no real strategy is better than the luckiest of N random trials" null).

    `n_trials` lets the caller supply the TRUE number of trials searched
    (the N inside the two Phi^-1 terms) separately from `len(trial_sharpes)`
    (the sample actually available to estimate Var[{SR_n}]), for the common
    case where not every trial's score was persisted/recoverable. Defaults
    to `len(trial_sharpes)` when omitted (the two coincide when the full
    trial set's scores are available). If `n_trials` is supplied and larger
    than `len(trial_sharpes)`, Var[{SR_n}] is still estimated only from the
    available `trial_sharpes` (a caller-documented approximation) while N in
    the Phi^-1 terms uses the true trial count.

    Returns (e_max_sr, var_across_trials). Requires len(trial_sharpes) >= 2
    (to estimate variance) and effective N >= 2.
    """
    n_available = len(trial_sharpes)
    if n_available < 2:
        raise ValueError(f"expected_max_sharpe_under_null requires >= 2 trial_sharpes, got {n_available}")
    n = n_trials if n_trials is not None else n_available
    if n < 2:
        raise ValueError(f"n_trials must be >= 2, got {n}")
    mean_sr = sum(trial_sharpes) / n_available
    var_across = sum((s - mean_sr) ** 2 for s in trial_sharpes) / (n_available - 1)
    std_across = math.sqrt(var_across)
    if std_across == 0.0:
        return 0.0, 0.0
    term1 = (1.0 - EULER_MASCHERONI) * stats.norm.ppf(1.0 - 1.0 / n)
    term2 = EULER_MASCHERONI * stats.norm.ppf(1.0 - 1.0 / (n * math.e))
    e_max_sr = std_across * (term1 + term2)
    return float(e_max_sr), float(var_across)


@dataclass(frozen=True)
class DeflatedSharpeResult:
    """Full DSR computation output for one winning configuration."""

    n_trials: int
    var_across_trials: float
    expected_max_sr_null: float
    winner_stats: ReturnSeriesStats
    psr_zero: float  # PSR(SR*=0): probability true SR > 0
    dsr: float  # PSR(SR*=E[max SR under null]): probability true SR beats the best of N lucky trials


def deflated_sharpe_ratio(
    winner_returns: list[float],
    trial_sharpes: list[float],
    n_trials: int | None = None,
) -> DeflatedSharpeResult:
    """End-to-end DSR: winner's own return series stats + trial-corrected benchmark.

    `winner_returns` = the winning configuration's own per-period return
    series (e.g. per-trade R-multiples), used for SR_hat/T/skew/kurtosis.
    `trial_sharpes` = the Sharpe-like score observed for EACH of the trials
    for which a score could be recovered, used to estimate the cross-trial
    variance for the E[max SR] null benchmark — NOT used as the return
    series for skew/kurtosis/T. `n_trials` optionally supplies the TRUE
    number of trials searched (may exceed `len(trial_sharpes)` if not every
    trial's score was recoverable — see `expected_max_sharpe_under_null`);
    defaults to `len(trial_sharpes)`.

    IMPORTANT: `winner_returns` and the individual scores in `trial_sharpes`
    must be on the SAME Sharpe scale/units (e.g. all per-trade, or all
    per-fold) for SR_hat and the E[max SR] benchmark to be comparable inside
    one PSR call — mixing scales silently produces a meaningless DSR. If
    your winner's return series and your trials' scores come from different
    granularities (e.g. per-trade returns vs. per-fold summary stats), build
    the winner's own SR_hat on the SAME granularity as `trial_sharpes`
    instead of passing a differently-scaled return series here.
    """
    winner_stats = summarize_return_series(winner_returns)
    e_max_sr, var_across = expected_max_sharpe_under_null(trial_sharpes, n_trials=n_trials)
    psr_zero = probabilistic_sharpe_ratio(
        winner_stats.sharpe, 0.0, winner_stats.n, winner_stats.skew, winner_stats.kurtosis
    )
    dsr = probabilistic_sharpe_ratio(
        winner_stats.sharpe, e_max_sr, winner_stats.n, winner_stats.skew, winner_stats.kurtosis
    )
    return DeflatedSharpeResult(
        n_trials=n_trials if n_trials is not None else len(trial_sharpes),
        var_across_trials=var_across,
        expected_max_sr_null=e_max_sr,
        winner_stats=winner_stats,
        psr_zero=psr_zero,
        dsr=dsr,
    )


def bonferroni_check(p_value: float, n_trials: int, alpha: float = 0.05) -> dict:
    """Bonferroni-corrected significance check: does a single-trial p-value
    survive multiplying the significance threshold's implied per-trial alpha
    by `n_trials`?

    Returns a dict with the raw p-value, the Bonferroni-adjusted p-value
    (p_value * n_trials, capped at 1.0), the corrected threshold
    (alpha / n_trials), and whether the trial clears the corrected bar
    (equivalently: whether adjusted p-value < alpha).
    """
    if not (0.0 <= p_value <= 1.0):
        raise ValueError(f"p_value must be in [0, 1], got {p_value}")
    if n_trials < 1:
        raise ValueError(f"n_trials must be >= 1, got {n_trials}")
    adjusted_p = min(1.0, p_value * n_trials)
    corrected_alpha = alpha / n_trials
    return {
        "p_value_raw": p_value,
        "n_trials": n_trials,
        "alpha": alpha,
        "bonferroni_corrected_alpha": corrected_alpha,
        "bonferroni_adjusted_p": adjusted_p,
        "passes_bonferroni": adjusted_p < alpha,
    }


def one_sample_bootstrap_p_value(
    sample: list[float],
    *,
    n_boot: int = 10_000,
    seed: int = 0,
) -> float:
    """One-sided bootstrap p-value for H0: true mean <= 0 vs H1: true mean > 0.

    Resamples `sample` with replacement `n_boot` times, shifts each bootstrap
    mean to be centered under the null (subtract the observed sample mean,
    so the null distribution is centered at 0), and computes the fraction of
    null-centered bootstrap means >= the observed sample mean. This is the
    standard "shift to the null" one-sample bootstrap test, avoiding the
    invalid shortcut of just resampling and checking how often the resample
    mean is negative (which tests the wrong hypothesis).
    """
    import random

    n = len(sample)
    if n < 2:
        raise ValueError(f"need at least 2 observations for bootstrap, got {n}")
    observed_mean = sum(sample) / n
    rng = random.Random(seed)
    count_ge = 0
    for _ in range(n_boot):
        resample = [sample[rng.randrange(n)] for _ in range(n)]
        resample_mean = sum(resample) / n
        null_centered = resample_mean - observed_mean
        if null_centered >= observed_mean:
            count_ge += 1
    return count_ge / n_boot
