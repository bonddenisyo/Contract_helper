"""Audit log in SQLite. Stores flags and human decisions, never the full contract text."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "audit.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS reviews (
  id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT, doc_name TEXT, role TEXT,
  provider TEXT, model TEXT, n_clauses INTEGER, n_flags INTEGER, routes TEXT);
CREATE TABLE IF NOT EXISTS flags (
  review_id INTEGER, flag_id TEXT, clause_id TEXT, category TEXT, risk TEXT,
  confidence REAL, source TEXT, verified INTEGER, route TEXT, route_reason TEXT, quote TEXT);
CREATE TABLE IF NOT EXISTS decisions (
  review_id INTEGER, flag_id TEXT, decision TEXT, note TEXT, decided_at TEXT);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path: Path = DB_PATH) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, check_same_thread=False)
    con.executescript(SCHEMA)
    return con


def save_review(con, review, doc_name: str, role: str) -> int:
    routes = {r: len(review.by_route(r)) for r in ("info", "review", "lawyer")}
    cur = con.execute(
        "INSERT INTO reviews (created_at, doc_name, role, provider, model, n_clauses, n_flags, routes) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (_now(), doc_name, role, review.provider, review.model, len(review.clauses), len(review.flags), json.dumps(routes)),
    )
    rid = cur.lastrowid
    con.executemany(
        "INSERT INTO flags VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        [(rid, f["id"], f["clause_id"], f["category"], f["risk"], f["confidence"], f["source"],
          int(f["verified"]), f["route"], f["route_reason"], f["quote"]) for f in review.flags],
    )
    con.commit()
    return rid


def record_decision(con, review_id: int, flag_id: str, decision: str, note: str = "") -> None:
    con.execute("INSERT INTO decisions VALUES (?,?,?,?,?)", (review_id, flag_id, decision, note, _now()))
    con.commit()


def reviews_today(con) -> int:
    """AI reviews run today (UTC). Used to keep a public deployment inside free-tier limits."""
    today = datetime.now(timezone.utc).date().isoformat()
    return con.execute(
        "SELECT COUNT(*) FROM reviews WHERE created_at >= ? AND provider != 'demo'", (today,)).fetchone()[0]


def recent(con, limit: int = 20) -> list[dict]:
    rows = con.execute(
        "SELECT r.id, r.created_at, r.doc_name, r.provider, r.n_flags, r.routes, "
        "(SELECT COUNT(*) FROM decisions d WHERE d.review_id = r.id) "
        "FROM reviews r ORDER BY r.id DESC LIMIT ?", (limit,)).fetchall()
    keys = ["review", "time", "document", "provider", "flags", "routes", "decisions"]
    return [dict(zip(keys, r)) for r in rows]


def decision_stats(con) -> dict:
    """How often humans agree with the AI, per category. Feeds the eval set and roadmap."""
    rows = con.execute(
        "SELECT f.category, d.decision, COUNT(*) FROM decisions d JOIN flags f "
        "ON f.review_id = d.review_id AND f.flag_id = d.flag_id GROUP BY f.category, d.decision").fetchall()
    out: dict[str, dict[str, int]] = {}
    for cat, dec, n in rows:
        out.setdefault(cat, {})[dec] = n
    return out
