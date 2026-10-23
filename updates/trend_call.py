"""Three predefined trend-following entries, one Call per signal, no pyramiding."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import store
from updates.detail_descriptions import description

ROWS=[('trend_pullback20','顺势EMA20回调突破确认',{'type':'trend_pullback','period':20}),
      ('trend_pullback5','顺势EMA5回调突破确认',{'type':'trend_pullback','period':5}),
      ('trend_high10','顺势突破10根高点',{'type':'trend_high10'})]

def apply():
 store.initialize()
 with store.locked():
  items=store._read();existing={x['id'] for x in items}
  for key,name,rule in ROWS:
   if key in existing:continue
   item=dict(id=key,name=name,kind='buy',implementation=rule,version=1,realize=False,updated_at=store.now())
   item['description']=description(item)
   item['implementation_hash']=store.description_hash(item)
   items.append(item)
  store._write(items)
 print('Trend entries registered with detailed descriptions.')

if __name__=='__main__':apply()
