"""Standalone synthetic Call repricing, separate from existing research/Paper accounts.

European: Black–Scholes–Merton with continuous dividend yield.
American: CRR binomial tree with early exercise (continuous-yield approximation).
Prices/Greeks are per underlying unit; contract values explicitly use multiplier.
No market data, contract discovery, account mutations or broker orders here.
"""
from dataclasses import dataclass
from datetime import datetime
import math
import numpy as np

YEAR_SECONDS = 365 * 24 * 60 * 60


def normal_cdf(x):
    return .5 * math.erfc(-x / math.sqrt(2))


def _validate(spot, strike, years, volatility, rate, dividend):
    if not all(math.isfinite(x) for x in (spot,strike,years,volatility,rate,dividend)):
        raise ValueError('Pricing inputs must be finite')
    if min(spot,strike,volatility) <= 0 or years < 0:
        raise ValueError('Spot, strike, volatility must be positive; years cannot be negative')


def european_call(spot, strike, years, volatility, rate=0., dividend=0.):
    _validate(spot,strike,years,volatility,rate,dividend)
    if years == 0:
        return max(spot-strike,0.)
    width=volatility*math.sqrt(years)
    d1=(math.log(spot/strike)+(rate-dividend+.5*volatility**2)*years)/width
    d2=d1-width
    return max(0.,spot*math.exp(-dividend*years)*normal_cdf(d1)-strike*math.exp(-rate*years)*normal_cdf(d2))


def european_greeks(spot, strike, years, volatility, rate=0., dividend=0.):
    """Theta per CALENDAR minute per unit; vega per 1 percentage point IV."""
    _validate(spot,strike,years,volatility,rate,dividend)
    if years == 0:
        return dict(delta=1. if spot>strike else 0. if spot<strike else .5,
                    gamma=None,theta_per_minute=None,vega_per_iv_point=None)
    root=math.sqrt(years);d1=(math.log(spot/strike)+(rate-dividend+.5*volatility**2)*years)/(volatility*root)
    d2=d1-volatility*root; density=math.exp(-.5*d1*d1)/math.sqrt(2*math.pi)
    discq=math.exp(-dividend*years);discr=math.exp(-rate*years)
    theta=(-spot*discq*density*volatility/(2*root)
           -rate*strike*discr*normal_cdf(d2)+dividend*spot*discq*normal_cdf(d1))
    return dict(delta=discq*normal_cdf(d1), gamma=discq*density/(spot*volatility*root),
                theta_per_minute=theta/(365*24*60),
                vega_per_iv_point=spot*discq*density*root*.01)


def call_price(spot,strike,years,volatility,rate=0.,dividend=0.,exercise='european',steps=501):
    _validate(spot,strike,years,volatility,rate,dividend)
    if exercise not in ('european','american'):
        raise ValueError('Unknown exercise style')
    if exercise=='european' or years==0:
        return european_call(spot,strike,years,volatility,rate,dividend)
    # No early-exercise benefit for a non-dividend Call with nonnegative rates.
    if dividend==0 and rate>=0:
        return european_call(spot,strike,years,volatility,rate,dividend)
    if type(steps) is not int or steps<50:
        raise ValueError('At least 50 CRR steps required')
    dt=years/steps;up=math.exp(volatility*math.sqrt(dt));down=1/up
    prob=(math.exp((rate-dividend)*dt)-down)/(up-down)
    if not 0<=prob<=1:
        raise ValueError('Invalid CRR probability; increase steps or review inputs')
    spots=spot*np.exp((2*np.arange(steps+1)-steps)*math.log(up))
    values=np.maximum(spots-strike,0.)
    discount=math.exp(-rate*dt)
    for _ in range(steps,0,-1):
        values=discount*((1-prob)*values[:-1]+prob*values[1:])
        spots=spots[:-1]*up
        values=np.maximum(values,spots-strike)
    return float(values[0])


def implied_volatility(price,spot,strike,years,rate=0.,dividend=0.,exercise='european'):
    """Calibrate from an independently observed per-unit option price, not a budget."""
    if not math.isfinite(price) or price<=0 or years<=0:
        raise ValueError('Positive option quote and remaining time required')
    lo,hi=1e-4,5.
    def value(sigma):
        return call_price(spot,strike,years,sigma,rate,dividend,exercise)
    # American near-zero vol can violate a coarse CRR grid; use a wider low bracket.
    if exercise=='american' and (dividend!=0 or rate<0):lo=.01
    if not value(lo)<price<value(hi):
        raise ValueError('Quote outside supported IV bracket; no fabricated volatility')
    for _ in range(70):
        mid=(lo+hi)/2
        if value(mid)<price:lo=mid
        else:hi=mid
    return (lo+hi)/2


def historical_volatility(daily_closes, asof, sessions=20):
    """Daily close-to-close HV proxy, prior completed dates only. Not option IV."""
    import pandas as pd
    if sessions<2 or not daily_closes.index.is_monotonic_increasing or daily_closes.index.has_duplicates:
        raise ValueError('Ordered unique daily closes and >=2 returns required')
    dates=daily_closes.index.date
    values=daily_closes[dates<pd.Timestamp(asof).date()].iloc[-(sessions+1):].astype(float)
    if len(values)!=sessions+1 or not np.isfinite(values).all() or (values<=0).any():
        raise ValueError('Insufficient or invalid completed daily closes; no fallback constant')
    sigma=float(np.log(values).diff().dropna().std(ddof=1)*math.sqrt(252))
    if not math.isfinite(sigma) or sigma<=0:
        raise ValueError('Cannot estimate positive volatility')
    return dict(volatility=sigma,source='prior_20_session_close_to_close_HV_proxy' if sessions==20 else 'daily_HV_proxy',
                sessions=sessions,from_date=str(values.index[0]),through_date=str(values.index[-1]),
                annualization='sqrt(252), sample std; BSM clock ACT/365')


@dataclass(frozen=True)
class CallContract:
    symbol: str
    strike: float
    expiry: datetime
    exercise: str
    multiplier: int=100
    synthetic: bool=True

    def mark(self,spot,asof,volatility,rate=0.,dividend=0.):
        if self.expiry.tzinfo is None or asof.tzinfo is None:
            raise ValueError('Timezone-aware expiry and valuation time required')
        if asof>self.expiry:
            raise ValueError('Past expiry: supply actual settlement separately, not a later spot')
        if type(self.multiplier) is not int or self.multiplier<=0:
            raise ValueError('Positive explicit contract multiplier required')
        years=(self.expiry-asof).total_seconds()/YEAR_SECONDS
        price=call_price(spot,self.strike,years,volatility,rate,dividend,self.exercise)
        result=dict(symbol=self.symbol,underlying_price=spot,strike=self.strike,expiry=self.expiry.isoformat(),
                    asof=asof.isoformat(),remaining_minutes=years*365*24*60,volatility=volatility,
                    option_quote=price,contract_value=price*self.multiplier,multiplier=self.multiplier,
                    exercise=self.exercise,synthetic_contract=self.synthetic,
                    model='BSM' if self.exercise=='european' or (dividend==0 and rate>=0) else 'CRR_501',
                    rate=rate,dividend_yield=dividend)
        # Do not pretend European sensitivities are American-tree Greeks.
        if self.exercise=='european' or (dividend==0 and rate>=0):
            result['greeks_per_unit']=european_greeks(spot,self.strike,years,volatility,rate,dividend)
        return result
