"""Fixed research adaptations of noise areas, ADX filters and late momentum."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import store
from updates.detail_descriptions import MARKET,ENTRY,EXIT,MODEL,LIVE,ema


def specs():
    yield '异常波动上界突破·14日同时刻',{'type':'noise_breakout'},[
        '来源：https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4824172 。以下为本项目只做Call、固定仓位和公共退出的改编，不是论文完整复制。',
        '对今天每个分钟时刻t，用前14个已完成交易日在相同时刻的abs(C_d,t/O_d,09:30−1)取简单均值sigma_t，绝不包含今天。至少14个历史交易日且有前日收盘才有效；不足则跳过当天。',
        '每日上界U_t=max(今日09:30开盘价,前一交易日15:59分钟收盘价)×(1+sigma_t)。不使用当前日最终高低点。VWAP=当日累计[(H+L+C)/3×volume]/累计volume，每日重置，累计量为0无效；现有成交量为Nasdaq单一场所，非全市场。',
        '仅在纽约时间10:00、10:30…15:30检查刚完成的一分钟（如09:59根在10:00结束），要求其C>U且C>VWAP，即下一分钟开盘买入。不要求上一次在上界以下，不要求阳线。每个检查点独立发信号，持仓时忽略，不加仓。']
    for distance in (.05,.10):
        yield f'ADX强上涨过滤·EMA20前10分钟回调<{distance:.2f}',{'type':'adx_ten_touch','distance':distance},[
            '来源：https://www.fidelity.com/viewpoints/active-investor/average-directional-index-adx 。ADX>25及+DI>−DI用于过滤此前已实现的EMA20连续10分钟回调，具体组合为本项目研究假设。',ema(20),
            'ADX14按连续正常时段K线计算，跨日保留状态。Up=H_t−H_(t−1)，Down=L_(t−1)−L_t；+DM=Up仅当Up>Down且Up>0，否则0；−DM=Down仅当Down>Up且Down>0，否则0，相等两者为0。TR=max(H−L,abs(H−C_prev),abs(L−C_prev))。',
            '从第2根开始取首14个TR、+DM、−DM各自算术均值初始化，随后按(13×前值+当前值)/14递推。+DI=100×平滑+DM/平滑TR，−DI同理，平滑TR=0时两者取0。DX=100×abs(+DI−−DI)/(+DI+−DI)，分母0时DX=0。首14个有效DX均值初始化ADX，再按同样Wilder公式递推；第28根K线才有首个ADX。',
            f'当前回调根t之前10个EMA一分钟增量全部严格为正：E_(t−1)>…>E_(t−11)，观察窗必须同日。当根阴线C<O、C≥E，整根距离d=max(L−E,E−H,0)严格<{distance:.2f}美元，差距≤1e−10视为等于门槛而不触发。影线触线或穿线d=0。',
            '同时要求回调根ADX14>25且+DI>−DI；等于不触发。不额外要求ADX抬升，不设EMA累计涨幅。全部在t收盘确认，下一分钟开盘买入。每分钟独立检查，任一指标未预热不触发。']
    yield '早盘正收益·15点30分尾盘动量',{'type':'late_momentum'},[
        '来源：https://www.sciencedirect.com/science/article/pii/S0304405X18301351 。改编为只做Call；原研究早盘收益包括隔夜，不是仅从09:30起算。',
        '使用前一交易日正常时段最后一分钟收盘P和今日09:59分钟收盘C_09:59。定义r=C_09:59/P−1，要求r>0；等于0或没有前日收盘则跳过。该信息10:00已经确定。',
        '满足时只在当日15:30分钟开盘买入一次，不添加下午趋势或VWAP过滤，不引用15:30之后的数据。主比较卖出为现有持有30分钟（15:59根收盘即16:00退出）；同时展示其他11个公共退出作对照，不将它们称为原论文策略。']


def apply():
    for name,rule,steps in specs():
        prose='\n\n'.join([MARKET]+steps+[ENTRY,EXIT,'所有所需时刻缺失或指标无效时跳过。除明确的历史指标与前日价格引用外，信号观察同日，日终取消。全部使用现有12种卖出方法，固定参数，不根据本轮结果调优。',MODEL,LIVE])
        item=next((x for x in store.ideas() if x['name']==name),None)
        if item is None:item=store.save('buy',name,prose)
        elif item['description']!=prose:raise ValueError('Review changed description: '+name)
        if not store.ready(item):store.register(item['id'],rule)
        print(name)

if __name__=='__main__':apply()
