"""Correct the misinterpreted two-leg draft to independent 12 bearish bars."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import store
from updates.detail_descriptions import description


def apply():
    item = next(x for x in store.ideas() if x['id']=='79e85327181a')
    rule = {'type':'red_count','window':12,'count':12}
    prose = description({'kind':'buy','implementation':rule})
    if item['description'] != prose:
        item = store.save('buy','连续 12 根阴线',prose,idea_id=item['id'],expected_updated_at=item['updated_at'])
    if not store.ready(item):
        store.register(item['id'],rule)

if __name__=='__main__':
    apply()
