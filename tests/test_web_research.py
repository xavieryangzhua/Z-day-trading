import numpy as np
import pandas as pd
import pytest
from engine import add_web_indicators,entry_signals


def data(n=100):
    return pd.DataFrame({'open':100.,'close':100.,'high':101.,'low':99.,'ema20':100.},index=pd.date_range('2025-01-02 09:30',periods=n,freq='min',tz='America/New_York'))


def sig(d,kind,**kwargs):
    return np.flatnonzero(entry_signals(d,{'type':kind,**kwargs})).tolist()


@pytest.mark.parametrize('n',[5,15])
def test_orb_only_first_after_complete_range(n):
    d=data();d.iloc[n,d.columns.get_loc('close')]=102;d.iloc[n+3,d.columns.get_loc('close')]=103
    assert sig(d,'opening_range',minutes=n)==[n+1]
    assert sig(d.iloc[:n+1],'opening_range',minutes=n)==[]


def test_orb_cutoff_gap_and_equality():
    d=data();d.iloc[90,d.columns.get_loc('close')]=102
    assert not sig(d,'opening_range',minutes=5)
    d.iloc[89,d.columns.get_loc('close')]=102
    assert sig(d,'opening_range',minutes=5)==[90]
    assert not sig(d.drop(d.index[2]),'opening_range',minutes=5)


def test_rsi_wilder_seed_and_recursion():
    d=data(17);d['close']=100+np.array([0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,2,1])
    add_web_indicators(d)
    assert d.rsi14.iloc[:14].isna().all()
    assert d.rsi14.iloc[14]==50
    assert d.rsi14.iloc[15]==pytest.approx(100-100/(1+((.5*13+2)/14)/((.5*13)/14)))


@pytest.mark.parametrize('direction,expected',[(0,50),(1,100),(-1,0)])
def test_rsi_zero_loss_cases(direction,expected):
    d=data(20);d['close']=100+np.arange(20)*direction;add_web_indicators(d)
    assert (d.rsi14.iloc[14:]==expected).all()


def test_bands_and_cutoff_no_lookahead():
    d=data();d['close']=100+np.arange(100)*.01;add_web_indicators(d)
    assert d.bb_upper.iloc[19]==pytest.approx(d.close.iloc[:20].mean()+2*d.close.iloc[:20].std(ddof=0))
    assert d.bb_cutoff.iloc[80]==pytest.approx(d.bb_width.iloc[19:79].quantile(.2))
    old=d.iloc[:81].copy();d.loc[d.index[81:],'close']=1000;add_web_indicators(d)
    pd.testing.assert_series_equal(d.bb_cutoff.iloc[:81],old.bb_cutoff)


def test_rsi_reclaim_requires_price_confirmation():
    d=data(4);d['rsi14']=[29,30,31,31];d.iloc[1,d.columns.get_loc('close')]=102
    assert sig(d,'rsi_reclaim')==[2]
    d.iloc[1,d.columns.get_loc('close')]=101
    assert not sig(d,'rsi_reclaim')


def test_bb_reclaim_requires_immediate_green_close_above():
    d=data(4);d['bb_lower']=[101,99,99,99];d.iloc[1,d.columns.get_loc('close')]=100.5
    assert sig(d,'bb_reclaim')==[2]
    d.iloc[1,d.columns.get_loc('close')]=99
    assert not sig(d,'bb_reclaim')


def test_squeeze_breakout_and_prior_ten_high():
    d=data(13);d['bb_upper']=101.;d['bb_width']=.01;d['bb_prev_width']=.01;d['bb_cutoff']=.01
    d.iloc[10,d.columns.get_loc('close')]=102;d.iloc[10,d.columns.get_loc('bb_width')]=.02
    assert sig(d,'bb_squeeze')==[11]
    d.iloc[9,d.columns.get_loc('high')]=102
    assert not sig(d,'bb_squeeze')


def fib():
    d=data(50);d['ema20']=100+np.arange(50)*.01
    d.iloc[20,d.columns.get_loc('close')]=103;d.iloc[20,d.columns.get_loc('high')]=104
    d.loc[d.index[21:],['close','open','high','low']]=[103,103,103.5,103]
    return d


def test_shallow_touch_and_cancellation():
    d=fib();level=104-.236*5;d.iloc[21,d.columns.get_loc('low')]=level
    assert sig(d,'fib_shallow')==[22]
    d.iloc[21,d.columns.get_loc('high')]=105
    assert not sig(d,'fib_shallow')


def test_confluence_equal_distance_and_waiting():
    d=fib();level=104-.618*5
    d.iloc[21,d.columns.get_loc('low')]=level;d.iloc[21,d.columns.get_loc('ema20')]=level+.1
    assert sig(d,'fib_confluence')==[22]
    d.iloc[21,d.columns.get_loc('ema20')]=level+.101
    assert not sig(d,'fib_confluence')


def test_extension_cannot_enter_on_breakout_and_fifth_retest_allowed():
    d=fib();level=99+1.272*5
    # Stop unrelated later candidates by flattening their EMA.
    d.loc[d.index[21:],'ema20']=99
    d.loc[d.index[21:],['open','close','high','low']]=[level+.2,level+.3,level+.5,level+.1]
    d.iloc[21,d.columns.get_loc('low')]=level-.1
    assert not sig(d,'fib_extension')
    d.iloc[26,d.columns.get_loc('low')]=level
    assert sig(d,'fib_extension')==[27]
    d.iloc[26,d.columns.get_loc('low')]=level+.1;d.iloc[27,d.columns.get_loc('low')]=level
    assert not sig(d,'fib_extension')


def test_extension_twentieth_breakout_and_cancel():
    d=fib();level=99+1.272*5;d.loc[d.index[21:],'ema20']=99
    d.loc[d.index[40:],['open','close','high','low']]=[level+.2,level+.3,level+.5,level]
    assert sig(d,'fib_extension')==[42]
    d.iloc[39,d.columns.get_loc('low')]=98
    assert not sig(d,'fib_extension')
