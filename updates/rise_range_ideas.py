"""Six user-approved rising EMA20 and candle-range pullbacks."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import store
from updates.detail_descriptions import MARKET, ENTRY, EXIT, MODEL, LIVE, ema


def specs():
    for rise in (.10,.20,.30):
        for distance in (.05,.10):
            rule={'type':'ema20_rise_range_touch','rise':rise,'distance':distance}
            name=f'EMA20五分钟升≥{rise:.2f}·阴线触线距离<{distance:.2f}'
            steps=[MARKET,ema(20),
                '将刚结束的分钟记为t，E为EMA20。要求E_t>E_(t−1)>E_(t−2)>E_(t−3)，即最近连续3个一分钟增量都严格为正；不使用屏幕角度。',
                f'同时要求E_t−E_(t−5)≥{rise:.2f}美元，允许等于；浮点差距≤1e−10美元按相等处理。t至t−5必须全部属于同一交易日，指标未预热或数据不足不触发。',
                '当根t必须为阴线C_t<O_t，且收盘C_t≥E_t（允许等于）。不要求之前5根全部在线上，也不等待后续阳线。',
                f'整根K线与当根EMA20的距离d=max(L_t−E_t,E_t−H_t,0)。若L_t≤E_t≤H_t，表示含影线的整根K线触及或穿过均线，d=0；否则取最近边界到均线的距离。要求d严格<{distance:.2f}美元，等于不触发；浮点差距≤1e−10美元按相等处理。最低价可跌到均线下方，但收盘必须守住均线。',
                '全部条件在t收盘确认，下一分钟开盘买入1张Call。每分钟独立检查；持仓时忽略信号不补买，平仓后可响应新信号，不加仓。没有当日下一根则跳过。',
                ENTRY,EXIT,'退出分别使用现有12种公共卖出方法，不额外附加均线止损。',MODEL,LIVE]
            yield name,rule,'\n\n'.join(steps)


def apply():
    for name,rule,prose in specs():
        item=next((x for x in store.ideas() if x['name']==name),None)
        if item is None:item=store.save('buy',name,prose)
        elif item['description']!=prose:raise ValueError('Existing description changed; review first: '+name)
        if not store.ready(item):store.register(item['id'],rule)
        print(name)

if __name__=='__main__':apply()
