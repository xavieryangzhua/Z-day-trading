import numpy as np
import pandas as pd
import pytest
from engine import entry_signals,validate_rule


def frame():
    return pd.DataFrame({'open':[101.]*8,'close':[100.8]*8,'low':[100.7]*8,'high':[101.2]*8,
                         'ema20':[100.,100.1,100.2,100.3,100.4,100.5,100.6,100.7]})


def sig(d,rise=.1,distance=.05):
    return entry_signals(d,{'type':'ema20_rise_range_touch','rise':rise,'distance':distance})


@pytest.mark.parametrize('rise',[.1,.2,.3])
@pytest.mark.parametrize('distance',[.05,.1])
def test_crossing_with_deep_wick_counts(rise,distance):
    d=frame();d.loc[5,'low']=99
    assert sig(d,rise,distance)[6]
    d.loc[6:,'close']=0
    assert sig(d,rise,distance)[6]


@pytest.mark.parametrize('distance',[.05,.1])
def test_strict_near_boundary(distance):
    d=frame();d.loc[5,'low']=100.5+distance
    assert not sig(d,distance=distance)[6]
    d.loc[5,'low']-=.001
    assert sig(d,distance=distance)[6]


def test_minimum_rise_equality_and_below():
    d=frame();d.loc[5,'low']=100.5;d.loc[0,'ema20']=100.2
    assert sig(d,.3)[6]
    d.loc[0,'ema20']+=.001
    assert not sig(d,.3)[6]


@pytest.mark.parametrize('row,col,value',[(4,'ema20',100.3),(5,'close',100.49),(5,'close',101.),(2,'ema20',np.nan)])
def test_rejects_broken_trend_close_or_warmup(row,col,value):
    d=frame();d.loc[5,'low']=100.;d.loc[row,col]=value
    assert not sig(d)[6]


def test_equal_close_and_day_boundary():
    d=frame();d.loc[5,'low']=100.;d.loc[5,'close']=100.5
    assert sig(d)[6]
    assert not sig(d.iloc[:6]).any()
    assert not sig(d.iloc[3:]).any()


def test_rejects_unapproved_parameter():
    with pytest.raises(ValueError):validate_rule('buy',{'type':'ema20_rise_range_touch','rise':.4,'distance':.1})
