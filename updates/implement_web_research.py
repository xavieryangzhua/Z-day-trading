"""Register only reviewed web research descriptions, preserving sources."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import store
from updates.web_research_ideas import drafts


def apply():
    rules=[{'type':t} for t in ('fib_shallow','fib_confluence','fib_extension')]
    rules += [{'type':'opening_range','minutes':n} for n in (5,15)]
    rules += [{'type':t} for t in ('bb_squeeze','bb_reclaim','rsi_reclaim')]
    for (name,draft),rule in zip(drafts(),rules):
        prose=draft.replace('此条为买入研究想法，仅保存待实现，realize=false。未来实现后配对现有12种卖出方法；目前没有新增卖出规则或回测成绩。','此条为买入研究想法，配对现有12种卖出方法，不新增卖出规则。')
        item=next(x for x in store.ideas() if x['name']==name)
        if item['description'] not in (draft,prose):raise ValueError('Review changed description: '+name)
        if item['description']!=prose:
            item=store.save('buy',name,prose,idea_id=item['id'],expected_updated_at=item['updated_at'])
        if not store.ready(item):store.register(item['id'],rule)
        print(name)

if __name__=='__main__':apply()
