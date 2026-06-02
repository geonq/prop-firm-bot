from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.optimizer.search import OptimizerCellResult, search_adaptive_grid
from src.pipeline.monte_carlo import ParametricGridResult, run_parametric_grid
from src.rules.lucidflex import LucidFlex50K
from src.rules.topstep import TopStepPayoutPath

st.set_page_config(
    page_title="Prop Firm Probability Lab",
    page_icon="PF",
    layout="wide",
    initial_sidebar_state="expanded",
)


DEFAULT_SUMMARY_PATHS = (
    ROOT / "Research/OrderFlowL2/summary.csv",
)
STANDARD_LUCID_EVAL_FEE = LucidFlex50K().eval_fee


DEFAULT_SWEEP_PROFILES = ((0.50, 1.00), (0.65, 0.50), (0.75, 0.30))
DEFAULT_EVAL_RISKS = (150.0, 200.0, 250.0, 300.0)
DEFAULT_FUNDED_RISKS = (125.0, 200.0, 300.0)
DEFAULT_SWEEP_SIMS = 1_000


def assign_tier(mean_ev: float, breach_cond: float, max_payout: float) -> str:
    if mean_ev <= 0:
        return "Negative EV"
    if breach_cond >= 0.85 or max_payout < 0.02:
        return "Aggressive"
    return "Candidate"


ENGINE_PHASES = [
    {
        "phase": "Phase 1 — Ruleset encoding",
        "status": "done",
        "artifacts": "src/rules/lucidflex.py, src/rules/topstep.py, Rulesets/PHASE1_RULESET_AUDIT.md",
        "done": "Both firms encoded with reviewer-pass sign-off. Trailing DD, consistency, payout, max contracts, EOD flatten / weekend hold all live. 102 tests green.",
        "next": "Deferred: TopStep news / CME price-limit proximity rules; LucidFlex news/velocity logic. Audit-flagged as second-order risk.",
        "priority": 1,
    },
    {
        "phase": "Phase 2 — Account state machines",
        "status": "done",
        "artifacts": "lucidflex_account.py, lucidflex_pipeline.py, topstep_account.py, topstep_pipeline.py",
        "done": "Per-ruleset state machines and full eval/Combine -> funded/XFA -> payout pipelines exist for both firms.",
        "next": "Generic cross-ruleset src/pipeline/simulator.py not built. tests/test_simulator.py not written.",
        "priority": 2,
    },
    {
        "phase": "Phase 3 — Parametric Monte Carlo",
        "status": "partial",
        "artifacts": "parametric.py, sizing/dynamic.py, pipeline/monte_carlo.py, optimizer/search.py",
        "done": "Bernoulli + phase-aware + state-aware strategies. Generic LucidFlex/TopStep Monte Carlo aggregator with CI bounds. Cross-firm adaptive sizing grid optimizer.",
        "next": "Regime-dependent / autocorrelated trade variants. Bayesian optimization to replace grid.",
        "priority": 3,
    },
    {
        "phase": "Phase 4 — Order-flow / L2 research",
        "status": "active",
        "artifacts": "Research/OrderFlowL2/README.md",
        "done": "Model A/Pine and prior paper/public-strategy attempts are parked. Main now focuses on objective depth/tape data.",
        "next": "Capture or import NQ+ES Rithmic depth/tape data, then compute queue imbalance, OFI, delta, absorption, replenishment, and ES/NQ confirmation features.",
        "priority": 4,
    },
    {
        "phase": "Phase 5 — Optimizer + cross-firm comparison",
        "status": "partial",
        "artifacts": "Probability tab firm selector; cross-firm Sizing Lab; reset_economics.py",
        "done": "Probability and Sizing Lab run LucidFlex or TopStep. TopStep supports Standard/Consistency path, optional DLL, and Back2Funded retries. Reset-vs-fresh cost helper exists.",
        "next": "Bayesian optimization and richer reset timing economics after an L2-derived trade distribution exists.",
        "priority": 5,
    },
    {
        "phase": "Archived — TV/Pine and paper strategy search",
        "status": "parked",
        "artifacts": "GitHub branch `archived`; ignored local `Archived/` payloads",
        "done": "Discretionary Model A automation, public Pine concepts, and paper-mined strategy attempts are no longer active on main.",
        "next": "Re-open only if Georg explicitly requests a timeboxed falsification pass.",
        "priority": 6,
    },
]


def pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def money(value: float) -> str:
    sign = "-" if value < 0 else ""
    return f"{sign}${abs(value):,.0f}"


@st.cache_data(show_spinner="Running parametric Monte Carlo sweep...")
def run_phase_sweep(
    firm: str,
    profiles: tuple[tuple[float, float], ...],
    eval_risks: tuple[float, ...],
    funded_risks: tuple[float, ...],
    n_sims: int,
) -> pd.DataFrame:
    firm_key = "topstep" if firm == "TopStep 50K NoFee" else "lucidflex"
    rows: list[ParametricGridResult] = run_parametric_grid(
        firm=firm_key,
        profiles=profiles,
        eval_risks=eval_risks,
        funded_risks=funded_risks,
        n_simulations=n_sims,
        payout_cap=5 if firm_key == "topstep" else None,
    )
    records = []
    for r in rows:
        records.append(
            {
                "profile": f"{int(r.win_rate * 100)}% WR / {r.rr_ratio:.2f}R reward",
                "win_rate": r.win_rate,
                "rr": r.rr_ratio,
                "eval_risk": r.eval_risk,
                "funded_risk": r.funded_risk,
                "eval_pass": r.eval_pass_rate,
                "funded_breach_all": r.funded_breach_rate,
                "funded_breach_cond": r.funded_breach_after_pass_rate,
                "max_payout": r.max_payout_rate,
                "avg_payouts": r.mean_payouts,
                "avg_paid": r.mean_trader_payouts,
                "mean_ev": r.mean_net_ev,
                "median_ev": r.median_net_ev,
                "ev_stderr": r.ev_stderr,
                "ev_ci_low": r.ev_ci.low,
                "ev_ci_high": r.ev_ci.high,
            }
        )
    df = pd.DataFrame(records)
    df["tier"] = [
        assign_tier(row["mean_ev"], row["funded_breach_cond"], row["max_payout"])
        for _, row in df.iterrows()
    ]
    return df


def priced_phase_rows(df: pd.DataFrame, eval_fee: int) -> pd.DataFrame:
    out = df.copy()
    fee_delta = STANDARD_LUCID_EVAL_FEE - eval_fee
    out["eval_fee"] = eval_fee
    out["mean_ev"] = out["mean_ev"] + fee_delta
    out["median_ev"] = out["median_ev"] + fee_delta
    out["ev_ci_low"] = out["ev_ci_low"] + fee_delta
    out["ev_ci_high"] = out["ev_ci_high"] + fee_delta
    return out


@st.cache_data(show_spinner=False)
def load_l2_summary(path_text: str | None) -> pd.DataFrame:
    candidates = []
    if path_text:
        candidates.append(Path(path_text).expanduser())
    candidates.extend(DEFAULT_SUMMARY_PATHS)

    for candidate in candidates:
        if not candidate.is_absolute():
            candidate = ROOT / candidate
        if candidate.exists():
            df = pd.read_csv(candidate)
            df.attrs["source_path"] = str(candidate)
            numeric_cols = [
                "target_records",
                "seconds",
                "seconds_with_events",
                "median_events_per_active_second",
                "median_spread",
                "max_spread",
                "trade_records",
                "trade_volume",
                "invalid_or_crossed_spread_records",
            ]
            corr_cols = [col for col in df.columns if col.startswith(("corr_", "pressure_corr_"))]
            for col in numeric_cols + corr_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
            return df
    empty = pd.DataFrame()
    empty.attrs["source_path"] = ""
    return empty


def style_app() -> None:
    st.markdown(
        """
        <style>
        :root {
          --pf-bg: #050607;
          --pf-panel: #0d0f10;
          --pf-panel-2: #141718;
          --pf-border: #252b2d;
          --pf-text: #f4f4f5;
          --pf-muted: #9ca3af;
          --pf-green: #34d399;
          --pf-cyan: #22d3ee;
          --pf-amber: #fbbf24;
          --pf-red: #fb7185;
        }
        .stApp {
          background: var(--pf-bg);
          color: var(--pf-text);
        }
        [data-testid="stSidebar"] {
          background: #080a0b;
          border-right: 1px solid var(--pf-border);
        }
        [data-testid="stMetric"] {
          background: var(--pf-panel);
          border: 1px solid var(--pf-border);
          border-radius: 8px;
          padding: 12px;
        }
        div[data-testid="stDataFrame"] {
          border: 1px solid var(--pf-border);
          border-radius: 8px;
        }
        .pf-card {
          border: 1px solid var(--pf-border);
          border-radius: 8px;
          background: var(--pf-panel);
          padding: 12px;
          min-height: 148px;
        }
        .pf-card h3 {
          font-size: 0.98rem;
          margin: 0 0 8px 0;
        }
        .pf-card p {
          color: var(--pf-muted);
          font-size: 0.82rem;
          line-height: 1.42;
          margin: 0 0 7px 0;
        }
        .pf-badge {
          display: inline-block;
          font-size: 0.72rem;
          border: 1px solid var(--pf-border);
          border-radius: 999px;
          padding: 2px 7px;
          margin-bottom: 9px;
          color: var(--pf-muted);
        }
        .pf-badge.done { color: var(--pf-green); border-color: rgba(52, 211, 153, .55); }
        .pf-badge.partial { color: var(--pf-cyan); border-color: rgba(34, 211, 238, .55); }
        .pf-badge.pending { color: var(--pf-amber); border-color: rgba(251, 191, 36, .55); }
        .pf-badge.parked { color: var(--pf-red); border-color: rgba(251, 113, 133, .55); }
        .pf-note {
          border-left: 3px solid var(--pf-amber);
          background: var(--pf-panel);
          padding: 10px 12px;
          color: var(--pf-muted);
          border-radius: 6px;
        }
        h1, h2, h3 { letter-spacing: 0; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def plot_probability_scatter(df: pd.DataFrame) -> go.Figure:
    plot_df = df.copy()
    plot_df["bubble_size"] = plot_df["mean_ev"].clip(lower=0) + 50
    fig = px.scatter(
        plot_df,
        x="eval_pass",
        y="funded_breach_cond",
        size="bubble_size",
        color="tier",
        hover_data=["profile", "eval_risk", "funded_risk", "max_payout", "mean_ev", "median_ev"],
        labels={
            "eval_pass": "Eval pass probability",
            "funded_breach_cond": "Funded breach after pass",
            "tier": "Risk band",
        },
        color_discrete_map={
            "Candidate": "#34d399",
            "Aggressive": "#fb7185",
            "Negative EV": "#9ca3af",
        },
    )
    fig.update_layout(
        template="plotly_dark",
        height=380,
        margin=dict(l=10, r=10, t=20, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#0d0f10",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    fig.update_xaxes(tickformat=".0%", gridcolor="rgba(255,255,255,.08)")
    fig.update_yaxes(tickformat=".0%", gridcolor="rgba(255,255,255,.08)")
    return fig


def plot_ev_bar(df: pd.DataFrame) -> go.Figure:
    ordered = df.sort_values("mean_ev", ascending=True).copy()
    ordered["label"] = (
        ordered["profile"]
        + " | eval "
        + ordered["eval_risk"].astype(str)
        + " / funded "
        + ordered["funded_risk"].astype(str)
    )
    fig = go.Figure()
    fig.add_bar(
        x=ordered["mean_ev"],
        y=ordered["label"],
        orientation="h",
        marker_color=ordered["tier"].map(
            {"Candidate": "#34d399", "Aggressive": "#fb7185", "Negative EV": "#9ca3af"}
        ),
        name="Mean EV",
    )
    fig.add_scatter(
        x=ordered["median_ev"],
        y=ordered["label"],
        mode="markers",
        marker=dict(color="#fbbf24", size=9),
        name="Median EV",
    )
    fig.update_layout(
        template="plotly_dark",
        height=390,
        margin=dict(l=10, r=10, t=20, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#0d0f10",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    fig.update_xaxes(tickprefix="$", gridcolor="rgba(255,255,255,.08)")
    fig.update_yaxes(gridcolor="rgba(255,255,255,.04)")
    return fig


def plot_l2_summary(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_bar(
        x=df["session"],
        y=df["median_events_per_active_second"],
        name="Median events / active sec",
        marker_color="#22d3ee",
        yaxis="y",
    )
    fig.add_scatter(
        x=df["session"],
        y=df["median_spread"],
        name="Median spread",
        marker=dict(color="#34d399", size=9),
        yaxis="y2",
    )
    fig.update_layout(
        template="plotly_dark",
        height=360,
        margin=dict(l=10, r=10, t=20, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#0d0f10",
        yaxis=dict(title="Events", gridcolor="rgba(255,255,255,.08)"),
        yaxis2=dict(title="Spread", overlaying="y", side="right", gridcolor="rgba(255,255,255,0)"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    return fig


def plot_corr_heatmap(df: pd.DataFrame) -> go.Figure:
    corr_cols = [
        col
        for col in df.columns
        if (
            col.startswith("corr_")
            and "_imbalance_" in col
            and pd.api.types.is_numeric_dtype(df[col])
        )
    ]
    if not corr_cols:
        return go.Figure()
    matrix = df[["session"] + corr_cols].set_index("session")
    fig = px.imshow(
        matrix,
        aspect="auto",
        color_continuous_scale="RdBu",
        color_continuous_midpoint=0,
        labels=dict(color="corr"),
    )
    fig.update_layout(
        template="plotly_dark",
        height=360,
        margin=dict(l=10, r=10, t=20, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#0d0f10",
    )
    return fig


def plot_pressure_heatmap(df: pd.DataFrame) -> go.Figure:
    corr_cols = [
        col
        for col in df.columns
        if (
            col.startswith("pressure_corr_")
            and "_depth_pressure_" in col
            and pd.api.types.is_numeric_dtype(df[col])
        )
    ]
    if not corr_cols:
        return go.Figure()
    matrix = df[["session"] + corr_cols].set_index("session")
    fig = px.imshow(
        matrix,
        aspect="auto",
        color_continuous_scale="RdBu",
        color_continuous_midpoint=0,
        labels=dict(color="corr"),
    )
    fig.update_layout(
        template="plotly_dark",
        height=360,
        margin=dict(l=10, r=10, t=20, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#0d0f10",
    )
    return fig


def feature_correlation_rank(summary_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for col in summary_df.columns:
        if not (
            (col.startswith("corr_") and "_imbalance_" in col)
            or (col.startswith("pressure_corr_") and "_depth_pressure_" in col)
        ):
            continue
        if not pd.api.types.is_numeric_dtype(summary_df[col]):
            continue

        values = summary_df[col].dropna()
        if values.empty:
            continue

        feature_type = "Depth pressure" if col.startswith("pressure_corr_") else "Depth imbalance"
        horizon = col.split("_")[2] if feature_type == "Depth pressure" else col.split("_")[1]
        rows.append(
            {
                "feature": col,
                "type": feature_type,
                "horizon": horizon,
                "avg_abs_corr": values.abs().mean(),
                "mean_corr": values.mean(),
                "min_corr": values.min(),
                "max_corr": values.max(),
            }
        )

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("avg_abs_corr", ascending=False)


def plot_feature_rank(rank_df: pd.DataFrame) -> go.Figure:
    display = rank_df.head(12).sort_values("avg_abs_corr", ascending=True)
    fig = px.bar(
        display,
        x="avg_abs_corr",
        y="feature",
        color="type",
        orientation="h",
        color_discrete_map={"Depth pressure": "#fbbf24", "Depth imbalance": "#22d3ee"},
        labels={"avg_abs_corr": "Average abs corr", "feature": ""},
    )
    fig.update_layout(
        template="plotly_dark",
        height=420,
        margin=dict(l=10, r=10, t=20, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#0d0f10",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    fig.update_xaxes(gridcolor="rgba(255,255,255,.08)")
    fig.update_yaxes(gridcolor="rgba(255,255,255,.04)")
    return fig


def render_engine_overview() -> None:
    st.markdown(
        '<div class="pf-note">Project thesis: the prop-firm payout structure is the alpha. '
        "Map the (WR, reward/risk, freq, sizing) cells where eval fee → eval → funded → payouts is "
        "net-EV positive, then find strategies that live in those cells. Status of the engine pieces below.</div>",
        unsafe_allow_html=True,
    )
    df = pd.DataFrame(ENGINE_PHASES).sort_values("priority")
    cols = st.columns(3)
    for idx, row in enumerate(df.to_dict("records")):
        with cols[idx % 3]:
            st.markdown(
                f"""
                <div class="pf-card">
                  <span class="pf-badge {row["status"]}">{row["status"]}</span>
                  <h3>{row["phase"]}</h3>
                  <p><b>Artifacts:</b> {row["artifacts"]}</p>
                  <p><b>Done:</b> {row["done"]}</p>
                  <p><b>Next:</b> {row["next"]}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )


def render_tv_strategies_tab() -> None:
    st.subheader("Archived TV/Pine Work")
    st.info(
        "TradingView/Pine strategy ingestion is parked. Tracked legacy files are on "
        "the GitHub branch `archived`; private/raw artifacts remain in ignored local "
        "`Archived/` folders. Main now expects candidate trades to come from the "
        "order-flow/L2 research path."
    )


def render_l2_tab(summary_df: pd.DataFrame) -> None:
    st.subheader("L2 Evidence")
    if summary_df.empty:
        st.markdown(
            '<div class="pf-note">No L2 summary found yet. Capture or import Rithmic/Quantower depth and tape data first.</div>',
            unsafe_allow_html=True,
        )
        return

    source_path = summary_df.attrs.get("source_path", "")
    st.caption(f"Source: `{source_path}`")

    total_records = int(summary_df["target_records"].sum()) if "target_records" in summary_df else 0
    active_seconds = int(summary_df["seconds_with_events"].sum()) if "seconds_with_events" in summary_df else 0
    med_spread = summary_df["median_spread"].median() if "median_spread" in summary_df else float("nan")
    med_events = (
        summary_df["median_events_per_active_second"].median()
        if "median_events_per_active_second" in summary_df
        else float("nan")
    )

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Sessions", f"{len(summary_df):,}")
    col2.metric("Records", f"{total_records:,}")
    col3.metric("Active Seconds", f"{active_seconds:,}")
    col4.metric("Median Spread", f"{med_spread:.2f}")

    col5, col6 = st.columns((1.1, 1))
    with col5:
        st.plotly_chart(plot_l2_summary(summary_df), width="stretch")
    with col6:
        fig = plot_corr_heatmap(summary_df)
        if fig.data:
            st.caption("Static depth imbalance vs forward returns")
            st.plotly_chart(fig, width="stretch")
        else:
            st.markdown(
                '<div class="pf-note">Correlation columns will appear after full batch report output is available.</div>',
                unsafe_allow_html=True,
            )

    rank_df = feature_correlation_rank(summary_df)
    if not rank_df.empty:
        best_imbalance = rank_df[rank_df["type"] == "Depth imbalance"].head(1)
        best_pressure = rank_df[rank_df["type"] == "Depth pressure"].head(1)

        st.subheader("Feature Comparison")
        metric_cols = st.columns(2)
        if not best_imbalance.empty:
            row = best_imbalance.iloc[0]
            metric_cols[0].metric("Best Imbalance", f"{row['avg_abs_corr']:.4f}", row["horizon"])
        if not best_pressure.empty:
            row = best_pressure.iloc[0]
            metric_cols[1].metric("Best Pressure", f"{row['avg_abs_corr']:.4f}", row["horizon"])

        left, right = st.columns((1.05, 1))
        with left:
            st.plotly_chart(plot_feature_rank(rank_df), width="stretch")
        with right:
            pressure_fig = plot_pressure_heatmap(summary_df)
            if pressure_fig.data:
                st.caption("Rolling depth pressure vs matching forward returns")
                st.plotly_chart(pressure_fig, width="stretch")

        st.dataframe(
            rank_df.head(16).style.format(
                {
                    "avg_abs_corr": "{:.4f}",
                    "mean_corr": "{:.4f}",
                    "min_corr": "{:.4f}",
                    "max_corr": "{:.4f}",
                }
            ),
            width="stretch",
            hide_index=True,
        )

    display_cols = [
        col
        for col in [
            "session",
            "target_symbol",
            "target_records",
            "seconds_with_events",
            "median_events_per_active_second",
            "median_spread",
            "max_spread",
            "trade_records",
            "trade_volume",
        ]
        if col in summary_df.columns
    ]
    st.dataframe(summary_df[display_cols], width="stretch", hide_index=True)

    st.caption(f"Median active-second event count: {med_events:.0f}")


def render_probability_tab(firm: str, eval_fee: int) -> None:
    st.subheader("Prop-Firm Probability — Parametric Sweep")
    if firm == "TopStep 50K NoFee":
        note = (
            "No strategy is being tested. This sweeps i.i.d. Bernoulli trade distributions "
            "through the TopStep Combine -> XFA -> payout state machine. The 5-payout marker "
            "is a simulation comparison stop, not a TopStep rule."
        )
    else:
        note = (
            "No strategy is being tested. This sweeps i.i.d. Bernoulli trade distributions "
            "through the LucidFlex eval -> funded -> payout state machine to map which "
            "(WR, reward/risk, eval risk, funded risk) cells are net-EV positive."
        )
    st.markdown(f'<div class="pf-note">{note}</div>', unsafe_allow_html=True)

    with st.expander("Sweep parameters", expanded=True):
        col_wr, col_rr = st.columns(2)
        wr_text = col_wr.text_input(
            "Win rates (comma-separated)", value="0.50, 0.65, 0.75"
        )
        rr_text = col_rr.text_input(
            "Reward/risk R-multiples paired with win rates", value="1.00, 0.50, 0.30"
        )
        col_eval, col_fund = st.columns(2)
        eval_risks_text = col_eval.text_input(
            "Eval per-trade risk ($)", value="150, 200, 250, 300"
        )
        funded_risks_text = col_fund.text_input(
            "Funded per-trade risk ($)", value="125, 200, 300"
        )
        n_sims = st.slider(
            "Sims per cell", min_value=200, max_value=10_000, value=DEFAULT_SWEEP_SIMS, step=200
        )

    try:
        wrs = tuple(float(x) for x in wr_text.split(",") if x.strip())
        rrs = tuple(float(x) for x in rr_text.split(",") if x.strip())
        eval_risks = tuple(float(x) for x in eval_risks_text.split(",") if x.strip())
        funded_risks = tuple(float(x) for x in funded_risks_text.split(",") if x.strip())
    except ValueError:
        st.error("Could not parse sweep inputs as numbers.")
        return

    if len(wrs) != len(rrs):
        st.error(f"Win rate count ({len(wrs)}) must match reward/risk count ({len(rrs)}).")
        return
    if not (wrs and eval_risks and funded_risks):
        st.error("Provide at least one win rate, one eval risk, and one funded risk.")
        return

    profiles = tuple(zip(wrs, rrs))
    n_cells = len(profiles) * len(eval_risks) * len(funded_risks)
    st.caption(f"Sweep size: {n_cells} cells × {n_sims} sims = {n_cells * n_sims:,} pipelines")

    if not st.button("Run sweep", type="primary"):
        st.info("Configure parameters above and click **Run sweep** to compute.")
        return

    raw_df = run_phase_sweep(firm, profiles, eval_risks, funded_risks, n_sims)
    phase_df = priced_phase_rows(raw_df, eval_fee) if firm == "LucidFlex 50K" else raw_df

    candidates = phase_df[phase_df["tier"] == "Candidate"]
    if candidates.empty:
        st.warning("No candidate cells: every sweep cell is negative-EV or aggressive.")
        best = phase_df.sort_values("mean_ev", ascending=False).iloc[0]
    else:
        best = candidates.sort_values("mean_ev", ascending=False).iloc[0]

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Best Cell Eval Pass", pct(best["eval_pass"]))
    col2.metric("Funded Breach After Pass", pct(best["funded_breach_cond"]))
    col3.metric("Mean EV", money(best["mean_ev"]))
    col4.metric("Median EV", money(best["median_ev"]))
    st.caption(
        f"Best-cell EV 95% CI: {money(best['ev_ci_low'])} to {money(best['ev_ci_high'])} "
        f"(stderr {money(best['ev_stderr'])})"
    )

    left, right = st.columns((1, 1))
    with left:
        st.plotly_chart(plot_probability_scatter(phase_df), width="stretch")
    with right:
        st.plotly_chart(plot_ev_bar(phase_df), width="stretch")

    st.dataframe(
        phase_df[
            [
                "profile",
                "tier",
                "eval_risk",
                "funded_risk",
                "eval_pass",
                "funded_breach_cond",
                "max_payout",
                "mean_ev",
                "ev_stderr",
                "ev_ci_low",
                "ev_ci_high",
                "median_ev",
            ]
        ]
        .sort_values("mean_ev", ascending=False)
        .style.format(
            {
                "eval_pass": "{:.1%}",
                "funded_breach_cond": "{:.1%}",
                "max_payout": "{:.1%}",
                "mean_ev": "${:,.0f}",
                "ev_stderr": "${:,.0f}",
                "ev_ci_low": "${:,.0f}",
                "ev_ci_high": "${:,.0f}",
                "median_ev": "${:,.0f}",
            }
        ),
        width="stretch",
        hide_index=True,
    )


@st.cache_data(show_spinner="Searching adaptive sizing grid...")
def run_optimizer_search(
    firm: str,
    win_rate: float,
    rr_ratio: float,
    eval_bases: tuple[float, ...],
    funded_bases: tuple[float, ...],
    buffer_full_fracs: tuple[float, ...],
    buffer_floors: tuple[float, ...],
    post_payout_shrinks: tuple[float, ...],
    n_sims: int,
    topstep_payout_path: str,
    topstep_use_daily_loss_limit: bool,
    topstep_max_back2funded_reactivations: int,
) -> pd.DataFrame:
    firm_key = "topstep" if firm == "TopStep 50K NoFee" else "lucidflex"
    rows: list[OptimizerCellResult] = search_adaptive_grid(
        firm=firm_key,
        win_rate=win_rate,
        rr_ratio=rr_ratio,
        eval_bases=eval_bases,
        funded_bases=funded_bases,
        buffer_full_fracs=buffer_full_fracs,
        buffer_floors=buffer_floors,
        post_payout_shrinks=post_payout_shrinks,
        n_sims=n_sims,
        topstep_payout_path=TopStepPayoutPath(topstep_payout_path),
        topstep_use_daily_loss_limit=topstep_use_daily_loss_limit,
        topstep_max_back2funded_reactivations=topstep_max_back2funded_reactivations,
        payout_cap=5 if firm_key == "topstep" else None,
    )
    return pd.DataFrame(
        [
            {
                "firm": r.firm,
                "eval_base": r.eval_base,
                "funded_base": r.funded_base,
                "buffer_full_frac": r.buffer_full_frac,
                "buffer_floor": r.buffer_floor,
                "post_payout_shrink": r.post_payout_shrink,
                "topstep_payout_path": r.topstep_payout_path.value if r.topstep_payout_path else "",
                "topstep_dll": r.topstep_use_daily_loss_limit,
                "topstep_back2funded": r.topstep_max_back2funded_reactivations,
                "eval_pass": r.eval_pass_rate,
                "funded_breach_cond": r.funded_breach_after_pass_rate,
                "max_payout": r.max_payout_rate,
                "mean_ev": r.mean_net_ev,
                "median_ev": r.median_net_ev,
                "ev_stderr": r.ev_stderr,
            }
            for r in rows
        ]
    )


def render_sizing_lab(firm: str, eval_fee: int) -> None:
    st.subheader("Sizing Lab — adaptive sizing optimizer")
    st.markdown(
        '<div class="pf-note">Pick one (WR, reward/risk) cell. Sweeps an AdaptiveSizing function '
        "across base risk, buffer-aware shrink, and post-payout shrink. Tests whether "
        "state-dependent sizing flips negative-EV cells positive — the load-bearing "
        "test of the structured-product thesis.</div>",
        unsafe_allow_html=True,
    )

    col_wr, col_rr = st.columns(2)
    win_rate = col_wr.slider("Win rate", min_value=0.30, max_value=0.70, value=0.50, step=0.01)
    rr_ratio = col_rr.slider(
        "Reward/risk R multiple",
        min_value=0.10,
        max_value=5.0,
        value=0.30,
        step=0.05,
    )
    topstep_payout_path = TopStepPayoutPath.STANDARD.value
    topstep_use_daily_loss_limit = False
    topstep_max_back2funded_reactivations = 0
    if firm == "TopStep 50K NoFee":
        col_path, col_dll, col_b2f = st.columns(3)
        topstep_payout_path = col_path.selectbox(
            "TopStep payout path",
            [TopStepPayoutPath.STANDARD.value, TopStepPayoutPath.CONSISTENCY.value],
            index=0,
        )
        topstep_use_daily_loss_limit = col_dll.checkbox("Use optional DLL", value=False)
        topstep_max_back2funded_reactivations = int(
            col_b2f.number_input("Back2Funded retries", min_value=0, max_value=2, value=0, step=1)
        )

    with st.expander("Sizing search grid", expanded=True):
        col_eb, col_fb = st.columns(2)
        eval_bases_text = col_eb.text_input("Eval base risk ($)", value="150, 200, 250, 300")
        funded_bases_text = col_fb.text_input("Funded base risk ($)", value="75, 125, 200")
        col_bf, col_floor = st.columns(2)
        buffer_full_text = col_bf.text_input(
            "Buffer-full fraction (0-1)", value="0.02, 0.04, 0.06"
        )
        buffer_floor_text = col_floor.text_input("Buffer floor scale (0-1)", value="0.25, 0.5")
        shrink_text = st.text_input("Post-payout shrink (0-1)", value="0.5, 1.0")
        n_sims = st.slider(
            "Sims per grid point", min_value=100, max_value=5_000, value=500, step=100
        )

    try:
        eval_bases = tuple(float(x) for x in eval_bases_text.split(",") if x.strip())
        funded_bases = tuple(float(x) for x in funded_bases_text.split(",") if x.strip())
        buffer_fulls = tuple(float(x) for x in buffer_full_text.split(",") if x.strip())
        buffer_floors = tuple(float(x) for x in buffer_floor_text.split(",") if x.strip())
        shrinks = tuple(float(x) for x in shrink_text.split(",") if x.strip())
    except ValueError:
        st.error("Could not parse one of the grid inputs as numbers.")
        return

    if not (eval_bases and funded_bases and buffer_fulls and buffer_floors and shrinks):
        st.error("Each grid axis needs at least one value.")
        return

    n_cells = (
        len(eval_bases) * len(funded_bases) * len(buffer_fulls) * len(buffer_floors) * len(shrinks)
    )
    st.caption(f"Search size: {n_cells} sizing combos × {n_sims} sims = {n_cells * n_sims:,} pipelines")

    if not st.button("Run optimizer", type="primary"):
        st.info("Configure the grid and click **Run optimizer**.")
        return

    raw_df = run_optimizer_search(
        firm,
        win_rate,
        rr_ratio,
        eval_bases,
        funded_bases,
        buffer_fulls,
        buffer_floors,
        shrinks,
        n_sims,
        topstep_payout_path,
        topstep_use_daily_loss_limit,
        topstep_max_back2funded_reactivations,
    )
    if firm == "LucidFlex 50K":
        fee_delta = STANDARD_LUCID_EVAL_FEE - eval_fee
        raw_df["mean_ev"] = raw_df["mean_ev"] + fee_delta
        raw_df["median_ev"] = raw_df["median_ev"] + fee_delta
    df = raw_df.sort_values("mean_ev", ascending=False).reset_index(drop=True)

    best = df.iloc[0]
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Best Mean EV", money(best["mean_ev"]))
    col2.metric("Eval Pass", pct(best["eval_pass"]))
    col3.metric("Funded Breach After Pass", pct(best["funded_breach_cond"]))
    col4.metric("Max Payouts Reached", pct(best["max_payout"]))

    st.caption(
        f"Best params: eval_base=${best['eval_base']:.0f} | funded_base=${best['funded_base']:.0f} | "
        f"buffer_full_frac={best['buffer_full_frac']:.2f} | buffer_floor={best['buffer_floor']:.2f} | "
        f"post_payout_shrink={best['post_payout_shrink']:.2f} | EV stderr ±${best['ev_stderr']:.0f}"
    )

    st.dataframe(
        df.head(20).style.format(
            {
                "eval_base": "${:,.0f}",
                "funded_base": "${:,.0f}",
                "buffer_full_frac": "{:.2f}",
                "buffer_floor": "{:.2f}",
                "post_payout_shrink": "{:.2f}",
                "topstep_dll": "{}",
                "topstep_back2funded": "{:.0f}",
                "eval_pass": "{:.1%}",
                "funded_breach_cond": "{:.1%}",
                "max_payout": "{:.1%}",
                "mean_ev": "${:,.0f}",
                "median_ev": "${:,.0f}",
                "ev_stderr": "${:,.0f}",
            }
        ),
        width="stretch",
        hide_index=True,
    )


def render_runbook() -> None:
    st.subheader("Runbook")
    st.markdown(
        """
        **Active data contract**

        - Instruments: NQ and ES
        - Feed: Rithmic preferred
        - Platform: Quantower, R|Trader Pro, Sierra Chart, ATAS, Jigsaw, Bookmap, or equivalent
        - Streams: trades/tape plus Level 2 depth
        - Depth: top 10 levels minimum; MBO if available
        - Timestamps: millisecond precision preferred
        - First output: reproducible capture file plus a small summary CSV under `Research/OrderFlowL2/`
        """
    )


def main() -> None:
    style_app()

    rules = LucidFlex50K()
    st.sidebar.title("Probability Lab")
    summary_path = st.sidebar.text_input("L2 summary CSV", value="")
    firm = st.sidebar.selectbox("Ruleset", ["LucidFlex 50K", "TopStep 50K NoFee"], index=0)
    mode = st.sidebar.segmented_control("Mode", ["Research", "Replay", "Optimize"], default="Research")
    pricing_mode = st.sidebar.selectbox(
        "LucidFlex pricing",
        ["Normal 30% coupon", "Vault 40%", "Vault 50%", "Custom realized"],
        index=0,
    )
    accounts_used = st.sidebar.number_input(
        "Vault accounts used",
        min_value=0,
        max_value=rules.vault_discount_account_count,
        value=0,
        step=1,
    )
    discount_by_mode = {
        "Normal 30% coupon": None,
        "Vault 40%": 0.40,
        "Vault 50%": 0.50,
    }
    if pricing_mode == "Custom realized":
        realized_discount = st.sidebar.slider("Realized discount", 0.0, 0.75, 0.40, 0.01)
    else:
        realized_discount = discount_by_mode[pricing_mode]
    current_eval_fee = rules.eval_fee_for_vault_account(
        accounts_used_in_cycle=int(accounts_used),
        realized_discount=realized_discount,
    )
    st.sidebar.metric("Current eval fee", money(current_eval_fee))
    st.sidebar.caption(f"{firm} | {mode}")

    l2_summary = load_l2_summary(summary_path.strip() or None)

    st.title("Prop Firm Probability Lab")
    st.caption("Research shell for thesis evidence, L2 feature stability, and prop-firm outcome translation.")

    tab_engine, tab_strategies, tab_probability, tab_sizing, tab_l2, tab_runbook = st.tabs(
        [
            "Engine Overview",
            "Archived TV/Pine",
            "Probability",
            "Sizing Lab",
            "L2 Workbench",
            "Runbook",
        ]
    )

    with tab_engine:
        render_engine_overview()

    with tab_strategies:
        render_tv_strategies_tab()

    with tab_l2:
        render_l2_tab(l2_summary)

    with tab_probability:
        render_probability_tab(firm, current_eval_fee)

    with tab_sizing:
        render_sizing_lab(firm, current_eval_fee)

    with tab_runbook:
        render_runbook()


if __name__ == "__main__":
    main()
