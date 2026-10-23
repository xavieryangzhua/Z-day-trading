"""Ten prior consecutive rising EMA20 minutes, then bearish pullback."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import store
from updates.detail_descriptions import MARKET,ENTRY,EXIT,MODEL,LIVE,ema


def specs():
    for distance in (.05,.10):
        name=f'EMA20前10分钟连续上升·回调距离<{distance:.2f}'
        rule={'type':'ema20_ten_rising_touch','distance':distance}
        steps=[MARKET,ema(20),
               '当前回调根记为t。只检查它之前的10个一分钟EMA20增量，要求E_(t−1)>E_(t−2)>…>E_(t−11)，全部10次比较严格上升；任何一次走平或下降都不满足。不是只比较起点和终点，也不要求10根价格K线都为阳线。不设累计美元涨幅或角度门槛。',
               '这11个EMA观测点和回调根必须都属于同一交易日。EMA跨日保持连续，但观察窗口不跨日；预热或前置数据不足则跳过。当前回调根不计入前10个增量。',
               '回调根t必须为阴线C_t<O_t，且C_t≥E_t，允许收盘等于EMA20；不要求之前价格都在线上。',
               f'距离d=max(L_t−E_t,E_t−H_t,0)，整根K线（含影线）触及或穿过EMA20时d=0，否则取最近边界的距离。要求d严格<{distance:.2f}美元，距离与门槛相差≤1e−10美元视为相等，不触发。允许下影线穿线，但收盘必须守住EMA20。',
               't收盘满足全部条件后下一分钟开盘买入，不等阳线确认。每分钟独立滚动检查；持仓时忽略信号不补买，平仓后可响应新的信号，没有当天下一根则跳过。',
               ENTRY,EXIT,'沿用现有12种卖出方法分别回测，不额外附加均线退出。',MODEL,LIVE]
        yield name,rule,'\n\n'.join(steps)


def apply():
    for name,rule,prose in specs():
        item=next((x for x in store.ideas() if x['name']==name),None)
        if item is None:item=store.save('buy',name,prose)
        elif item['description']!=prose:raise ValueError('Review changed description: '+name)
        if not store.ready(item):store.register(item['id'],rule)
        print(name)

if __name__=='__main__':apply()
