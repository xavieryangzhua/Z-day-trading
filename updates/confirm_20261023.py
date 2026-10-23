"""Register the six definitions explicitly confirmed by the user."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import store

DEFINITIONS = {
 'three_bar_drop_3': ('最近3根已完成分钟线累计下跌超过3美元：第一根开盘价减第三根收盘价严格大于3美元，不要求三根都是阴线。下一根开盘买入，窗口不跨日。', {'type':'three_bar_drop'}),
 'pullback_ma20': ('前5根分钟线收盘都高于各自EMA20，随后出现一根阴线，其收盘价距离本根EMA20不超过0.10美元（允许在线上或线下）。下一根开盘买入。信号窗口不跨日。', {'type':'ema_pullback','period':20}),
 'pullback_ma5': ('前5根分钟线收盘都高于各自EMA5，随后出现一根阴线，其收盘价距离本根EMA5不超过0.10美元（允许在线上或线下）。下一根开盘买入。信号窗口不跨日。', {'type':'ema_pullback','period':5}),
 'entry_green_025': ('只检查买入所在的第一根分钟线：收盘价减买入开盘价严格大于0.25美元时，在该根收盘卖出；不满足则当天收盘退出。', {'type':'entry_gain','minutes':1}),
 'entry_three_025': ('只检查买入后的第3根分钟线（买入所在K线算第1根）：第3根收盘价减买入价严格大于0.25美元时，在该根收盘卖出；不满足或当天不足3根则当天收盘退出。', {'type':'entry_gain','minutes':3}),
 'option_25_in_10': ('从买入所在分钟开始，最多10分钟内逐分钟收盘检查：固定Delta 0.5、每分钟报价损耗0.01美元后的模拟期权报价严格超过2.50美元（初始2美元，上涨超过25%），就在本分钟收盘卖出。未达到则第10分钟收盘退出；不足10分钟则当天收盘退出。手续费在净收益中另扣。', {'type':'option_target_10'}),
}

def apply():
 store.initialize()
 catalog={x['id']:x for x in store.ideas()}
 for key,(description,rule) in DEFINITIONS.items():
  item=catalog[key]
  if item['description']==description and item.get('implementation')==rule and store.ready(item):
   continue
  store.save(item['kind'], item['name'], description, key)
  store.register(key, rule)
 print('Confirmed 6 definitions; ready for pending backtests.')

if __name__ == '__main__':
 apply()
