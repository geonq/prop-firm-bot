from __future__ import annotations

from datetime import date

import pandas as pd

from Analysis.scripts.orb_nq_multiyear_70_30 import chronological_folds, load_databento_csv


def test_chronological_folds_are_contiguous_and_cover_input_once():
    dates = [date(2024, 1, day) for day in range(1, 13)]
    folds = chronological_folds(dates, 4)
    flattened = [d for fold in folds for d in fold]
    assert flattened == dates
    assert [len(fold) for fold in folds] == [3, 3, 3, 3]
    assert all(left[-1] < right[0] for left, right in zip(folds, folds[1:]))


def test_load_databento_csv_parses_utc_and_converts_to_new_york(tmp_path):
    path = tmp_path / "nq.csv"
    pd.DataFrame(
        {
            "ts_event": ["2024-01-02 14:30:00+00:00", "2024-01-02 14:35:00+00:00"],
            "open": [17000.0, 17001.0],
            "high": [17002.0, 17003.0],
            "low": [16999.0, 17000.0],
            "close": [17001.0, 17002.0],
            "volume": [100, 110],
        }
    ).to_csv(path, index=False)

    bars = load_databento_csv(path)

    assert str(bars.index.tz) == "America/New_York"
    assert bars.index[0].hour == 9
    assert bars.index[0].minute == 30
    assert list(bars.columns) == ["open", "high", "low", "close", "volume"]
