import hashlib
import json
import pandas as pd
import pytest
import engine
import store


def write_source(root, gap=False):
    folder=root/'data';folder.mkdir()
    stamps=pd.date_range('2025-11-28 14:30',periods=210,freq='min',tz='UTC')
    bars=pd.DataFrame({'timestamp':stamps,'open':100.,'high':101.,'low':99.,'close':100.,'volume':10.})
    if gap:bars=bars.drop(5)
    path=folder/'SPY.csv';bars.to_csv(path,index=False)
    (folder/'source.json').write_text(json.dumps({'symbol':'SPY','whatToShow':'TRADES','file':'SPY.csv',
        'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'early_close_dates':['2025-11-28']}))


def test_spy_ibkr_half_day_uses_new_york_and_actual_close(tmp_path,monkeypatch):
    write_source(tmp_path)
    monkeypatch.setattr(store,'ROOT',tmp_path)
    bars,source=engine.load_data()
    assert len(bars)==210 and set(bars.symbol)=={'SPY'}
    assert bars.index[0].hour==9 and bars.index[0].minute==30
    assert source['actual_sha256']==source['sha256']
    _,_,exit_time,reason=engine.exit_trade(bars,209,{'type':'fixed','minutes':30})
    assert exit_time.hour==13 and exit_time.minute==0 and reason=='session_close'


def test_spy_ibkr_rejects_half_day_gaps(tmp_path,monkeypatch):
    write_source(tmp_path,gap=True)
    monkeypatch.setattr(store,'ROOT',tmp_path)
    with pytest.raises(ValueError,match='不完整'):engine.load_data()
