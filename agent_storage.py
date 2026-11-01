import os
import sqlite3
import time
import uuid
import json
from typing import List, Dict, Any, Optional

def get_db_path() -> str:
    path = os.environ.get("AGENT_DB_PATH")
    if path:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        return path
    
    # Try /app/data in container
    if os.path.exists("/app/data"):
        return "/app/data/agent_storage.db"
    
    # Local fallback
    local_data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    os.makedirs(local_data_dir, exist_ok=True)
    return os.path.join(local_data_dir, "agent_storage.db")

def get_db():
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        c = conn.cursor()
        c.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            icon TEXT DEFAULT '📁',
            description TEXT,
            working_dir TEXT DEFAULT '/',
            is_default INTEGER DEFAULT 0,
            created_at INTEGER
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS threads (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            title TEXT NOT NULL,
            agent_mode TEXT DEFAULT 'single',
            created_at INTEGER,
            updated_at INTEGER,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            thread_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT,
            tool_calls TEXT,
            created_at INTEGER,
            FOREIGN KEY (thread_id) REFERENCES threads(id) ON DELETE CASCADE
        )
        """)

        # Seed default projects if none exist
        c.execute("SELECT COUNT(*) FROM projects")
        if c.fetchone()[0] == 0:
            defaults = [
                ("server", "Infrastructure & Server Admin", "⚡", "Oracle Cloud Ubuntu VM, Docker, Coolify Apps", "/", 1),
                ("thaid-online", "ThaiD Portal", "🌐", "Next.js 16, Central SSO, Hero, Services", "/var/www/thaid.online", 0),
                ("novel", "Novel Studio", "📚", "AI Novel & Chapter Generator", "/var/www/novel", 0),
                ("social", "Social Poster", "📢", "Auto Facebook Page Poster 24h", "/var/www/social", 0),
                ("vault", "Vault Storage", "🔐", "Secure Password & Key Vault", "/var/www/vault", 0),
                ("clip", "Clip AI Shorts", "🎬", "Short Video & Cartoon Shorts Generator", "/var/www/clip", 0),
                ("chat", "Smart Chat AI", "💬", "LINE Official Account Auto Reply", "/var/www/chat", 0),
                ("sticker", "Sticker Studio", "🎨", "LINE & Telegram AI Sticker Maker", "/var/www/sticker", 0),
                ("mockup", "Mockup Studio", "📸", "4K Product Mockup Generator", "/var/www/mockup", 0),
            ]
            now = int(time.time())
            for pid, name, icon, desc, wdir, is_def in defaults:
                c.execute("""
                    INSERT INTO projects (id, name, icon, description, working_dir, is_default, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (pid, name, icon, desc, wdir, is_def, now))

            # Create default first thread
            tid = "init-welcome-thread"
            c.execute("""
                INSERT INTO threads (id, project_id, title, agent_mode, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (tid, "server", "⚡ สนทนาเริ่มต้น (DevOps & Server)", "single", now, now))

        conn.commit()

# Projects CRUD
def list_projects() -> List[Dict[str, Any]]:
    init_db()
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM projects ORDER BY is_default DESC, name ASC")
        return [dict(r) for r in c.fetchall()]

def create_project(name: str, icon: str = "📁", description: str = "", working_dir: str = "/") -> Dict[str, Any]:
    init_db()
    pid = str(uuid.uuid4())[:8]
    now = int(time.time())
    with get_db() as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO projects (id, name, icon, description, working_dir, is_default, created_at)
            VALUES (?, ?, ?, ?, ?, 0, ?)
        """, (pid, name, icon or "📁", description, working_dir or "/", now))
        conn.commit()
    return {"id": pid, "name": name, "icon": icon, "description": description, "working_dir": working_dir}

# Threads CRUD
def list_threads(project_id: Optional[str] = None) -> List[Dict[str, Any]]:
    init_db()
    with get_db() as conn:
        c = conn.cursor()
        if project_id:
            c.execute("SELECT * FROM threads WHERE project_id = ? ORDER BY updated_at DESC", (project_id,))
        else:
            c.execute("SELECT * FROM threads ORDER BY updated_at DESC")
        return [dict(r) for r in c.fetchall()]

def create_thread(project_id: str, title: str = "แชทใหม่", agent_mode: str = "single") -> Dict[str, Any]:
    init_db()
    tid = str(uuid.uuid4())
    now = int(time.time())
    with get_db() as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO threads (id, project_id, title, agent_mode, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (tid, project_id, title, agent_mode, now, now))
        conn.commit()
    return {"id": tid, "project_id": project_id, "title": title, "agent_mode": agent_mode, "created_at": now, "updated_at": now}

def get_thread(thread_id: str) -> Optional[Dict[str, Any]]:
    init_db()
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM threads WHERE id = ?", (thread_id,))
        row = c.fetchone()
        return dict(row) if row else None

def update_thread_title(thread_id: str, title: str):
    init_db()
    now = int(time.time())
    with get_db() as conn:
        c = conn.cursor()
        c.execute("UPDATE threads SET title = ?, updated_at = ? WHERE id = ?", (title, now, thread_id))
        conn.commit()

def delete_thread(thread_id: str):
    init_db()
    with get_db() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM messages WHERE thread_id = ?", (thread_id,))
        c.execute("DELETE FROM threads WHERE id = ?", (thread_id,))
        conn.commit()

# Messages CRUD
def get_messages(thread_id: str) -> List[Dict[str, Any]]:
    init_db()
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM messages WHERE thread_id = ? ORDER BY id ASC", (thread_id,))
        rows = c.fetchall()
        msgs = []
        for r in rows:
            d = dict(r)
            if d.get("tool_calls"):
                try:
                    d["tool_calls"] = json.loads(d["tool_calls"])
                except Exception:
                    pass
            msgs.append(d)
        return msgs

def save_message(thread_id: str, role: str, content: str, tool_calls: Optional[Any] = None):
    init_db()
    now = int(time.time())
    tc_json = json.dumps(tool_calls, ensure_ascii=False) if tool_calls else None
    with get_db() as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO messages (thread_id, role, content, tool_calls, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (thread_id, role, content, tc_json, now))
        c.execute("UPDATE threads SET updated_at = ? WHERE id = ?", (now, thread_id))
        conn.commit()
