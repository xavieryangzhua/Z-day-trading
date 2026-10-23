import numpy as np
import pandas as pd
from engine import entry_signals


def test_below_ten_strict_and_shifted():
    d=pd.DataFrame({'rsi14':[np.nan,10.,9.99,0.,11.,2.]})
    assert np.flatnonzero(entry_signals(d,{'type':'rsi14_below10'})).tolist()==[3,4]
    assert np.flatnonzero(entry_signals(d,{'type':'rsi14_below3'})).tolist()==[4]


def test_below_ten_no_next_day_or_future():
    d=pd.DataFrame({'rsi14':[9.,11.,11.]})
    assert entry_signals(d,{'type':'rsi14_below10'}).tolist()==[False,True,False]
    d.loc[1:,'rsi14']=0
    assert entry_signals(d,{'type':'rsi14_below10'})[1]
    assert not entry_signals(d.iloc[:1],{'type':'rsi14_below10'}).any()
