import sqlite3, logging


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
                    sent_date   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_events_sent_date ON events(sent_date);
            """
            )

    # Проверка на наличие события в бд
    def has_event(self, event_id: str) -> bool:
        try:
            cur = self.conn.cursor()
            cur.execute("SELECT 1 FROM events WHERE id = ? LIMIT 1", (event_id,))
            return cur.fetchone() is not None
        except sqlite3.Error as e:
            logging.error(f"has_event. SQLite3 error: {e}")
            return False

    # Добавление события в бд, хранить 180 дней, после - удалять
    def add_event(self, event_id: str, message: str) -> None:
        try:
            with self.conn:
                self.conn.execute(
                    "INSERT OR IGNORE INTO events (id, message) VALUES (?, ?)",
                    (event_id, message)
                )
        except sqlite3.Error as e:
            logging.error(f"add_event. SQLite3 error: {e}")

    # Очистка бд от событий старше 180 дней
    def remove_old_events(self, days: int = 180) -> None:
        """Удалить события старше `days` дней (по sent_date)."""
        try:
            cutoff = f"-{days} days"
            with self.conn:
                self.conn.execute(
                    "DELETE FROM events WHERE sent_date < datetime('now', ?)",
                    (cutoff,)
                )
        except sqlite3.Error as e:
            logging.error(f"remove_old_events. SQLite error: {e}")

    # Закрытие бд
    def close(self) -> None:
        self.conn.close()