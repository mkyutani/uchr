import os
import sqlite3
import sys
from pathlib import Path

from .errors import DatabaseError


def get_data_dir():
    """データディレクトリのパスを決定する"""
    if os.getuid() == 0:  # rootユーザー
        # /procを使って親プロセスをチェック（Linuxのみ）
        try:
            with open("/proc/self/stat") as f:
                stats = f.read().split()
                parent_pid = int(stats[3])  # 4番目が親プロセスID

            with open(f"/proc/{parent_pid}/comm") as f:
                parent_name = f.read().strip()

            if parent_name in ["systemd", "cron"]:
                # システムサービスとして実行されている
                return Path("/var/lib/uchr")
        except (FileNotFoundError, ValueError, IndexError):
            # /procが読めない場合やLinux以外の場合
            pass

        # rootの個人利用
        return Path("/root/.local/share/uchr")
    else:
        # 通常ユーザー
        return Path.home() / ".local/share/uchr"


# データベースパスの設定
data_dir = get_data_dir()
unicode_sqlite3_database_path = str(data_dir / "unicode.db")

# Bump when the schema changes, and add the matching step to _migrate().
SCHEMA_VERSION = 1

# Version label for rows written before the `version` column existed: the
# data source used to be hardcoded to Public/15.0.0.
LEGACY_VERSION = "15.0.0"

# DB file mode. For the shared /var/lib/uchr DB this makes it readable by
# everyone but writable (update/use/delete) only by its owner, root.
DB_FILE_MODE = 0o644
DB_DIR_MODE = 0o755


class Database:
    def get_path(self):
        return unicode_sqlite3_database_path

    def exists(self):
        return os.path.exists(unicode_sqlite3_database_path)

    def open_for_read(self):
        """Prepare an existing DB for queries.

        Writes only when the schema is outdated and needs migrating, so
        searching a read-only shared DB works as long as it is up to date.
        """
        if not self.exists():
            raise DatabaseError(f"No database file: {unicode_sqlite3_database_path}")
        with Connection() as conn:
            if _schema_version(conn) >= SCHEMA_VERSION:
                return
        self.open_for_write()

    def open_for_write(self):
        """Create the DB if missing, migrate the schema, and check that the
        file is writable before any modification is attempted."""
        path = unicode_sqlite3_database_path
        if self.exists():
            if not os.access(path, os.W_OK):
                raise DatabaseError(
                    f"Permission denied: {path} is read-only for this user"
                )
        else:
            _ensure_data_dir()
            # Create the file ourselves so the mode does not depend on umask.
            os.close(os.open(path, os.O_CREAT | os.O_WRONLY, DB_FILE_MODE))
            os.chmod(path, DB_FILE_MODE)
        with Connection() as conn:
            _migrate(conn)

    def delete_version(self, version):
        """Delete one version's rows; returns the number of characters removed."""
        with Connection() as conn:
            with conn:
                deleted = delete_version_rows(conn, version)
                conn.execute(
                    "delete from db_meta where key = 'current_version' and value = ?",
                    (version,),
                )
            if deleted:
                conn.execute("vacuum")
        return deleted

    def delete_all(self):
        path = unicode_sqlite3_database_path
        if not os.path.exists(path):
            print(f"No database file: {path}", file=sys.stderr)
        else:
            os.remove(path)
            print(f"Deleted database file: {path}", file=sys.stderr)

    def local_versions(self):
        """Return {version: {"draft": bool, "chars": int}} for stored versions."""
        with Connection() as conn:
            rows = conn.execute(
                "select version, draft, char_count from version"
            ).fetchall()
        return {v: {"draft": bool(d), "chars": n} for v, d, n in rows}

    def get_current_version(self):
        with Connection() as conn:
            row = conn.execute(
                "select value from db_meta where key = 'current_version'"
            ).fetchone()
        return row[0] if row else None

    def set_current_version(self, version):
        with Connection() as conn:
            with conn:
                conn.execute(
                    "insert into db_meta(key, value) values('current_version', ?) "
                    "on conflict(key) do update set value = excluded.value",
                    (version,),
                )


def delete_version_rows(conn, version):
    """Delete every row belonging to `version`; the caller owns the
    transaction. Returns the number of characters removed."""
    # codepoint has no version column; it resolves to a version via its
    # char FK, so delete it before the char rows go away.
    conn.execute(
        "delete from codepoint where char in "
        "(select id from char where version = ?)",
        (version,),
    )
    deleted = conn.execute("delete from char where version = ?", (version,)).rowcount
    conn.execute("delete from version where version = ?", (version,))
    return deleted


def _ensure_data_dir():
    directory = os.path.dirname(unicode_sqlite3_database_path)
    if os.path.exists(directory):
        return
    try:
        os.makedirs(directory, mode=DB_DIR_MODE)
        print(f"Created directory: {directory}", file=sys.stderr)
    except PermissionError as e:
        raise DatabaseError(
            f"Permission denied: cannot create directory {directory}"
        ) from e


def _schema_version(conn):
    return conn.execute("pragma user_version").fetchone()[0]


def _table_columns(conn, table):
    return {row[1] for row in conn.execute(f"pragma table_info({table})")}


def _migrate(conn):
    """Bring the schema up to SCHEMA_VERSION, in a single transaction."""
    if _schema_version(conn) >= SCHEMA_VERSION:
        return

    with conn:
        # Python's sqlite3 does not open a transaction for DDL on its own.
        conn.execute("begin immediate")
        # 0 -> 1: a DB from before versioning (no `version` column), or a
        # brand-new empty file. `create table if not exists` won't add
        # columns to an existing table, so legacy tables need ALTER TABLE.
        conn.execute(
            "create table if not exists char("
            "id integer primary key, name text, detail text, "
            "codetext text, char text, block text, version text)"
        )
        # codepoint.char (= char.id) is unique across all versions, so
        # codepoint rows resolve to a version via char and need no own
        # version column.
        conn.execute(
            "create table if not exists codepoint("
            "char integer, seq integer, code integer, "
            "primary key(char, seq))"
        )
        conn.execute(
            "create table if not exists version("
            "version text primary key, draft integer not null default 0, "
            "char_count integer not null default 0)"
        )
        conn.execute(
            "create table if not exists db_meta(key text primary key, value text)"
        )

        if "version" not in _table_columns(conn, "char"):
            conn.execute("alter table char add column version text")
        # An unreleased build labelled legacy rows "15.0"; normalize to X.Y.Z.
        conn.execute(
            "update char set version = ? where version = '15.0'", (LEGACY_VERSION,)
        )
        conn.execute(
            "update db_meta set value = ? where key = 'current_version' "
            "and value = '15.0'",
            (LEGACY_VERSION,),
        )
        legacy_count = conn.execute(
            "update char set version = ? where version is null", (LEGACY_VERSION,)
        ).rowcount
        if legacy_count:
            print(
                f"Migrated {legacy_count} pre-versioning rows to version "
                f"{LEGACY_VERSION}",
                file=sys.stderr,
            )
            conn.execute(
                "insert or ignore into db_meta(key, value) "
                "values('current_version', ?)",
                (LEGACY_VERSION,),
            )
        conn.execute(
            "insert or ignore into version(version, char_count) "
            "select version, count(*) from char group by version"
        )

        conn.execute("drop index if exists char_index")
        conn.execute("create unique index char_index on char(codetext, version)")
        conn.execute("create index if not exists codepoint_code on codepoint(code)")
        conn.execute(f"pragma user_version = {SCHEMA_VERSION}")


class Connection:
    def __init__(self):
        self.conn = None

    def __enter__(self):
        self.conn = sqlite3.connect(unicode_sqlite3_database_path)
        return self.conn

    def __exit__(self, *args):
        if self.conn:
            self.conn.close()


class Cursor:
    def __init__(self, conn):
        self.conn = conn
        self.cur = None

    def __enter__(self):
        self.cur = self.conn.cursor()
        return self.cur

    def __exit__(self, *args):
        if self.cur:
            self.cur.close()
            self.cur = None
