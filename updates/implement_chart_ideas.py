"""Explicitly implement the three chart drafts without changing trading rules."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import store
from updates.chart_ideas import drafts


def apply():
    rules = [{'type':'double_red_run'},
             {'type':'large_green_pullback','dollars':2},
             {'type':'large_green_pullback','dollars':3}]
    for (name, draft), rule in zip(drafts(), rules):
        description = draft.replace('当前仅保存待实现想法，未实现、未回测；', '')
        item = next(x for x in store.ideas() if x['name'] == name)
        if item['description'] not in (draft, description):
            raise ValueError(f'{name} description has changed; review before implementing')
        if item['description'] != description:
            item = store.save('buy', name, description, idea_id=item['id'],
                              expected_updated_at=item['updated_at'])
        if not store.ready(item):
            store.register(item['id'], rule)
        print('Implemented:', name)

if __name__ == '__main__':
    apply()
