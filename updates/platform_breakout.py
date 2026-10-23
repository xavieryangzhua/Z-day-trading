"""Register the user's agreed five/three/three trend setup without changing exits."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import store
from updates.detail_descriptions import description

def apply():
 store.initialize()
 with store.locked():
  items=store._read()
  if any(x['id']=='impulse_platform_breakout' for x in items):
   print('Already registered.');return
  item=dict(id='impulse_platform_breakout',kind='buy',name='上涨后首次整理突破',implementation={'type':'impulse_platform_breakout'},version=1,realize=False,updated_at=store.now())
  item['description']=description(item)
  item['implementation_hash']=store.description_hash(item)
  items.append(item);store._write(items)
 print('Registered detailed platform breakout idea.')

if __name__=='__main__':apply()
