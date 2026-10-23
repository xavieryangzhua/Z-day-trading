"""Fixed breakout and day-to-date Fibonacci hypotheses with ordinary-ratio controls."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import store
from updates.detail_descriptions import MARKET,ENTRY,EXIT,MODEL,LIVE,ema


def specs():
    for anchor in ('window20','day'):
        for ratio in (.382,.4,.5,.6,.618):
            label='前20根突破' if anchor=='window20' else '当日高低点'
            name=f'回撤{ratio*100:g}%·{label}'+('·对照' if ratio in (.4,.6) else '')
            rule={'type':'fibonacci_pullback','anchor':anchor,'ratio':ratio}
            definition=(
                '候选根A收盘必须严格突破此前20根当日K线的最高价，且EMA20_A>EMA20_(A−5)。L取此前20根的最低价（不含A），H取A最高价。'
                if anchor=='window20' else
                '候选根A前需至少20根当日已结束K线，A收盘必须严格突破当日开盘以来此前所有K线最高价，且EMA20_A>EMA20_(A−5)。L取当日开盘至A的最低价，H取同区间最高价即A最高价。若A最低价严格低于此前当日最低价，则取消候选，避免同根同时创高低点时无法判断顺序；相等允许。这里只用截至A的当日高低点，绝不使用收盘后才知道的全天最终极值。')
            steps=[MARKET,ema(20),definition,
                f'在A收盘冻结H、L及回撤位F=H−{ratio}×(H−L)。要求H>L；之后不随价格更新本候选的水平。50%是中点回撤，40%/60%为普通比例对照；不把这些比例都称作斐波那契比率。',
                '只观察紧接A的最多10根K线B1…B10，不含A。每根先检查取消：最低价<L或最高价>H则立即取消候选，允许等于。若同根既触线又越界，取消优先，分钟OHLC不足以判断先后。',
                '未取消时，首次出现最低价≤F且收盘>F即确认回调收回；不额外要求阴线或阳线，不限定距F的美元数。只有触及但收盘≤F不买，仍可等待剩余分钟，直至取消或超时。',
                '确认根结束后下一分钟开盘买入，单个候选只触发一次，持仓导致忽略也不补买。10根没有确认则过期；各阶段同日、数据不足或EMA未预热不触发，当日无下一根则跳过。',
                '每次新的合格突破可建立独立候选，即使已有其他候选。每个候选独立冻结边界与计时；同一分钟多个候选触发合并为一个信号。全部组合独立回测、不加仓、不重叠。',
                ENTRY,EXIT,'分别配对现有12种卖出方法，不额外增加回撤位止损或延伸位止盈。',MODEL,LIVE]
            yield name,rule,'\n\n'.join(steps)


def apply():
    for name,rule,prose in specs():
        item=next((x for x in store.ideas() if x['name']==name),None)
        if item is None:item=store.save('buy',name,prose)
        elif item['description']!=prose:raise ValueError('Review changed description: '+name)
        if not store.ready(item):store.register(item['id'],rule)
        print(name)

if __name__=='__main__':apply()
