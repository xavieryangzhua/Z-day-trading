import numpy as np
import pandas as pd
import pytest
from engine import entry_signals


def frame():
    d=pd.DataFrame({'open':[102.]*34,'close':[102.]*34,'high':[103.]*34,'low':[100.]*34,'ema20':np.arange(34)*.01+100})
    d.loc[20,['open','close','high','low']]=[102,103.5,104,101]
    d.loc[21:,['open','close','high','low']]=[103,103,103.5,103]
    return d


def sig(d,anchor='window20',ratio=.5):
    return entry_signals(d,{'type':'fibonacci_pullback','anchor':anchor,'ratio':ratio})


@pytest.mark.parametrize('anchor',['window20','day'])
@pytest.mark.parametrize('ratio',[.382,.4,.5,.6,.618])
def test_exact_touch_next_open_once(anchor,ratio):
    d=frame();f=104-ratio*4;d.loc[21,'low']=f
    assert np.flatnonzero(sig(d,anchor,ratio)).tolist()==[22]
    d.loc[22:,'high']=1000;d.loc[22:,'low']=1
    assert sig(d,anchor,ratio)[22]


@pytest.mark.parametrize('anchor',['window20','day'])
def test_tenth_allowed_eleventh_expired(anchor):
    d=frame();d.loc[30,'low']=102
    assert sig(d,anchor)[31]
    d.loc[30,'low']=103;d.loc[31,'low']=102
    assert not sig(d,anchor).any()


@pytest.mark.parametrize('col,value',[('low',99),('high',105)])
def test_cancel_before_confirmation(col,value):
    d=frame();d.loc[21,'low']=102;d.loc[21,col]=value;d.loc[22,'low']=102
    assert not sig(d).any()


def test_close_equal_does_not_confirm_and_can_wait():
    d=frame();d.loc[21,['low','close']]=[101,102];d.loc[22,'low']=102
    assert np.flatnonzero(sig(d)).tolist()==[23]


def test_breakout_strict_and_ema_rising():
    d=frame();d.loc[20,'close']=103
    assert not sig(d).any()
    d=frame();d.loc[20,'ema20']=d.loc[15,'ema20'];d.loc[21,'low']=102
    assert not sig(d).any()


def test_day_low_same_candle_rejected():
    d=frame();d.loc[20,'low']=99;d.loc[21,'low']=101.5
    assert not sig(d,'day').any()
    assert sig(d,'window20')[22]


def test_day_and_window_anchors_differ():
    d=frame();d.loc[20,['close','high']]=[102,103]
    d.loc[0,'low']=90
    d.loc[22,['close','high','low']]=[103.75,104,101]
    d.loc[23,'low']=102
    assert sig(d,'window20')[24]
    assert not sig(d,'day').any()


def test_last_bar_and_insufficient_history():
    d=frame();d.loc[21,'low']=102
    assert not sig(d.iloc[:22]).any()
    assert not sig(d.iloc[1:]).any()
