import sqlite3, logging

from typing import Sequence, Tuple


# База данных
class DataBase:
    def __init__(self, path: str, test_mode: bool = False) -> None:
        dbfile = ":memory:" if test_mode else path
        self.conn = sqlite3.connect(dbfile, detect_types=sqlite3.PARSE_DECLTYPES)

        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("PRAGMA synchronous=NORMAL;")
        self.conn.execute("PRAGMA foreign_keys = ON;")

        self._init_tables()

    # Инициализация таблиц
    def _init_tables(self) -> None:
        with self.conn:
            self.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id          TEXT PRIMARY KEY,
                    message     TEXT NOT NULL,
                    translation TEXT,
                    sent_date   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_events_sent_date ON events(sent_date);
                CREATE TABLE IF NOT EXISTS cache (
                    source      TEXT PRIMARY KEY,
                    translated  TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_msg_source ON cache(source);
            """
            )

    # Добавление события в бд, хранить 90 дней, после - удалять
    def add_events(self, events: Sequence[Tuple[str, str, str]]) -> None:
        try:
            with self.conn:
                self.conn.executemany(
                    "INSERT OR IGNORE INTO events (id, message, translation) VALUES (?, ?, ?)",
                    events,
                )
        except sqlite3.Error as e:
            logging.error(f"add_events: SQLite3 error: {e}")

    # Проверка на наличие события в бд
    def has_event(self, event_id: str) -> bool:
        try:
            cur = self.conn.cursor()
            cur.execute("SELECT 1 FROM events WHERE id = ? LIMIT 1", (event_id,))
            return cur.fetchone() is not None
        except sqlite3.Error as e:
            logging.error(f"has_event: SQLite3 error: {e}")
            return False

    # Очистка бд от событий старше 90 дней
    def remove_old_events(self, days: int = 90) -> None:
        try:
            with self.conn:
                self.conn.execute(
                    "DELETE FROM events WHERE sent_date < datetime('now', ?)",
                    (f"-{days} days",),
                )
        except sqlite3.Error as e:
            logging.error(f"remove_old_events: SQLite3 error: {e}")

    # Добавление строк перевода в кэш
    def add_cache_lines(self, lines: Sequence[Tuple[str, str]]) -> None:
        try:
            with self.conn:
                self.conn.executemany(
                    "INSERT OR IGNORE INTO cache (source, translated) VALUES (?, ?)",
                    lines,
                )
        except sqlite3.Error as e:
            logging.error(f"add_cache_lines: SQLite3 error: {e}")

    # Получение перевода из кэша
    def get_translate_line(self, source_line: str) -> str:
        try:
            cur = self.conn.cursor()
            cur.execute("SELECT translated FROM cache WHERE source = ? LIMIT 1", (source_line,))
            row = cur.fetchone()
            return row[0] if row else source_line
        except sqlite3.Error as e:
            logging.error(f"get_translate_line: SQLite3 error: {e}")
            return source_line

    # Закрытие бд
    def close(self):
        self.conn.close()
