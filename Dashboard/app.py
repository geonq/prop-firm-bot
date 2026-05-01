from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


st.set_page_config(
    page_title="Prop Firm Probability Lab",
    page_icon="PF",
    layout="wide",
    initial_sidebar_state="expanded",
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SUMMARY_PATHS = (
    ROOT / "Analysis/output/mbp10_batch/summary.csv",
    ROOT / "Analysis/output/mbp10_batch_smoke/summary.csv",
)


PHASE_RISK_ROWS = [
    {
        "profile": "50% WR / 1.25R",
        "win_rate": 0.50,
        "rr": 1.25,
        "eval_risk": 300,
        "funded_risk": 125,
        "eval_pass": 0.5180,
        "funded_breach_all": 0.4124,
        "funded_breach_cond": 0.7961,
        "max_payout": 0.0566,
        "avg_payouts": 0.99,
        "avg_paid": 482,
        "mean_ev": 307,
        "median_ev": -175,
        "tier": "Candidate",
    },
    {
        "profile": "50% WR / 1.25R",
        "win_rate": 0.50,
        "rr": 1.25,
        "eval_risk": 250,
        "funded_risk": 125,
        "eval_pass": 0.4968,
        "funded_breach_all": 0.3900,
        "funded_breach_cond": 0.7850,
        "max_payout": 0.0582,
        "avg_payouts": 0.98,
        "avg_paid": 474,
        "mean_ev": 299,
        "median_ev": -175,
        "tier": "Candidate",
    },
    {
        "profile": "45% WR / 1.50R",
        "win_rate": 0.45,
        "rr": 1.50,
        "eval_risk": 250,
        "funded_risk": 125,
        "eval_pass": 0.4886,
        "funded_breach_all": 0.4134,
        "funded_breach_cond": 0.8461,
        "max_payout": 0.0458,
        "avg_payouts": 0.89,
        "avg_paid": 444,
        "mean_ev": 269,
        "median_ev": -175,
        "tier": "Candidate",
    },
    {
        "profile": "45% WR / 1.50R",
        "win_rate": 0.45,
        "rr": 1.50,
        "eval_risk": 300,
        "funded_risk": 125,
        "eval_pass": 0.4858,
        "funded_breach_all": 0.4060,
        "funded_breach_cond": 0.8357,
        "max_payout": 0.0460,
        "avg_payouts": 0.89,
        "avg_paid": 442,
        "mean_ev": 267,
        "median_ev": -175,
        "tier": "Candidate",
    },
    {
        "profile": "50% WR / 1.25R",
        "win_rate": 0.50,
        "rr": 1.25,
        "eval_risk": 300,
        "funded_risk": 300,
        "eval_pass": 0.5214,
        "funded_breach_all": 0.4710,
        "funded_breach_cond": 0.9033,
        "max_payout": 0.0504,
        "avg_payouts": 0.86,
        "avg_paid": 573,
        "mean_ev": 398,
        "median_ev": -175,
        "tier": "Aggressive",
    },
    {
        "profile": "45% WR / 1.50R",
        "win_rate": 0.45,
        "rr": 1.50,
        "eval_risk": 250,
        "funded_risk": 300,
        "eval_pass": 0.4878,
        "funded_breach_all": 0.4466,
        "funded_breach_cond": 0.9155,
        "max_payout": 0.0412,
        "avg_payouts": 0.74,
        "avg_paid": 548,
        "mean_ev": 373,
        "median_ev": -175,
        "tier": "Aggressive",
    },
    {
        "profile": "50% WR / 1.25R",
        "win_rate": 0.50,
        "rr": 1.25,
        "eval_risk": 200,
        "funded_risk": 125,
        "eval_pass": 0.3866,
        "funded_breach_all": 0.3114,
        "funded_breach_cond": 0.8055,
        "max_payout": 0.0410,
        "avg_payouts": 0.73,
        "avg_paid": 356,
        "mean_ev": 181,
        "median_ev": -175,
        "tier": "Lower risk",
    },
]


THESIS_ROWS = [
    {
        "thesis": "Depth-normalized L2 pressure",
        "status": "visualized",
        "data": "Databento GLBX.MDP3 MBP-10",
        "variables": "L1/L3/L5/L10 imbalance, rolling depth pressure, spread",
        "falsifier": "No stable forward-return relation after spread/slippage across sessions.",
        "priority": 1,
    },
    {
        "thesis": "Realized-standard-deviation normalization",
        "status": "mapped",
        "data": "NQ/MNQ intraday returns",
        "variables": "Rolling realized std, return/std units, target-before-breach paths",
        "falsifier": "Vol-normalized outcomes do not reduce path variance or breach clustering.",
        "priority": 2,
    },
    {
        "thesis": "IV/RV regime filter",
        "status": "mapped",
        "data": "Official IV proxy or derived options surface",
        "variables": "IV-RV spread, forward realized vol, prop-firm outcome split",
        "falsifier": "Regime buckets do not change forward distribution or payout odds.",
        "priority": 3,
    },
    {
        "thesis": "Options-flow pressure into NQ",
        "status": "blocked",
        "data": "Paid OPRA/ThetaData-style trade+NBBO",
        "variables": "Put/call imbalance, premium pressure, delta pressure",
        "falsifier": "Aggressor inference unavailable or signal appears only after NQ moves.",
        "priority": 4,
    },
    {
        "thesis": "VWAP context",
        "status": "mapped",
        "data": "NQ/MNQ intraday bars or tick-derived bars",
        "variables": "Session VWAP distance, slope, volume participation",
        "falsifier": "No incremental value after L2/vol state controls.",
        "priority": 5,
    },
]


def pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def money(value: float) -> str:
    sign = "-" if value < 0 else ""
    return f"{sign}${abs(value):,.0f}"


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
        .pf-badge.visualized { color: var(--pf-green); border-color: rgba(52, 211, 153, .55); }
        .pf-badge.mapped { color: var(--pf-cyan); border-color: rgba(34, 211, 238, .55); }
        .pf-badge.blocked { color: var(--pf-amber); border-color: rgba(251, 191, 36, .55); }
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
    fig = px.scatter(
        df,
        x="eval_pass",
        y="funded_breach_cond",
        size="mean_ev",
        color="tier",
        hover_data=["profile", "eval_risk", "funded_risk", "max_payout", "median_ev"],
        labels={
            "eval_pass": "Eval pass probability",
            "funded_breach_cond": "Funded breach after pass",
            "tier": "Risk band",
        },
        color_discrete_map={
            "Candidate": "#34d399",
            "Aggressive": "#fb7185",
            "Lower risk": "#22d3ee",
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
            {"Candidate": "#34d399", "Aggressive": "#fb7185", "Lower risk": "#22d3ee"}
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


def render_thesis_cards() -> None:
    df = pd.DataFrame(THESIS_ROWS).sort_values("priority")
    cols = st.columns(3)
    for idx, row in enumerate(df.to_dict("records")):
        with cols[idx % 3]:
            st.markdown(
                f"""
                <div class="pf-card">
                  <span class="pf-badge {row["status"]}">{row["status"]}</span>
                  <h3>{row["thesis"]}</h3>
                  <p><b>Data:</b> {row["data"]}</p>
                  <p><b>Variables:</b> {row["variables"]}</p>
                  <p><b>Falsifier:</b> {row["falsifier"]}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )


def render_l2_tab(summary_df: pd.DataFrame) -> None:
    st.subheader("L2 Evidence")
    if summary_df.empty:
        st.markdown(
            '<div class="pf-note">No batch summary found yet. Run the MBP-10 batch report after downloads finish.</div>',
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
            st.plotly_chart(fig, width="stretch")
        else:
            st.markdown(
                '<div class="pf-note">Correlation columns will appear after full batch report output is available.</div>',
                unsafe_allow_html=True,
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


def render_probability_tab(phase_df: pd.DataFrame) -> None:
    st.subheader("Prop-Firm Probability")
    candidates = phase_df[phase_df["tier"] == "Candidate"]
    best = candidates.sort_values("mean_ev", ascending=False).iloc[0]

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Candidate Eval Pass", pct(best["eval_pass"]))
    col2.metric("Funded Breach After Pass", pct(best["funded_breach_cond"]))
    col3.metric("Mean EV", money(best["mean_ev"]))
    col4.metric("Median EV", money(best["median_ev"]))

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
                "median_ev",
            ]
        ].style.format(
            {
                "eval_pass": "{:.1%}",
                "funded_breach_cond": "{:.1%}",
                "max_payout": "{:.1%}",
                "mean_ev": "${:,.0f}",
                "median_ev": "${:,.0f}",
            }
        ),
        width="stretch",
        hide_index=True,
    )

    st.markdown(
        '<div class="pf-note">These are synthetic LucidFlex phase-risk results, not a validated strategy. '
        "They show candidate risk geometry while the L2 signal research is still unresolved.</div>",
        unsafe_allow_html=True,
    )


def render_runbook() -> None:
    st.subheader("Runbook")
    st.code(
        ".venv/bin/python Analysis/scripts/databento_mbp10_sample.py --download-job JOB_ID\n"
        ".venv/bin/python Analysis/scripts/databento_mbp10_batch_report.py "
        "TVExports/l2_sample --symbol MNQM6 --output-dir Analysis/output/mbp10_batch --overwrite",
        language="zsh",
    )
    st.markdown(
        """
        **Pending Databento Jobs**

        - `GLBX-20260501-9MYYFW877G`
        - `GLBX-20260501-C53EPEATLB`
        - `GLBX-20260501-N7KU43ME5X`
        - `GLBX-20260501-BCRJXJXW8J`
        - `GLBX-20260501-A7RU7JT4M5`
        """
    )


def main() -> None:
    style_app()

    st.sidebar.title("Probability Lab")
    summary_path = st.sidebar.text_input("L2 summary CSV", value="")
    firm = st.sidebar.selectbox("Ruleset", ["LucidFlex 50K", "TopStep 50K NoFee"], index=0)
    mode = st.sidebar.segmented_control("Mode", ["Research", "Replay", "Optimize"], default="Research")
    st.sidebar.caption(f"{firm} | {mode}")

    l2_summary = load_l2_summary(summary_path.strip() or None)
    phase_df = pd.DataFrame(PHASE_RISK_ROWS)

    st.title("Prop Firm Probability Lab")
    st.caption("Research shell for thesis evidence, L2 feature stability, and prop-firm outcome translation.")

    tab_evidence, tab_l2, tab_probability, tab_runbook = st.tabs(
        ["Evidence Board", "L2 Workbench", "Probability", "Runbook"]
    )

    with tab_evidence:
        render_thesis_cards()

    with tab_l2:
        render_l2_tab(l2_summary)

    with tab_probability:
        render_probability_tab(phase_df)

    with tab_runbook:
        render_runbook()


if __name__ == "__main__":
    main()
