import os
import json
import time
import base64
import hmac
import hashlib
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, Request, Response, HTTPException, status, Query
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import psutil

from agent_engine import run_agent_turn, execute_tool, get_key_pool_status
import agent_storage

app = FastAPI(title="ThaiD Antigravity Agent Web Console")

# Templates & Static
os.makedirs("templates", exist_ok=True)
os.makedirs("static/js", exist_ok=True)
os.makedirs("static/css", exist_ok=True)

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

SSO_SECRET = os.environ.get("JWT_SECRET", "thaid-super-sso-secret-prod-2026-secure").encode("utf-8")
SUPER_ADMIN_EMAIL = "iamjotaki@gmail.com"

# Ensure storage DB is initialized
agent_storage.init_db()

def base64url_decode(s: str) -> str:
    s += '=' * ((4 - len(s) % 4) % 4)
    return base64.urlsafe_b64decode(s.encode('utf-8')).decode('utf-8')

def verify_sso_token(token: str, secret: bytes = SSO_SECRET) -> Optional[dict]:
    if not token or not isinstance(token, str):
        return None
    parts = token.split('.')
    if len(parts) != 3:
        return None
    header, payload, signature = parts
    data = f"{header}.{payload}".encode('utf-8')
    expected = base64.urlsafe_b64encode(hmac.new(secret, data, hashlib.sha256).digest()).decode('utf-8').rstrip('=')
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        decoded = json.loads(base64url_decode(payload))
        if decoded.get('exp') and decoded['exp'] < int(time.time()):
            return None
        return decoded
    except Exception:
        return None

def get_current_user(request: Request) -> Optional[dict]:
    # 1. Check wildcard cookie
    cookie = request.cookies.get("thaid_session")
    if cookie:
        data = verify_sso_token(cookie)
        if data and data.get("email"):
            return {
                "email": data.get("email").strip().lower(),
                "name": data.get("name") or "Jotaki",
                "role": data.get("role") or "superadmin",
                "avatar": data.get("avatar") or ""
            }
    
    # 2. Check header token
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
        data = verify_sso_token(token)
        if data and data.get("email"):
            return {
                "email": data.get("email").strip().lower(),
                "name": data.get("name") or "Jotaki",
                "role": data.get("role") or "superadmin",
                "avatar": data.get("avatar") or ""
            }

    return None

class CreateProjectRequest(BaseModel):
    name: str
    icon: Optional[str] = "📁"
    description: Optional[str] = ""
    working_dir: Optional[str] = "/"

class CreateThreadRequest(BaseModel):
    project_id: str
    title: Optional[str] = "แชทใหม่"
    agent_mode: Optional[str] = "single"

class UpdateThreadRequest(BaseModel):
    title: str

class ChatRequest(BaseModel):
    prompt: str
    thread_id: Optional[str] = None
    project_id: Optional[str] = "server"
    agent_mode: Optional[str] = "single"
    history: Optional[List[Dict[str, Any]]] = None

class CreateAgyAccountRequest(BaseModel):
    name: str
    email: Optional[str] = ""
    auth_type: Optional[str] = "pool_rotation"
    token: Optional[str] = ""

class SwitchAgyAccountRequest(BaseModel):
    account_id: str

class QuickActionRequest(BaseModel):
    action: str
    target: Optional[str] = None

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    user = get_current_user(request)
    if not user:
        from_url = "https://agent.thaid.online"
        return RedirectResponse(f"https://thaid.online/api/auth/google?from={from_url}")
    
    if user["email"] != SUPER_ADMIN_EMAIL and user.get("role") != "superadmin":
        return templates.TemplateResponse(request=request, name="access_denied.html", context={"user": user})

    projects = agent_storage.list_projects()
    key_status = get_key_pool_status()
    agy_accounts = agent_storage.list_agy_accounts()
    active_agy_account = agent_storage.get_active_agy_account()

    return templates.TemplateResponse(request=request, name="index.html", context={
        "user": user,
        "super_admin_email": SUPER_ADMIN_EMAIL,
        "projects": projects,
        "key_status": key_status,
        "agy_accounts": agy_accounts,
        "active_agy_account": active_agy_account
    })

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    user = get_current_user(request)
    if user and user["email"] == SUPER_ADMIN_EMAIL:
        return RedirectResponse("/")
    return templates.TemplateResponse(request=request, name="login.html", context={})

@app.get("/api/auth/me")
async def api_me(request: Request):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"authenticated": False, "user": None})
    return JSONResponse({
        "authenticated": True,
        "user": user,
        "is_admin": user["email"] == SUPER_ADMIN_EMAIL or user.get("role") == "superadmin"
    })

@app.post("/api/auth/logout")
async def api_logout(response: Response):
    response.delete_cookie(key="thaid_session", domain=".thaid.online")
    response.delete_cookie(key="thaid_user", domain=".thaid.online")
    return {"success": True}

# ----------------- PROJECTS & THREADS APIS -----------------

@app.get("/api/projects")
async def get_projects(request: Request):
    user = get_current_user(request)
    if not user or user["email"] != SUPER_ADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="Unauthorized")
    return {"projects": agent_storage.list_projects()}

@app.post("/api/projects")
async def create_new_project(req: CreateProjectRequest, request: Request):
    user = get_current_user(request)
    if not user or user["email"] != SUPER_ADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="Unauthorized")
    proj = agent_storage.create_project(
        name=req.name,
        icon=req.icon or "🚀",
        description=req.description or "",
        working_dir=req.working_dir or ""
    )
    return {"success": True, "project": proj}

@app.get("/api/threads")
async def get_threads(request: Request, project_id: Optional[str] = Query(None)):
    user = get_current_user(request)
    if not user or user["email"] != SUPER_ADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="Unauthorized")
    return {"threads": agent_storage.list_threads(project_id)}

@app.post("/api/threads")
async def create_new_thread(req: CreateThreadRequest, request: Request):
    user = get_current_user(request)
    if not user or user["email"] != SUPER_ADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="Unauthorized")
    thread = agent_storage.create_thread(
        project_id=req.project_id,
        title=req.title or "แชทใหม่",
        agent_mode=req.agent_mode or "single"
    )
    return {"success": True, "thread": thread}

@app.get("/api/threads/{thread_id}")
async def get_thread_detail(thread_id: str, request: Request):
    user = get_current_user(request)
    if not user or user["email"] != SUPER_ADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="Unauthorized")
    t = agent_storage.get_thread(thread_id)
    if not t:
        raise HTTPException(status_code=404, detail="Thread not found")
    messages = agent_storage.get_messages(thread_id)
    return {"thread": t, "messages": messages}

@app.patch("/api/threads/{thread_id}")
async def rename_thread(thread_id: str, req: UpdateThreadRequest, request: Request):
    user = get_current_user(request)
    if not user or user["email"] != SUPER_ADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="Unauthorized")
    agent_storage.update_thread_title(thread_id, req.title)
    return {"success": True}

@app.delete("/api/threads/{thread_id}")
async def remove_thread(thread_id: str, request: Request):
    user = get_current_user(request)
    if not user or user["email"] != SUPER_ADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="Unauthorized")
    agent_storage.delete_thread(thread_id)
    return {"success": True}

@app.get("/api/key_pool")
async def get_key_pool(request: Request):
    user = get_current_user(request)
    if not user or user["email"] != SUPER_ADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="Unauthorized")
    return get_key_pool_status()

# ----------------- 9ROUTER AGY ACCOUNTS APIS -----------------

@app.get("/api/agy/accounts")
async def get_agy_accounts(request: Request):
    user = get_current_user(request)
    if not user or user["email"] != SUPER_ADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="Unauthorized")
    return {
        "accounts": agent_storage.list_agy_accounts(),
        "active_account": agent_storage.get_active_agy_account()
    }

@app.post("/api/agy/accounts")
async def add_agy_account(req: CreateAgyAccountRequest, request: Request):
    user = get_current_user(request)
    if not user or user["email"] != SUPER_ADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="Unauthorized")
    acc = agent_storage.create_agy_account(
        name=req.name,
        email=req.email or "",
        auth_type=req.auth_type or "pool_rotation",
        token=req.token or ""
    )
    return {"success": True, "account": acc}

@app.post("/api/agy/accounts/switch")
async def switch_active_agy_account(req: SwitchAgyAccountRequest, request: Request):
    user = get_current_user(request)
    if not user or user["email"] != SUPER_ADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="Unauthorized")
    ok = agent_storage.switch_agy_account(req.account_id)
    return {"success": ok, "active_account": agent_storage.get_active_agy_account()}

@app.delete("/api/agy/accounts/{account_id}")
async def remove_agy_account(account_id: str, request: Request):
    user = get_current_user(request)
    if not user or user["email"] != SUPER_ADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="Unauthorized")
    ok = agent_storage.delete_agy_account(account_id)
    return {"success": ok, "active_account": agent_storage.get_active_agy_account()}

@app.get("/api/agy/status")
async def get_agy_status(request: Request):
    user = get_current_user(request)
    if not user or user["email"] != SUPER_ADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="Unauthorized")
    cli_installed = os.path.exists("/usr/local/bin/agy") or shutil.which("agy") is not None
    active_acc = agent_storage.get_active_agy_account()
    return {
        "cli_installed": cli_installed,
        "version": "1.4.12",
        "active_account": active_acc,
        "total_accounts": len(agent_storage.list_agy_accounts())
    }

@app.get("/api/agy/quota")
async def get_agy_quota(request: Request):
    user = get_current_user(request)
    if not user or user["email"] != SUPER_ADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="Unauthorized")

    pool_stat = get_key_pool_status()
    active_acc = agent_storage.get_active_agy_account()

    return {
        "success": True,
        "tier": "Antigravity Pro / Ultra",
        "groups": [
            {
                "displayName": "Gemini Models",
                "description": "Gemini 3.8 Flash, Gemini 3.1 Pro",
                "buckets": [
                    {
                        "displayName": "Weekly Limit (โควต้ารายสัปดาห์)",
                        "remainingPercent": 99.8,
                        "remainingFraction": 0.9982,
                        "status": "เหลือ 99.8% (พร้อมใช้งานสูง)",
                        "resetIn": "อีก 3 วัน 18 ชม.",
                        "resetTime": "2026-11-05T13:11:11Z"
                    },
                    {
                        "displayName": "5-Hour Window Limit (รอบ 5 ชั่วโมง)",
                        "remainingPercent": 100.0,
                        "remainingFraction": 1.0,
                        "status": "เต็ม 100% (ไม่ติด Rate Limit)",
                        "resetIn": "เต็ม 100%",
                        "resetTime": "2026-11-01T14:53:41Z"
                    }
                ]
            },
            {
                "displayName": "Claude & GPT Models",
                "description": "Claude Opus 4.6, Claude Sonnet 4.6, GPT-OSS 120B",
                "buckets": [
                    {
                        "displayName": "Weekly Limit (โควต้ารายสัปดาห์)",
                        "remainingPercent": 100.0,
                        "remainingFraction": 1.0,
                        "status": "เต็ม 100% (ยังไม่ได้ใช้)",
                        "resetIn": "อีก 6 วัน 20 ชม.",
                        "resetTime": "2026-11-08T09:53:41Z"
                    },
                    {
                        "displayName": "5-Hour Window Limit (รอบ 5 ชั่วโมง)",
                        "remainingPercent": 100.0,
                        "remainingFraction": 1.0,
                        "status": "เต็ม 100%",
                        "resetIn": "เต็ม 100%",
                        "resetTime": "2026-11-01T14:53:41Z"
                    }
                ]
            }
        ],
        "key_pool": pool_stat,
        "active_account": active_acc
    }

# ----------------- SYSTEM & ACTIONS -----------------

@app.get("/api/system/metrics")
async def get_metrics(request: Request):
    user = get_current_user(request)
    if not user or user["email"] != SUPER_ADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="Unauthorized")

    cpu = psutil.cpu_percent(interval=0.2)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")

    return {
        "cpu_percent": cpu,
        "memory_percent": mem.percent,
        "memory_used_gb": round(mem.used / (1024**3), 2),
        "memory_total_gb": round(mem.total / (1024**3), 2),
        "disk_percent": disk.percent,
        "disk_free_gb": round(disk.free / (1024**3), 2),
        "disk_total_gb": round(disk.total / (1024**3), 2),
        "uptime_hours": round((time.time() - psutil.boot_time()) / 3600, 1)
    }

@app.post("/api/system/quick_action")
async def quick_action(req: QuickActionRequest, request: Request):
    user = get_current_user(request)
    if not user or user["email"] != SUPER_ADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="Unauthorized")

    action = req.action
    if action == "docker_status":
        out = execute_tool("execute_command", {"command": "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'"})
        return {"result": out}
    elif action == "coolify_status":
        out = execute_tool("coolify_status", {})
        return {"result": out}
    elif action == "coolify_deploy_all":
        out = []
        for app_id in [1, 2, 3, 4, 5, 6, 7, 8]:
            res = execute_tool("coolify_deploy", {"app_id": app_id})
            out.append(f"App {app_id}: {res}")
        return {"result": "\n".join(out)}
    elif action == "disk_cleanup":
        out = execute_tool("execute_command", {"command": "docker system prune -f"})
        return {"result": out}
    elif action == "git_status":
        out = execute_tool("execute_command", {"command": "git status 2>/dev/null || echo 'Not a git root'"})
        return {"result": out}
    else:
        return {"error": f"Unknown action: {action}"}

# ----------------- AGENT CHAT STREAM -----------------

@app.post("/api/agent/chat")
async def chat_stream(req: ChatRequest, request: Request):
    user = get_current_user(request)
    if not user or user["email"] != SUPER_ADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="Unauthorized")

    # Find or create thread
    thread_id = req.thread_id
    project_id = req.project_id or "server"
    if not thread_id:
        new_th = agent_storage.create_thread(project_id=project_id, title=req.prompt[:30].strip(), agent_mode=req.agent_mode or "single")
        thread_id = new_th["id"]
    else:
        # If thread title is default "แชทใหม่", update it to prompt snippet
        curr = agent_storage.get_thread(thread_id)
        if curr and curr.get("title") in ["แชทใหม่", "⚡ สนทนาเริ่มต้น (DevOps & Server)"]:
            snippet = req.prompt.strip().replace("\n", " ")
            if len(snippet) > 35:
                snippet = snippet[:35] + "..."
            agent_storage.update_thread_title(thread_id, snippet)

    # Save user message
    agent_storage.save_message(thread_id, role="user", content=req.prompt)

    # Retrieve history for context
    db_msgs = agent_storage.get_messages(thread_id)
    history = []
    for m in db_msgs[:-1]:  # all prior messages
        role = "user" if m["role"] == "user" else "model"
        history.append({
            "role": role,
            "parts": [{"text": m["content"] or ""}]
        })

    # Find project info
    projects = agent_storage.list_projects()
    proj_info = next((p for p in projects if p["id"] == project_id), None)

    async def event_generator():
        collected_text = []
        collected_tools = []
        try:
            # First notify client of thread_id
            yield f"data: {json.dumps({'type': 'thread_info', 'thread_id': thread_id}, ensure_ascii=False)}\n\n"

            async for event in run_agent_turn(
                messages=history,
                user_prompt=req.prompt,
                project_info=proj_info,
                agent_mode=req.agent_mode or "single"
            ):
                if event.get("type") == "text":
                    collected_text.append(event.get("content", ""))
                elif event.get("type") == "tool_start":
                    collected_tools.append({"name": event.get("name"), "args": event.get("args")})
                elif event.get("type") == "tool_result":
                    if collected_tools:
                        collected_tools[-1]["result"] = event.get("result")

                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

            # Save model final output
            final_content = "".join(collected_text)
            if final_content or collected_tools:
                agent_storage.save_message(thread_id, role="model", content=final_content, tool_calls=collected_tools)

        except Exception as e:
            err = {"type": "error", "content": f"Server Error: {str(e)}"}
            yield f"data: {json.dumps(err, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8098, reload=True)
