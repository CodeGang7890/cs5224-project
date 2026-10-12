"""The mock's local SQLite database: the customers you chat as, and the messages.

- customers: wa_id (the number without "+", as WhatsApp ids are), name.
- messages: one per WhatsApp message, either way: `from_customer` true (you sent it to the
  business) or false (the business's reply, received by the fake Graph API). `status`: sent /
  failed (the webhook call failed: `error` says why) / received.
"""

import random
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS customers (
    wa_id TEXT PRIMARY KEY,
    name TEXT NOT NULL DEFAULT '',
    created_time TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    wamid TEXT NOT NULL UNIQUE,
    wa_id TEXT NOT NULL,
    phone_number_id TEXT NOT NULL,
    from_customer INTEGER NOT NULL,
    text TEXT NOT NULL,
    status TEXT NOT NULL,
    error TEXT NOT NULL DEFAULT '',
    created_time TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS messages_chat ON messages (wa_id, phone_number_id, id);
"""
# Sample customers to chat as, added on start if they're missing (yours are kept).
SAMPLE_CUSTOMERS = [
    ('6591234567', 'Alice Tan'),
    ('6582345678', 'Ben Lim'),
    ('6593456789', 'Chloe Ng'),
    ('6584567890', 'Daniel Koh'),
    ('6595678901', 'Emily Wong'),
]


def now() -> str:
    return datetime.now(UTC).isoformat()


@contextmanager
def connect():
    connection = sqlite3.connect(config.DB_PATH)
    connection.row_factory = sqlite3.Row
    try:
        with connection:  # commits, or rolls back on an error
            yield connection
    finally:
        connection.close()


def init() -> None:
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect() as db:
        db.executescript(SCHEMA)
        # One by one, so they keep this order in the list (customers are listed by created_time).
        for wa_id, name in SAMPLE_CUSTOMERS:
            db.execute('INSERT OR IGNORE INTO customers (wa_id, name, created_time) VALUES (?, ?, ?)', (wa_id, name, now()))


def customers() -> list[dict]:
    with connect() as db:
        return [dict(row) for row in db.execute('SELECT * FROM customers ORDER BY created_time, wa_id')]


def customer(wa_id: str) -> dict | None:
    with connect() as db:
        row = db.execute('SELECT * FROM customers WHERE wa_id = ?', (wa_id,)).fetchone()
    return dict(row) if row else None


def random_sg_number() -> str:
    """A Singapore mobile number as a WhatsApp id: 65 + 8 or 9 + 7 digits."""
    return f'65{random.choice("89")}{random.randint(0, 9_999_999):07d}'


def add_customer(name: str, wa_id: str | None = None) -> dict:
    with connect() as db:
        while True:
            wa_id = wa_id or random_sg_number()
            if not db.execute('SELECT 1 FROM customers WHERE wa_id = ?', (wa_id,)).fetchone():
                break
            wa_id = None
        db.execute('INSERT INTO customers (wa_id, name, created_time) VALUES (?, ?, ?)', (wa_id, name.strip(), now()))
    return customer(wa_id)


def add_message(wamid: str, wa_id: str, phone_number_id: str, from_customer: bool, text: str, status: str) -> dict:
    with connect() as db:
        if not from_customer and not db.execute('SELECT 1 FROM customers WHERE wa_id = ?', (wa_id,)).fetchone():
            db.execute('INSERT INTO customers (wa_id, name, created_time) VALUES (?, ?, ?)', (wa_id, '', now()))
        cursor = db.execute(
            'INSERT INTO messages (wamid, wa_id, phone_number_id, from_customer, text, status, created_time) '
            'VALUES (?, ?, ?, ?, ?, ?, ?)',
            (wamid, wa_id, phone_number_id, int(from_customer), text, status, now()),
        )
        row = db.execute('SELECT * FROM messages WHERE id = ?', (cursor.lastrowid,)).fetchone()
    return message_dict(row)


def set_status(message_id: int, status: str, error: str = '') -> dict:
    with connect() as db:
        db.execute('UPDATE messages SET status = ?, error = ? WHERE id = ?', (status, error, message_id))
        row = db.execute('SELECT * FROM messages WHERE id = ?', (message_id,)).fetchone()
    return message_dict(row)


def messages(wa_id: str, phone_number_id: str, after: int = 0) -> list[dict]:
    with connect() as db:
        rows = db.execute(
            'SELECT * FROM messages WHERE wa_id = ? AND phone_number_id = ? AND id > ? ORDER BY id',
            (wa_id, phone_number_id, after),
        )
        return [message_dict(row) for row in rows]


def last_messages(wa_id: str) -> dict[str, dict]:
    """phone_number_id → the latest message of this customer's chat with that business."""
    with connect() as db:
        rows = db.execute(
            'SELECT m.* FROM messages m JOIN (SELECT phone_number_id, MAX(id) AS id FROM messages WHERE wa_id = ? '
            'GROUP BY phone_number_id) last ON last.id = m.id',
            (wa_id,),
        )
        return {row['phone_number_id']: message_dict(row) for row in rows}


def reset() -> None:
    with connect() as db:
        db.execute('DELETE FROM messages')


def message_dict(row) -> dict:
    item = dict(row)
    item['from_customer'] = bool(item['from_customer'])
    return item
