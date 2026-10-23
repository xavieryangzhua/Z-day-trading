"""Separate stock-sample runs using the same entry/exit engine, never SPY run IDs."""
import hashlib
import json
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

import engine
import store

SYMBOLS = ('NVDA', 'TSLA', 'AAPL', 'META')
DATA_DIR = store.ROOT / 'data/external/firstrate_samples'


def code_snapshot():
    return {name: (store.ROOT/name).read_text() for name in ('engine.py', 'store.py', 'equities.py')}


def initialize():
    with store.connect() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS stock_runs (
            id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, symbol TEXT NOT NULL,
            idea_id TEXT NOT NULL, signature TEXT NOT NULL, engine_hash TEXT NOT NULL,
            source_hash TEXT NOT NULL, status TEXT NOT NULL, reason TEXT NOT NULL,
            snapshot TEXT NOT NULL, source TEXT NOT NULL, parameters TEXT NOT NULL,
            summary TEXT NOT NULL, trades TEXT NOT NULL)''')
        db.execute('CREATE INDEX IF NOT EXISTS stock_run_lookup ON stock_runs(symbol,idea_id,id)')


def load_stock(symbol, directory=DATA_DIR):
    if symbol not in SYMBOLS:
        raise ValueError('Unsupported stock symbol')
    sources = json.loads((directory/'sources.json').read_text())
    source = next(x.copy() for x in sources if x['symbol']==symbol)
    path=directory/f'{symbol}_1min.csv'
    actual=hashlib.sha256(path.read_bytes()).hexdigest()
    if actual!=source['csv_sha256']:
        raise ValueError(f'{symbol} source SHA256 mismatch')
    bars=pd.read_csv(path,header=None,names=['timestamp','open','high','low','close','volume'])
    bars.index=pd.DatetimeIndex(pd.to_datetime(bars.pop('timestamp'))).tz_localize('America/New_York')
    if bars.index.has_duplicates or not bars.index.is_monotonic_increasing:
        raise ValueError('Duplicate or unordered timestamps')
    bars=bars.between_time('09:30','15:59').copy()
    if bars.empty or (bars.index.dayofweek>=5).any():
        raise ValueError('Invalid session dates')
    if not np.isfinite(bars).all().all() or (bars.volume<0).any():
        raise ValueError('Invalid OHLCV values')
    if ((bars.low>bars[['open','close']].min(axis=1)) | (bars.high<bars[['open','close']].max(axis=1)) | (bars.low<=0)).any():
        raise ValueError('Invalid OHLC geometry')
    for date,day in bars.groupby(bars.index.date):
        expected=pd.date_range(f'{date} 09:30',periods=390,freq='min',tz='America/New_York')
        if not day.index.equals(expected):
            raise ValueError(f'{symbol} {date}: incomplete session; do not fill missing bars')
    # Warmup uses regular sessions only and carries within this symbol, never across symbols.
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
    if any(not store.ready(x) or not x['realize'] for x in items):
        raise ValueError('Implement all ideas before running stock comparisons')
    code=code_snapshot();code_hash=store.digest(code)
    for symbol in symbols:
        bars,source=load_stock(symbol)
        for buy in buys:
            signature=store.signature(buy,sells)
            with store.connect() as db:
                exists=db.execute('SELECT id FROM stock_runs WHERE symbol=? AND idea_id=? AND signature=? AND engine_hash=? AND source_hash=?',
                                  (symbol,buy['id'],signature,code_hash,source['actual_sha256'])).fetchone()
            if exists:continue
            status,reason='complete',''
            if buy['implementation']['type']=='noise_breakout' and bars.noise_upper.isna().all():
                status,reason='insufficient_data','仅10个交易日，缺少前14个交易日的同时刻预热数据'
            summary,trades=engine.backtest(bars,buy,sells)
            wins=Counter(t['sell_id'] for t in trades if t['net_profit']>0)
            for s in summary:s['profitable_trades']=wins[s['sell_id']]
            snapshot={'buy':buy,'sells':sells,'code':code,
                      'application':'Original idea text may say SPY; apply its exact numeric rules to '+symbol+'. No scaling or retuning. Minute stock bars with synthetic Call returns, not observed option quotes.'}
            params={**engine.PARAMETERS,'symbol':symbol,'indicator_warmup':'regular sessions, per symbol'}
            with store.connect() as db:
                db.execute('INSERT INTO stock_runs (created_at,symbol,idea_id,signature,engine_hash,source_hash,status,reason,snapshot,source,parameters,summary,trades) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                           (store.now(),symbol,buy['id'],signature,code_hash,source['actual_sha256'],status,reason,
                            json.dumps(snapshot,ensure_ascii=False),json.dumps(source,ensure_ascii=False),json.dumps(params),json.dumps(summary,ensure_ascii=False),json.dumps(trades)))
        print(f'{symbol}: {len(buys)} ideas × {len(sells)} exits saved',flush=True)


def ranking_rows(items):
    initialize()
    buys={x['id']:x for x in items if x['kind']=='buy'}
    sells=[x for x in items if x['kind']=='sell']
    sell_names={x['id']:x['name'] for x in sells}
    code_hash=store.digest(code_snapshot())
    # Verify local source bytes before displaying a run as current.
    hashes={s:hashlib.sha256((DATA_DIR/f'{s}_1min.csv').read_bytes()).hexdigest() for s in SYMBOLS if (DATA_DIR/f'{s}_1min.csv').exists()}
    with store.connect() as db:
        runs=db.execute('''SELECT r.symbol,r.idea_id,r.signature,r.engine_hash,r.source_hash,r.status,r.reason,r.summary
            FROM stock_runs r JOIN (SELECT symbol,idea_id,max(id) id FROM stock_runs GROUP BY symbol,idea_id) latest ON r.id=latest.id''').fetchall()
    rows=[]
    for r in runs:
        buy=buys.get(r['idea_id'])
        if not (buy and buy['realize'] and store.ready(buy) and all(x['realize'] and store.ready(x) for x in sells)
                and r['signature']==store.signature(buy,sells) and r['engine_hash']==code_hash and r['source_hash']==hashes.get(r['symbol'])):
            continue
        for s in json.loads(r['summary']):
            rows.append({'股票':r['symbol'],'买入想法':buy['name'],'卖出方法':sell_names[s['sell_id']],
                         '平均净收益率':s['mean_return']*100 if s['mean_return'] is not None else None,
                         '胜率':s['win_rate']*100 if s['win_rate'] is not None else None,
                         '盈利笔数':s['profitable_trades'],'笔数':s['trades'],
                         '状态':'预热不足' if r['status']=='insufficient_data' else ('无信号' if s['trades']==0 else '已回测')})
    return rows

if __name__=='__main__':run_stocks()
