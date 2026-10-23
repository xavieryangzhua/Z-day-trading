import numpy as np
import pandas as pd
import pytest
from engine import entry_signals


def angle_frame():
    d=pd.DataFrame({'open':[105.]*8,'close':[104.]*8,'low':[103.]*8,'high':[106.]*8,
                    'ema20':[100.,100.,100.,100.,100.,103.,100.,100.]})
    return d


@pytest.mark.parametrize('distance',[.05,.1])
def test_angle_next_open(distance):
    d=angle_frame()
    assert np.flatnonzero(entry_signals(d,{'type':'ema20_angle_touch','distance':distance})).tolist()==[6]
    d.loc[6:,'close']=1000
    assert entry_signals(d,{'type':'ema20_angle_touch','distance':distance})[6]


@pytest.mark.parametrize('distance',[.05,.1])
def test_angle_strict_distance(distance):
    d=angle_frame();d.loc[5,'low']=103-distance
    assert not entry_signals(d,{'type':'ema20_angle_touch','distance':distance}).any()


def test_angle_equal_30_and_short_day():
    d=angle_frame();d.loc[5,'ema20']=100+5*np.tan(np.deg2rad(30));d.loc[5,'low']=d.loc[5,'ema20']
    assert not entry_signals(d,{'type':'ema20_angle_touch','distance':.1}).any()
    assert not entry_signals(angle_frame().iloc[:6],{'type':'ema20_angle_touch','distance':.1}).any()


def impulse():
    return pd.DataFrame({'open':[100.,103.,102.,101.,101.,101.],
                         'close':[103.,102.,101.,100.,101.,101.],
                         'low':[99.,101.,100.,99.,100.,100.],
                         'high':[104.,104.,103.,102.,102.,102.],
                         'ema5':[101.,101.,100.,99.,100.,100.]})


@pytest.mark.parametrize('distance',[.05,.1])
def test_first_touch_consumes_even_if_third_touches(distance):
    assert np.flatnonzero(entry_signals(impulse(),{'type':'green2_touch','distance':distance})).tolist()==[3]


def test_third_touch_and_close_below_support_allowed():
    d=impulse();d.loc[2,'ema5']=101;d.loc[3,'close']=99.5;d.loc[3,'ema5']=99.51;d.loc[3,'low']=99.49
    assert np.flatnonzero(entry_signals(d,{'type':'green2_touch','distance':.05})).tolist()==[4]


@pytest.mark.parametrize('distance',[.05,.1])
def test_green_equal_distance_excluded(distance):
    d=impulse();d.loc[2,'low']=100-distance;d.loc[3,'low']=99-distance
    assert not entry_signals(d,{'type':'green2_touch','distance':distance}).any()


@pytest.mark.parametrize('row,col,value',[(0,'close',102),(1,'close',103),(2,'close',102)])
def test_invalid_impulse_or_broken_run(row,col,value):
    d=impulse();d.loc[row,col]=value
    assert not entry_signals(d,{'type':'green2_touch','distance':.1}).any()


def test_unwarmed_or_end_of_day():
    d=impulse();d['ema5']=np.nan
    assert not entry_signals(d,{'type':'green2_touch','distance':.1}).any()
    assert not entry_signals(impulse().iloc[:3],{'type':'green2_touch','distance':.1}).any()
