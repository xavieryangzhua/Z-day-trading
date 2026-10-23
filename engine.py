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
        if rule.get("type") == "rsi14_below3":
            return
        if rule.get("type") in ("noise_breakout", "late_momentum"):
            return
        if rule.get("type") == "adx_ten_touch" and rule.get("distance") in (.05,.10):
            return
        if rule.get("type") in ("fib_shallow", "fib_confluence", "fib_extension", "bb_squeeze", "bb_reclaim", "rsi_reclaim"):
            return
        if rule.get("type") == "opening_range" and rule.get("minutes") in (5, 15):
            return
        if (rule.get("type") == "fibonacci_pullback" and rule.get("anchor") in ("window20", "day")
                and rule.get("ratio") in (.382, .4, .5, .6, .618)):
            return
        if rule.get("type") == "ema20_ten_rising_touch" and rule.get("distance") in (0.05, 0.10):
            return
        if (rule.get("type") == "ema20_rise_range_touch"
                and rule.get("rise") in (0.10, 0.20, 0.30)
                and rule.get("distance") in (0.05, 0.10)):
            return
        if rule.get("type") in ("ema20_angle_touch", "green2_touch") and rule.get("distance") in (0.05, 0.10):
            return
        if rule.get("type") == "double_red_run":
            return
        if rule.get("type") == "large_green_pullback" and rule.get("dollars") in (2, 3):
            return
        if rule.get("type") == "impulse_platform_breakout":
            return
        if rule.get("type") in ("trend_vwap", "trend_sma50", "trend_price_blocks"):
            return
        if rule.get("type") == "trend_pullback" and rule.get("period") in (5, 20):
            return
        if rule.get("type") == "trend_high10":
            return
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
    bars["sma50"] = bars.close.rolling(50, min_periods=50).mean()
    add_web_indicators(bars)
    add_regime_indicators(bars)
    metadata = json.loads((store.ROOT / "data/source.json").read_text())
    actual_hash = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    if actual_hash != metadata["sha256"]:
        raise ValueError("行情文件与来源记录的 SHA256 不一致。")
    metadata.update(local_file=Path(path).name, actual_sha256=actual_hash,
                    regular_rows=len(bars), start=str(bars.index[0]), end=str(bars.index[-1]))
    return bars, metadata


def wilder_average(values, period, first):
    out = np.full(len(values), np.nan)
    end = first+period-1
    if end < len(values):
        out[end] = np.mean(values[first:end+1])
        for i in range(end+1, len(values)):
            out[i] = (out[i-1]*(period-1)+values[i])/period
    return out


def add_regime_indicators(bars):
    up = bars.high.diff().to_numpy()
    down = (-bars.low.diff()).to_numpy()
    plus = np.where((up>down)&(up>0), up, 0)
    minus = np.where((down>up)&(down>0), down, 0)
    tr = pd.concat([bars.high-bars.low, (bars.high-bars.close.shift()).abs(),
                    (bars.low-bars.close.shift()).abs()],axis=1).max(axis=1).to_numpy()
    atr = wilder_average(tr,14,1)
    pg, mg = wilder_average(plus,14,1), wilder_average(minus,14,1)
    with np.errstate(divide="ignore",invalid="ignore"):
        pdm = np.where(atr==0,0,100*pg/atr)
        mdm = np.where(atr==0,0,100*mg/atr)
        dx = np.where(pdm+mdm==0,0,100*np.abs(pdm-mdm)/(pdm+mdm))
    bars["plus_di"],bars["minus_di"] = pdm,mdm
    bars["adx14"] = wilder_average(dx,14,14)
    dates=bars.index.date
    opening=bars.open.groupby(dates).transform('first')
    closes=bars.close.groupby(dates).last()
    previous=pd.Series(dates,index=bars.index).map(closes.shift(1))
    bars['previous_close']=previous
    movement=(bars.close/opening-1).abs()
    sigma=movement.groupby(bars.index.strftime('%H:%M')).transform(lambda x:x.shift(1).rolling(14).mean())
    bars['noise_upper']=np.maximum(opening,previous)*(1+sigma)


def regime_signals(day, rule):
    if rule['type']=='adx_ten_touch':
        entries=entry_signals(day,{'type':'ema20_ten_rising_touch','distance':rule['distance']})
        filter_=(day.adx14>25)&(day.plus_di>day.minus_di)
        return entries & filter_.shift(1,fill_value=False).to_numpy()
    signals=np.zeros(len(day),dtype=bool)
    if rule['type']=='late_momentum':
        morning=np.flatnonzero(day.index.strftime('%H:%M')=='09:59')
        entry=np.flatnonzero(day.index.strftime('%H:%M')=='15:30')
        if len(morning) and len(entry) and day.close.iloc[morning[0]]>day.previous_close.iloc[morning[0]]:
            signals[entry[0]]=True
        return signals
    for t in range(len(day)-1):
        # Bars timestamped by open: 09:59 closes at the 10:00 checkpoint.
        hm=day.index[t].strftime('%H:%M')
        if hm>='09:59' and hm<='15:29' and day.index[t].minute in (29,59):
            if day.close.iloc[t]>day.noise_upper.iloc[t] and day.close.iloc[t]>day.vwap.iloc[t]:
                signals[t+1]=True
    return signals


def add_web_indicators(bars):
    close = bars.close
    mean = close.rolling(20).mean()
    std = close.rolling(20).std(ddof=0)
    bars["bb_upper"], bars["bb_lower"] = mean+2*std, mean-2*std
    bars["bb_width"] = 4*std/mean
    bars["bb_cutoff"] = bars.bb_width.shift(2).rolling(60).quantile(.2, interpolation="linear")
    bars["bb_prev_width"] = bars.bb_width.shift(1)
    changes = close.diff().to_numpy()
    rsi = np.full(len(bars), np.nan)
    if len(bars) >= 15:
        gain = np.maximum(changes[1:15], 0).mean()
        loss = np.maximum(-changes[1:15], 0).mean()
        for t in range(14, len(bars)):
            if t > 14:
                gain = (13*gain+max(changes[t], 0))/14
                loss = (13*loss+max(-changes[t], 0))/14
            rsi[t] = 100-100/(1+gain/loss) if loss > 0 else (100 if gain > 0 else 50)
    bars["rsi14"] = rsi


def web_entry_signals(day, rule):
    kind = rule["type"]
    signals = np.zeros(len(day), dtype=bool)
    if kind == "opening_range":
        n = rule["minutes"]
        if len(day) < n or day.index[0].strftime("%H:%M") != "09:30":
            return signals
        if not day.index[:n].equals(pd.date_range(day.index[0], periods=n, freq="min")):
            return signals
        high = day.high.iloc[:n].max()
        for t in range(n, len(day)-1):
            if day.index[t].strftime("%H:%M") >= "11:00":
                break
            if day.close.iloc[t] > high and day.close.iloc[t-1] <= high:
                signals[t+1] = True
                break
        return signals
    if kind == "bb_squeeze":
        signal = (day.bb_prev_width <= day.bb_cutoff) & (day.bb_width > day.bb_prev_width)
        signal &= (day.close > day.bb_upper) & (day.close.shift(1) <= day.bb_upper.shift(1))
        signal &= day.close > day.high.shift(1).rolling(10).max()
        return signal.shift(1, fill_value=False).to_numpy()
    if kind == "bb_reclaim":
        signal = (day.close.shift(1) < day.bb_lower.shift(1)) & (day.close > day.bb_lower) & (day.close > day.open)
        return signal.shift(1, fill_value=False).to_numpy()
    if kind == "rsi_reclaim":
        signal = (day.rsi14.shift(1) < 30) & (day.rsi14 >= 30)
        signal &= (day.close > day.open) & (day.close > day.high.shift(1))
        return signal.shift(1, fill_value=False).to_numpy()
    h, l, c, e = (day[col].to_numpy() for col in ("high", "low", "close", "ema20"))
    eps = 1e-10 if kind == "fib_confluence" else 0
    for a in range(20, len(day)-1):
        if not (c[a] > h[a-20:a].max()+eps and e[a] > e[a-5]+eps):
            continue
        floor, ceiling = l[a-20:a].min(), h[a]
        if ceiling <= floor+eps:
            continue
        if kind == "fib_extension":
            level = floor+1.272*(ceiling-floor)
            for b in range(a+1, min(a+21, len(day))):
                if l[b] < floor:
                    break
                if c[b] > level:
                    for t in range(b+1, min(b+6, len(day))):
                        if l[t] < floor:
                            break
                        if l[t] <= level and c[t] > level:
                            if t+1 < len(day): signals[t+1] = True
                            break
                    break
        else:
            ratio = .236 if kind == "fib_shallow" else .618
            level = ceiling-ratio*(ceiling-floor)
            for t in range(a+1, min(a+11, len(day))):
                if l[t] < floor-eps or h[t] > ceiling+eps:
                    break
                confirmed = l[t] <= level+eps and c[t] > level+eps
                if kind == "fib_confluence":
                    confirmed &= abs(level-e[t]) <= .10+eps and c[t] >= e[t]-eps
                if confirmed:
                    if t+1 < len(day): signals[t+1] = True
                    break
    return signals


def fibonacci_signals(day, rule):
    """Freeze anchors at a completed breakout; never use final daily extrema."""
    signals = np.zeros(len(day), dtype=bool)
    h, l, c, e = (day[col].to_numpy() for col in ("high", "low", "close", "ema20"))
    for a in range(20, len(day)-1):
        start = a-20 if rule["anchor"] == "window20" else 0
        if not (c[a] > h[start:a].max() and e[a] > e[a-5]):
            continue
        floor, ceiling = l[start:a].min(), h[a]
        # Daily low must already be known before the new daily high candle.
        if rule["anchor"] == "day":
            if l[a] < floor:
                continue
            floor = min(floor, l[a])
        if ceiling <= floor:
            continue
        level = ceiling-rule["ratio"]*(ceiling-floor)
        for t in range(a+1, min(a+11, len(day))):
            # Cancellation wins when OHLC cannot reveal intraminute ordering.
            if l[t] < floor or h[t] > ceiling:
                break
            if l[t] <= level and c[t] > level:
                if t+1 < len(day):
                    signals[t+1] = True
                break
    return signals


def strict_near(distance, limit):
    # Exclude mathematical equality despite binary floating-point rounding.
    return (distance < limit) & ~np.isclose(distance, limit, rtol=0, atol=1e-10)


def touch_entry_signals(day, rule):
    limit = rule["distance"]
    if rule["type"] == "ema20_angle_touch":
        slope = (day.ema20 - day.ema20.shift(5)) / 5
        threshold = np.tan(np.deg2rad(30))
        rising = (slope > threshold) & ~np.isclose(slope, threshold, rtol=0, atol=1e-10)
        signal = rising & (day.close < day.open) & strict_near((day.low-day.ema20).abs(), limit)
        return signal.shift(1, fill_value=False).to_numpy()
    result = np.zeros(len(day), dtype=bool)
    for a in np.flatnonzero((day.close-day.open).to_numpy() > 2):
        # First eligible touch after two or three bearish bars consumes the setup.
        for k in (1, 2, 3):
            b = a + k
            if b + 1 >= len(day) or day.close.iloc[b] >= day.open.iloc[b]:
                break
            if k >= 2 and strict_near(abs(day.low.iloc[b]-day.ema5.iloc[b]), limit):
                result[b+1] = True
                break
    return result


def chart_entry_signals(day, rule):
    signals = np.zeros(len(day), dtype=bool)
    o, c = day.open.to_numpy(), day.close.to_numpy()
    red = c < o
    if rule["type"] == "double_red_run":
        small = (c > o) & (c - o <= 0.25)
        for end in range(22, len(day) - 1):
            if (red[end-22:end-13].all() and small[end-13:end-11].all()
                    and red[end-11:end+1].all()):
                signals[end+1] = True
        return signals
    e = day.ema5.to_numpy()
    for a in np.flatnonzero(c - o > rule["dollars"]):
        t = a + 1
        while t < len(day) and red[t]:
            t += 1
        if t + 1 >= len(day) or t - a - 1 not in (2, 3):
            continue
        b = t - 1
        if ((c[a+1:t] >= o[a]).all()
                and abs(day.low.iloc[b] - e[b]) <= 0.10 and c[b] >= e[b]
                and c[t] > o[t] and c[t] > day.high.iloc[b]
                and c[t] > e[t] and e[t] > e[b]):
            signals[t+1] = True
    return signals


def platform_breakout_signals(day):
    """Five-bar impulse, exactly three consolidation bars, up to three trigger bars."""
    signals = np.zeros(len(day), dtype=bool)
    for end in range(5, len(day) - 3):
        impulse = day.iloc[end - 4:end + 1]
        if not (impulse.close.iloc[-1] > impulse.open.iloc[0]
                and (impulse.close > impulse.open).sum() >= 3
                and day.close.iloc[end] > day.ema20.iloc[end]
                and day.ema20.iloc[end] > day.ema20.iloc[end - 5]):
            continue
        consolidation = day.iloc[end + 1:end + 4]
        midpoint = (impulse.high.max() + impulse.low.min()) / 2
        if not ((consolidation.close < consolidation.open).any()
                and (consolidation.low >= midpoint).all()
                and (consolidation.close > consolidation.ema20).all()):
            continue
        floor, ceiling = consolidation.low.min(), consolidation.high.max()
        for trigger in range(end + 4, min(end + 7, len(day))):
            bar = day.iloc[trigger]
            # Cancel takes precedence over triggering; equality does not breach.
            if bar.close < floor or bar.close < bar.ema20:
                break
            if bar.close > bar.open and bar.close > ceiling:
                if trigger + 1 < len(day):
                    signals[trigger + 1] = True
                break  # One trigger per five-bar candidate, even if execution is skipped.
    return signals


def entry_signals(day, rule):
    validate_rule("buy", rule)
    if rule["type"] == "rsi14_below3":
        return (day.rsi14 < 3).shift(1, fill_value=False).to_numpy()
    if rule["type"] in ("noise_breakout", "late_momentum", "adx_ten_touch"):
        return regime_signals(day, rule)
    if rule["type"] in ("fib_shallow", "fib_confluence", "fib_extension", "opening_range", "bb_squeeze", "bb_reclaim", "rsi_reclaim"):
        return web_entry_signals(day, rule)
    if rule["type"] == "fibonacci_pullback":
        return fibonacci_signals(day, rule)
    if rule["type"] == "ema20_ten_rising_touch":
        e = day.ema20
        # Ten increments strictly before the pullback candle, all within this session.
        rising = (e > e.shift(1)).shift(1, fill_value=False).rolling(10).sum() == 10
        distance = np.maximum(np.maximum(day.low - e, e - day.high), 0)
        signal = rising & (day.close < day.open) & (day.close >= e)
        signal &= strict_near(distance, rule["distance"])
        return signal.shift(1, fill_value=False).to_numpy()
    if rule["type"] == "ema20_rise_range_touch":
        e = day.ema20
        rising = (e > e.shift(1)) & (e.shift(1) > e.shift(2)) & (e.shift(2) > e.shift(3))
        gain = e - e.shift(5)
        enough = (gain >= rule["rise"]) | np.isclose(gain, rule["rise"], rtol=0, atol=1e-10)
        distance = np.maximum(np.maximum(day.low - e, e - day.high), 0)
        signal = rising & enough & (day.close < day.open) & (day.close >= e)
        signal &= strict_near(distance, rule["distance"])
        return signal.shift(1, fill_value=False).to_numpy()
    if rule["type"] in ("ema20_angle_touch", "green2_touch"):
        return touch_entry_signals(day, rule)
    if rule["type"] in ("double_red_run", "large_green_pullback"):
        return chart_entry_signals(day, rule)
    if rule["type"] == "impulse_platform_breakout":
        return platform_breakout_signals(day)
    if rule["type"] == "trend_vwap":
        line = day.vwap
        rising = line > line.shift(5)
        above = (day.close > line).shift(1).rolling(5).sum() == 5
        pullback = above & rising & (day.close < day.open) & (day.close >= line)
        pullback &= (day.low - line).abs() <= 0.10 + 1e-10
        signal = pullback.shift(1, fill_value=False) & rising & (day.close > day.open)
        signal &= (day.close > day.high.shift(1)) & (day.close > line)
        return signal.shift(1, fill_value=False).to_numpy()
    if rule["type"] == "trend_sma50":
        line = day.sma50
        above = (day.close > line).shift(1).rolling(5).sum() == 5
        signal = above & (line > line.shift(10)) & (day.close > line) & (day.close > day.open)
        signal &= day.close > day.high.shift(1).rolling(5).max()
        return signal.shift(1, fill_value=False).to_numpy()
    if rule["type"] == "trend_price_blocks":
        # Three disjoint, completed five-bar blocks; no future swing pivot labels.
        high = day.high.rolling(5).max()
        low = day.low.rolling(5).min()
        signal = (high > high.shift(5)) & (high.shift(5) > high.shift(10))
        signal &= (low > low.shift(5)) & (low.shift(5) > low.shift(10))
        signal &= (day.close > high.shift(5)) & (day.close > day.open)
        return signal.shift(1, fill_value=False).to_numpy()
    if rule["type"] in ("trend_pullback", "trend_high10"):
        rising = day.ema20 > day.ema20.shift(5)
        if rule["type"] == "trend_high10":
            above = (day.close > day.ema20).shift(1).rolling(10).sum() == 10
            signal = rising & above & (day.close > day.open) & (day.close > day.ema20)
            signal &= day.close > day.high.shift(1).rolling(10).max()
        else:
            line = day[f"ema{rule['period']}"]
            above = ((day.close > day.ema20) & (day.close > line)).shift(1).rolling(5).sum() == 5
            pullback = rising & above & (day.close < day.open)
            pullback &= (day.low - line).abs() <= 0.10 + 1e-10
            pullback &= (day.close >= line) & (day.close >= day.ema20)
            signal = pullback.shift(1, fill_value=False) & rising & (day.close > day.open)
            signal &= (day.close > day.high.shift(1)) & (day.close > line) & (day.close > day.ema20)
        return signal.shift(1, fill_value=False).to_numpy()
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
    sessions = [(day, np.flatnonzero(entry_signals(day, buy["implementation"])))
                for _, day in bars.groupby(bars.index.date)]
    for sell in sells:
        rule = sell["implementation"]
        validate_rule("sell", rule)
        sample = []
        for day, entries in sessions:
            busy_until = -1
            for entry in entries:
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
