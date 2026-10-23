"""Expand existing descriptions to match their implemented rules, without tuning."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import store
from engine import validate_rule

MARKET = '通用口径：使用SPY正常交易时段09:30–16:00（America/New_York，自动处理夏令时）的1分钟K线。O/H/L/C分别为开盘/最高/最低/收盘价；本文价格差以SPY每股美元计，除非明确写“期权报价”。阴线=C<O，阳线=C>O，十字星=C=O，不算阴线或阳线。所有条件只用已结束K线。'
ENTRY = '执行：仅做买入Call。信号确认后，在当日下一根K线刚开始时买入，回测成交价为该根O；没有当日下一根则不入场。每个买入＋卖出组合独立持仓，已有持仓时忽略入场信号，不加仓、不重叠；平仓后允许下一分钟按新信号入场。观察窗口不跨交易日。'
EXIT = '执行：买入所在分钟算持有第1分钟，入场标的价S0为该分钟O。卖出统一在指定分钟结束时，回测标的成交价为该根C；忽略分钟内最高/最低价，不做盘中触发。不隔夜，任何未完成的持仓均在当日最后一根K线收盘退出。'
MODEL = '收益模型：每笔1张Call，初始期权报价2美元/股，100股/张，成本200美元；Delta固定0.5。持有m分钟的期权报价Q=max(0,2+0.5×(C−S0)−0.01×m)。净损益=(Q−2)×100−2美元往返手续费；净收益率=净损益/200，净损益>0才算盈利。'
LIVE = '实现边界：以上是信号及回测成交约定，不是已完成的实盘下单规范。分钟收盘确认后不能保证实际成交在刚刚结束的收盘价或下一根精确开盘价；未来接API时仍需定义期权到期日/行权价、实际买卖报价、订单类型、滑点、仓位与异常处理。'


def ema(n):
 return f'EMA{n}使用正常交易时段收盘价，alpha=2/({n}+1)，E_t=alpha×C_t+(1−alpha)×E_(t−1)，初值为首根C；至少预热{n}根才有效。跨交易日保留EMA状态，不包含盘前盘后K线。'


def description(item):
 r=item['implementation']; validate_rule(item['kind'],r); t=r['type']; steps=[]
 if item['kind']=='buy':
  if t=='trend_vwap':
   steps=['VWAP从每个交易日09:30重置，按累计[(H+L+C)/3×volume]/累计volume计算，累计成交量为0则无效。它是分钟近似值；当前数据仅含Nasdaq单一场所，非全市场汇总成交量。',
    '将回调根记为A。A之前连续5根当日分钟线的收盘必须严格高于各自VWAP；A的VWAP还必须严格高于5根前VWAP。',
    'A要求阴线C_A<O_A，最低价满足abs(L_A−VWAP_A)≤0.10美元，收盘C_A≥VWAP_A。此处附近看最低价，不是收盘距离；等于边界允许。',
    '紧接的B要求阳线C_B>O_B，C_B>H_A且C_B>VWAP_B，并且VWAP_B高于5根前VWAP。所有VWAP按相应K线收盘时计算。',
    'B收盘确认后下一根开盘买入。B未确认则该形态取消；前置K线不足不触发。无需EMA20条件。']
  elif t=='trend_sma50':
   steps=['SMA50为最近50根正常交易时段1分钟收盘价的算术平均；至少50根才有效，跨交易日连续计算，不含盘前盘后，不使用指数加权。',
    '当前信号根记为A；A之前5根当日K线收盘分别严格高于各自SMA50。A的SMA50严格高于当日10根之前的SMA50；缺少任何观察值则不触发。',
    'A必须是阳线C_A>O_A，且C_A>SMA50_A；同时C_A严格高于之前5根最高价的最大值，不包含A本身。',
    'A收盘确认后下一根开盘买入1张Call；无需EMA20条件。每分钟滚动重新检查，持仓期间忽略重复信号。']
  elif t=='trend_price_blocks':
   steps=['不使用均线或成交量。取当日最近15根已结束分钟K线，按时间顺序分成不重叠的3组A、B、C，每组5根。每分钟滚动更新一次分组。',
    '分别计算每组的最高价HA/HB/HC=max(H)和最低价LA/LB/LC=min(L)。要求HA<HB<HC且LA<LB<LC，全部为严格不等式。代表三个五分钟观察区间的高点及低点同时抬高，不是利用未来K线标注波峰波谷。',
    '最新一根即C组第5根还须为阳线，且该根收盘严格超过B组最高价HB。组内不要求所有K线都上涨。',
    '最新一根收盘确认后，下一根开盘买入1张Call；当天不足15根不触发，观察组不跨日。']
  elif t=='trend_pullback':
   n=r['period'];steps=[ema(20)]+([ema(5)] if n==5 else [])+[
    f'先判断回调根A：A之前连续5根已结束K线的收盘，必须分别严格高于各自EMA20和EMA{n}。所有这些K线属于同一交易日。',
    'A收盘时EMA20必须严格大于5根之前的EMA20，表示均线抬升；不是只因价格位于均线上方就算上升趋势。',
    f'A必须为阴线C_A<O_A；最低价与A的EMA{n}之差绝对值≤0.10美元，表示低点回到均线附近；同时C_A≥EMA{n}_A且C_A≥EMA20_A，收盘不能失守这两条线。',
    f'紧接A的B必须为阳线C_B>O_B，收盘严格超过A最高价H_A，并严格高于B的EMA20和EMA{n}；B的EMA20仍必须大于5根前的EMA20。',
    '只有A和紧接的B都满足才在下一根C开盘买入1张Call。B不满足就取消这次形态，不无限等待、不在A未确认时提前入场；不足前置K线时不触发。']
  elif t=='trend_high10':
   steps=[ema(20),'在当前信号根A之前，取连续10根当日已结束K线；每根收盘必须严格高于各自EMA20。','A必须为阳线C_A>O_A，且C_A严格超过前10根最高价的最大值max(H)，不包含A本身的最高价；同时C_A>EMA20_A。','要求EMA20_A严格大于5根之前的EMA20；前置观察不足10根或指标未预热时不触发。','A收盘确认后，紧接下一根开盘买入1张Call；不增加第二根确认，持仓期间不加仓。']
  elif t=='red_body':
   d=r['dollars'];steps=[f'只观察最近已结束的1根K线A，不是累计多根。',f'计算实体下跌D=O_A−C_A；要求D>{d}美元，等于{d}美元不触发。不使用H−L，也不使用前一根收盘差。','A满足后，紧接的下一根B开盘买入。无需额外阳线确认。']
  elif t=='red_count':
   w,c=r['window'],r['count'];steps=[f'取当日最近{w}根已结束且连续的分钟K线；不足{w}根不触发。',f'逐根判断C<O，统计阴线数量N；要求N≥{c}。'+('因此这整个窗口必须全部是阴线；十字星或阳线打断连续阴线。' if w==c else f'阴线不必连续，窗口中最多允许{w-c}根非阴线。'),'在窗口最后一根结束后，下一根开盘买入。每分钟重新检查滚动窗口；更长的阴线序列仍可产生信号，但持仓期间不重复买入。']
  elif t in ('three_bar_drop','three_bar_drop_2'):
   d=3 if t=='three_bar_drop' else 2
   steps=['取当日最近3根已结束分钟线，按时间顺序记为A、B、C；不足3根不触发。',f'累计净下跌D=O_A−C_C，要求D>{d}美元，等于{d}不触发。不是三根绝对振幅之和、不是H−L之和，也不要求三根都是阴线。','第三根C结束并满足条件后，紧接的第四根D开盘买入。']
  elif t=='red_rebound_1':
   steps=['观察当日相邻的两根已结束K线A、B。','A必须为阴线且O_A−C_A>1美元；B必须紧接A，且C_B>O_B、C_B>C_A。B为阳线并收回A的一部分跌幅即可，不要求超过A开盘。','B收盘确认后，在紧接的第三根C开盘买入。A后若紧接的B不满足，本次形态不成立，不无限等待后续阳线。']
  elif t=='ema_pullback':
   n=r['period'];steps=[ema(n),'取当日连续6根已结束K线：前5根A1…A5及随后1根回调K线B。',f'前5根必须分别满足C_Ai>EMA{n}_Ai，仅要求收盘在线上，不要求整根高低价在线上。',f'B必须满足C_B<O_B，且abs(C_B−EMA{n}_B)≤0.10美元，等于0.10也允许；收盘在线上或线下都可以。均线使用各根收盘时的最终值，不按最低价判断触线。','B收盘满足后，紧接下一根开盘买入。']
  elif t=='breakout':
   line='VWAP' if r['indicator']=='vwap' else 'EMA20'
   indicator='VWAP每个交易日从09:30重置，按累计[(H+L+C)/3×volume]/累计volume计算；累计成交量为0时指标无效。' if line=='VWAP' else ema(20)
   steps=[indicator,'观察当日相邻的A、B两根已结束K线。A为突破根，B为确认根；P为A的前一根（如存在）。',f'A要求C_A>{line}_A，并且以下任意一项成立：O_A<{line}_A，或C_P<{line}_P。比较严格使用大于/小于，等于不算。A开盘与A收盘后确定的指标比较，判断发生在A结束后。',f'B要求C_B>{line}_B。'+(f'同时要求O_B>{line}_B，即B开盘和收盘都高于B收盘后确定的指标；不限制B最低价。' if r['confirmation']=='body' else '不要求B开盘或最低价在线上。'),'B收盘确认后，第三根C开盘买入；即使C开盘跳空至指标下方，也按已确认信号入场。']
  else:raise ValueError(t)
  return MARKET+'\n\n'+ '\n'.join(f'{i}. {s}' for i,s in enumerate(steps,1))+'\n\n'+ENTRY+'\n\n'+MODEL+'\n\n'+LIVE
 if t=='fixed':
  n=r['minutes'];steps=[f'从买入所在K线开始计数，记为第1根。',f'持有到第{n}根分钟线结束时，不管盈亏都按该根C卖出；正常持有时间为{n}分钟。',f'如果距离当天收盘不足{n}分钟，提前在当日最后一根收盘退出，不跨日补足时间。']
 elif t=='two_green':
  steps=['从买入所在K线开始，逐分钟收盘检查C>O。','连续阳线计数：阳线加1，阴线或十字星归零。不是累计出现任意两根阳线，也不要求买入后立刻连续两根阳线。','首次计数达到2，在第二根阳线本身的收盘卖出，不等下一根开盘。不要求卖出时相对买入价盈利。','若当天一直未出现连续两根阳线，在当日最后一根收盘退出。']
 elif t=='entry_gain':
  n=r['minutes'];steps=[f'只检查买入后的第{n}根K线，买入所在K线计为第1根。',f'在第{n}根结束时计算G=C_{n}−S0；要求G>0.25美元，等于0.25不触发。'+('这相当于买入所在第一根阳线的实体大于0.25美元。' if n==1 else '这是从入场到第三根收盘的净上涨，不是三根阳线实体之和，不要求三根全部为阳线。'),f'满足则第{n}根收盘卖出。','不满足则不再重复检查这个条件，继续持有至当天收盘退出；若当天不足指定根数，也在当天收盘退出。']
 elif t in ('option_target_10','option_bracket_10'):
  steps=['买入所在K线计为第1根；在第1至第10根各自收盘时，使用下方收益模型计算含时间损耗的期权报价Q。','若Q>2.50美元（相对初始2美元涨幅严格超过25%），立刻按本分钟收盘卖出。报价恰好2.50不触发。']
  if t=='option_bracket_10': steps+=['若Q≤1.70美元（相对初始报价跌幅达到或超过15%），按本分钟收盘止损。只在收盘检查，实际模拟退出跌幅可以超过15%；不使用盘中最低价，也不假定恰好在1.70成交。']
  steps+=['首次触发即结束持仓；若到第10根收盘仍未触发，按第10根收盘退出；当天不足10根则当天收盘退出。','25%目标及15%止损（如本规则包含止损）按期权报价变化计算，不是SPY价格变化，也不含手续费；手续费在最终净收益中另扣。']
 else:raise ValueError(t)
 return MARKET+'\n\n'+'\n'.join(f'{i}. {s}' for i,s in enumerate(steps,1))+'\n\n'+EXIT+'\n\n'+MODEL+'\n\n'+LIVE


def apply():
 store.initialize(); changed=[]
 for item in store.ideas():
  detailed=description(item)
  if detailed==item['description']:continue
  store.save(item['kind'],item['name'],detailed,item['id'])
  store.register(item['id'],item['implementation'])
  changed.append(item['id'])
 seed=store.ROOT/'seed_ideas.json'
 rows=json.loads(seed.read_text())
 for item in rows:item['description']=description(item)
 seed.write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
 print('Detailed descriptions updated:',len(changed))

if __name__=='__main__':apply()
