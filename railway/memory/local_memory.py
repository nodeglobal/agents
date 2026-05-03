"""
Local SQLite-based memory module — drop-in replacement for Mem0.
Stores memories at ~/.deltanode/memory.db with keyword-based search.
"""

import os
import sqlite3
import logging
import datetime
import uuid
from typing import Optional, List
from pathlib import Path

logger = logging.getLogger(__name__)

VALID_PROJECTS = None

DB_DIR = Path.home() / '.deltanode'
DB_PATH = DB_DIR / 'memory.db'

_conn: Optional[sqlite3.Connection] = None


def _get_conn() -> sqlite3.Connection:
    """Get or create the SQLite connection, initializing tables on first use."""
    global _conn
    if _conn is None:
        DB_DIR.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _init_tables(_conn)
    return _conn


def _init_tables(conn: sqlite3.Connection):
    """Create tables if they don't exist."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS memories (
            id TEXT PRIMARY KEY,
            content TEXT NOT NULL,
            project TEXT NOT NULL DEFAULT 'general',
            source TEXT DEFAULT 'agent_stack',
            date TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_memories_project ON memories(project);
        CREATE INDEX IF NOT EXISTS idx_memories_date ON memories(date);
    """)
    conn.commit()


def add_memory(content: str, project: str = 'general') -> dict:
    """Store a memory with metadata."""
    if project not in VALID_PROJECTS:
        project = 'general'
    try:
        conn = _get_conn()
        memory_id = str(uuid.uuid4())
        now = datetime.datetime.utcnow().isoformat()
        today = datetime.date.today().isoformat()
        conn.execute(
            "INSERT INTO memories (id, content, project, source, date, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (memory_id, content, project, 'agent_stack', today, now)
        )
        conn.commit()
        logger.info(f'Memory added [{project}]: {content[:60]}...')
        return {'id': memory_id, 'content': content, 'project': project, 'date': today}
    except Exception as e:
        logger.error(f'add_memory failed: {e}')
        return {}


def search_memory(query: str, project: Optional[str] = None, limit: int = 10) -> List[dict]:
    """Search memories using keyword matching. Splits query into words and ranks by match count."""
    try:
        conn = _get_conn()
        # Get candidate rows
        if project:
            cursor = conn.execute(
                "SELECT * FROM memories WHERE project IN (?, 'general', 'agents') ORDER BY created_at DESC",
                (project,)
            )
        else:
            cursor = conn.execute("SELECT * FROM memories ORDER BY created_at DESC")

        rows = cursor.fetchall()

        # Keyword scoring
        keywords = [w.lower() for w in query.split() if len(w) > 2]
        if not keywords:
            # No meaningful keywords, return most recent
            results = [_row_to_dict(r) for r in rows[:limit]]
            return results

        scored = []
        for row in rows:
            content_lower = row['content'].lower()
            score = sum(1 for kw in keywords if kw in content_lower)
            if score > 0:
                scored.append((score, row))

        # Sort by score descending, then by recency
        scored.sort(key=lambda x: x[0], reverse=True)
        results = [_row_to_dict(r) for _, r in scored[:limit]]
        return results
    except Exception as e:
        logger.error(f'search_memory failed: {e}')
        return []


def get_all_for_project(project: str) -> List[dict]:
    """Return all memories for a project (includes 'general')."""
    try:
        conn = _get_conn()
        cursor = conn.execute(
            "SELECT * FROM memories WHERE project IN (?, 'general') ORDER BY created_at DESC",
            (project,)
        )
        return [_row_to_dict(row) for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f'get_all_for_project failed: {e}')
        return []


def log_agent_update(agent: str, change: str):
    """Log an agent audit trail entry."""
    content = f"[{datetime.date.today()}] {agent}: {change}"
    add_memory(content, project='agents')


def _row_to_dict(row: sqlite3.Row) -> dict:
    """Convert a sqlite3.Row to a dict matching Mem0 response shape."""
    return {
        'id': row['id'],
        'memory': row['content'],
        'metadata': {
            'project': row['project'],
            'source': row['source'],
            'date': row['date'],
        },
        'created_at': row['created_at'],
    }
