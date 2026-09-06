import os
import sqlite3
import sys
from pathlib import Path


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
unicode_sqlite3_database_dir = str(data_dir)

# ディレクトリが存在しない場合は作成（ただし警告を出す）
if not os.path.exists(unicode_sqlite3_database_dir):
    try:
        os.makedirs(unicode_sqlite3_database_dir)
        print(f"Created directory: {unicode_sqlite3_database_dir}", file=sys.stderr)
    except PermissionError:
        print(
            f"Permission denied: Cannot create directory {unicode_sqlite3_database_dir}",
            file=sys.stderr,
        )
        print("Please create the directory manually", file=sys.stderr)
        sys.exit(1)


LEGACY_VERSION = "15.0"


class Database:
    def create(self):
        """Create tables if they don't exist yet, and migrate legacy schema.

        Note: `CREATE TABLE IF NOT EXISTS` only applies its column
        definitions when the table doesn't exist yet — it does NOT add
        columns to an existing table. So a `char`/`codepoint` table from
        before the `version` column existed needs an explicit
        `ALTER TABLE ... ADD COLUMN` here, or `version` would silently
        never get added and every version-aware query would fail.
        """
        with Connection() as conn:
            with Cursor(conn) as cur:
                cur.execute(
                    "create table if not exists char("
                    "id integer primary key, name text, detail text, "
                    "codetext text, char text, block text)"
                )
                # codepoint.char (= char.id) is globally unique across all
                # versions (ids are assigned from a single running counter
                # in database.py), so (char, seq) alone is already a valid
                # primary key — no need to also key on version.
                cur.execute(
                    "create table if not exists codepoint("
                    "char integer, seq integer, code integer, "
                    "primary key(char, seq))"
                )
                cur.execute(
                    "create table if not exists db_meta("
                    "key text primary key, value text)"
                )
                conn.commit()
                self._add_version_columns(cur, conn)
                self._migrate_legacy_rows(cur, conn)

    def _add_version_columns(self, cur, conn):
        # Only `char` needs `version` directly: `codepoint.char` (= char.id)
        # is globally unique across versions, so codepoint rows already
        # resolve to a version transitively via their `char` FK — no need
        # to duplicate the version onto every codepoint row too.
        cur.execute("pragma table_info(char)")
        char_columns = {row[1] for row in cur.fetchall()}
        if "version" not in char_columns:
            cur.execute("alter table char add column version text")

        cur.execute("drop index if exists char_index")
        cur.execute(
            "create unique index if not exists char_index " "on char(codetext, version)"
        )
        conn.commit()

    def _migrate_legacy_rows(self, cur, conn):
        """Backfill rows from before the `version` column existed."""
        cur.execute("select count(*) from char where version is null")
        (legacy_count,) = cur.fetchone()
        if legacy_count == 0:
            return

        print(
            f"Migrating {legacy_count} pre-versioning rows to version "
            f"{LEGACY_VERSION} ...",
            file=sys.stderr,
        )
        cur.execute(
            "update char set version = ? where version is null", (LEGACY_VERSION,)
        )
        cur.execute(
            "insert or ignore into db_meta(key, value) values('current_version', ?)",
            (LEGACY_VERSION,),
        )
        conn.commit()

    def delete_version(self, version):
        with Connection() as conn:
            with Cursor(conn) as cur:
                cur.execute("delete from char where version = ?", (version,))
                cur.execute("delete from codepoint where version = ?", (version,))
                deleted = cur.rowcount
                cur.execute("select value from db_meta where key = 'current_version'")
                row = cur.fetchone()
                if row and row[0] == version:
                    cur.execute("delete from db_meta where key = 'current_version'")
                conn.commit()
        return deleted

    def delete_all(self):
        if not os.path.exists(unicode_sqlite3_database_path):
            print(f"No database file: {unicode_sqlite3_database_path}", file=sys.stderr)
        else:
            os.remove(unicode_sqlite3_database_path)
            print(
                f"Deleted database file: {unicode_sqlite3_database_path}",
                file=sys.stderr,
            )

    def get_path(self):
        return unicode_sqlite3_database_path

    def exists(self):
        return os.path.exists(unicode_sqlite3_database_path)

    def local_versions(self):
        """Return [(version, row_count)] for versions stored locally."""
        with Connection() as conn:
            with Cursor(conn) as cur:
                cur.execute(
                    "select version, count(*) from char "
                    "where version is not null group by version"
                )
                return cur.fetchall()

    def get_current_version(self):
        with Connection() as conn:
            with Cursor(conn) as cur:
                cur.execute("select value from db_meta where key = 'current_version'")
                row = cur.fetchone()
                return row[0] if row else None

    def set_current_version(self, version):
        with Connection() as conn:
            with Cursor(conn) as cur:
                cur.execute(
                    "insert into db_meta(key, value) values('current_version', ?) "
                    "on conflict(key) do update set value = excluded.value",
                    (version,),
                )
                conn.commit()


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


class AutoID:
    def init(self):
        self.value = 1
        return self

    def next(self):
        value = self.value
        self.value = self.value + 1
        return value
