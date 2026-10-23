"""JSON is the editable idea queue; SQLite stores immutable backtest snapshots."""
import copy
import fcntl
import hashlib
import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HOME = Path(os.environ.get("ZDAY_STORAGE", ROOT / "storage"))


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def description_hash(idea):
    return digest(idea["description"])


@contextmanager
def locked():
    HOME.mkdir(parents=True, exist_ok=True)
    with (HOME / ".lock").open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def _write(items):
    temporary = HOME / "ideas.json.tmp"
    temporary.write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(HOME / "ideas.json")
    _sync_catalog(items)


def _sync_catalog(items):
    """Mirror all ideas, including unrealized prose, into the database."""
    with connect() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS ideas (
            id TEXT PRIMARY KEY, kind TEXT NOT NULL, name TEXT NOT NULL,
            description TEXT NOT NULL, version INTEGER NOT NULL,
            realize INTEGER NOT NULL, document TEXT NOT NULL)""")
        db.executemany("""INSERT INTO ideas VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET kind=excluded.kind, name=excluded.name,
            description=excluded.description, version=excluded.version,
            realize=excluded.realize, document=excluded.document""",
            [(x["id"], x["kind"], x["name"], x["description"], x["version"],
              int(x["realize"]), json.dumps(x, ensure_ascii=False)) for x in items])


def _read():
    return json.loads((HOME / "ideas.json").read_text())


def initialize():
    with locked():
        if not (HOME / "ideas.json").exists():
            items = json.loads((ROOT / "seed_ideas.json").read_text())
            for item in items:
                item.update(version=1, realize=False, updated_at=now())
                item["implementation_hash"] = description_hash(item)
            _write(items)
        else:
            _sync_catalog(_read())
    with connect() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, idea_id TEXT NOT NULL,
            signature TEXT NOT NULL, snapshot TEXT NOT NULL, source TEXT NOT NULL,
            parameters TEXT NOT NULL, engine_hash TEXT NOT NULL,
            summary TEXT NOT NULL, trades TEXT NOT NULL)""")


def connect():
    HOME.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(HOME / "research.sqlite3")
    db.row_factory = sqlite3.Row
    return db


def ideas():
    with locked():
        return _read()


def save(kind, name, description, idea_id=None, reset=False, expected_updated_at=None):
    name, description = name.strip(), description.strip()
    if not name or not description:
        raise ValueError("请填写名称和 description。")
    with locked():
        items = _read()
        if idea_id:
            item = next(x for x in items if x["id"] == idea_id)
            if expected_updated_at and item["updated_at"] != expected_updated_at:
                raise ValueError("想法已在其他窗口更新，请刷新后再保存。")
            changed = description != item["description"]
            item["name"] = name
            if changed:
                item["description"] = description
                item["version"] += 1
            if changed or reset:
                item["realize"] = False
                item.pop("error", None)
                if kind == "sell":
                    for buy in items:
                        if buy["kind"] == "buy":
                            buy["realize"] = False
            item["updated_at"] = now()
        else:
            item = dict(id=uuid.uuid4().hex[:12], kind=kind, name=name,
                        description=description, version=1, realize=False,
                        updated_at=now(), implementation=None, implementation_hash=None)
            items.append(item)
            if kind == "sell":
                for buy in items:
                    if buy["kind"] == "buy":
                        buy["realize"] = False
        _write(items)
        return copy.deepcopy(item)


def ready(item):
    return bool(item.get("implementation")) and item.get("implementation_hash") == description_hash(item)


def signature(buy, sells):
    return digest([{k: x.get(k) for k in ("id", "version", "description", "implementation")}
                   for x in [buy, *sells]])


def register(idea_id, implementation):
    """Explicit Codex implementation step, never infer arbitrary prose silently."""
    from engine import validate_rule
    with locked():
        items = _read()
        item = next(x for x in items if x["id"] == idea_id)
        validate_rule(item["kind"], implementation)
        item["implementation"] = implementation
        item["implementation_hash"] = description_hash(item)
        item["realize"] = False
        item["updated_at"] = now()
        if item["kind"] == "sell":
            for buy in items:
                if buy["kind"] == "buy":
                    buy["realize"] = False
        _write(items)


def latest(idea_id):
    with connect() as db:
        row = db.execute("SELECT * FROM runs WHERE idea_id=? ORDER BY id DESC LIMIT 1", (idea_id,)).fetchone()
    if not row:
        return None
    result = dict(row)
    for key in ("snapshot", "source", "parameters", "summary", "trades"):
        result[key] = json.loads(result[key])
    return result
