"""RSI14 strictly below ten, without rebound confirmation."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import store
from updates.detail_descriptions import MARKET,ENTRY,EXIT,MODEL,LIVE
from updates.web_research_ideas import specs
NAME='RSI14严格小于10直接买入'


def apply():
    formula=next(steps[0] for name,source,steps in specs() if name=='RSI14超卖后重新站上30')
    prose='\n\n'.join([MARKET,formula,
        '每根当日分钟t收盘后检查RSI14_t<10，严格小于，等于10不触发。沿用已有14周期，不是RSI10，也不是小于30。RSI未预热无效则跳过。',
        '满足后下一分钟开盘买入1张Call，不要求阳线、阴线、重新站回10或突破前高，不等待反弹确认。每分钟独立检查，不只在首次下穿10时触发；已有持仓忽略信号不补买，平仓后若新的检查仍小于10可再次入场。观察与下一根执行限同日，无当日下一根则跳过。',ENTRY,EXIT,
        '分别使用现有12种公共卖出方法，不新增卖出规则。',MODEL,LIVE])
    x=next((x for x in store.ideas() if x['name']==NAME),None)
    if x is None:x=store.save('buy',NAME,prose)
    elif x['description']!=prose:raise ValueError('Review changed description')
    if not store.ready(x):store.register(x['id'],{'type':'rsi14_below10'})
    print(NAME)

if __name__=='__main__':apply()
