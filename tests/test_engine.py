import copy

import numpy as np
import pandas as pd
import pytest

import engine
import store


def day(opens, closes):
    frame = pd.DataFrame({"open": opens, "close": closes},
                         index=pd.date_range("2025-01-02 09:30", periods=len(opens), freq="min", tz="America/New_York"))
    frame["vwap"] = 100.0
    frame["ema20"] = 100.0
    return frame


RULE = {"type": "breakout", "indicator": "vwap", "confirmation": "close"}


@pytest.mark.parametrize("opens,closes", [
    ([101, 99, 101, 102], [101, 101, 101, 102]),  # A only
    ([99, 101, 101, 102], [99, 101, 101, 102]),  # B, gap up
])
def test_a_or_b_enters_third_candle(opens, closes):
    assert engine.entry_signals(day(opens, closes), RULE).tolist() == [False, False, False, True]


def test_continuously_above_is_not_a_breakout():
    assert not engine.entry_signals(day([101] * 6, [102] * 6), RULE).any()


def test_confirmation_body_and_failed_close():
    bars = day([99, 99, 99, 101], [99, 101, 101, 102])
    assert engine.entry_signals(bars, RULE)[3]
    assert not engine.entry_signals(bars, {**RULE, "confirmation": "body"})[3]
    bars.iloc[2, bars.columns.get_loc("close")] = 99
    assert not engine.entry_signals(bars, RULE)[3]


def test_signal_uses_only_completed_bars():
    bars = day([99, 99, 101, 102], [99, 101, 102, 103])
    before = engine.entry_signals(bars, RULE)
    bars.iloc[3, :] = 500
    assert np.array_equal(before, engine.entry_signals(bars, RULE))


def test_two_green_counts_entry_resets_on_red_and_exits_at_close():
    bars = day([100, 101, 100, 101, 105], [101, 100, 101, 102, 106])
    index, price, time, reason = engine.exit_trade(bars, 0, {"type": "two_green"})
    assert (index, price, reason) == (3, 102, "two_green")
    assert time == bars.index[4]
    result = engine.exit_trade(bars.iloc[:4], 0, {"type": "two_green"})
    assert result[3] == "two_green"
    assert result[2] == bars.index[3] + pd.Timedelta(minutes=1)


def test_fixed_horizon_and_close_cap():
    bars = day([100] * 5, [101] * 5)
    assert engine.exit_trade(bars, 0, {"type": "fixed", "minutes": 1})[2] == bars.index[1]
    result = engine.exit_trade(bars, 3, {"type": "fixed", "minutes": 30})
    assert result[3] == "session_close"
    assert (result[2] - bars.index[3]).total_seconds() == 120


def test_profit_decay_fee_and_floor():
    option, profit, ret = engine.calculate_trade(100, 101, 10)
    assert option == pytest.approx(2.4)
    assert profit == pytest.approx(38)
    assert ret == pytest.approx(.19)
    assert engine.calculate_trade(100, 100, 5)[1] == pytest.approx(-7)
    assert engine.calculate_trade(100, 80, 30) == (0, -202, -1.01)


def test_positions_never_overlap():
    bars = day([99, 99, 101, 99, 99, 101, 99, 99, 101, 102],
               [99, 101, 101, 99, 101, 101, 99, 101, 101, 102])
    buy = {"implementation": RULE}
    sell = {"id": "exit", "name": "exit", "version": 1, "implementation": {"type": "fixed", "minutes": 5}}
    summary, trades = engine.backtest(bars, buy, [sell])
    assert summary[0]["trades"] == 2
    assert pd.Timestamp(trades[1]["entry_time"]) >= pd.Timestamp(trades[0]["exit_time"])


@pytest.fixture
def storage(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "HOME", tmp_path)
    store.initialize()
    return tmp_path


def test_edit_invalidation_and_history(storage):
    item = store.ideas()[0]
    renamed = store.save("buy", "新名字", item["description"], item["id"])
    assert store.ready(renamed)
    edited = store.save("buy", "新名字", "不同规则", item["id"])
    assert not store.ready(edited) and not edited["realize"]
    assert edited["version"] == 2
    store.register(edited["id"], RULE)
    assert store.ready(store.ideas()[0])


def test_sell_change_invalidates_all_buys(storage):
    with store.locked():
        items = store._read()
        for x in items:
            x["realize"] = True
        store._write(items)
    sell = next(x for x in items if x["kind"] == "sell")
    store.save("sell", sell["name"], "修改卖出方法", sell["id"])
    assert all(not x["realize"] for x in store.ideas() if x["kind"] == "buy")
    assert engine.run_pending()["errors"]


def test_unknown_description_never_uses_old_implementation(storage, monkeypatch):
    monkeypatch.setattr(engine, "load_data", lambda: (day([101] * 5, [102] * 5), {}))
    item = store.ideas()[0]
    store.save("buy", item["name"], "完全不同的策略", item["id"])
    result = engine.run_pending()
    assert len(result["errors"]) == 1
    assert store.latest(item["id"]) is None
    assert len(result["completed"]) == 2


def test_run_only_false_and_preserve_snapshots(storage, monkeypatch):
    monkeypatch.setattr(engine, "load_data", lambda: (day([99, 99, 101, 102], [99, 101, 102, 103]), {}))
    assert len(engine.run_pending()["completed"]) == 3
    old = store.latest("vwap_close")
    assert engine.run_pending() == {"completed": [], "errors": []}
    item = store.ideas()[0]
    store.save("buy", "改名", item["description"], item["id"], reset=True)
    assert len(engine.run_pending()["completed"]) == 1
    assert store.latest("vwap_close")["id"] > old["id"]
    with store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 4


def test_real_data_vwap_resets_ema_carries_and_dst():
    bars, source = engine.load_data()
    assert len(bars) == 30810
    assert source["actual_sha256"] == source["sha256"]
    days = list(bars.groupby(bars.index.date))
    next_day = days[1][1]
    first = next_day.iloc[0]
    assert first.vwap == pytest.approx((first.high + first.low + first.close) / 3)
    assert pd.notna(first.ema20)
    assert bars.index[0].utcoffset() != bars.index[-1].utcoffset()
    altered = bars.copy()
    altered.loc[altered.index[-10:], "close"] = 999
    assert np.array_equal(engine.entry_signals(days[0][1], RULE),
                          engine.entry_signals(altered.loc[days[0][1].index], RULE))
