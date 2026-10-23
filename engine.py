"""Minute-bar Call research. No brokerage connection and no model API."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

import store

PARAMETERS = {"symbol": "SPY", "delta": 0.5, "premium_per_share": 2.0,
              "multiplier": 100, "decay_per_share_minute": 0.01,
              "round_trip_fee": 2.0, "return_denominator": 200.0,
              "overlapping": False, "direction": "call",
              "entry_execution": "minute_open", "exit_execution": "minute_close"}
DATA = store.ROOT / "data" / "SPY_1min_2025-01-02_2025-04-28.csv"


def validate_rule(kind, rule):
    if kind == "buy":
        if rule.get("type") in ("three_bar_drop_2", "red_rebound_1"):
            return
        if rule.get("type") == "three_bar_drop":
            return
        if rule.get("type") == "ema_pullback" and rule.get("period") in (5, 20):
            return
        if rule.get("type") == "red_count":
            window, count = rule.get("window"), rule.get("count")
            if type(window) is int and type(count) is int and 1 <= count <= window <= 390:
                return
        if rule.get("type") == "red_body" and rule.get("dollars") in (1, 1.5, 2, 3):
            return
    if kind == "buy" and rule.get("type") == "breakout":
        if rule.get("indicator") in ("vwap", "ema20") and rule.get("confirmation") in ("close", "body"):
            return
    if kind == "sell":
        if rule.get("type") == "option_bracket_10":
            return
        if rule.get("type") == "entry_gain" and rule.get("minutes") in (1, 3):
            return
        if rule.get("type") == "option_target_10":
            return
        if rule.get("type") == "two_green":
            return
        if rule.get("type") == "fixed" and type(rule.get("minutes")) is int and 1 <= rule["minutes"] <= 390:
            return
    raise ValueError("规则尚未实现，请让 Codex 实现该 description 后再运行。")


def load_data(path=DATA):
    bars = pd.read_csv(path)
    bars.index = pd.to_datetime(bars.pop("ts_event"), utc=True).dt.tz_convert("America/New_York")
    if bars.index.has_duplicates or not bars.index.is_monotonic_increasing:
        raise ValueError("行情时间重复或未排序。")
    if set(bars.symbol.unique()) != {"SPY"}:
        raise ValueError("第一版仅支持 SPY。")
    bars = bars.between_time("09:30", "15:59").copy()
    if bars.empty or (bars.index.dayofweek >= 5).any():
        raise ValueError("常规交易时段数据不合法。")
    cols = ["open", "high", "low", "close", "volume"]
    if not np.isfinite(bars[cols]).all().all() or (bars.volume < 0).any():
        raise ValueError("行情包含非法数值。")
    if ((bars.low > bars[["open", "close"]].min(axis=1)) |
        (bars.high < bars[["open", "close"]].max(axis=1)) |
        (bars.low <= 0)).any():
        raise ValueError("行情 OHLC 不合法。")
    # This dataset contains complete, full-length sessions only. Reject gaps;
    # never call the last available bar a market close when minutes are missing.
    for date, day in bars.groupby(bars.index.date):
        expected = pd.date_range(f"{date} 09:30", periods=390, freq="min", tz="America/New_York")
        if not day.index.equals(expected):
            raise ValueError(f"{date} 行情不完整；请补齐来源数据后再回测。")
    typical = (bars.high + bars.low + bars.close) / 3
    groups = bars.index.date
    bars["vwap"] = (typical * bars.volume).groupby(groups).cumsum() / bars.volume.groupby(groups).cumsum().replace(0, np.nan)
    # EMA carries across regular sessions; overnight/premarket bars are excluded.
    bars["ema20"] = bars.close.ewm(span=20, adjust=False, min_periods=20).mean()
    bars["ema5"] = bars.close.ewm(span=5, adjust=False, min_periods=5).mean()
    metadata = json.loads((store.ROOT / "data/source.json").read_text())
    actual_hash = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    if actual_hash != metadata["sha256"]:
        raise ValueError("行情文件与来源记录的 SHA256 不一致。")
    metadata.update(local_file=Path(path).name, actual_sha256=actual_hash,
                    regular_rows=len(bars), start=str(bars.index[0]), end=str(bars.index[-1]))
    return bars, metadata


def entry_signals(day, rule):
    validate_rule("buy", rule)
    if rule["type"] == "three_bar_drop_2":
        signal = day.open.shift(2) - day.close > 2.0
        return signal.shift(1, fill_value=False).to_numpy()
    if rule["type"] == "red_rebound_1":
        dropped = (day.open - day.close > 1.0).shift(1, fill_value=False)
        signal = dropped & (day.close > day.open) & (day.close > day.close.shift(1))
        return signal.shift(1, fill_value=False).to_numpy()
    if rule["type"] == "three_bar_drop":
        signal = day.open.shift(2) - day.close > 3.0
        return signal.shift(1, fill_value=False).to_numpy()
    if rule["type"] == "ema_pullback":
        line = day[f"ema{rule['period']}"]
        prior_above = (day.close > line).shift(1).rolling(5).sum() == 5
        # Tiny tolerance only for binary floating-point representation of $0.10.
        near = (day.close - line).abs() <= 0.10 + 1e-10
        signal = prior_above & (day.close < day.open) & near
        return signal.shift(1, fill_value=False).to_numpy()
    if rule["type"] == "red_count":
        # Count completed candles only; every qualifying rolling window is a
        # signal, with overlapping positions filtered by the execution loop.
        signal = (day.close < day.open).rolling(rule["window"]).sum() >= rule["count"]
        return signal.shift(1, fill_value=False).to_numpy()
    if rule["type"] == "red_body":
        signal = day.open - day.close > rule["dollars"]
        return signal.shift(1, fill_value=False).to_numpy()
    line = day[rule["indicator"]]
    # Conditions are evaluated only after the bar closes. Comparing its open
    # and close against its completed line does not advance the entry time.
    a = day.open < line
    b = day.close.shift(1) < line.shift(1)
    first = (a | b) & (day.close > line)
    confirmation = day.close > line
    if rule["confirmation"] == "body":
        confirmation &= day.open > line
    return (first.shift(2, fill_value=False) & confirmation.shift(1, fill_value=False)).to_numpy()


def exit_trade(day, entry, rule):
    validate_rule("sell", rule)
    last = len(day) - 1
    if rule["type"] == "entry_gain":
        target = entry + rule["minutes"] - 1
        if target <= last and day.close.iloc[target] - day.open.iloc[entry] > 0.25:
            return target, float(day.close.iloc[target]), day.index[target] + pd.Timedelta(minutes=1), "entry_gain"
        return last, float(day.close.iloc[last]), day.index[last] + pd.Timedelta(minutes=1), "session_close"
    if rule["type"] in ("option_target_10", "option_bracket_10"):
        limit = min(entry + 9, last)
        for i in range(entry, limit + 1):
            quote, _, _ = calculate_trade(float(day.open.iloc[entry]), float(day.close.iloc[i]), i - entry + 1)
            if quote > 2.50 + 1e-10:
                return i, float(day.close.iloc[i]), day.index[i] + pd.Timedelta(minutes=1), "option_target"
            if rule["type"] == "option_bracket_10" and quote <= 1.70 + 1e-10:
                return i, float(day.close.iloc[i]), day.index[i] + pd.Timedelta(minutes=1), "option_stop"
        reason = "timeout_10" if entry + 9 <= last else "session_close"
        return limit, float(day.close.iloc[limit]), day.index[limit] + pd.Timedelta(minutes=1), reason
    if rule["type"] == "fixed":
        target = entry + rule["minutes"] - 1
        index = min(target, last)
        reason = "fixed" if target <= last else "session_close"
        return index, float(day.close.iloc[index]), day.index[index] + pd.Timedelta(minutes=1), reason
    streak = 0
    for i in range(entry, len(day)):
        streak = streak + 1 if day.close.iloc[i] > day.open.iloc[i] else 0
        if streak >= 2:
            return i, float(day.close.iloc[i]), day.index[i] + pd.Timedelta(minutes=1), "two_green"
    return last, float(day.close.iloc[last]), day.index[last] + pd.Timedelta(minutes=1), "session_close"


def calculate_trade(entry_price, exit_price, minutes):
    option_exit = max(0.0, 2.0 + 0.5 * (exit_price - entry_price) - 0.01 * minutes)
    net = (option_exit - 2.0) * 100 - 2.0
    return option_exit, net, net / 200.0


def backtest(bars, buy, sells):
    validate_rule("buy", buy["implementation"])
    summaries, trades = [], []
    for sell in sells:
        rule = sell["implementation"]
        validate_rule("sell", rule)
        sample = []
        for _, day in bars.groupby(bars.index.date):
            busy_until = -1
            for entry in np.flatnonzero(entry_signals(day, buy["implementation"])):
                if entry <= busy_until:
                    continue
                index, price, exit_time, reason = exit_trade(day, entry, rule)
                busy_until = index
                entry_time = day.index[entry]
                minutes = (exit_time - entry_time).total_seconds() / 60
                entry_price = float(day.open.iloc[entry])
                option_exit, net, ret = calculate_trade(entry_price, price, minutes)
                sample.append(dict(sell_id=sell["id"], entry_time=entry_time.isoformat(),
                                   exit_time=exit_time.isoformat(), entry_price=entry_price,
                                   exit_price=price, minutes=minutes, exit_reason=reason,
                                   option_exit=option_exit, net_profit=net, net_return=ret))
        trades.extend(sample)
        summaries.append(dict(sell_id=sell["id"], name=sell["name"], version=sell["version"],
                              trades=len(sample), mean_return=float(np.mean([t["net_return"] for t in sample])) if sample else None,
                              win_rate=sum(t["net_profit"] > 0 for t in sample) / len(sample) if sample else None))
    return summaries, trades


def run_pending():
    store.initialize()
    # Serialize edits and processing, so an old computation cannot mark a new
    # description realized. SQLite commits before JSON marks successful work.
    with store.locked():
        items = store._read()
        sells = [x for x in items if x["kind"] == "sell"]
        buys = [x for x in items if x["kind"] == "buy" and not x["realize"]]
        if not buys:
            return {"completed": [], "errors": []}
        if not sells or any(not store.ready(x) for x in sells):
            return {"completed": [], "errors": ["有卖出方法尚未实现，请先让 Codex 实现，再回测。"]}
        bars, source = load_data()
        completed, errors = [], []
        code = {name: (store.ROOT / name).read_text() for name in ("engine.py", "store.py")}
        for buy in buys:
            try:
                if not store.ready(buy):
                    raise ValueError("description 尚未实现，请让 Codex 读取并实现。")
                summary, trades = backtest(bars, buy, sells)
                snapshot = {"buy": buy.copy(), "sells": sells, "code": code}
                values = (store.now(), buy["id"], store.signature(buy, sells),
                          json.dumps(snapshot, ensure_ascii=False), json.dumps(source, ensure_ascii=False),
                          json.dumps(PARAMETERS), store.digest(code), json.dumps(summary, ensure_ascii=False), json.dumps(trades))
                with store.connect() as db:
                    db.execute("INSERT INTO runs (created_at, idea_id, signature, snapshot, source, parameters, engine_hash, summary, trades) VALUES (?,?,?,?,?,?,?,?,?)", values)
                buy["realize"] = True
                buy.pop("error", None)
                buy["updated_at"] = store.now()
                completed.append(buy["name"])
            except (ValueError, KeyError) as exc:
                buy["error"] = str(exc)
                errors.append(f"{buy['name']}：{exc}")
        if completed:
            for sell in sells:
                sell["realize"] = True
        store._write(items)
        return {"completed": completed, "errors": errors}
