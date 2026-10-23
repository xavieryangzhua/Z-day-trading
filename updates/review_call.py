"""Descriptive period checks of existing backtests, not unseen holdout testing."""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import store


def stats(trades):
 n=len(trades)
 return dict(n=n,mean=sum(t['net_return'] for t in trades)/n if n else None,
             win=sum(t['net_profit']>0 for t in trades)/n if n else None)


def review():
 items=store.ideas(); sells=[x for x in items if x['kind']=='sell']; rows=[]
 for buy in [x for x in items if x['kind']=='buy']:
  run=store.latest(buy['id'])
  assert buy['realize'] and run['signature']==store.signature(buy,sells)
  for sell in sells:
   trades=[t for t in run['trades'] if t['sell_id']==sell['id']]
   early=[t for t in trades if t['entry_time'][:10]<'2025-04-01']
   late=[t for t in trades if t['entry_time'][:10]>='2025-04-01']
   total=sum(t['net_profit'] for t in trades)
   best_day={}
   for t in trades:best_day[t['entry_time'][:10]]=best_day.get(t['entry_time'][:10],0)+t['net_profit']
   rows.append(dict(buy=buy['name'],sell=sell['name'],buy_id=buy['id'],sell_id=sell['id'],
                    full=stats(trades),jan_mar=stats(early),april=stats(late),
                    profit_excluding_best_day=total-max(best_day.values()) if best_day else None))
 rows.sort(key=lambda x:x['full']['mean'] if x['full']['mean'] is not None else float('-inf'),reverse=True)
 (store.HOME/'call-exploration-summary.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
 def output(r):
  print(r['buy'], '|',r['sell'],'|',*[f"{key}: n={r[key]['n']} avg={r[key]['mean']:.2%} win={r[key]['win']:.1%}" if r[key]['n'] else f'{key}: n=0' for key in ('full','jan_mar','april')], '| ex_best_day_profit=',round(r['profit_excluding_best_day'],2) if r['profit_excluding_best_day'] is not None else None)
 print('NEW COMBINATIONS, n >= 30:')
 for r in [r for r in rows if (r['buy_id'].startswith('research_') or r['sell_id'].startswith('research_')) and r['full']['n']>=30][:15]:output(r)
 print('BOTH PERIODS POSITIVE, n >= 20 EACH:')
 for r in rows:
  if all(r[k]['n']>=20 and r[k]['mean']>0 for k in ('jan_mar','april')):output(r)
 print('BEST NEW BUY:')
 for bid in ('research_red_15','research_drop3_2','research_rebound'):
  output(next(r for r in rows if r['buy_id']==bid))
 print('TOTAL',len(rows),'positive',sum(r['full']['mean'] is not None and r['full']['mean']>0 for r in rows))

if __name__=='__main__':review()
