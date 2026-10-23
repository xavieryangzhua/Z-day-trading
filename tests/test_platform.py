import numpy as np
import pandas as pd
import pytest
from engine import entry_signals

RULE={'type':'impulse_platform_breakout'}


def frame():
 # Only impulse ending at 5 qualifies: preceding dummy prevents an earlier one,
 # subsequent consolidation has two red bars and breaks later five-bar impulses.
 f=pd.DataFrame({'open':[100,100,100.3,100.7,101,101.4,102,101.8,101.7,101.6,101.6,101.6,103,103],
                 'close':[100,100.3,100.7,101,101.4,102,101.8,101.6,101.7,101.6,101.6,101.6,103,103],
                 'high':[100,100.4,100.8,101.1,101.5,102.1,102,101.9,101.8,101.8,101.8,101.8,103.1,103.1],
                 'low':[100,99.9,100.2,100.6,100.9,101.3,101.5,101.4,101.5,101.5,101.5,101.5,102.9,102.9],
                 'ema20':[99.0]+[99.1]*13},dtype=float)
 return f


@pytest.mark.parametrize('trigger',[9,10,11])
def test_can_trigger_on_any_of_three_wait_bars(trigger):
 f=frame();f.loc[trigger,['open','close','high']]=[101.7,102.2,102.3]
 assert np.flatnonzero(entry_signals(f,RULE)).tolist()==[trigger+1]
 f.loc[trigger+1:,'close']=1 # future prices cannot change the already emitted entry
 assert entry_signals(f,RULE)[trigger+1]


def test_expiry_and_strict_breakout():
 f=frame();f.loc[12,['open','close']]=[101.7,102.2]
 assert not entry_signals(f,RULE).any()
 f.loc[9,['open','close']]=[101.7,102.0] # equals ceiling
 assert not entry_signals(f,RULE).any()


@pytest.mark.parametrize('field,value',[('low',100.99),('close',99.1)])
def test_consolidation_retrace_or_ema_failure(field,value):
 f=frame();f.loc[9,['open','close']]=[101.7,102.2]
 f.loc[7,field]=value
 assert not entry_signals(f,RULE).any()


def test_cancellation_is_not_revived_by_later_breakout():
 f=frame();f.loc[9,'close']=101.3 # below consolidation low 101.4
 f.loc[10,['open','close']]=[101.7,102.2]
 assert not entry_signals(f,RULE).any()
 f=frame();f.loc[9,'ema20']=102 # below EMA even though above floor
 f.loc[10,['open','close']]=[101.7,102.2]
 assert not entry_signals(f,RULE).any()


def test_only_first_breakout_and_no_entry_past_session():
 f=frame();f.loc[9:11,'close']=102.2
 assert np.flatnonzero(entry_signals(f,RULE)).tolist()==[10]
 assert not entry_signals(f.iloc[:10],RULE).any()


def test_retrace_boundary_inclusive_and_three_greens_required():
 f=frame();f.loc[7,'low']=101 # midpoint=(102.1+99.9)/2
 f.loc[9,['open','close']]=[101.7,102.2]
 assert entry_signals(f,RULE)[10]
 f.loc[[1,2,3],'close']=f.loc[[1,2,3],'open']
 assert not entry_signals(f,RULE).any()
