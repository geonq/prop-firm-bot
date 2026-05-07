from src.optimizer.search import search_adaptive_grid
from src.pipeline.lucidflex_pipeline import simulate_lucidflex_pipeline
from src.rules.topstep import TopStepPayoutPath
from src.sizing.dynamic import FixedSizing, SizingContext
from src.strategies.parametric import StateAwareBernoulliStrategy


class TestStateAwarePipeline:
    def test_state_aware_strategy_runs_through_pipeline(self):
        strategy = StateAwareBernoulliStrategy(
            win_rate=0.55,
            rr_ratio=1.0,
            sizing_fn=FixedSizing(eval_size=200.0, funded_size=125.0),
        )
        result = simulate_lucidflex_pipeline(strategy, seed=42, max_eval_days=20, max_funded_days=20)
        assert result.eval_days >= 1
        assert isinstance(result.eval_passed, bool)
        assert result.terminal_reason in {
            "eval_breach",
            "eval_timeout",
            "max_payouts",
            "funded_breach",
            "funded_timeout",
        }

    def test_sizer_receives_live_buffer(self):
        # Sizer logs the buffer it sees on each call; trade history confirms
        # the simulator passes evolving account state, not stale snapshots.
        seen_buffers: list[float] = []

        class RecordingSizer:
            def __call__(self, ctx: SizingContext) -> float:
                seen_buffers.append(ctx.buffer)
                return 50.0

        strategy = StateAwareBernoulliStrategy(
            win_rate=0.40,
            rr_ratio=1.0,
            sizing_fn=RecordingSizer(),
        )
        simulate_lucidflex_pipeline(strategy, seed=1, max_eval_days=5, max_funded_days=0)
        assert len(seen_buffers) >= 2
        # Buffer should differ across trades (at minimum start vs after first trade).
        assert len(set(seen_buffers)) > 1


class TestOptimizer:
    def test_returns_rows_sorted_by_mean_ev(self):
        rows = search_adaptive_grid(
            win_rate=0.50,
            rr_ratio=1.25,
            eval_bases=(150.0, 250.0),
            funded_bases=(125.0,),
            n_sims=80,
        )
        assert len(rows) == 2
        assert rows[0].mean_net_ev >= rows[1].mean_net_ev

    def test_records_correct_param_set(self):
        rows = search_adaptive_grid(
            win_rate=0.55,
            rr_ratio=1.0,
            eval_bases=(200.0,),
            funded_bases=(125.0, 200.0),
            buffer_full_fracs=(0.04,),
            buffer_floors=(0.25, 0.5),
            n_sims=50,
        )
        assert len(rows) == 4  # 1 * 2 * 1 * 2 * 1
        for row in rows:
            assert row.win_rate == 0.55
            assert row.rr_ratio == 1.0
            assert row.eval_base == 200.0
            assert row.funded_base in (125.0, 200.0)
            assert row.buffer_floor in (0.25, 0.5)
            assert row.n_sims == 50

    def test_ev_stderr_shrinks_with_more_sims(self):
        few = search_adaptive_grid(
            win_rate=0.50, rr_ratio=1.25, eval_bases=(200.0,), funded_bases=(125.0,), n_sims=50,
        )[0]
        many = search_adaptive_grid(
            win_rate=0.50, rr_ratio=1.25, eval_bases=(200.0,), funded_bases=(125.0,), n_sims=400,
        )[0]
        assert many.ev_stderr < few.ev_stderr

    def test_topstep_optimizer_records_payout_path_and_dll(self):
        rows = search_adaptive_grid(
            firm="topstep",
            win_rate=1.0,
            rr_ratio=1.0,
            eval_bases=(1_500.0,),
            funded_bases=(200.0,),
            n_sims=10,
            max_eval_days=10,
            max_funded_days=30,
            topstep_payout_path=TopStepPayoutPath.CONSISTENCY,
            topstep_use_daily_loss_limit=True,
            topstep_max_back2funded_reactivations=1,
            payout_cap=2,
        )

        assert len(rows) == 1
        row = rows[0]
        assert row.firm == "topstep"
        assert row.topstep_payout_path == TopStepPayoutPath.CONSISTENCY
        assert row.topstep_use_daily_loss_limit is True
        assert row.topstep_max_back2funded_reactivations == 1
        assert row.eval_pass_rate == 1.0
