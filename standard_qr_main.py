import base64
import hashlib
import hmac
import io
import json
import os
import time
from typing import Optional

from fastapi import FastAPI, Request, Form, Response
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import qrcode
from qrcode.image.styledpil import StyledPilImage
from PIL import Image, ImageColor

app = FastAPI(title="ThaiD QR Code Studio")

os.makedirs("templates", exist_ok=True)
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

SSO_SECRET = os.environ.get("JWT_SECRET", "thaid-super-sso-secret-prod-2026-secure").encode("utf-8")

def base64url_decode(input_str: str) -> str:
    rem = len(input_str) % 4
    if rem > 0:
        input_str += '=' * (4 - rem)
    return base64.urlsafe_b64decode(input_str.encode('utf-8')).decode('utf-8')

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
    cookie = request.cookies.get("thaid_session")
    if cookie:
        data = verify_sso_token(cookie)
        if data and data.get("email"):
            return {
                "email": data.get("email").strip().lower(),
                "name": data.get("name") or data.get("email").split("@")[0],
                "role": data.get("role") or "member",
                "avatar": data.get("avatar") or ""
            }
    return None

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    user = get_current_user(request)
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "user": user,
            "qr_code": None,
            "content": "",
            "app_url": "https://qr.thaid.online"
        }
    )

@app.post("/", response_class=HTMLResponse)
async def generate_qr_post(
    request: Request,
    text: str = Form(...),
    color: str = Form("#000000"),
    box_size: int = Form(10)
):
    user = get_current_user(request)
    text = text.strip() if text else ""
    img_b64 = None

    if text:
        try:
            qr = qrcode.QRCode(
                version=None,
                error_correction=qrcode.constants.ERROR_CORRECT_M,
                box_size=max(4, min(box_size, 20)),
                border=4
            )
            qr.add_data(text)
            qr.make(fit=True)

            fill_rgb = color if color.startswith("#") else "#000000"
            img = qr.make_image(fill_color=fill_rgb, back_color="white")

            buf = io.BytesIO()
            img.save(buf, format="PNG")
            img_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        except Exception as e:
            print("QR Generation error:", e)

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "user": user,
            "qr_code": img_b64,
            "content": text,
            "color": color,
            "app_url": "https://qr.thaid.online"
        }
    )

@app.post("/api/generate")
async def api_generate_qr(request: Request):
    try:
        data = await request.json()
        text = data.get("text", "").strip()
        color = data.get("color", "#000000")
        box_size = int(data.get("box_size", 10))

        if not text:
            return JSONResponse({"error": "Content cannot be empty"}, status_code=400)

        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=max(4, min(box_size, 25)),
            border=4
        )
        qr.add_data(text)
        qr.make(fit=True)

        fill_rgb = color if color.startswith("#") else "#000000"
        img = qr.make_image(fill_color=fill_rgb, back_color="white")

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        img_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

        return {"success": True, "qr_code": img_b64, "text": text}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/api/auth/logout")
async def logout(response: Response):
    response.delete_cookie(key="thaid_session", domain=".thaid.online")
    response.delete_cookie(key="thaid_user", domain=".thaid.online")
    return {"success": True}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8005)
