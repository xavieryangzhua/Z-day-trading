import numpy as np
import pandas as pd
import pytest
from engine import entry_signals


def frame(rows):
    return pd.DataFrame(rows, columns=['open', 'close', 'high', 'low', 'ema5'], dtype=float)


def red_frame(n=9):
    return frame([[100,99,101,98,100]]*n + [[99,99.25,100,98,100]]*2
                 + [[100,99,101,98,100]]*15)


def green_frame(k=2):
    return frame([[100,103.5,104,99,101]] + [[103,102.5,103,102.25,102.25]]*k
                 + [[102.5,103.5,104,102.5,102.5]] + [[103,103,104,102,103]]*2)


def signals(d, rule):
    return np.flatnonzero(entry_signals(d, rule)).tolist()


@pytest.mark.parametrize('n',[9,10,12])
def test_red_once_after_twelfth(n):
    assert signals(red_frame(n), {'type':'double_red_run'}) == [n+14]


@pytest.mark.parametrize('index,value',[(0,100),(9,99.26),(10,99),(15,100)])
def test_red_interruption(index,value):
    d=red_frame();d.loc[index,'close']=value
    assert signals(d, {'type':'double_red_run'}) == []


def test_red_not_enough_or_end_of_day():
    assert signals(red_frame(8), {'type':'double_red_run'}) == []
    assert signals(red_frame().iloc[:23], {'type':'double_red_run'}) == []


@pytest.mark.parametrize('k',[2,3])
@pytest.mark.parametrize('dollars',[2,3])
def test_green_confirm_next_open(k,dollars):
    d=green_frame(k)
    assert signals(d, {'type':'large_green_pullback','dollars':dollars}) == [k+2]
    d.loc[k+2:,'close']=0
    assert signals(d, {'type':'large_green_pullback','dollars':dollars}) == [k+2]


@pytest.mark.parametrize('k',[1,4])
def test_green_wrong_length(k):
    assert signals(green_frame(k), {'type':'large_green_pullback','dollars':2}) == []


@pytest.mark.parametrize('row,col,value',[(0,'close',102),(1,'close',99),(2,'low',102.14),(2,'ema5',float('nan')),(3,'close',103),(3,'ema5',102.25),(2,'close',103)])
def test_green_rejects_failed_conditions(row,col,value):
    d=green_frame();d.loc[row,col]=value
    assert signals(d, {'type':'large_green_pullback','dollars':2}) == []


def test_green_no_next_bar():
    assert signals(green_frame().iloc[:4], {'type':'large_green_pullback','dollars':2}) == []
