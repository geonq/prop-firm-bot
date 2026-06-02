"""Build strategy registry + MC artifacts for every TV export.

Reads ``TVExports/*.xlsx``, persists per-strategy meta + canonical ledger, and
runs TopStep 50K + LucidFlex 50K Monte Carlo on each. Writes everything under
``Analysis/output/tv_strategies/`` and ``Analysis/output/mc_runs/``.

Run:
    .venv/bin/python Analysis/scripts/build_strategy_registry.py
    .venv/bin/python Analysis/scripts/build_strategy_registry.py --skip-mc
    .venv/bin/python Analysis/scripts/build_strategy_registry.py --n 2000 --block-size 5
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.pipeline.strategy_registry import (
    DEFAULT_BLOCK_SIZE,
    DEFAULT_N_INIT,
    DEFAULT_N_MAX,
    DEFAULT_N_STEP,
    TV_EXPORTS_DIR,
    build_registry,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tv-dir", type=Path, default=TV_EXPORTS_DIR)
    parser.add_argument("--n-init", type=int, default=DEFAULT_N_INIT)
    parser.add_argument("--n-step", type=int, default=DEFAULT_N_STEP)
    parser.add_argument("--n-max", type=int, default=DEFAULT_N_MAX)
    parser.add_argument("--block-size", type=int, default=DEFAULT_BLOCK_SIZE)
    parser.add_argument("--skip-mc", action="store_true")
    parser.add_argument(
        "--only-pass",
        action="store_true",
        help="Skip MC for strategies that fail pre-MC screening",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = _build_parser().parse_args(argv)
    summary = build_registry(
        tv_dir=args.tv_dir,
        n_init=args.n_init,
        n_step=args.n_step,
        n_max=args.n_max,
        block_size=args.block_size,
        skip_mc=args.skip_mc,
        only_screened_pass=args.only_pass,
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
