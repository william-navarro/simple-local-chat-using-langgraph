"""Async SQLite conversation storage.

Stores conversations and messages in backend/data/conversations.db.
Each function opens its own connection (aiosqlite serializes writes via SQLite locking).
"""

import json
import time
import uuid
from pathlib import Path

import aiosqlite

_DB_PATH = Path(__file__).parent / "data" / "conversations.db"


async def init_db() -> None:
    """Create tables if they don't exist."""
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(str(_DB_PATH)) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL DEFAULT 'New conversation',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL DEFAULT '',
                message_type TEXT,
                image_base64 TEXT,
                image_media_type TEXT,
                tool_calls TEXT,
                images TEXT,
                timestamp REAL NOT NULL,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_conversation_id
            ON messages(conversation_id)
        """)
        await db.commit()


async def create_conversation(conv_id: str | None = None, title: str = "New conversation") -> dict:
    """Create a new conversation. Returns {id, title, created_at, updated_at}."""
    cid = conv_id or str(uuid.uuid4())
    now = time.time()
    async with aiosqlite.connect(str(_DB_PATH)) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute(
            "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (cid, title, now, now),
        )
        await db.commit()
    return {"id": cid, "title": title, "created_at": now, "updated_at": now}


async def list_conversations() -> list[dict]:
    """Return all conversations with metadata + message_count (no message content)."""
    async with aiosqlite.connect(str(_DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT c.id, c.title, c.created_at, c.updated_at,
                   COUNT(m.id) as message_count
            FROM conversations c
            LEFT JOIN messages m ON m.conversation_id = c.id
            GROUP BY c.id
            ORDER BY c.updated_at DESC
        """)
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_conversation(conv_id: str) -> dict | None:
    """Return conversation with all messages, or None if not found."""
    async with aiosqlite.connect(str(_DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM conversations WHERE id = ?", (conv_id,)
        )
        conv = await cursor.fetchone()
        if not conv:
            return None
        conv = dict(conv)

        cursor = await db.execute(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY timestamp ASC",
            (conv_id,),
        )
        rows = await cursor.fetchall()
        conv["messages"] = [_deserialize_message(r) for r in rows]
        return conv


async def delete_conversation(conv_id: str) -> bool:
    """Delete conversation + cascade messages. Return True if found."""
    async with aiosqlite.connect(str(_DB_PATH)) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cursor = await db.execute(
            "DELETE FROM conversations WHERE id = ?", (conv_id,)
        )
        await db.commit()
        return cursor.rowcount > 0


async def add_message(conv_id: str, message: dict) -> dict:
    """Insert a message and update conversation.updated_at. Returns the message with id."""
    msg_id = message.get("id") or str(uuid.uuid4())
    now = message.get("timestamp") or time.time()
    async with aiosqlite.connect(str(_DB_PATH)) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute(
            """INSERT INTO messages
               (id, conversation_id, role, content, message_type,
                image_base64, image_media_type, tool_calls, images, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                msg_id, conv_id, message["role"], message.get("content", ""),
                message.get("message_type"),
                message.get("image_base64"),
                message.get("image_media_type"),
                json.dumps(message["tool_calls"]) if message.get("tool_calls") else None,
                json.dumps(message["images"]) if message.get("images") else None,
                now,
            ),
        )
        await db.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (now, conv_id),
        )
        await db.commit()
    return {**message, "id": msg_id, "timestamp": now}


async def update_message(msg_id: str, updates: dict) -> bool:
    """Update specific fields on a message. Returns True if found."""
    allowed = {"content", "message_type", "tool_calls", "images"}
    fields = []
    values = []
    for key, val in updates.items():
        if key not in allowed:
            continue
        if key in ("tool_calls", "images") and val is not None:
            val = json.dumps(val)
        fields.append(f"{key} = ?")
        values.append(val)
    if not fields:
        return False
    values.append(msg_id)
    async with aiosqlite.connect(str(_DB_PATH)) as db:
        cursor = await db.execute(
            f"UPDATE messages SET {', '.join(fields)} WHERE id = ?",
            values,
        )
        await db.commit()
        return cursor.rowcount > 0


async def update_title(conv_id: str, title: str) -> bool:
    """Update a conversation's title. Return True if found."""
    async with aiosqlite.connect(str(_DB_PATH)) as db:
        cursor = await db.execute(
            "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
            (title, time.time(), conv_id),
        )
        await db.commit()
        return cursor.rowcount > 0


async def get_messages(conv_id: str) -> list[dict]:
    """Return all messages for a conversation, ordered by timestamp."""
    async with aiosqlite.connect(str(_DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY timestamp ASC",
            (conv_id,),
        )
        rows = await cursor.fetchall()
        return [_deserialize_message(r) for r in rows]


def _deserialize_message(row: aiosqlite.Row) -> dict:
    """Convert a DB row to a message dict, parsing JSON columns."""
    d = dict(row)
    for col in ("tool_calls", "images"):
        if d.get(col):
            try:
                d[col] = json.loads(d[col])
            except (json.JSONDecodeError, TypeError):
                d[col] = None
    return d
