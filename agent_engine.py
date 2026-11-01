import os
import json
import subprocess
import shutil
import time
import asyncio
from typing import AsyncGenerator, Dict, Any, List, Optional
import httpx

# ----------------------------------------------------
# 1. MULTI-API KEY POOL WITH ROTATION & FAILOVER
# ----------------------------------------------------
class GeminiKeyPool:
    def __init__(self):
        self.keys: List[str] = []
        self.current_idx = 0
        self.cooloffs: Dict[str, float] = {}  # key -> timestamp when available
        self.usage_count: Dict[str, int] = {}
        self.load_keys()

    def load_keys(self):
        loaded = []
        # 1. From active_vault_keys.json (Extracted from ThaiD Vault)
        candidates = [
            os.path.join(os.path.dirname(__file__), "active_vault_keys.json"),
            "/app/data/active_vault_keys.json",
            "active_vault_keys.json"
        ]
        for p in candidates:
            if os.path.exists(p):
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if isinstance(data, list):
                            for k in data:
                                if isinstance(k, str) and k.startswith("AIzaSy") and k not in loaded:
                                    loaded.append(k.strip())
                    if loaded:
                        break
                except Exception:
                    pass

        # 2. From env GEMINI_API_KEYS (comma separated)
        env_keys = os.environ.get("GEMINI_API_KEYS", "")
        if env_keys:
            for k in env_keys.split(","):
                k = k.strip().strip("'\"")
                if k.startswith("AIzaSy") and k not in loaded:
                    loaded.append(k)

        # 3. From env GEMINI_API_KEY (single fallback)
        single = os.environ.get("GEMINI_API_KEY", "").strip().strip("'\"")
        if single.startswith("AIzaSy") and single not in loaded:
            loaded.append(single)

        self.keys = loaded
        for k in self.keys:
            if k not in self.usage_count:
                self.usage_count[k] = 0

    def get_key(self) -> str:
        if not self.keys:
            self.load_keys()
        if not self.keys:
            return ""

        now = time.time()
        n = len(self.keys)
        # Find next available key not in cooloff
        for i in range(n):
            idx = (self.current_idx + i) % n
            key = self.keys[idx]
            if self.cooloffs.get(key, 0) <= now:
                self.current_idx = (idx + 1) % n
                self.usage_count[key] = self.usage_count.get(key, 0) + 1
                return key

        # If all in cooloff, choose the one cooling down earliest
        earliest_key = min(self.keys, key=lambda k: self.cooloffs.get(k, 0))
        self.usage_count[earliest_key] = self.usage_count.get(earliest_key, 0) + 1
        return earliest_key

    def report_rate_limit(self, key: str, cooldown_seconds: float = 60.0):
        self.cooloffs[key] = time.time() + cooldown_seconds

    def get_status(self) -> Dict[str, Any]:
        now = time.time()
        active = sum(1 for k in self.keys if self.cooloffs.get(k, 0) <= now)
        cooling = len(self.keys) - active
        total_used = sum(self.usage_count.values())
        return {
            "total_keys": len(self.keys),
            "active_keys": active,
            "cooling_keys": cooling,
            "total_requests": total_used
        }

key_pool = GeminiKeyPool()

def get_key_pool_status() -> Dict[str, Any]:
    return key_pool.get_status()

# ----------------------------------------------------
# 2. TOOL DEFINITIONS FOR GEMINI FUNCTION CALLING
# ----------------------------------------------------
TOOLS_DEFINITION = [
    {
        "function_declarations": [
            {
                "name": "execute_command",
                "description": "Execute a shell command on the host server (e.g. docker ps, git status, systemctl, check logs, etc.)",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "command": {
                            "type": "STRING",
                            "description": "The exact shell command line to run."
                        }
                    },
                    "required": ["command"]
                }
            },
            {
                "name": "read_file",
                "description": "Read the contents of a file on the server.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "path": {
                            "type": "STRING",
                            "description": "Absolute or relative path to the file."
                        },
                        "max_lines": {
                            "type": "INTEGER",
                            "description": "Maximum number of lines to return (default 200)."
                        }
                    },
                    "required": ["path"]
                }
            },
            {
                "name": "write_file",
                "description": "Write or overwrite content to a file on the server.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "path": {
                            "type": "STRING",
                            "description": "Absolute or relative path to the file."
                        },
                        "content": {
                            "type": "STRING",
                            "description": "The content to write into the file."
                        }
                    },
                    "required": ["path", "content"]
                }
            },
            {
                "name": "list_directory",
                "description": "List files and subdirectories in a directory path.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "path": {
                            "type": "STRING",
                            "description": "Directory path to list."
                        }
                    },
                    "required": ["path"]
                }
            },
            {
                "name": "get_system_status",
                "description": "Get real-time CPU, RAM, Disk usage, and Docker containers running on the server.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {}
                }
            },
            {
                "name": "coolify_deploy",
                "description": "Trigger deployment of an application (ID 1-8) in Coolify.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "app_id": {
                            "type": "INTEGER",
                            "description": "Coolify Application ID (1: thaid.online, 2: novel, 3: social, 4: vault, 5: sticker, 6: clip, 7: chat, 8: mockup)"
                        }
                    },
                    "required": ["app_id"]
                }
            },
            {
                "name": "coolify_status",
                "description": "Get current deployment and operational status of all Coolify applications.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {}
                }
            }
        ]
    }
]

def execute_tool(name: str, args: Dict[str, Any], working_dir: str = "/") -> str:
    """Executes local tool on the server host / container"""
    try:
        cwd = working_dir if os.path.exists(working_dir) else "/"
        if name == "execute_command":
            cmd = args.get("command", "")
            if not cmd:
                return "Error: Empty command"
            try:
                proc = subprocess.run(
                    cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=180,
                    cwd=cwd
                )
                out = proc.stdout
                err = proc.stderr
                res = f"Exit code: {proc.returncode}\n"
                if out:
                    res += f"STDOUT:\n{out[:4000]}\n"
                if err:
                    res += f"STDERR:\n{err[:2000]}\n"
                return res.strip()
            except subprocess.TimeoutExpired:
                return "Error: Command timed out after 180 seconds. If this is a long-running build or background process, run it with nohup or check its background task status."

        elif name == "read_file":
            path = args.get("path", "")
            if not os.path.isabs(path):
                path = os.path.join(cwd, path)
            max_lines = args.get("max_lines", 200)
            if not os.path.exists(path):
                return f"Error: File not found at {path}"
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                lines = [f.readline() for _ in range(max_lines)]
            return "".join(lines)

        elif name == "write_file":
            path = args.get("path", "")
            if not os.path.isabs(path):
                path = os.path.join(cwd, path)
            content = args.get("content", "")
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return f"Successfully wrote {len(content)} characters to {path}"

        elif name == "list_directory":
            path = args.get("path", ".")
            if not os.path.isabs(path):
                path = os.path.join(cwd, path)
            if not os.path.exists(path):
                return f"Error: Directory not found at {path}"
            entries = os.listdir(path)
            res = []
            for e in sorted(entries)[:100]:
                full = os.path.join(path, e)
                kind = "DIR" if os.path.isdir(full) else "FILE"
                res.append(f"[{kind}] {e}")
            return "\n".join(res)

        elif name == "get_system_status":
            total, used, free = shutil.disk_usage("/")
            disk_str = f"Disk: {used // (1024**3)}G used / {total // (1024**3)}G total ({free // (1024**3)}G free)"
            docker_proc = subprocess.run(
                "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' 2>/dev/null",
                shell=True, capture_output=True, text=True
            )
            docker_out = docker_proc.stdout.strip() if docker_proc.returncode == 0 else "Docker daemon inaccessible"
            free_proc = subprocess.run("free -h 2>/dev/null", shell=True, capture_output=True, text=True)
            mem_out = free_proc.stdout.strip() if free_proc.returncode == 0 else ""
            return f"{disk_str}\n\nMEMORY:\n{mem_out}\n\nDOCKER CONTAINERS:\n{docker_out}"

        elif name == "coolify_status":
            code = """
            $ids = [1, 2, 3, 4, 5, 6, 7, 8];
            foreach ($ids as $id) {
                $a = App\\Models\\Application::find($id);
                if (!$a) continue;
                $d = App\\Models\\ApplicationDeploymentQueue::where('application_id', $id)->latest()->first();
                $status = $d ? $d->status : 'none';
                $commit = $d ? substr($d->commit, 0, 7) : 'none';
                echo "APP: {$id} | {$a->name} | {$status} | {$a->fqdn}" . PHP_EOL;
            }
            """
            p = subprocess.run(
                ["docker", "exec", "-i", "coolify", "php", "artisan", "tinker"],
                input=code, capture_output=True, text=True, timeout=15
            )
            lines = [l.strip() for l in p.stdout.splitlines() if "APP: " in l]
            return "\n".join(lines) if lines else "No Coolify apps found or Coolify container not responding"

        elif name == "coolify_deploy":
            app_id = args.get("app_id")
            code = f"queue_application_deployment(application: App\\Models\\Application::find({app_id}), deployment_uuid: (string) Str::uuid(), force_rebuild: true);"
            p = subprocess.run(
                ["docker", "exec", "-i", "coolify", "php", "artisan", "tinker"],
                input=code, capture_output=True, text=True, timeout=15
            )
            return f"Deployment queued for Application {app_id}"

        else:
            return f"Unknown tool: {name}"
    except Exception as e:
        return f"Tool execution failed: {str(e)}"

# ----------------------------------------------------
# 3. CORE AI CALL WITH AUTOMATIC KEY ROTATION & RETRY
# ----------------------------------------------------
async def call_gemini_api(payload: Dict[str, Any], max_attempts: int = 5) -> Dict[str, Any]:
    # Prioritize fast, production-ready Gemini models
    candidate_models = [
        "models/gemini-3-flash-preview",
        "models/gemini-3.5-flash",
        "models/gemini-3.8-flash"
    ]
    last_err = ""

    async with httpx.AsyncClient(timeout=25.0) as client:
        for attempt in range(max_attempts):
            api_key = key_pool.get_key()
            if not api_key:
                raise RuntimeError("No Gemini API Keys available in pool.")

            for mod in candidate_models:
                url = f"https://generativelanguage.googleapis.com/v1beta/{mod}:generateContent?key={api_key}"
                try:
                    resp = await client.post(url, json=payload)
                    if resp.status_code == 200:
                        return resp.json()
                    elif resp.status_code == 429:
                        # Rate limit reached on this key, mark cooloff and rotate
                        key_pool.report_rate_limit(api_key, cooldown_seconds=60.0)
                        last_err = f"Key {api_key[:10]}... rate limited (429). Rotating to next pool key."
                        break # Try next key in outer loop
                    elif resp.status_code == 503:
                        last_err = f"{mod} 503 High Demand"
                        await asyncio.sleep(0.5)
                        continue
                    else:
                        last_err = f"{mod} HTTP {resp.status_code}: {resp.text[:200]}"
                        continue
                except Exception as ex:
                    last_err = f"{mod} {type(ex).__name__}: {str(ex)}"
                    continue
            await asyncio.sleep(0.3)

    raise RuntimeError(f"All AI API attempts failed. Last error: {last_err}")

# ----------------------------------------------------
# 4. MULTI-AGENT EXECUTION ENGINE
# ----------------------------------------------------
def build_system_instruction(project_info: Optional[Dict[str, Any]] = None, agent_role: str = "fullstack") -> str:
    proj_desc = ""
    if project_info:
        proj_desc = f"""
ปัจจุบันคุณกำลังทำงานในบริบทของโปรเจกต์:
- ชื่อโปรเจกต์: {project_info.get('name', 'General')}
- ไดเรกทอรีทำงาน (Working Directory): {project_info.get('working_dir', '/')}
- รายละเอียด: {project_info.get('description', '')}
"""

    if agent_role == "planner":
        return f"""คุณคือ "Lead Software Architect & Strategic Planner" ประจำระบบ ThaiD Ecosystem
หน้าที่ของคุณ:
1. วิเคราะห์คำขอของผู้ใช้ (Admin Jotaki) อย่างละเอียด
2. วางแผนขั้นตอนการทำงานเชิงเทคนิคที่ชัดเจน เป็นระบบ 3-4 ขั้นตอน (1. ตรวจสอบสถานะ/อ่านโค้ด 2. พัฒนาโค้ด/เขียนไฟล์ 3. รันคอนเทนเนอร์/ทดสอบ)
3. กฎเหล็ก UI Theme: ในแผนงานต้องกำหนดให้ผู้พัฒนาสร้าง UI ตาม "ThaiD App Shell Doctrine" (Floating Pill Navbar + SaaS 10-App Dropdown + Google SSO Avatar + Slate-50 Theme + Editorial Footer) เสมอ
{proj_desc}
ตอบเป็นภาษาไทยแบบกระชับ มีโครงสร้างชัดเจน ไม่ต้องเรียกใช้เครื่องมือเอง แต่ให้ร่างเป็น Action Plan เพื่อส่งต่อให้ทีม Developer"""

    elif agent_role == "reviewer":
        return f"""คุณคือ "Senior DevOps Reviewer & QA Lead" ประจำระบบ ThaiD Ecosystem
หน้าที่ของคุณ:
1. สรุปผลการปฏิบัติงานของเครื่องมือและโค้ดที่รันไปแล้วอย่างชัดเจน
2. ตรวจสอบความถูกต้องว่า URL โดเมนเข้าใช้งานได้ และ UI เป็นไปตามมาตรฐาน ThaiD
3. แนะนำขั้นตอนถัดไปอย่างมืออาชีพ
{proj_desc}
ตอบเป็นภาษาไทยที่เป็นมิตร และนำเสนอข้อมูลให้อ่านเข้าใจง่าย"""

    else:
        return f"""คุณคือ "ThaiD Antigravity Agent" ผู้ช่วย AI อัจฉริยะด้าน DevOps, Fullstack Engineering และ Cloud Architect ประจำระบบ ThaiD Ecosystem (thaid.online)
คุณกำลังทำงานบนเครื่องเซิร์ฟเวอร์หลัก (Oracle Cloud Ubuntu 24.04 VM: 129.221.170.225) ผ่าน Agent Container (เชื่อมต่อ Docker socket และระบบไฟล์โดยตรง)
{proj_desc}
แนวทางการทำงานและกฎเหล็กการปฏิบัติการ (Execution Doctrine):
1. มุ่งเน้นผลลัพธ์ที่จับต้องได้ รวดเร็ว และเป็นขั้นตอน (Action-Oriented):
   - ห้ามวนรันคำสั่งสำรวจโฟลเดอร์กว้างๆ ซ้ำๆ (เช่น `ls /root`, `ls /home`, `whoami`) โดยไม่มีความจำเป็น
   - เมื่อผู้ใช้สั่งสร้างโปรเจกต์ใหม่ หรือเพิ่มฟีเจอร์ ให้ลงมือสร้างโฟลเดอร์ปลายทาง เขียนไฟล์โค้ด (write_file), คอนฟิก หรือ Dockerfile ทันทีอย่างมีระเบียบ

2. การบริหารจัดการ Docker & Traefik Routing Doctrine:
   - ควบคุม Docker Containers ของทุกบริการในระบบ ThaiD ได้โดยตรง
   - เมื่อต้องการรันคอนเทนเนอร์ใหม่ ให้เชื่อมต่อ network 'coolify' (external: true)
   - กฎเหล็ก Traefik Labels ประจำระบบ ThaiD:
     * ห้ามใช้ entrypoints 'web' หรือ 'websecure' เด็ดขาด! บนระบบนี้ชื่อคือ 'http' และ 'https'
     * ตัวอย่าง Labels มาตรฐานที่ถูกต้องเสมอ:
       - "traefik.enable=true"
       - "traefik.docker.network=coolify"
       - "traefik.http.middlewares.redirect-to-https.redirectscheme.scheme=https"
       - "traefik.http.routers.http-<app>.entryPoints=http"
       - "traefik.http.routers.http-<app>.middlewares=redirect-to-https"
       - "traefik.http.routers.http-<app>.rule=Host(`<subdomain>.thaid.online`)"
       - "traefik.http.routers.https-<app>.entryPoints=https"
       - "traefik.http.routers.https-<app>.rule=Host(`<subdomain>.thaid.online`)"
       - "traefik.http.routers.https-<app>.tls=true"
       - "traefik.http.routers.https-<app>.tls.certresolver=letsencrypt"
       - "traefik.http.services.https-<app>.loadbalancer.server.port=<port>"
   - สำหรับ FastAPI / Starlette:
     * คำสั่ง TemplateResponse ต้องใช้ keyword arguments เสมอ:
       `templates.TemplateResponse(request=request, name="index.html", context={...})`
       (ห้ามส่ง positional `templates.TemplateResponse("index.html", {...})` เพราะจะติด TypeError: unhashable type: 'dict')

3. กฎเหล็กโครงสร้าง UI/UX และธีม ThaiD Ecosystem (ThaiD App Shell Doctrine):
   - ทุกเว็บแอพพลิเคชันที่สร้างขึ้นใหม่ในเครือ ThaiD (เช่น qr.thaid.online, remove.thaid.online, novel.thaid.online ฯลฯ) ต้องมีดีไซน์และโครงสร้าง UI เป็นมาตรฐานเดียวกัน 100%:
     * ธีมหลักและฟอนต์: พื้นหลัง `#f8fafc` (slate-50), ใช้ฟอนต์ 'Google Sans', 'Noto Sans Thai', sans-serif, ดึง Tailwind CSS CDN และ FontAwesome 6.5.1
     * แถบนำทางด้านบน (Floating Pill Navbar): แถบเม็ดแคปซูลแก้วลอยตัวตรงกลางด้านบน (`fixed top-0 inset-x-0 z-50 pt-4 px-4 ... max-w-5xl mx-auto bg-white/85 backdrop-blur-xl border border-black/[0.08] rounded-full px-5 py-2.5 shadow-sm`)
       - โลโก้แบรนด์ซ้าย: กล่องสี่เหลี่ยมมืดไอคอน T♭ + ข้อความ ThaiD + สแลช / + ชื่อแอพ + ป้ายสีเขียว Free AI Tool
       - เมนูดรอปดาวน์ขวา: ปุ่ม `✦ เลือกบริการ SaaS` บรรจุ 10 เครื่องมือในเครือ ThaiD (ThaiD Portal, Agent Console, Remove BG AI, QR Code Studio, Novel Studio, Social Auto-Poster, Vault Storage, LINE Sticker Creator, Clip AI & Reels, Smart Chat AI, Mockup Studio) พร้อมไฮไลต์สถานะของแอพปัจจุบัน
       - โปรไฟล์ Google SSO ขวาสุด: แสดงรูป/อักษรย่อเช่น `(J) Jotaki` เมื่อมีคุกกี้ thaid_session หรือแสดงปุ่มเข้าสู่ระบบ
     * การเชื่อมต่อ Central SSO:
       - ตรวจสอบคุกกี้ `thaid_session` (โดเมน `.thaid.online`) โดยถอดรหัส JWT ด้วยความลับ `os.environ.get("JWT_SECRET", "thaid-super-sso-secret-prod-2026-secure")`
       - ส่งอ็อบเจกต์ `user` เข้า Context ของ template ทุกครั้ง
     * โครงสร้างการ์ดทำงาน (Workspace Card):
       - กล่องคอนเทนเนอร์สีขาวลอยตัว `rounded-3xl border border-slate-200/80 bg-white/90 shadow-sm backdrop-blur-md p-6 sm:p-8 max-w-4xl mx-auto mt-28 mb-12`
       - ปุ่มหลักใช้สีฟ้าสด `bg-[#0569ff] hover:bg-blue-600 text-white font-semibold rounded-2xl shadow-sm`
     * ส่วนท้ายหน้าเว็บ (Unified Editorial Footer):
       - แสดงข้อความ `© 2026 ThaiD.online • ศูนย์รวมเครื่องมือ AI อัจฉริยะสำหรับคนไทย` และลิงก์เชื่อมต่อเครื่องมืออื่นๆ

4. การตอบกลับและสรุปงาน:
   - สรุปผลการทำงานให้ชัดเจนเสมอว่าได้สร้างไฟล์อะไร รันคอนเทนเนอร์อะไร หรือเกิดปัญหาใด
   - แสดง URL โดเมนที่เข้าใช้งานได้ หรือคำสั่งถัดไปให้ผู้ใช้เสมอ ห้ามจบเทิร์นโดยไม่สรุปข้อความ"""

async def run_agent_turn(
    messages: List[Dict[str, Any]],
    user_prompt: str,
    project_info: Optional[Dict[str, Any]] = None,
    agent_mode: str = "single"
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Runs Agent turn with support for:
    - Single Fast Agent
    - Multi-Agent Team (Planner -> Coder/DevOps -> QA Reviewer)
    - Multi-Key auto-rotation & SSE streaming
    """
    working_dir = project_info.get("working_dir", "/") if project_info else "/"

    # Emit Key Pool Status info
    pool_stat = key_pool.get_status()
    yield {
        "type": "pool_status",
        "active_keys": pool_stat["active_keys"],
        "total_keys": pool_stat["total_keys"]
    }

    active_prompt = user_prompt

    # MODE A: MULTI-AGENT COLLABORATION TEAM
    if agent_mode == "team":
        # 1. PLANNER AGENT
        yield {
            "type": "agent_badge",
            "role": "Planner Agent 🧠",
            "message": "สถาปนิกกำลังวิเคราะห์คำขอและวางแผนงาน..."
        }
        planner_instruction = build_system_instruction(project_info, agent_role="planner")
        planner_payload = {
            "system_instruction": {"parts": [{"text": planner_instruction}]},
            "contents": list(messages) + [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generation_config": {"temperature": 0.3, "max_output_tokens": 1024}
        }
        try:
            p_data = await call_gemini_api(planner_payload)
            p_cands = p_data.get("candidates", [])
            plan_text = ""
            if p_cands:
                parts = p_cands[0].get("content", {}).get("parts", [])
                plan_text = "".join(p["text"] for p in parts if "text" in p)

            yield {
                "type": "plan_ready",
                "plan": plan_text
            }
            if plan_text:
                active_prompt = f"{user_prompt}\n\n[Action Plan]:\n{plan_text}\n\nกรุณาลงมือปฏิบัติตามขั้นตอนข้างต้นทันที"
        except Exception as e:
            yield {"type": "error", "content": f"Planner Error: {str(e)}"}
            return

        # 2. CODER & EXECUTION AGENT
        yield {
            "type": "agent_badge",
            "role": "Coder & DevOps Agent 💻",
            "message": "วิศวกรกำลังลงมือปฏิบัติการตามแผนงานและเครื่องมือ..."
        }

    # STANDARD OR CODER EXECUTION LOOP
    current_contents = list(messages)
    current_contents.append({
        "role": "user",
        "parts": [{"text": active_prompt}]
    })

    system_inst = build_system_instruction(project_info, agent_role="fullstack")
    max_tool_iterations = 25 if agent_mode == "team" else 15
    iteration = 0
    start_time = time.time()
    executed_tools_history = []
    generated_text_accum = []

    while iteration < max_tool_iterations:
        iteration += 1

        yield {
            "type": "step_progress",
            "step": iteration,
            "max_steps": max_tool_iterations,
            "agent_mode": agent_mode
        }

        payload = {
            "system_instruction": {"parts": [{"text": system_inst}]},
            "contents": current_contents,
            "tools": TOOLS_DEFINITION,
            "generation_config": {
                "temperature": 0.4,
                "max_output_tokens": 4096
            }
        }

        try:
            data = await call_gemini_api(payload)
        except Exception as ex:
            yield {
                "type": "error",
                "content": f"AI Engine Exception: {str(ex)}"
            }
            return

        candidates = data.get("candidates", []) if isinstance(data, dict) else []
        if not candidates:
            yield {"type": "error", "content": "No response from AI model"}
            return

        candidate = candidates[0]
        content = candidate.get("content", {})
        parts = content.get("parts", [])

        tool_calls = []
        text_blocks = []

        for p in parts:
            if "text" in p and p["text"]:
                text_blocks.append(p["text"])
            if "functionCall" in p:
                tool_calls.append(p["functionCall"])

        if text_blocks:
            full_text = "".join(text_blocks)
            generated_text_accum.append(full_text)
            yield {"type": "text", "content": full_text}

        # If no tool calls, turn is finished!
        if not tool_calls:
            if agent_mode == "team":
                yield {
                    "type": "agent_badge",
                    "role": "QA Reviewer Lead 🛡️",
                    "message": "ตรวจสอบผลลัพธ์และความปลอดภัยเรียบร้อย"
                }
            elapsed = round(time.time() - start_time, 1)
            yield {
                "type": "done",
                "status": "finished",
                "total_tools": len(executed_tools_history),
                "total_steps": iteration,
                "duration_s": elapsed,
                "limit_reached": False
            }
            return

        # Append model's response
        current_contents.append({
            "role": "model",
            "parts": parts
        })

        # Execute tool calls
        tool_response_parts = []
        for tc in tool_calls:
            fn_name = tc.get("name")
            fn_args = tc.get("args", {})
            executed_tools_history.append({"name": fn_name, "args": fn_args})

            yield {
                "type": "tool_start",
                "name": fn_name,
                "args": fn_args,
                "step": iteration,
                "max_steps": max_tool_iterations
            }

            # Run tool
            tool_result = execute_tool(fn_name, fn_args, working_dir=working_dir)

            yield {
                "type": "tool_result",
                "name": fn_name,
                "result": tool_result,
                "step": iteration,
                "max_steps": max_tool_iterations
            }

            tool_response_parts.append({
                "functionResponse": {
                    "name": fn_name,
                    "response": {
                        "output": tool_result
                    }
                }
            })

        current_contents.append({
            "role": "user",
            "parts": tool_response_parts
        })

    # If maximum tool iterations reached, force a final synthesis turn WITHOUT tools
    summary_inst = system_inst + "\n\n[คำสั่งบังคับ]: คุณได้ปฏิบัติงานครบจำนวนรอบสูงสุดแล้ว ตอนนี้ห้ามเรียก tool ใดๆ เพิ่ม ให้สรุปผลงานที่ทำสำเร็จทั้งหมด และแนะนำขั้นตอนถัดไปให้ผู้ใช้ทราบอย่างชัดเจน"
    summary_payload = {
        "system_instruction": {"parts": [{"text": summary_inst}]},
        "contents": current_contents,
        "generation_config": {"temperature": 0.4, "max_output_tokens": 2048}
    }
    try:
        final_data = await call_gemini_api(summary_payload)
        cands = final_data.get("candidates", []) if isinstance(final_data, dict) else []
        if cands:
            txt = "".join(p["text"] for p in cands[0].get("content", {}).get("parts", []) if "text" in p)
            if txt:
                generated_text_accum.append(txt)
                yield {"type": "text", "content": "\n\n" + txt}
    except Exception as ex:
        print(f"Summary call error: {ex}")

    # Fallback if text is still empty:
    if not "".join(generated_text_accum).strip():
        recent_summary = "\n".join([f"- `{t['name']}`: สำเร็จ" for t in executed_tools_history[-6:]])
        fallback_msg = f"""
### 📊 สรุปผลการปฏิบัติงานของ Agent (ถึงขีดจำกัด {max_tool_iterations} รอบ)
Agent ได้ดำเนินการเรียกใช้เครื่องมือในโปรเจกต์นี้สำเร็จแล้ว **{len(executed_tools_history)} รายการ**:
{recent_summary}

คุณสามารถสั่งการขั้นตอนต่อไปได้ทันทีครับ เช่น พิมพ์สั่ง: **`ดำเนินการต่อจากขั้นตอนล่าสุดจนเสร็จสมบูรณ์`**
"""
        yield {"type": "text", "content": fallback_msg}

    elapsed = round(time.time() - start_time, 1)
    yield {
        "type": "done",
        "status": "limit_reached",
        "total_tools": len(executed_tools_history),
        "total_steps": iteration,
        "duration_s": elapsed,
        "limit_reached": True
    }
