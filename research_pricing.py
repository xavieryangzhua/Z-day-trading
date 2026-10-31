"""Versioned historical research pricing. Synthetic contracts, never observed IV."""
import pandas as pd
from option_pricing import historical_volatility, european_call, YEAR_SECONDS

PARAMETERS = dict(pricing_model='synthetic_atm_hv20_v1', symbol='SPY',
    valuation='BSM; American non-dividend Call equivalent', volatility='prior 20 daily log returns, 21 prior closes, frozen per trade; NOT IV',
    strike='entry underlying open, synthetic ATM, not listed strike',
    expiry='same session final minute close; synthetic, actual expiration availability not verified',
    multiplier=100, rate=0., dividend_yield=0., round_trip_fee=2.,
    return_denominator='entry model quote * 100', spread=0., slippage=0.,
    overlapping=False, direction='call', entry_execution='minute_open', exit_execution='minute_close',
    insufficient_volatility='skip session, no constant fallback', clock='ACT/365')


def prepare_sessions(bars):
    groups=list(bars.groupby(bars.index.date))
    closes=pd.Series([float(d.close.iloc[-1]) for _,d in groups],index=pd.DatetimeIndex([date for date,_ in groups]))
    result=[]
    for n,(_,day) in enumerate(groups):
        if n<21:continue
        hv=historical_volatility(closes,day.index[0])
        result.append((day,hv))
    return result


class trade_pricer:
    def __init__(self,day,entry,hv,symbol):
        self.day=day
        self.strike=float(day.open.iloc[entry])
        self.expiry=day.index[-1]+pd.Timedelta(minutes=1)
        self.sigma=hv['volatility']
        self.entry_quote=european_call(self.strike,self.strike,(self.expiry-day.index[entry]).total_seconds()/YEAR_SECONDS,self.sigma)
        self.cache={}
        self.details=dict(option_entry=self.entry_quote,entry_contract_value=self.entry_quote*100,
            strike=self.strike,expiry=self.expiry.isoformat(),volatility=self.sigma,
            volatility_source=hv,pricing_model=PARAMETERS['pricing_model'],synthetic_contract=True,
            exercise='european' if symbol=='SPX' else 'american',multiplier=100,round_trip_fee=2.)
    def __call__(self,index):
        if index not in self.cache:
            t=self.day.index[index]+pd.Timedelta(minutes=1)
            self.cache[index]=european_call(float(self.day.close.iloc[index]),self.strike,(self.expiry-t).total_seconds()/YEAR_SECONDS,self.sigma)
        return self.cache[index]
