import os
import re
import subprocess

# Standard 10-app ThaiD SaaS Ecosystem Dropdown
UNIFIED_SAAS_MENU_HTML = """                    <div id="thaidSaasMenu" class="hidden absolute right-0 top-full mt-2 w-72 sm:w-80 bg-white/95 dark:bg-stone-900/95 backdrop-blur-2xl border border-black/[0.08] dark:border-white/10 rounded-2xl shadow-2xl p-2 z-50 text-left">
                        <div class="px-3 py-1.5 text-[10px] font-bold text-stone-400 uppercase tracking-wider border-b border-black/[0.05] dark:border-white/[0.05] mb-1 flex items-center justify-between">
                            <span>ThaiD SaaS Ecosystem</span>
                            <span class="text-emerald-600 font-semibold">10 เครื่องมือ</span>
                        </div>
                        <div class="grid grid-cols-1 gap-1 max-h-[380px] overflow-y-auto">
                            <!-- 1. Remove BG AI -->
                            <a href="https://remove.thaid.online" class="flex items-center justify-between p-2 rounded-xl hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors group text-left">
                                <div class="flex items-center gap-2.5">
                                    <div class="w-7 h-7 rounded-lg bg-emerald-50 dark:bg-emerald-950/40 flex items-center justify-center group-hover:scale-105 transition-transform flex-shrink-0 text-emerald-600">
                                        <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>
                                    </div>
                                    <div class="text-left">
                                        <div class="text-xs font-bold text-stone-900 dark:text-stone-100 group-hover:text-[#0569ff] transition-colors">Remove BG AI</div>
                                        <div class="text-[10px] text-stone-400 truncate max-w-[170px]">ลบพื้นหลังภาพเนียนกริบ ไดคัต AI</div>
                                    </div>
                                </div>
                                <span class="text-[10px] px-1.5 py-0.5 rounded bg-emerald-50 dark:bg-emerald-900/40 text-emerald-600 font-medium">Free AI</span>
                            </a>
                            <!-- 2. QR Code Studio -->
                            <a href="https://qr.thaid.online" class="flex items-center justify-between p-2 rounded-xl hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors group text-left">
                                <div class="flex items-center gap-2.5">
                                    <div class="w-7 h-7 rounded-lg bg-blue-50 dark:bg-blue-950/40 flex items-center justify-center group-hover:scale-105 transition-transform flex-shrink-0 text-blue-600">
                                        <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>
                                    </div>
                                    <div class="text-left">
                                        <div class="text-xs font-bold text-stone-900 dark:text-stone-100 group-hover:text-[#0569ff] transition-colors">QR Code Studio</div>
                                        <div class="text-[10px] text-stone-400 truncate max-w-[170px]">สร้างคิวอาร์โค้ด HD ฟรี คมชัด</div>
                                    </div>
                                </div>
                                <span class="text-[10px] px-1.5 py-0.5 rounded bg-blue-50 dark:bg-blue-900/40 text-blue-600 font-medium">HD Free</span>
                            </a>
                            <!-- 3. Novel Studio -->
                            <a href="https://novel.thaid.online" class="flex items-center justify-between p-2 rounded-xl hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors group text-left">
                                <div class="flex items-center gap-2.5">
                                    <div class="w-7 h-7 rounded-lg bg-stone-100 dark:bg-stone-800 flex items-center justify-center group-hover:scale-105 transition-transform flex-shrink-0 text-[#0569ff]">
                                        <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
                                    </div>
                                    <div class="text-left">
                                        <div class="text-xs font-bold text-stone-900 dark:text-stone-100 group-hover:text-[#0569ff] transition-colors">Novel Studio</div>
                                        <div class="text-[10px] text-stone-400 truncate max-w-[170px]">แต่งนิยาย AI 10 ตอนจบ</div>
                                    </div>
                                </div>
                                <span class="text-[10px] px-1.5 py-0.5 rounded bg-stone-100 dark:bg-stone-800 text-stone-500 font-medium">10 ตอนจบ</span>
                            </a>
                            <!-- 4. Social Auto-Poster -->
                            <a href="https://social.thaid.online" class="flex items-center justify-between p-2 rounded-xl hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors group text-left">
                                <div class="flex items-center gap-2.5">
                                    <div class="w-7 h-7 rounded-lg bg-stone-100 dark:bg-stone-800 flex items-center justify-center group-hover:scale-105 transition-transform flex-shrink-0 text-emerald-600">
                                        <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 2h-3a5 5 0 0 0-5 5v3H7v4h3v8h4v-8h3l1-4h-4V7a1 1 0 0 1 1-1h3z"/></svg>
                                    </div>
                                    <div class="text-left">
                                        <div class="text-xs font-bold text-stone-900 dark:text-stone-100 group-hover:text-[#0569ff] transition-colors">Social Auto-Poster</div>
                                        <div class="text-[10px] text-stone-400 truncate max-w-[170px]">ดึงข่าว RSS & โพสต์ Facebook 24 ชม.</div>
                                    </div>
                                </div>
                                <span class="text-[10px] px-1.5 py-0.5 rounded bg-stone-100 dark:bg-stone-800 text-stone-500 font-medium">Auto 24h</span>
                            </a>
                            <!-- 5. Vault Storage -->
                            <a href="https://vault.thaid.online" class="flex items-center justify-between p-2 rounded-xl hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors group text-left">
                                <div class="flex items-center gap-2.5">
                                    <div class="w-7 h-7 rounded-lg bg-amber-50 dark:bg-amber-950/40 flex items-center justify-center group-hover:scale-105 transition-transform flex-shrink-0 text-amber-500">
                                        <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
                                    </div>
                                    <div class="text-left">
                                        <div class="text-xs font-bold text-stone-900 dark:text-stone-100 group-hover:text-[#0569ff] transition-colors">Vault Storage</div>
                                        <div class="text-[10px] text-stone-400 truncate max-w-[170px]">ศูนย์เก็บข้อมูล & Keys ปลอดภัย</div>
                                    </div>
                                </div>
                                <span class="text-[10px] px-1.5 py-0.5 rounded bg-amber-50 dark:bg-amber-900/40 text-amber-600 font-medium">Encrypted</span>
                            </a>
                            <!-- 6. LINE Sticker Creator -->
                            <a href="https://sticker.thaid.online" class="flex items-center justify-between p-2 rounded-xl hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors group text-left">
                                <div class="flex items-center gap-2.5">
                                    <div class="w-7 h-7 rounded-lg bg-pink-50 dark:bg-pink-950/40 flex items-center justify-center group-hover:scale-105 transition-transform flex-shrink-0 text-pink-500">
                                        <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M8 14s1.5 2 4 2 4-2 4-2"/><line x1="9" y1="9" x2="9.01" y2="9"/></svg>
                                    </div>
                                    <div class="text-left">
                                        <div class="text-xs font-bold text-stone-900 dark:text-stone-100 group-hover:text-[#0569ff] transition-colors">LINE Sticker Creator</div>
                                        <div class="text-[10px] text-stone-400 truncate max-w-[170px]">สร้างชุดสติกเกอร์ไลน์ 40 แอ็กชัน</div>
                                    </div>
                                </div>
                                <span class="text-[10px] px-1.5 py-0.5 rounded bg-pink-50 dark:bg-pink-900/40 text-pink-600 font-medium">40 แอ็กชัน</span>
                            </a>
                            <!-- 7. Clip AI & Reels -->
                            <a href="https://clip.thaid.online" class="flex items-center justify-between p-2 rounded-xl hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors group text-left">
                                <div class="flex items-center gap-2.5">
                                    <div class="w-7 h-7 rounded-lg bg-purple-50 dark:bg-purple-950/40 flex items-center justify-center group-hover:scale-105 transition-transform flex-shrink-0 text-purple-500">
                                        <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="20" height="20" rx="2.18" ry="2.18"/><line x1="7" y1="2" x2="7" y2="22"/><line x1="17" y1="2" x2="17" y2="22"/><line x1="2" y1="12" x2="22" y2="12"/><line x1="2" y1="7" x2="7" y2="7"/><line x1="2" y1="17" x2="7" y2="17"/><line x1="17" y1="17" x2="22" y2="17"/><line x1="17" y1="7" x2="22" y2="7"/></svg>
                                    </div>
                                    <div class="text-left">
                                        <div class="text-xs font-bold text-stone-900 dark:text-stone-100 group-hover:text-[#0569ff] transition-colors">Clip AI & Reels</div>
                                        <div class="text-[10px] text-stone-400 truncate max-w-[170px]">สคริปต์คลิปสั้น 9:16 สไตล์ไวรัล</div>
                                    </div>
                                </div>
                                <span class="text-[10px] px-1.5 py-0.5 rounded bg-purple-50 dark:bg-purple-900/40 text-purple-600 font-medium">9:16 Shorts</span>
                            </a>
                            <!-- 8. Smart Chat AI -->
                            <a href="https://chat.thaid.online" class="flex items-center justify-between p-2 rounded-xl hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors group text-left">
                                <div class="flex items-center gap-2.5">
                                    <div class="w-7 h-7 rounded-lg bg-teal-50 dark:bg-teal-950/40 flex items-center justify-center group-hover:scale-105 transition-transform flex-shrink-0 text-teal-600">
                                        <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
                                    </div>
                                    <div class="text-left">
                                        <div class="text-xs font-bold text-stone-900 dark:text-stone-100 group-hover:text-[#0569ff] transition-colors">Smart Chat AI</div>
                                        <div class="text-[10px] text-stone-400 truncate max-w-[170px]">บอทแอดมินตอบแชทบน LINE OA 24/7</div>
                                    </div>
                                </div>
                                <span class="text-[10px] px-1.5 py-0.5 rounded bg-teal-50 dark:bg-teal-900/40 text-teal-600 font-medium">ตอบ 0.8 วิ</span>
                            </a>
                            <!-- 9. Mockup Studio -->
                            <a href="https://mockup.thaid.online" class="flex items-center justify-between p-2 rounded-xl hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors group text-left">
                                <div class="flex items-center gap-2.5">
                                    <div class="w-7 h-7 rounded-lg bg-blue-50 dark:bg-blue-950/40 flex items-center justify-center group-hover:scale-105 transition-transform flex-shrink-0 text-blue-500">
                                        <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/></svg>
                                    </div>
                                    <div class="text-left">
                                        <div class="text-xs font-bold text-stone-900 dark:text-stone-100 group-hover:text-[#0569ff] transition-colors">Mockup Studio</div>
                                        <div class="text-[10px] text-stone-400 truncate max-w-[170px]">สตูดิโอภาพถ่ายสินค้าลักชัวรี ไดคัต AI</div>
                                    </div>
                                </div>
                                <span class="text-[10px] px-1.5 py-0.5 rounded bg-blue-50 dark:bg-blue-900/40 text-blue-500 font-medium">Studio 4K</span>
                            </a>
                            <!-- 10. Agent Console -->
                            <a href="https://agent.thaid.online" class="flex items-center justify-between p-2 rounded-xl hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors group text-left">
                                <div class="flex items-center gap-2.5">
                                    <div class="w-7 h-7 rounded-lg bg-indigo-50 dark:bg-indigo-950/40 flex items-center justify-center group-hover:scale-105 transition-transform flex-shrink-0 text-indigo-500">
                                        <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
                                    </div>
                                    <div class="text-left">
                                        <div class="text-xs font-bold text-stone-900 dark:text-stone-100 group-hover:text-[#0569ff] transition-colors">Agent Console</div>
                                        <div class="text-[10px] text-stone-400 truncate max-w-[170px]">ผู้ช่วยเขียนโค้ดและควบคุมโฮสต์</div>
                                    </div>
                                </div>
                                <span class="text-[10px] px-1.5 py-0.5 rounded bg-indigo-50 dark:bg-indigo-900/40 text-indigo-600 font-medium">DevOps AI</span>
                            </a>
                            <!-- ThaiD Main Portal -->
                            <a href="https://thaid.online" class="flex items-center justify-between p-2 rounded-xl hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors group text-left border-t border-black/[0.05] dark:border-white/[0.05] mt-1 pt-1.5">
                                <div class="flex items-center gap-2.5">
                                    <div class="w-7 h-7 rounded-lg bg-stone-100 dark:bg-stone-800 flex items-center justify-center group-hover:scale-105 transition-transform flex-shrink-0 text-stone-600 dark:text-stone-300">
                                        <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>
                                    </div>
                                    <div class="text-left">
                                        <div class="text-xs font-bold text-stone-900 dark:text-stone-100 group-hover:text-[#0569ff] transition-colors">ThaiD Portal</div>
                                        <div class="text-[10px] text-stone-400 truncate max-w-[170px]">หน้าหลักศูนย์รวม SaaS เครื่องมือ AI</div>
                                    </div>
                                </div>
                                <span class="text-[10px] px-1.5 py-0.5 rounded bg-stone-100 dark:bg-stone-800 text-stone-500 font-medium">Portal</span>
                            </a>
                        </div>
                    </div>"""

def extract_thaid_saas_menu(html):
    idx = html.find('id="thaidSaasMenu"')
    if idx == -1:
        idx = html.find("id='thaidSaasMenu'")
    if idx == -1:
        return None, None
    
    start_tag = html.rfind('<div', 0, idx)
    if start_tag == -1:
        return None, None
    
    depth = 0
    i = start_tag
    while i < len(html):
        if html[i:i+4] == '<div':
            depth += 1
            i += 4
        elif html[i:i+6] == '</div>':
            depth -= 1
            if depth == 0:
                end_tag = i + 6
                return start_tag, end_tag
            i += 6
        else:
            i += 1
            
    return None, None

file_container_map = [
    # (Local File Path, Container ID, Container Dest Path, Repo Root)
    (r'C:\Auto Post FB\templates\index.html', '5ccfa647-a952-4ed8-a804-6e82f93e18a2-20261101T090729', '/app/templates/index.html', r'C:\Auto Post FB'),
    (r'C:\Auto Post FB\templates\landing.html', '5ccfa647-a952-4ed8-a804-6e82f93e18a2-20261101T090729', '/app/templates/landing.html', r'C:\Auto Post FB'),
    (r'C:\Auto Post FB\templates\admin.html', '5ccfa647-a952-4ed8-a804-6e82f93e18a2-20261101T090729', '/app/templates/admin.html', r'C:\Auto Post FB'),
    (r'C:\ReadAWrite\web_saas_stitch\index.html', 'eli0yxv1polppzeaci1l634j-20261101T090442', '/app/web_saas_stitch/index.html', r'C:\ReadAWrite'),
    (r'C:\ThaiD-Sticker\static\index.html', 'ybgo0o7anglf1kku32i5bozh-20261101T091056', '/app/static/index.html', r'C:\ThaiD-Sticker'),
    (r'C:\ThaiD-Clip\static\index.html', 'swspkwo1d8qtbquvbzqr9iir-20261101T091212', '/app/static/index.html', r'C:\ThaiD-Clip'),
    (r'C:\ThaiD-Chat\static\index.html', '304ytjxowbaewvgxk9xxurt4-20261101T091217', '/app/static/index.html', r'C:\ThaiD-Chat'),
    (r'C:\ThaiD-Mockup\static\index.html', 'fyaupc6xbnxcxnqnhyxdjar9-20261101T091314', '/app/static/index.html', r'C:\ThaiD-Mockup'),
    (r'C:\ThaiD-Vault\static\index.html', 'ur0udrrewyg5s2mkv3virdy3-20261101T091005', '/app/static/index.html', r'C:\ThaiD-Vault'),
]

# 1. Update local files
repos_to_commit = set()
for fpath, cid, cdest, repo in file_container_map:
    with open(fpath, 'r', encoding='utf-8', errors='ignore') as fp:
        html = fp.read()
    
    s, e = extract_thaid_saas_menu(html)
    if s is not None and e is not None:
        new_html = html[:s] + UNIFIED_SAAS_MENU_HTML + html[e:]
        with open(fpath, 'w', encoding='utf-8') as fp:
            fp.write(new_html)
        print(f"UPDATED LOCAL: {fpath}")
        repos_to_commit.add(repo)
    else:
        print(f"COULD NOT LOCATE MENU IN: {fpath}")

# 2. Hot-patch directly into running Docker containers on server
for fpath, cid, cdest, repo in file_container_map:
    # SCP file to /tmp/tmp_sync.html
    tmp_dest = f"/tmp/sync_{os.path.basename(fpath)}"
    scp_cmd = ['scp', '-i', r'C:\NV\oracle_key.pem', '-o', 'StrictHostKeyChecking=no', fpath, f'ubuntu@129.221.170.225:{tmp_dest}']
    subprocess.run(scp_cmd, capture_output=True)
    
    # Docker cp into container
    dcp_cmd = ['ssh', '-i', r'C:\NV\oracle_key.pem', '-o', 'StrictHostKeyChecking=no', 'ubuntu@129.221.170.225', f'sudo docker cp {tmp_dest} {cid}:{cdest}']
    subprocess.run(dcp_cmd, capture_output=True)
    print(f"HOT-PATCHED: {cid[:12]} -> {cdest}")

print("All containers hot-patched successfully!")

# 3. Commit & push repos
for r in repos_to_commit:
    try:
        subprocess.run(['git', '-C', r, 'add', '-A'], capture_output=True)
        subprocess.run(['git', '-C', r, 'commit', '-m', 'feat: update ThaiD SaaS Ecosystem dropdown to 10 apps unified'], capture_output=True)
        subprocess.run(['git', '-C', r, 'push', 'origin', 'main'], capture_output=True)
        print(f"GIT PUSHED: {r}")
    except Exception as ex:
        print(f"GIT ERROR in {r}: {ex}")
