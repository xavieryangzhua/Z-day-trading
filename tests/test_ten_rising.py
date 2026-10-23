import numpy as np
import pandas as pd
import pytest
from engine import entry_signals


def frame():
    e=100+np.arange(14)*.001
    d=pd.DataFrame({'ema20':e,'open':e+1,'close':e+.5,'high':e+1,'low':e+.4})
    d.loc[11,'low']=99
    return d


def sig(d,distance=.05):
    return entry_signals(d,{'type':'ema20_ten_rising_touch','distance':distance})


def test_ten_prior_increments_small_rise_and_next_open():
    d=frame();assert np.flatnonzero(sig(d)).tolist()==[12]
    d.loc[12:,'close']=0
    assert sig(d)[12]


@pytest.mark.parametrize('index',[1,5,10])
@pytest.mark.parametrize('change',[0,-.001])
def test_flat_or_falling_prior_minute_rejected(index,change):
    d=frame();d.loc[index,'ema20']=d.loc[index-1,'ema20']+change
    assert not sig(d)[12]


def test_current_bar_not_part_of_prior_window():
    d=frame();d.loc[11,'ema20']=d.loc[10,'ema20'];d.loc[11,'close']=d.loc[11,'ema20']
    assert sig(d)[12]


@pytest.mark.parametrize('distance',[.05,.1])
def test_distance_strict(distance):
    d=frame();d.loc[11,'low']=d.loc[11,'ema20']+distance
    assert not sig(d,distance)[12]
    d.loc[11,'low']-=.001
    assert sig(d,distance)[12]


@pytest.mark.parametrize('close',[99,102])
def test_must_be_red_and_close_above_ema(close):
    d=frame();d.loc[11,'close']=close
    assert not sig(d)[12]


def test_history_warmup_and_end_of_day():
    d=frame()
    assert not sig(d.iloc[1:]).any()
    assert not sig(d.iloc[:12]).any()
    d.loc[0,'ema20']=np.nan
    assert not sig(d).any()
