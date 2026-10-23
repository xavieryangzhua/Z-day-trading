"""User-confirmed angle and direct pullback variants, with exact definitions."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import store
from updates.detail_descriptions import MARKET, ENTRY, EXIT, MODEL, LIVE, ema


def specs():
    for kind in ('ema20_angle_touch','green2_touch'):
        for distance in (.05,.10):
            name = (f'EMA20上升超30度·回调距离<{distance:.2f}美元' if kind=='ema20_angle_touch'
                    else f'单根涨超2美元·回调EMA5距离<{distance:.2f}美元')
            common = [MARKET, ema(20 if kind=='ema20_angle_touch' else 5)]
            if kind=='ema20_angle_touch':
                steps = [
                    '在每根当日分钟线t收盘检查。固定图形比例为横向1分钟与纵向1美元等长；角度theta=atan((EMA20_t−EMA20_(t−5))/5)×180/pi。要求theta严格>30度，等价于EMA20在5分钟内上涨严格超过5×tan(30度)≈2.886751346美元。不是截图缩放后的视觉角度，也不要求5个单分钟都上涨。',
                    '当前根必须为阴线C_t<O_t，且abs(L_t−EMA20_t)严格小于距离门槛。此处距离用最低价，不用收盘价；允许最低价在均线任意一侧，不额外要求收盘守住均线，也不需要此前5根收盘在线上。',
                    '当根收盘确认后下一分钟开盘买入；不等待阳线。每分钟独立检查，持仓时忽略信号，平仓后可响应新信号。t与t−5必须在同一天；前置数据或EMA预热不足不触发。',
                ]
            else:
                steps = [
                    '先识别已结束的单根大阳线A，要求C_A−O_A严格>2美元；不是最高减最低，不是多根累计涨幅。',
                    '紧接A观察最多3根K线B1、B2、B3，必须从B1开始连续阴线C<O；阳线或十字星立即取消候选。只在第2或第3根阴线结束时检查abs(L_Bk−EMA5_Bk)严格小于距离门槛。',
                    'B2符合距离就确认信号并结束该候选，不需要等待B3；B2不符合则只再检查B3。B3仍不符合则取消。确认后下一根开盘买入。与旧版不同：不等阳线确认，不要求回调收盘守住大阳线开盘价或EMA5，也不要求EMA5抬升。',
                    '每个大阳线候选最多触发一次，即使持仓导致信号被忽略也不补买；不同候选独立，同一分钟信号合并一次。全部观察根在同一天，EMA未预热不触发。',
                ]
            tail = [f'距离门槛为{distance:.2f}美元，严格小于，等于不触发；浮点比较距门槛差≤1e−10按等于处理。角度版本的斜率距tan(30度)差≤1e−10也按等于处理。',
                    ENTRY, EXIT, '退出沿用现有12种公共卖出方法分别回测，不新增退出条件。', MODEL, LIVE]
            yield name, {'type':kind,'distance':distance}, '\n\n'.join(common+steps+tail)


def apply():
    for name, rule, prose in specs():
        items=store.ideas()
        if rule=={'type':'green2_touch','distance':.05}:
            item=next(x for x in items if x['id']=='7d9180812193')
        else:
            item=next((x for x in items if x['name']==name),None)
        if item is None:
            item=store.save('buy',name,prose)
        elif item['description']!=prose or item['name']!=name:
            item=store.save('buy',name,prose,idea_id=item['id'],expected_updated_at=item['updated_at'])
        if not store.ready(item):store.register(item['id'],rule)
        print(name)

if __name__=='__main__':apply()
