"""Predeclared non-EMA20 trend hypotheses; reuse all existing exit methods."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import store
from updates.detail_descriptions import description

ROWS=[('alt_vwap','VWAP上升回调确认','trend_vwap'),
      ('alt_sma50','SMA50上升突破确认','trend_sma50'),
      ('alt_price','价格结构高低点抬高','trend_price_blocks')]

def apply():
 store.initialize()
 with store.locked():
  items=store._read();ids={x['id'] for x in items}
  for key,name,kind in ROWS:
   if key in ids:continue
   item=dict(id=key,name=name,kind='buy',implementation={'type':kind},version=1,realize=False,updated_at=store.now())
   item['description']=description(item)
   item['implementation_hash']=store.description_hash(item)
   items.append(item)
  store._write(items)
 print('Registered 3 non-EMA20 trend ideas with complete descriptions.')

if __name__=='__main__':apply()
