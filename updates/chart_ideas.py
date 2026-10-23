"""Save user chart hypotheses as pending ideas; provisional thresholds are explicit."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import store
from updates.detail_descriptions import MARKET, ENTRY, EXIT, MODEL, LIVE, ema


def drafts():
    common = [MARKET, ENTRY, EXIT, MODEL, '退出使用现有公共卖出方法分别评估，不新增卖出规则。当前仅保存待实现想法，未实现、未回测；截图只提供形态灵感，不能据此验证实际信号或收益。', LIVE]
    red = [
        '来源：用户图1，连续下跌被两根小阳线短暂打断后再次连续下跌。小阳线暂定每根实体不超过0.25美元，属于研究参数，并非从截图精确测得。',
        '按当日时间顺序识别：首先连续至少9根阴线；这一段可超过9根，直到紧接的第一根阳线出现。十字星会打断阴线计数。',
        '随后必须紧接恰好2根小阳线B1、B2，各自满足0<C−O≤0.25美元。任何十字星、阴线或过大的阳线使这次候选失效；不允许第三根阳线插入。',
        'B2之后必须立即开始连续12根阴线D1…D12，中间不能夹杂阳线或十字星。D12收盘确认后，下一根开盘买入。无需额外要求D12低于第一段低点，也不增加止跌阳线确认。',
        '同一第二段下跌只在第12根结束时触发一次，第13根及以后不重复触发；即使持仓导致信号被忽略也不补买。失效后重新滚动识别完整序列，数据不足或跨日候选取消。此规则尝试抄底，不表示下跌已经结束。',
    ]
    yield '两段急跌：9阴＋2小阳＋12阴', '\n\n'.join(red + common)
    for threshold in (2, 3):
        steps = [
            f'来源：用户图2。单根大阳线后2或3根回调到均线附近，再次转强。此版本大阳线实体严格大于{threshold}美元；均线暂定EMA5，附近沿用0.10美元；这些选择为明确的研究初稿。',
            ema(5),
            f'先识别一根已完成阳线A，要求C_A−O_A>{threshold}美元，使用单根实体，不是最高减最低，也不是多根累计上涨。',
            '紧接A必须出现连续恰好2或3根阴线B1…Bk（k只能为2或3），所有回调根收盘均须≥O_A。之后紧接第一根阳线记为确认根T。若回调只有1根、超过3根、夹杂十字星或任一收盘<O_A，该候选取消。',
            '最后一根回调Bk的最低价需满足abs(L_Bk−EMA5_Bk)≤0.10美元，且C_Bk≥EMA5_Bk。只检查最后一根回调的均线距离，不要求所有回调根都触及均线。',
            '确认根T必须C_T>O_T、C_T>H_Bk、C_T>EMA5_T且EMA5_T>EMA5_Bk，四项同时满足才触发。T失败立即取消，不继续等待。确认后下一根开盘买入，不在大阳线A结束时追入。',
            '每根大阳线A最多触发一次；不同候选独立，同一分钟多个候选合并为一个信号。缺少预热或前置数据不触发；全部K线必须在同一天，收盘前没有下一根则跳过。2美元版本与3美元版本可包含相同信号，作为不同想法单独评估。',
        ]
        yield f'单根阳线涨超{threshold}美元后回调EMA5确认', '\n\n'.join(steps + common)


def apply():
    store.initialize()
    existing = {x['name'] for x in store.ideas()}
    for name, description in drafts():
        if name in existing:
            print('Already present:', name)
            continue
        item = store.save('buy', name, description)
        assert not item['realize'] and item['implementation'] is None
        print('Saved pending:', name, item['id'])

if __name__ == '__main__':
    apply()
