import json

import numpy as np
import pandas as pd
import pytest

import engine
import store


def bars(opens, closes):
    return pd.DataFrame({'open': opens, 'close': closes},
                        index=pd.date_range('2025-01-02 09:30', periods=len(opens),
                                            freq='min', tz='America/New_York'))


@pytest.mark.parametrize('n', [8, 9])
def test_consecutive_red_enters_only_after_completed_window(n):
    frame = bars([100] * (n + 2), [99] * n + [101, 99])
    rule = dict(type='red_count', window=n, count=n)
    indices = np.flatnonzero(engine.entry_signals(frame, rule))
    assert indices.tolist() == [n]
    frame.iloc[n] = [500, 10]
    assert engine.entry_signals(frame, rule)[n]


def test_seventeen_red_requires_full_twenty_candles():
    frame = bars([100] * 22, [99] * 17 + [101] * 5)
    signal = engine.entry_signals(frame, dict(type='red_count', window=20, count=17))
    assert not signal[:20].any()
    assert signal[20] and not signal[21]


@pytest.mark.parametrize('threshold', [1, 2, 3])
def test_red_body_is_strict_and_uses_open_not_high(threshold):
    frame = bars([100] * 4, [100-threshold, 100-threshold-.01, 101, 101])
    frame['high'] = 999
    assert engine.entry_signals(frame, dict(type='red_body', dollars=threshold)).tolist() == [False, False, True, False]


def test_two_green_sells_close_even_on_final_bar():
    frame = bars([100, 101], [101, 102])
    index, price, timestamp, reason = engine.exit_trade(frame, 0, {'type': 'two_green'})
    assert (index, price, reason) == (1, 102, 'two_green')
    assert timestamp == frame.index[1] + pd.Timedelta(minutes=1)


def test_unrealized_idea_exists_in_database(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'HOME', tmp_path)
    store.initialize()
    item = store.save('buy', '新想法', '暂未实现的买入描述')
    with store.connect() as db:
        row = db.execute('SELECT * FROM ideas WHERE id=?', (item['id'],)).fetchone()
    assert row['realize'] == 0
    assert json.loads(row['document'])['description'] == item['description']
