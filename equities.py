"""Separate stock runs using the same entry/exit engine, never SPY run IDs."""
import hashlib
import json
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

import engine
import store

SYMBOLS = ('NVDA', 'TSLA', 'AAPL', 'META', 'MU', 'GOOGL')
DATA_DIR = store.ROOT / 'data/external/ibkr/2025-10-23_2026-10-23'
# NYSE/Nasdaq calendar: early closes within the downloaded interval.
EARLY_CLOSES = {'2025-11-28', '2025-12-24'}


def code_snapshot():
    return {**engine.code_snapshot(), 'equities.py': (store.ROOT/'equities.py').read_text()}


def initialize():
    with store.connect() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS stock_runs (
            id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, symbol TEXT NOT NULL,
            idea_id TEXT NOT NULL, signature TEXT NOT NULL, engine_hash TEXT NOT NULL,
            source_hash TEXT NOT NULL, status TEXT NOT NULL, reason TEXT NOT NULL,
            snapshot TEXT NOT NULL, source TEXT NOT NULL, parameters TEXT NOT NULL,
            summary TEXT NOT NULL, trades TEXT NOT NULL)''')
        db.execute('CREATE INDEX IF NOT EXISTS stock_run_lookup ON stock_runs(symbol,idea_id,id)')


def load_stock(symbol, directory=None):
    directory = DATA_DIR if directory is None else directory
    if symbol not in (*SYMBOLS, 'QQQ', 'SPX'):
        raise ValueError('Unsupported stock symbol')
    sources = json.loads((directory/'sources.json').read_text())
    source = next(x.copy() for x in sources if x['symbol']==symbol)
    path=directory/f'{symbol}_1min.csv'
    actual=hashlib.sha256(path.read_bytes()).hexdigest()
    if actual!=source.get('sha256', source.get('csv_sha256')):
        raise ValueError(f'{symbol} source SHA256 mismatch')
    if source.get('whatToShow') == 'TRADES':
        bars = pd.read_csv(path)
        bars.index = pd.DatetimeIndex(pd.to_datetime(bars.pop('timestamp'), utc=True)).tz_convert('America/New_York')
        bars = bars[['open','high','low','close','volume']]
    else:
        bars=pd.read_csv(path,header=None,names=['timestamp','open','high','low','close','volume'])
        bars.index=pd.DatetimeIndex(pd.to_datetime(bars.pop('timestamp'))).tz_localize('America/New_York')
    if bars.index.has_duplicates or not bars.index.is_monotonic_increasing:
        raise ValueError('Duplicate or unordered timestamps')
    bars=bars.between_time('09:30','15:59').copy()
    if bars.empty or (bars.index.dayofweek>=5).any():
        raise ValueError('Invalid session dates')
    check=bars[['open','high','low','close']] if symbol=='SPX' else bars
    if not np.isfinite(check).all().all() or (symbol!='SPX' and (bars.volume<0).any()):
        raise ValueError('Invalid OHLCV values')
    if ((bars.low>bars[['open','close']].min(axis=1)) | (bars.high<bars[['open','close']].max(axis=1)) | (bars.low<=0)).any():
        raise ValueError('Invalid OHLC geometry')
    for date,day in bars.groupby(bars.index.date):
        periods = 210 if str(date) in EARLY_CLOSES else 390
        expected=pd.date_range(f'{date} 09:30',periods=periods,freq='min',tz='America/New_York')
        if not day.index.equals(expected):
            raise ValueError(f'{symbol} {date}: incomplete session; do not fill missing bars')
    # Warmup uses regular sessions only and carries within this symbol, never across symbols.
    bars.attrs['symbol']=symbol
    if symbol=='SPX':bars['volume']=np.nan
    dates=bars.index.date
    typical=(bars.high+bars.low+bars.close)/3
    bars['vwap']=(typical*bars.volume).groupby(dates).cumsum()/bars.volume.groupby(dates).cumsum().replace(0,np.nan)
    bars['ema20']=bars.close.ewm(span=20,adjust=False,min_periods=20).mean()
    bars['ema5']=bars.close.ewm(span=5,adjust=False,min_periods=5).mean()
    bars['sma50']=bars.close.rolling(50,min_periods=50).mean()
    engine.add_web_indicators(bars)
    engine.add_regime_indicators(bars)
    source.update(actual_sha256=actual,start=str(bars.index[0]),end=str(bars.index[-1]),regular_rows=len(bars),
                  days=len(set(dates)),processing='Retain 09:30–15:59 New York; no filling or price changes; per-symbol indicators')
    source['limitations']=[x for x in source.get('limitations',[]) if 'Not yet integrated' not in x]
    return bars,source


def run_stocks(symbols=SYMBOLS):
    store.initialize();initialize()
    items=store.ideas()
    buys=[x for x in items if x['kind']=='buy']
    sells=[x for x in items if x['kind']=='sell']
    if any(not store.ready(x) for x in items):
        raise ValueError('Implement all ideas before running stock comparisons')
    code=code_snapshot();code_hash=store.digest(code)
    for symbol in symbols:
        bars,source=load_stock(symbol)
        for number, buy in enumerate(buys, 1):
            if buy['implementation']['type']=='spx_first_round_touch' and symbol!='SPX':continue
            signature=store.signature(buy,sells)
            with store.connect() as db:
                exists=db.execute('SELECT id FROM stock_runs WHERE symbol=? AND idea_id=? AND signature=? AND engine_hash=? AND source_hash=?',
                                  (symbol,buy['id'],signature,code_hash,source['actual_sha256'])).fetchone()
            if exists:continue
            status,reason='complete',''
            if buy['implementation']['type']=='noise_breakout' and bars.noise_upper.isna().all():
                status,reason='insufficient_data','缺少前14个交易日的同时刻预热数据'
            removed=store.excluded(symbol,buy['id'])
            active_sells=[s for s in sells if s['id'] not in removed]
            rule=buy['implementation']
            needs_volume=rule.get('indicator')=='vwap' or rule['type'] in ('trend_vwap','noise_breakout')
            if symbol=='SPX' and needs_volume:
                status,reason='unsupported_data','SPX指数无成交量，不能计算VWAP；未用SPY代替'
                summary=[dict(sell_id=s['id'],name=s['name'],version=s['version'],trades=0,mean_return=None,win_rate=None) for s in active_sells]
                trades=[]
            else:summary,trades=engine.backtest(bars,buy,active_sells)
            wins=Counter(t['sell_id'] for t in trades if t['net_profit']>0)
            for s in summary:s['profitable_trades']=wins[s['sell_id']]
            snapshot={'buy':buy,'sells':sells,'code':code,'excluded_sell_ids':sorted(removed),
                      'application':'Original idea text may say SPY; apply its exact numeric rules to '+symbol+'. No scaling or retuning. Underlying minute bars with synthetic Call returns, not observed option quotes. SPX is an index, not SPY; no volume-based signals on SPX.'}
            params={**engine.PARAMETERS,'symbol':symbol,'indicator_warmup':'regular sessions, per symbol'}
            with store.connect() as db:
                db.execute('INSERT INTO stock_runs (created_at,symbol,idea_id,signature,engine_hash,source_hash,status,reason,snapshot,source,parameters,summary,trades) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                           (store.now(),symbol,buy['id'],signature,code_hash,source['actual_sha256'],status,reason,
                            json.dumps(snapshot,ensure_ascii=False),json.dumps(source,ensure_ascii=False),json.dumps(params),json.dumps(summary,ensure_ascii=False),json.dumps(trades)))
            if number % 10 == 0:
                print(f'{symbol}: {number}/{len(buys)} ideas complete', flush=True)
        if symbol=='SPX':
            with store.locked():
                current=store._read()
                for x in current:
                    if (x.get('implementation') or {}).get('type')=='spx_first_round_touch' and store.ready(x):
                        x['realize']=True;x.pop('error',None);x['updated_at']=store.now()
                store._write(current)
        print(f'{symbol}: {len(buys)} ideas × {len(sells)} exits saved',flush=True)


def ranking_rows(items, symbols=SYMBOLS):
    initialize()
    buys={x['id']:x for x in items if x['kind']=='buy'}
    sells=[x for x in items if x['kind']=='sell']
    sell_names={x['id']:x['name'] for x in sells}
    code_hash=store.digest(code_snapshot())
    # Verify local source bytes before displaying a run as current.
    hashes={s:hashlib.sha256((DATA_DIR/f'{s}_1min.csv').read_bytes()).hexdigest() for s in symbols if (DATA_DIR/f'{s}_1min.csv').exists()}
    with store.connect() as db:
        runs=db.execute('''SELECT r.symbol,r.idea_id,r.signature,r.engine_hash,r.source_hash,r.status,r.reason,r.summary
            FROM stock_runs r JOIN (SELECT symbol,idea_id,max(id) id FROM stock_runs GROUP BY symbol,idea_id) latest ON r.id=latest.id''').fetchall()
    rows=[]
    for r in runs:
        buy=buys.get(r['idea_id'])
        if not (buy and buy['realize'] and store.ready(buy) and all(x['realize'] and store.ready(x) for x in sells)
                and r['signature']==store.signature(buy,sells) and r['engine_hash']==code_hash and r['source_hash']==hashes.get(r['symbol'])):
            continue
        if r['symbol'] not in symbols:continue
        removed=store.excluded(r['symbol'],r['idea_id'])
        for s in json.loads(r['summary']):
            if s['sell_id'] in removed:continue
            rows.append({'股票':r['symbol'],'买入想法':buy['name'],'卖出方法':sell_names[s['sell_id']],
                         '平均净收益率':s['mean_return']*100 if s['mean_return'] is not None else None,
                         '胜率':s['win_rate']*100 if s['win_rate'] is not None else None,
                         '盈利笔数':s['profitable_trades'],'笔数':s['trades'],
                         '状态':'缺少成交量（不适用）' if r['status']=='unsupported_data' else '预热不足' if r['status']=='insufficient_data' else ('无信号' if s['trades']==0 else '已回测')})
    return rows

if __name__=='__main__':run_stocks()
