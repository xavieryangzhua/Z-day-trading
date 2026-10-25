import hashlib
import json
import numpy as np
import pandas as pd
import pytest
import equities,store,engine


def source(tmp_path, gap=False):
    times=pd.date_range('2026-10-05 09:30',periods=390,freq='min')
    d=pd.DataFrame({'time':times,'open':100.,'high':101.,'low':99.,'close':100.,'volume':10})
    if gap:d=d.drop(5)
    path=tmp_path/'NVDA_1min.csv';d.to_csv(path,index=False,header=False)
    (tmp_path/'sources.json').write_text(json.dumps([{'symbol':'NVDA','csv_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}]))
    return path


def test_stock_loader_validates_and_warms_independently(tmp_path):
    source(tmp_path)
    bars,meta=equities.load_stock('NVDA',tmp_path)
    assert len(bars)==390 and meta['symbol']=='NVDA'
    assert bars.ema20.iloc[:19].isna().all()
    assert bars.noise_upper.isna().all()
    assert bars.previous_close.isna().all()
    assert bars.rsi14.iloc[14]==50


def test_missing_minute_rejected(tmp_path):
    source(tmp_path,gap=True)
    with pytest.raises(ValueError,match='incomplete'):equities.load_stock('NVDA',tmp_path)


def test_source_hash_rejected(tmp_path):
    path=source(tmp_path);path.write_text(path.read_text()+'\n')
    with pytest.raises(ValueError,match='SHA256'):equities.load_stock('NVDA',tmp_path)


def test_stock_runs_isolate_spy_and_stale_rules(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'HOME',tmp_path/'store')
    store.initialize();equities.initialize()
    buy={'id':'b','kind':'buy','name':'buy','version':1,'realize':True,'description':'rule','implementation':{'type':'rsi14_below3'}}
    sell={'id':'s','kind':'sell','name':'sell','version':1,'realize':True,'description':'exit','implementation':{'type':'fixed','minutes':1}}
    for x in (buy,sell):x['implementation_hash']=store.description_hash(x)
    dat=tmp_path/'data';dat.mkdir();p=source(dat);monkeypatch.setattr(equities,'DATA_DIR',dat)
    signature=store.signature(buy,[sell]);h=hashlib.sha256(p.read_bytes()).hexdigest()
    with store.connect() as db:
        db.execute('INSERT INTO stock_runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(1,'today','NVDA','b',signature,store.digest(equities.code_snapshot()),h,'complete','','{}','{}','{}',json.dumps([{'sell_id':'s','trades':1,'mean_return':.1,'win_rate':1,'profitable_trades':1}]),'[]'))
        assert db.execute('SELECT count(*) FROM runs').fetchone()[0]==0
    assert len(equities.ranking_rows([buy,sell]))==1
    (dat/'QQQ_1min.csv').write_bytes(p.read_bytes())
    with store.connect() as db:
        db.execute('INSERT INTO stock_runs SELECT 2,created_at,?,idea_id,signature,engine_hash,source_hash,status,reason,snapshot,source,parameters,summary,trades FROM stock_runs WHERE id=1', ('QQQ',))
    assert [r['股票'] for r in equities.ranking_rows([buy,sell])] == ['NVDA']
    assert [r['股票'] for r in equities.ranking_rows([buy,sell], symbols=('QQQ',))] == ['QQQ']
    buy['description']='changed'
    assert not equities.ranking_rows([buy,sell])


def ibkr_source(tmp_path, gap=False):
    # Includes DST winter UTC offset and the Thanksgiving half-day.
    times = pd.date_range('2025-11-28 14:30', periods=210, freq='min', tz='UTC')
    data = pd.DataFrame({'timestamp': times, 'open':100., 'high':101.,
                         'low':99., 'close':100., 'volume':10., 'bar_count':1})
    if gap:
        data = data.drop(5)
    path = tmp_path/'NVDA_1min.csv'
    data.to_csv(path,index=False)
    (tmp_path/'sources.json').write_text(json.dumps([{
        'symbol':'NVDA','whatToShow':'TRADES',
        'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}]))


def test_ibkr_half_day_timezone_and_exit(tmp_path):
    ibkr_source(tmp_path)
    bars, meta = equities.load_stock('NVDA',tmp_path)
    assert len(bars)==210
    assert bars.index[0].hour==9 and bars.index[0].minute==30
    assert bars.index[-1].hour==12 and bars.index[-1].minute==59
    _, _, exit_time, reason = engine.exit_trade(bars,209,{'type':'fixed','minutes':30})
    assert exit_time.hour==13 and exit_time.minute==0
    assert reason=='session_close'


def test_ibkr_half_day_does_not_allow_missing_minutes(tmp_path):
    ibkr_source(tmp_path,gap=True)
    with pytest.raises(ValueError,match='incomplete'):
        equities.load_stock('NVDA',tmp_path)
