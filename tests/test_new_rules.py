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


def test_three_bar_drop_is_net_drop_not_three_red_bodies():
    frame = bars([105, 102, 104, 99], [102, 104, 101, 100])
    assert engine.entry_signals(frame, {'type': 'three_bar_drop'}).tolist() == [False, False, False, True]
    frame.loc[frame.index[2], 'close'] = 102
    assert not engine.entry_signals(frame, {'type': 'three_bar_drop'}).any()


@pytest.mark.parametrize('period', [5, 20])
def test_pullback_prior_five_and_distance(period):
    frame = bars([101] * 7, [101] * 5 + [100.1, 102])
    frame[f'ema{period}'] = 100.0
    rule = {'type': 'ema_pullback', 'period': period}
    assert np.flatnonzero(engine.entry_signals(frame, rule)).tolist() == [6]
    frame.loc[frame.index[5], 'close'] = 100.1001
    assert not engine.entry_signals(frame, rule).any()
    frame.loc[frame.index[5], 'close'] = 99.95
    frame.loc[frame.index[2], 'close'] = 100
    assert not engine.entry_signals(frame, rule).any()


@pytest.mark.parametrize('minutes', [1, 3])
def test_entry_gain_checks_only_designated_bar(minutes):
    frame = bars([100] * 6, [100] * 6)
    frame.loc[frame.index[minutes-1], 'close'] = 100.26
    index, price, time, reason = engine.exit_trade(frame, 0, {'type': 'entry_gain', 'minutes': minutes})
    assert index == minutes-1 and price == 100.26 and reason == 'entry_gain'
    assert time == frame.index[0] + pd.Timedelta(minutes=minutes)
    frame.loc[frame.index[minutes-1], 'close'] = 100.25
    frame.loc[frame.index[4], 'close'] = 103
    assert engine.exit_trade(frame, 0, {'type': 'entry_gain', 'minutes': minutes})[3] == 'session_close'


def test_option_target_checks_close_and_decay_then_times_out():
    frame = bars([100] * 12, [100] * 12)
    frame['high'] = 200  # Intraminute highs must not trigger a close-only exit.
    frame.loc[frame.index[0], 'close'] = 101.02  # quote exactly 2.50, not above
    frame.loc[frame.index[1], 'close'] = 101.05  # quote 2.505 after two minutes
    result = engine.exit_trade(frame, 0, {'type': 'option_target_10'})
    assert result[0] == 1 and result[3] == 'option_target'
    frame['close'] = 100
    frame.loc[frame.index[10], 'close'] = 110  # Too late.
    result = engine.exit_trade(frame, 0, {'type': 'option_target_10'})
    assert result[0] == 9 and result[3] == 'timeout_10'
    assert engine.exit_trade(frame.iloc[:5], 0, {'type': 'option_target_10'})[3] == 'session_close'
