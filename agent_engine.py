import os
import json
import subprocess
import shutil
import time
import httpx
from typing import AsyncGenerator, Dict, Any, List

def get_gemini_api_key():
    k = os.environ.get("GEMINI_API_KEY", "")
    if not k and os.path.exists(".env"):
        with open(".env", "r") as f:
            for line in f:
                if line.startswith("GEMINI_API_KEY="):
                    k = line.strip().split("=", 1)[1].strip("'\"")
    return k

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "models/gemini-3.5-flash")

# Tool Definitions for Gemini Function Calling
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

SYSTEM_INSTRUCTION = """คุณคือ "ThaiD Antigravity Agent" ผู้ช่วย AI ระดับสูงด้าน DevOps, Software Engineering และ System Administration ประจำระบบ ThaiD Ecosystem (thaid.online)
คุณกำลังทำงานบนเครื่องเซิร์ฟเวอร์หลัก (Oracle Cloud Ubuntu 24.04 VM: 129.221.170.225) โดยมีสิทธิ์เข้าถึงคำสั่ง Shell, Docker, Git, ไฟล์ในระบบ และ Coolify

บทบาทหน้าที่และความสามารถของคุณ:
1. บริหารจัดการ Docker Containers และดู Logs ของทั้ง 8 บริการ SaaS (thaid.online, novel, social, vault, sticker, clip, chat, mockup)
2. สั่งคำสั่ง Shell ตรวจสอบสถานะ CPU, RAM, Disk, Network และความปลอดภัยของเซิร์ฟเวอร์
3. อ่าน/แก้ไขโค้ดโปรเจกต์ รันการทดสอบ จัดการไฟล์ .env และสั่ง Git commit / push
4. สั่ง Rebuild หรือ Deploy แอปพลิเคชันผ่าน Coolify
5. สื่อสารกับผู้ใช้งาน (Admin Jotaki - iamjotaki@gmail.com) ด้วยภาษาไทยที่เป็นมิตร ชัดเจน ตรงประเด็น และรายงานผลการทำงานแบบเป็นขั้นเป็นตอน
6. เมื่อมีการเรียกใช้ Tool (เช่น execute_command, get_system_status) ให้อธิบายผลลัพธ์และสิ่งที่ทำอย่างเข้าใจง่าย

หากผู้ใช้สั่งให้ตรวจสอบหรือแก้ไขสิ่งใด ให้ลงมือเรียก Tool ที่เหมาะสมทันที แล้วสรุปผลลัพธ์อย่างมืออาชีพ"""

def execute_tool(name: str, args: Dict[str, Any]) -> str:
    """Executes local tool on the server host / container"""
    try:
        if name == "execute_command":
            cmd = args.get("command", "")
            if not cmd:
                return "Error: Empty command"
            # Execute with timeout
            proc = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=60,
                cwd="/"
            )
            out = proc.stdout
            err = proc.stderr
            res = f"Exit code: {proc.returncode}\n"
            if out:
                res += f"STDOUT:\n{out[:4000]}\n"
            if err:
                res += f"STDERR:\n{err[:2000]}\n"
            return res.strip()

        elif name == "read_file":
            path = args.get("path", "")
            max_lines = args.get("max_lines", 200)
            if not os.path.exists(path):
                return f"Error: File not found at {path}"
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                lines = [f.readline() for _ in range(max_lines)]
            return "".join(lines)

        elif name == "write_file":
            path = args.get("path", "")
            content = args.get("content", "")
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return f"Successfully wrote {len(content)} characters to {path}"

        elif name == "list_directory":
            path = args.get("path", ".")
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
            # Disk
            total, used, free = shutil.disk_usage("/")
            disk_str = f"Disk: {used // (1024**3)}G used / {total // (1024**3)}G total ({free // (1024**3)}G free)"
            
            # Docker
            docker_proc = subprocess.run(
                "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' 2>/dev/null",
                shell=True, capture_output=True, text=True
            )
            docker_out = docker_proc.stdout.strip() if docker_proc.returncode == 0 else "Docker daemon inaccessible"
            
            # Memory
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

async def run_agent_turn(
    messages: List[Dict[str, Any]],
    user_prompt: str
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Runs multi-step Agent reasoning & tool execution with Gemini 3.8 Flash.
    Yields event dictionaries for SSE streaming.
    """
    # Append user prompt to contents
    current_contents = list(messages)
    current_contents.append({
        "role": "user",
        "parts": [{"text": user_prompt}]
    })

    max_tool_iterations = 6
    iteration = 0

    while iteration < max_tool_iterations:
        iteration += 1

        payload = {
            "system_instruction": {
                "parts": [{"text": SYSTEM_INSTRUCTION}]
            },
            "contents": current_contents,
            "tools": TOOLS_DEFINITION,
            "generation_config": {
                "temperature": 0.4,
                "max_output_tokens": 4096
            }
        }

        api_key = get_gemini_api_key()
        api_url = f"https://generativelanguage.googleapis.com/v1beta/{GEMINI_MODEL}:generateContent?key={api_key}"

        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.post(api_url, json=payload)
            if resp.status_code != 200:
                yield {
                    "type": "error",
                    "content": f"Gemini API Error {resp.status_code}: {resp.text}"
                }
                return

            data = resp.json()
            candidates = data.get("candidates", []) if isinstance(data, dict) else (data[0].get("candidates", []) if data else [])

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

            # If model generated text, stream it
            if text_blocks:
                full_text = "".join(text_blocks)
                yield {"type": "text", "content": full_text}

            # If no tool calls, turn is finished!
            if not tool_calls:
                yield {"type": "done", "status": "finished"}
                return

            # Append model's response to message history
            current_contents.append({
                "role": "model",
                "parts": parts
            })

            # Execute tool calls
            tool_response_parts = []
            for tc in tool_calls:
                fn_name = tc.get("name")
                fn_args = tc.get("args", {})
                
                yield {
                    "type": "tool_start",
                    "name": fn_name,
                    "args": fn_args
                }

                # Run tool
                tool_result = execute_tool(fn_name, fn_args)

                yield {
                    "type": "tool_result",
                    "name": fn_name,
                    "result": tool_result
                }

                tool_response_parts.append({
                    "functionResponse": {
                        "name": fn_name,
                        "response": {
                            "output": tool_result
                        }
                    }
                })

            # Append function response to history and loop back
            current_contents.append({
                "role": "user",
                "parts": tool_response_parts
            })

    yield {"type": "done", "status": "max_iterations_reached"}
