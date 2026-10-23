import numpy as np
import pandas as pd
import pytest
from engine import entry_signals


def fixture():
 n=14
 frame=pd.DataFrame({'open':[101.1]*n,'close':[101.2]*n,'high':[101.3]*n,'low':[101.0]*n,
                     'ema20':np.linspace(99.8,100.1,n),'ema5':np.linspace(99.8,100.1,n)},
                    index=pd.date_range('2025-01-02 09:30',periods=n,freq='min',tz='America/New_York'))
 return frame


@pytest.mark.parametrize('period',[5,20])
def test_pullback_waits_for_green_break_of_high(period):
 f=fixture()
 f.loc[f.index[7],['open','close','high','low']]=[100.6,100.2,100.7,100.0]
 f.loc[f.index[8],['open','close','high','low']]=[100.2,100.8,100.9,100.1]
 rule={'type':'trend_pullback','period':period}
 assert np.flatnonzero(entry_signals(f,rule)).tolist()==[9]
 f.loc[f.index[9],['open','close']]=[1,1]
 assert entry_signals(f,rule)[9]
 f.loc[f.index[8],'close']=100.7 # equality with A high fails
 assert not entry_signals(f,rule).any()


def test_falling_ema_rejects_pullback():
 f=fixture();f['ema20']=np.linspace(100.1,99.8,len(f))
 f.loc[f.index[7],['open','close','high','low']]=[100.6,100.2,100.7,100.0]
 f.loc[f.index[8],['open','close']]=[100.2,100.8]
 assert not entry_signals(f,{'type':'trend_pullback','period':20}).any()


def test_high10_uses_prior_highs_and_next_open():
 f=fixture();f.loc[f.index[10],['open','close','high']]=[101.2,101.5,102]
 rule={'type':'trend_high10'}
 assert np.flatnonzero(entry_signals(f,rule)).tolist()==[11]
 f.loc[f.index[10],'close']=101.3
 assert not entry_signals(f,rule).any()
 f.loc[f.index[10],'close']=101.5
 f.loc[f.index[4],'close']=99
 assert not entry_signals(f,rule).any()
