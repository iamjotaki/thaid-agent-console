import os
import json
import time
import base64
import hmac
import hashlib
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, Request, Response, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import psutil

from agent_engine import run_agent_turn, execute_tool

app = FastAPI(title="ThaiD Antigravity Agent Web Console")

# Templates & Static
os.makedirs("templates", exist_ok=True)
os.makedirs("static/js", exist_ok=True)
os.makedirs("static/css", exist_ok=True)

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

SSO_SECRET = os.environ.get("JWT_SECRET", "thaid-super-sso-secret-prod-2026-secure").encode("utf-8")
SUPER_ADMIN_EMAIL = "iamjotaki@gmail.com"

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
    
    # 2. Check local dev or header token
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

class ChatRequest(BaseModel):
    prompt: str
    history: Optional[List[Dict[str, Any]]] = []

class QuickActionRequest(BaseModel):
    action: str
    target: Optional[str] = None

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    user = get_current_user(request)
    if not user:
        # Redirect to Central SSO Google Login
        from_url = "https://agent.thaid.online"
        return RedirectResponse(f"https://thaid.online/api/auth/google?from={from_url}")
    
    # Only allow Super Admin
    if user["email"] != SUPER_ADMIN_EMAIL and user.get("role") != "superadmin":
        return templates.TemplateResponse("access_denied.html", {"request": request, "user": user})

    return templates.TemplateResponse("index.html", {
        "request": request,
        "user": user,
        "super_admin_email": SUPER_ADMIN_EMAIL
    })

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    user = get_current_user(request)
    if user and user["email"] == SUPER_ADMIN_EMAIL:
        return RedirectResponse("/")
    return templates.TemplateResponse("login.html", {"request": request})

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

@app.post("/api/agent/chat")
async def chat_stream(req: ChatRequest, request: Request):
    user = get_current_user(request)
    if not user or user["email"] != SUPER_ADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="Unauthorized")

    async def event_generator():
        try:
            async for event in run_agent_turn(req.history or [], req.prompt):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
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
