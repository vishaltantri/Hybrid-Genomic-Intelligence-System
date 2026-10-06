"""Database backup, verification and restore (Phase 25).

  python -m scripts.backup_db backup  [--db PATH] [--out DIR]
  python -m scripts.backup_db verify  BACKUP_FILE
  python -m scripts.backup_db restore BACKUP_FILE [--db PATH] [--force]

Backups use SQLite's online backup API, so they are consistent while the API is running (WAL mode). A manifest next to
each backup records the SHA-256, table row counts and migration versions. Every command reports success only after it has
re-opened the file and checked it: `verify` and `restore` recompute the hash, run `PRAGMA integrity_check` and compare row
counts with the manifest. A restore never overwrites an existing database unless --force, and then keeps the old file.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import sys
import time
from pathlib import Path
from typing import Dict, Optional

ROOT = Path(__file__).resolve().parents[1]


class BackupError(RuntimeError):
    pass


def default_db() -> Path:
    from backend.app import store
    return Path(store.DB_PATH)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _inspect(path: Path) -> dict:
    uri = f"file:{path.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        counts: Dict[str, int] = {t: conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in tables}
        try:
            versions = [r[0] for r in conn.execute("SELECT version FROM schema_migrations ORDER BY version")]
        except sqlite3.Error:
            versions = []
    finally:
        conn.close()
    return {"integrity": integrity, "row_counts": counts, "migrations": versions}


def backup(db: Optional[Path] = None, out: Optional[Path] = None) -> Path:
    db = Path(db or default_db())
    if not db.exists():
        raise BackupError(f"database not found: {db}")
    out = Path(out or ROOT / "backups")
    out.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    dest = out / f"genomera-{stamp}.sqlite3"
    src = sqlite3.connect(db)
    dst = sqlite3.connect(dest)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    info = _inspect(dest)
    if info["integrity"] != "ok":
        dest.unlink(missing_ok=True)
        raise BackupError(f"backup failed integrity check: {info['integrity']}")
    manifest = {"created_utc": stamp, "source": db.name, "size_bytes": dest.stat().st_size, "sha256": _sha256(dest), **info}
    dest.with_suffix(".manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return dest


def verify(backup_file: Path) -> dict:
    backup_file = Path(backup_file)
    mf = backup_file.with_suffix(".manifest.json")
    if not backup_file.exists() or not mf.exists():
        raise BackupError("backup file or its manifest is missing")
    manifest = json.loads(mf.read_text(encoding="utf-8"))
    if _sha256(backup_file) != manifest["sha256"]:
        raise BackupError("checksum mismatch: the backup file has changed since it was created")
    info = _inspect(backup_file)
    if info["integrity"] != "ok":
        raise BackupError(f"integrity check failed: {info['integrity']}")
    if info["row_counts"] != manifest["row_counts"]:
        raise BackupError("row counts differ from the manifest")
    return {"ok": True, "tables": len(info["row_counts"]), "rows": sum(info["row_counts"].values()), "migrations": info["migrations"]}


def restore(backup_file: Path, db: Optional[Path] = None, force: bool = False) -> dict:
    backup_file = Path(backup_file)
    verify(backup_file)                                    # never restore something that does not verify
    target = Path(db or default_db())
    kept = None
    if target.exists():
        if not force:
            raise BackupError(f"{target} exists; pass --force to replace it (the old file is kept)")
        kept = target.with_name(target.name + f".pre-restore-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}")
        shutil.move(str(target), str(kept))
        for ext in ("-wal", "-shm"):
            side = Path(str(target) + ext)
            if side.exists():
                shutil.move(str(side), str(kept) + ext)
    target.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(f"file:{backup_file.as_posix()}?mode=ro", uri=True)
    dst = sqlite3.connect(target)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    after = _inspect(target)
    manifest = json.loads(backup_file.with_suffix(".manifest.json").read_text(encoding="utf-8"))
    if after["integrity"] != "ok" or after["row_counts"] != manifest["row_counts"]:
        raise BackupError("restored database does not match the backup; the previous file was kept" if kept else "restored database does not match the backup")
    return {"restored": str(target), "previous_kept_as": str(kept) if kept else None, "rows": sum(after["row_counts"].values())}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("backup"); b.add_argument("--db"); b.add_argument("--out")
    v = sub.add_parser("verify"); v.add_argument("file")
    r = sub.add_parser("restore"); r.add_argument("file"); r.add_argument("--db"); r.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "backup":
            p = backup(a.db, a.out)
            print(f"backup written and verified: {p}")
            print(json.dumps(verify(p)))
        elif a.cmd == "verify":
            print(json.dumps(verify(Path(a.file))))
        else:
            print(json.dumps(restore(Path(a.file), a.db, a.force)))
    except BackupError as ex:
        print(f"FAILED: {ex}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
