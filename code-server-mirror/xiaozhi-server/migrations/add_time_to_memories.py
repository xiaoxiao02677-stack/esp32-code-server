"""Migration: add time reference table to holographic memory DBs.

Creates the `memory_times` table (if absent) so every existing agent DB can
store per-fact time references. Run once against each `.db` in data/memory/;
idempotent — safe to re-run.
"""
import sqlite3
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS memory_times (
    memory_id       INTEGER NOT NULL,
    time_reference  TEXT    NOT NULL,
    actual_date     TIMESTAMP,
    PRIMARY KEY (memory_id, time_reference),
    FOREIGN KEY (memory_id) REFERENCES facts(fact_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_memory_times_ref ON memory_times(time_reference);
CREATE INDEX IF NOT EXISTS idx_memory_times_date ON memory_times(actual_date);
"""

_RELATIVE_DB_DIR = Path("data/memory")


def _run(db_path: Path) -> int:
    conn = sqlite3.connect(str(db_path))
    conn.executescript(_SCHEMA)
    conn.commit()
    count = int(conn.execute(
        "SELECT COUNT(*) FROM memory_times"
    ).fetchone()[0])
    conn.close()
    return count


def migrate(db_dir: Path = _RELATIVE_DB_DIR) -> dict:
    """Run migration over all agent DBs under db_dir.

    Returns {"dbs_touched": N, "total_references": int}.
    """
    db_dir = db_dir if db_dir.is_absolute() else _RELATIVE_DB_DIR
    touched, total = 0, 0
    if db_dir.exists():
        for db_file in sorted(db_dir.glob("*.db")):
            refs = _run(db_file)
            touched += 1
            total += refs
    return {"dbs_touched": touched, "total_references": total}


if __name__ == "__main__":
    import sys
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else _RELATIVE_DB_DIR
    result = migrate(target)
    print(f"Migrated {result['dbs_touched']} DB(s), {result['total_references']} time references")
