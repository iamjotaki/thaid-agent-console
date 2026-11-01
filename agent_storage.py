import os
import re
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

        # 9router-style Antigravity Accounts
        c.execute("""
        CREATE TABLE IF NOT EXISTS agy_accounts (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT,
            auth_type TEXT DEFAULT 'pool_rotation',
            token TEXT,
            profile_dir TEXT,
            is_active INTEGER DEFAULT 0,
            created_at INTEGER,
            last_used_at INTEGER
        )
        """)

        # Add attachments column to messages if missing
        try:
            c.execute("ALTER TABLE messages ADD COLUMN attachments TEXT")
        except Exception:
            pass

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
                ("remove", "Remove BG AI", "✨", "AI Background Removal & HD Cutout Studio", "/var/www/remove", 0),
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

        # Seed default AGY accounts if none exist
        c.execute("SELECT COUNT(*) FROM agy_accounts")
        if c.fetchone()[0] == 0:
            now = int(time.time())
            c.execute("""
                INSERT INTO agy_accounts (id, name, email, auth_type, token, profile_dir, is_active, created_at, last_used_at)
                VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
            """, ("acc_jotaki_pool", "Jotaki (47 Keys Auto-Rotation)", "iamjotaki@gmail.com", "pool_rotation", "", "/app/data/agy_profiles/acc_jotaki_pool", now, now))
            c.execute("""
                INSERT INTO agy_accounts (id, name, email, auth_type, token, profile_dir, is_active, created_at, last_used_at)
                VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)
            """, ("acc_thaid_work", "ThaiD Enterprise Workspace", "admin@thaid.online", "pool_rotation", "", "/app/data/agy_profiles/acc_thaid_work", now, now))

        conn.commit()

# Projects CRUD
def list_projects() -> List[Dict[str, Any]]:
    init_db()
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM projects ORDER BY is_default DESC, name ASC")
        return [dict(r) for r in c.fetchall()]

def create_project(name: str, icon: str = "🚀", description: str = "", working_dir: str = "") -> Dict[str, Any]:
    init_db()
    clean_slug = re.sub(r'[^a-zA-Z0-9]+', '-', name.lower()).strip('-')
    if not clean_slug:
        clean_slug = f"project-{str(uuid.uuid4())[:6]}"
    pid = clean_slug

    if not working_dir or working_dir == "/":
        working_dir = f"/var/www/{clean_slug}"

    # Auto create directory & persist in /app/data/projects/<clean_slug>
    try:
        persist_dir = f"/app/data/projects/{clean_slug}" if os.path.exists("/app/data") else f"/var/lib/coolify/agent_data/projects/{clean_slug}"
        os.makedirs(persist_dir, exist_ok=True)
        if working_dir.startswith("/var/www/"):
            os.makedirs(os.path.dirname(working_dir), exist_ok=True)
            if os.path.exists(working_dir) and not os.path.islink(working_dir):
                try:
                    os.rmdir(working_dir)
                except Exception:
                    pass
            if not os.path.exists(working_dir):
                try:
                    os.symlink(persist_dir, working_dir)
                except Exception:
                    os.makedirs(working_dir, exist_ok=True)
        else:
            os.makedirs(working_dir, exist_ok=True)
    except Exception as e:
        print(f"Error creating dir for project {clean_slug}: {e}")

    now = int(time.time())
    with get_db() as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO projects (id, name, icon, description, working_dir, is_default, created_at)
            VALUES (?, ?, ?, ?, ?, 0, ?)
        """, (pid, name, icon or "🚀", description, working_dir, now))
        conn.commit()
    return {"id": pid, "name": name, "icon": icon or "🚀", "description": description, "working_dir": working_dir}

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
            if d.get("attachments"):
                try:
                    d["attachments"] = json.loads(d["attachments"])
                except Exception:
                    pass
            msgs.append(d)
        return msgs

def save_message(thread_id: str, role: str, content: str, tool_calls: Optional[Any] = None, attachments: Optional[Any] = None):
    init_db()
    now = int(time.time())
    tc_json = json.dumps(tool_calls, ensure_ascii=False) if tool_calls else None
    att_json = json.dumps(attachments, ensure_ascii=False) if attachments else None
    with get_db() as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO messages (thread_id, role, content, tool_calls, attachments, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (thread_id, role, content, tc_json, att_json, now))
        c.execute("UPDATE threads SET updated_at = ? WHERE id = ?", (now, thread_id))
        conn.commit()

# ----------------- 9ROUTER AGY ACCOUNTS CRUD -----------------

def get_profiles_base_dir() -> str:
    if os.path.exists("/app/data"):
        d = "/app/data/agy_profiles"
    elif os.path.exists("/var/lib/coolify/agent_data"):
        d = "/var/lib/coolify/agent_data/agy_profiles"
    else:
        d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "agy_profiles")
    os.makedirs(d, exist_ok=True)
    return d

def ensure_agy_profile(account_id: str, auth_type: str = "pool_rotation", token: str = "") -> str:
    base = get_profiles_base_dir()
    pdir = os.path.join(base, account_id)
    cli_dir = os.path.join(pdir, ".gemini", "antigravity-cli")
    os.makedirs(cli_dir, exist_ok=True)
    
    settings_file = os.path.join(cli_dir, "settings.json")
    if not os.path.exists(settings_file):
        with open(settings_file, "w", encoding="utf-8") as f:
            json.dump({"modelProvider": "gemini"}, f, indent=2)
    return pdir

def list_agy_accounts() -> List[Dict[str, Any]]:
    init_db()
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM agy_accounts ORDER BY is_active DESC, created_at ASC")
        rows = [dict(r) for r in c.fetchall()]
        for r in rows:
            ensure_agy_profile(r["id"], r.get("auth_type", "pool_rotation"), r.get("token", ""))
        return rows

def get_active_agy_account() -> Optional[Dict[str, Any]]:
    init_db()
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM agy_accounts WHERE is_active = 1 LIMIT 1")
        row = c.fetchone()
        if row:
            d = dict(row)
            ensure_agy_profile(d["id"], d.get("auth_type", "pool_rotation"), d.get("token", ""))
            return d
        
        # Fallback to first account
        c.execute("SELECT * FROM agy_accounts ORDER BY created_at ASC LIMIT 1")
        row = c.fetchone()
        if row:
            d = dict(row)
            c.execute("UPDATE agy_accounts SET is_active = 1 WHERE id = ?", (d["id"],))
            conn.commit()
            d["is_active"] = 1
            ensure_agy_profile(d["id"], d.get("auth_type", "pool_rotation"), d.get("token", ""))
            return d
        return None

def switch_agy_account(account_id: str) -> bool:
    init_db()
    now = int(time.time())
    with get_db() as conn:
        c = conn.cursor()
        c.execute("UPDATE agy_accounts SET is_active = 0")
        c.execute("UPDATE agy_accounts SET is_active = 1, last_used_at = ? WHERE id = ?", (now, account_id))
        conn.commit()
        return c.rowcount > 0

def create_agy_account(name: str, email: str = "", auth_type: str = "pool_rotation", token: str = "") -> Dict[str, Any]:
    init_db()
    clean_id = "acc_" + re.sub(r'[^a-zA-Z0-9]+', '_', name.lower()).strip('_')
    if len(clean_id) < 5 or clean_id == "acc_":
        clean_id = f"acc_{str(uuid.uuid4())[:8]}"
    
    # Check if exists
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT id FROM agy_accounts WHERE id = ?", (clean_id,))
        if c.fetchone():
            clean_id = f"{clean_id}_{str(uuid.uuid4())[:4]}"
            
        pdir = ensure_agy_profile(clean_id, auth_type, token)
        now = int(time.time())
        c.execute("""
            INSERT INTO agy_accounts (id, name, email, auth_type, token, profile_dir, is_active, created_at, last_used_at)
            VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)
        """, (clean_id, name, email, auth_type, token, pdir, now, now))
        conn.commit()
        
    return {
        "id": clean_id,
        "name": name,
        "email": email,
        "auth_type": auth_type,
        "token": token,
        "profile_dir": pdir,
        "is_active": 0
    }

def delete_agy_account(account_id: str) -> bool:
    init_db()
    with get_db() as conn:
        c = conn.cursor()
        # Do not delete if only 1 account remains
        c.execute("SELECT COUNT(*) FROM agy_accounts")
        if c.fetchone()[0] <= 1:
            return False
            
        c.execute("SELECT is_active FROM agy_accounts WHERE id = ?", (account_id,))
        row = c.fetchone()
        was_active = row and row[0] == 1
        
        c.execute("DELETE FROM agy_accounts WHERE id = ?", (account_id,))
        
        if was_active:
            # Activate another
            c.execute("UPDATE agy_accounts SET is_active = 1 WHERE id IN (SELECT id FROM agy_accounts LIMIT 1)")
            
        conn.commit()
        return True

