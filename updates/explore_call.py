"""Bounded, predeclared Call experiments; idempotent import."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import store
from engine import validate_rule

ROWS = [
 ('research_red_15','buy','阴线跌超1.5美元','阴线开盘减收盘严格超过1.5美元，下一根开盘买入Call。',{'type':'red_body','dollars':1.5}),
 ('research_drop3_2','buy','3分钟累计跌超2美元','当日最近3根已结束K线，第一根开盘减第三根收盘严格超过2美元，下一根开盘买入Call。',{'type':'three_bar_drop_2'}),
 ('research_rebound','buy','跌超1美元后阳线确认','先出现实体下跌严格超过1美元的阴线，紧接着一根收盘高于开盘、且高于前一根收盘的阳线确认，再下一根开盘买入Call。信号不跨日。',{'type':'red_rebound_1'}),
 ('research_hold2','sell','持有2分钟','买入所在K线算第1根，第2根收盘退出；不隔夜。',{'type':'fixed','minutes':2}),
 ('research_hold15','sell','持有15分钟','买入所在K线算第1根，第15根收盘退出；不隔夜。',{'type':'fixed','minutes':15}),
 ('research_bracket','sell','期权+25%/-15% · 最多10分钟','每分钟收盘计算含时间损耗的期权报价：严格超过2.50美元止盈，低于或等于1.70美元止损，先触发先退出；否则第10根收盘退出，不隔夜。手续费另扣。仅按收盘价检查，不保证盘中损失限制在15%。',{'type':'option_bracket_10'})
]

def apply():
 store.initialize()
 with store.locked():
  items=store._read(); ids={x['id'] for x in items}; added=[]
  for key,kind,name,desc,rule in ROWS:
   if key in ids: continue
   validate_rule(kind,rule)
   row=dict(id=key,kind=kind,name=name,description=desc,implementation=rule,version=1,realize=False,updated_at=store.now())
   row['implementation_hash']=store.description_hash(row)
   items.append(row);added.append(key)
  if any(key.startswith('research_') and kind=='sell' and key in added for key,kind,*_ in ROWS):
   for x in items:
    if x['kind']=='buy':x['realize']=False
  store._write(items)
 print('Added:',added)

if __name__=='__main__':apply()
