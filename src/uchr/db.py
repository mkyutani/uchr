import os
import sqlite3
import sys
from pathlib import Path


def get_data_dir():
    """データディレクトリのパスを決定する"""
    # 環境変数でオーバーライド可能
    if "UNICODE_DB_PATH" in os.environ:
        return Path(os.environ["UNICODE_DB_PATH"]).parent

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
        print(
            "Please create the directory manually or set UNICODE_DB_PATH environment variable",
            file=sys.stderr,
        )
        sys.exit(1)


class Database:
    def create(self):
        def execute(conn, name, dml):
            with Cursor(conn) as cur:
                try:
                    cur.execute(dml)
                    conn.commit()
                    print(f"Created table: {name}")
                except Exception as e:
                    t = type(e)
                    s = str(e)
                    if t == sqlite3.OperationalError and s.endswith(" already exists"):
                        print(f"Table already exists: {name}", file=sys.stderr)
                    else:
                        print(f"Failed to create table: {name}", file=sys.stderr)
                        print(f"{type(e).__name__}: {str(e)}", file=sys.stderr)

        with Connection() as conn:
            execute(
                conn,
                "char",
                "create table char(id integer primary key, name text, detail text, codetext text, char text, block text)",
            )
            execute(
                conn,
                "codepoint",
                "create table codepoint(char integer, seq integer, code integer, primary key(char, seq))",
            )
            execute(
                conn, "char_index", "create unique index char_index on char(codetext)"
            )

    def delete(self):
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
