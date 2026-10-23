"""Idempotent import of the user's October 23 ideas; never overwrite edits."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import store
from engine import validate_rule


def apply():
    store.initialize()
    rows = json.loads(Path(__file__).with_name('2026-10-23.json').read_text())
    with store.locked():
        backup_dir = store.HOME / 'backups' / 'before-20261023'
        backup_dir.mkdir(parents=True, exist_ok=True)
        if not (backup_dir / 'ideas.json').exists():
            (backup_dir / 'ideas.json').write_text((store.HOME / 'ideas.json').read_text())
            import sqlite3
            with store.connect() as source, sqlite3.connect(backup_dir / 'research.sqlite3') as target:
                source.backup(target)
        items = store._read()
        ids = {x['id'] for x in items}
        new_sells = False
        added = []
        for row in rows:
            if row['id'] in ids:
                continue
            row.update(version=1, realize=False, updated_at=store.now())
            if row.get('implementation'):
                validate_rule(row['kind'], row['implementation'])
                row['implementation_hash'] = store.description_hash(row)
            else:
                row.update(implementation=None, implementation_hash=None)
            items.append(row)
            added.append(row['name'])
            new_sells |= row['kind'] == 'sell'
        for item in items:
            if item['id'] == 'two_green' and '下一根开盘卖出' in item['description']:
                item['description'] = item['description'].replace('下一根开盘卖出', '第二根阳线的分钟结束时按收盘价卖出')
                item['version'] += 1
                item['updated_at'] = store.now()
                item['implementation_hash'] = store.description_hash(item)
                item['realize'] = False
                new_sells = True
        if new_sells:
            for item in items:
                if item['kind'] == 'buy':
                    item['realize'] = False
        store._write(items)
    print(json.dumps({'added': added, 'total': len(items)}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    apply()
