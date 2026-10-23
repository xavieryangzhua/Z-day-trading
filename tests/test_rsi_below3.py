import numpy as np
import pandas as pd
from engine import entry_signals


def test_strict_threshold_nan_and_next_open():
    d=pd.DataFrame({'rsi14':[np.nan,3,2.99,0,4,2.]})
    assert np.flatnonzero(entry_signals(d,{'type':'rsi14_below3'})).tolist()==[3,4]


def test_no_signal_from_prior_day_or_future():
    d=pd.DataFrame({'rsi14':[2.,4.,4.]})
    assert entry_signals(d,{'type':'rsi14_below3'}).tolist()==[False,True,False]
    d.loc[1:,'rsi14']=0
    assert entry_signals(d,{'type':'rsi14_below3'})[1]
    assert not entry_signals(d.iloc[:1],{'type':'rsi14_below3'}).any()
