import numpy as np
import pandas as pd
import pytest
from engine import add_regime_indicators,entry_signals,wilder_average


def data(days=1):
    idx=pd.DatetimeIndex([t for d in pd.bdate_range('2025-01-02',periods=days) for t in pd.date_range(str(d.date())+' 09:30',periods=390,freq='min',tz='America/New_York')])
    return pd.DataFrame({'open':100.,'close':100.,'high':101.,'low':99.,'ema20':100.,'vwap':100.},index=idx)


def test_adx_warmup_flat_and_direction():
    d=data();add_regime_indicators(d)
    assert d.adx14.iloc[:27].isna().all()
    assert (d.adx14.iloc[27:]==0).all()
    d['high']+=np.arange(len(d));d['low']+=np.arange(len(d));d['close']+=np.arange(len(d));add_regime_indicators(d)
    assert d.adx14.iloc[27]==pytest.approx(100)
    assert d.plus_di.iloc[27]>d.minus_di.iloc[27]


def test_wilder_recursion():
    x=np.arange(20,dtype=float);v=wilder_average(x,14,1)
    assert v[14]==7.5
    assert v[15]==pytest.approx((13*7.5+15)/14)


def test_noise_uses_previous_14_sessions_only():
    d=data(16);d['close']=101.;add_regime_indicators(d)
    assert d.noise_upper.iloc[:14*390].isna().all()
    assert d.noise_upper.iloc[14*390]==pytest.approx(101*1.01)
    old=d.noise_upper.iloc[14*390:15*390].copy()
    d.loc[d.index[14*390:],'close']=200;add_regime_indicators(d)
    pd.testing.assert_series_equal(old,d.noise_upper.iloc[14*390:15*390])


def test_noise_checkpoints_and_strict_bound():
    d=data();d['noise_upper']=101.;d['close']=102.
    s=np.flatnonzero(entry_signals(d,{'type':'noise_breakout'}))
    assert s.tolist()==list(range(30,361,30))
    d['close']=101.
    assert not entry_signals(d,{'type':'noise_breakout'}).any()


def test_late_only_known_morning_return():
    d=data();d['previous_close']=99.
    assert np.flatnonzero(entry_signals(d,{'type':'late_momentum'})).tolist()==[360]
    d.loc[d.index[360:],'close']=0
    assert entry_signals(d,{'type':'late_momentum'})[360]
    d['previous_close']=100.
    assert not entry_signals(d,{'type':'late_momentum'}).any()


@pytest.mark.parametrize('distance',[.05,.1])
def test_adx_filter_applies_to_confirmation_not_entry(distance):
    d=data().iloc[:14].copy();d['ema20']=100+np.arange(14)*.001
    d['open']=102.;d['close']=101.;d['low']=100.;d['high']=103.
    d['adx14']=25.;d['plus_di']=30.;d['minus_di']=10.
    assert not entry_signals(d,{'type':'adx_ten_touch','distance':distance}).any()
    d.iloc[11,d.columns.get_loc('adx14')]=26
    assert np.flatnonzero(entry_signals(d,{'type':'adx_ten_touch','distance':distance})).tolist()==[12]
    d.iloc[11,d.columns.get_loc('minus_di')]=30
    assert not entry_signals(d,{'type':'adx_ten_touch','distance':distance}).any()
