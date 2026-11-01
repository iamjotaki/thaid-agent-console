import os
import json
import time
import base64
import hmac
import hashlib
from playwright.sync_api import sync_playwright

SSO_SECRET = "thaid-super-sso-secret-prod-2026-secure".encode("utf-8")

def create_sso_token(email: str = "iamjotaki@gmail.com", name: str = "Jotaki"):
    header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode()).decode().rstrip("=")
    payload_data = {
        "email": email,
        "name": name,
        "role": "superadmin",
        "exp": int(time.time()) + 86400 * 30
    }
    payload = base64.urlsafe_b64encode(json.dumps(payload_data).encode()).decode().rstrip("=")
    to_sign = f"{header}.{payload}".encode()
    sig = base64.urlsafe_b64encode(hmac.new(SSO_SECRET, to_sign, hashlib.sha256).digest()).decode().rstrip("=")
    return f"{header}.{payload}.{sig}"

# Create a small test image with PIL or simple binary PNG
from PIL import Image, ImageDraw, ImageFont
img = Image.new("RGB", (400, 200), color=(15, 23, 42))
d = ImageDraw.Draw(img)
d.text((30, 70), "ThaiD AI Vision Test 2026", fill=(59, 130, 246))
d.text((30, 110), "Testing Image Attachment & Multimodal", fill=(248, 250, 252))
test_img_path = os.path.abspath("test_multimodal_sample.png")
img.save(test_img_path)
print(f"Created test image: {test_img_path}")

token = create_sso_token()

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(
        viewport={"width": 1400, "height": 900},
        ignore_https_errors=True
    )
    context.add_cookies([
        {
            "name": "thaid_session",
            "value": token,
            "domain": ".thaid.online",
            "path": "/"
        }
    ])
    
    page = context.new_page()
    print("Navigating to https://agent.thaid.online...")
    page.goto("https://agent.thaid.online", wait_until="networkidle")
    time.sleep(2)

    # 1. Screenshot showing attachment button
    page.screenshot(path="C:/Users/User/.gemini/antigravity/brain/360fe13d-d196-4c61-8c6c-c040f5045eec/agent_console_attachment_btn.png")
    print("Screenshot 1 captured: agent_console_attachment_btn.png")

    # 2. Attach test image via file input
    file_input = page.locator("#file-upload-input")
    file_input.set_input_files(test_img_path)
    print("Uploaded test image...")
    
    # Wait for attachment preview bar
    page.wait_for_selector("#attachment-preview-bar:not(.hidden)", timeout=10000)
    time.sleep(1)

    # Screenshot showing preview thumbnail
    page.screenshot(path="C:/Users/User/.gemini/antigravity/brain/360fe13d-d196-4c61-8c6c-c040f5045eec/agent_console_attachment_preview.png")
    print("Screenshot 2 captured: agent_console_attachment_preview.png")

    # 3. Type prompt and submit
    prompt_input = page.locator("#prompt-input")
    prompt_input.fill("ในรูปภาพนี้เขียนข้อความว่าอะไรบ้าง ช่วยอ่านและอธิบายให้ฟังหน่อยครับ")
    page.locator("#btn-send").click()
    print("Prompt submitted! Waiting for agent response...")

    # Wait for completion or streaming text
    time.sleep(12)
    page.screenshot(path="C:/Users/User/.gemini/antigravity/brain/360fe13d-d196-4c61-8c6c-c040f5045eec/agent_console_attachment_response.png")
    print("Screenshot 3 captured: agent_console_attachment_response.png")

    browser.close()
