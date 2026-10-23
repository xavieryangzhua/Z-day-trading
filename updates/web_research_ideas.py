"""Source-linked research drafts, not implemented signals or performance claims."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import store
from updates.detail_descriptions import MARKET,ENTRY,EXIT,MODEL,LIVE,ema
FIB='https://www.schwab.com/learn/story/using-fibonacci-retracement-levels-on-thinkorswim'
ORB='https://onlinelibrary.wiley.com/doi/10.1002/9781119203933.ch11'
BB='https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/bollinger-bands'
SQ='https://www.ig.com/en/trading-strategies/what-are-bollinger-bands-and-how-do-you-use-them-in-trading--200129'
RSI='https://www.fidelity.com/viewpoints/active-investor/how-to-use-RSI'
ANCHOR='候选根A收盘严格突破此前20根当日K线最高价且EMA20_A>EMA20_(A−5)。L取此前20根最低价（不含A），H取A最高价，要求H>L；A收盘后固定这些值。前置数据不足或EMA未预热跳过。'
BANDS='布林带使用连续正常时段收盘价，跨日保留历史；M为最近20根收盘简单均值，sigma为同窗口总体标准差ddof=0，U=M+2sigma，D=M−2sigma，W=(U−D)/M。满20根才有效；收盘为正。每根使用当根收盘计算的带值。'


def specs():
    yield '斐波那契23.6%浅回撤收回',FIB,[ema(20),ANCHOR,
        '固定F=H−0.236×(H−L)。只观察A之后10根；每根先检查最低价<L或最高价>H，任一成立立即取消，等于允许。未取消时首次L_t≤F且C_t>F触发，不限定阴阳线。收盘≤F可继续等剩余根。10根无确认取消。每个候选一次，重叠候选独立，信号同分钟合并。']
    yield '斐波那契61.8%与EMA20重合回调',FIB,[ema(20),ANCHOR,
        '固定F=H−0.618×(H−L)。只观察随后10根；最低价<L或最高价>H先取消。未取消时要求abs(F−EMA20_t)≤0.10美元、L_t≤F、C_t>F且C_t≥EMA20_t，首次同时满足触发。允许均线距离等于0.10；各价格比较浮点误差≤1e−10视为相等。首次触线但不满足其他条件仍可等剩余根；10根超时取消。候选一次，候选间独立。']
    yield '斐波那契127.2%延伸突破回踩',FIB,[ema(20),ANCHOR,
        '使用两点范围延伸定义X=L+1.272×(H−L)，不是三点投射C+1.272×AB。X在A收盘固定。随后最多20根等待首次C_B>X；等待中L_t<L先取消，创H以上高点不取消。',
        'B收盘突破X后只观察紧接5根，L_t<L先取消；未取消时首次L_t≤X且C_t>X确认回踩，下一根开盘买入。突破根B自身不算回踩，不额外要求阴阳线。任一阶段超时取消；每个候选只触发一次，多个候选独立。这里将延伸位用于买入参考，不增加止盈规则。']
    for minutes in (5,15):
        yield f'开盘{minutes}分钟区间首次向上突破',ORB,[
            f'按纽约时间固定开盘09:30起前{minutes}根完整分钟K线，H_OR取最高价，L_OR取最低价；必须等整个开盘区间结束才使用，整日固定不更新。',
            '从开盘区间后第一根开始观察，仅到11:00之前开盘的分钟根（最晚10:59根收盘）。首次C_t>H_OR且C_(t−1)≤H_OR触发，下一分钟开盘买入。没有量能、VWAP或均线过滤，不要求阳线。每天最多一次信号，即使持仓而跳过也不补买；未触发则当天放弃。区间缺根则当天跳过。']
    yield '布林带收窄后向上突破',BB+'\n'+SQ,[BANDS,
        '将当前根记t。要求W_(t−1)≤之前60根带宽W_(t−61)…W_(t−2)的20%分位数，分位数采用线性插值。带宽参考窗口可跨正常时段交易日，全部值须已有效。',
        '要求C_t>U_t、C_(t−1)≤U_(t−1)、W_t>W_(t−1)，且C_t严格超过此前10根当日最高价。t及这10根须同日。每根独立检查，无等待阶段；符合后下一根开盘买入。不符合则无信号，后续新穿越可触发，持仓期间忽略。']
    yield '布林带下轨跌出后收回',BB,[BANDS,
        '当日相邻A、B两根，要求C_A<D_A，紧接B为阳线C_B>O_B且C_B>D_B。A收盘等于下轨不算跌出，B等于下轨不算收回；B失败此候选取消，不延长等待。B收盘确认后下一根开盘买入。无趋势过滤；每个新的A可独立产生候选。']
    yield 'RSI14超卖后重新站上30',RSI,[
        '使用正常时段收盘价连续计算Wilder RSI14，跨日保留状态。Δ=C_t−C_(t−1)，G=max(Δ,0)，Loss=max(−Δ,0)。首14个有效变动分别取简单平均AG、AL，后续AG=(13×AG_prev+G)/14，AL同理。AL>0时RSI=100−100/(1+AG/AL)；AL=0且AG>0取100；AG=AL=0取50。至少15根收盘后有效。',
        '当日相邻A、B要求RSI_A<30且RSI_B≥30，同时B为阳线C_B>O_B、C_B>H_A。B收盘确认后下一根开盘买入。RSI仅跌到30以下不买；B失败不补买，之后必须再次出现新的下穿后上穿条件。无趋势过滤；前置数据不足跳过。']


def drafts():
    for name,source,steps in specs():
        text=['研究来源（检索日期2026-10-23）：'+source,
              '来源提供通用指标或方法思路；这里的分钟窗口、阈值、确认、超时和Call执行条件为本项目明确设定的待测试版本，不是来源宣称有效的完整策略，也不是实时热度排名。',MARKET]+steps+[
              '除指标跨日预热的明确约定外，候选建立、等待、确认均限同一交易日。日终未确认候选取消。所有信号在已结束分钟计算，确认后当日无下一根则不买。',ENTRY,EXIT,
              '此条为买入研究想法，仅保存待实现，realize=false。未来实现后配对现有12种卖出方法；目前没有新增卖出规则或回测成绩。',MODEL,LIVE]
        yield name,'\n\n'.join(text)


def apply():
    names={x['name'] for x in store.ideas()}
    for name,prose in drafts():
        if name in names:
            print('Already exists:',name);continue
        x=store.save('buy',name,prose)
        assert not x['realize'] and x['implementation'] is None
        print('Saved pending:',name)

if __name__=='__main__':apply()
