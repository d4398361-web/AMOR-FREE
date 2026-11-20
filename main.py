import vps_module, assistant
load_vps_orders = vps_module.load_orders
save_vps_orders = vps_module.save_orders
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import json
import os
import subprocess
import random
import string
import uuid
from datetime import datetime, timedelta
import sys
import shutil
import threading
import time
import zipfile
import psutil
import requests
from urllib.parse import quote as _urlquote

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "static"),
)
try:
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
except Exception as _pf_err:
    print(f"ProxyFix not applied: {_pf_err}")
app.secret_key = os.environ.get('SECRET_KEY', 'AMOR-super-secret-key-2026-change-me')
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=12)
# لو على HTTPS فعّل: app.config['SESSION_COOKIE_SECURE'] = True
app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024 * 1024  # 1GB

USERS_FILE = 'users.json'
BOTS_DIR = 'bots'
CPU_HISTORY = {}
CRASH_COUNT = {}
NET_STATS = {}

os.makedirs(BOTS_DIR, exist_ok=True)

# ============================================
# إعدادات بوت التليجرام (حماية كاملة - للأدمن فقط)
# ============================================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8637543839:AAH-nKf4TsHmgWZIz-FBw4mzjCufcADH-UU")
ADMIN_TELEGRAM_ID = 7411899950  # آيدي الأدمن الوحيد المسموح له بالتحدث مع البوت
TELEGRAM_CHAT_ID = str(ADMIN_TELEGRAM_ID)
import hashlib as _hashlib
# سر داخلي: الـ webhook بيقبل بس الطلبات اللي معاها السر ده (تليجرام أو الـ polling الداخلي)
TELEGRAM_WEBHOOK_SECRET = os.environ.get("TELEGRAM_WEBHOOK_SECRET") or _hashlib.sha256(("amor-wh:" + str(TELEGRAM_BOT_TOKEN)).encode()).hexdigest()[:48]
# 1 = البوت يشتغل بـ polling (يشتغل على localhost). 0 = webhook على دومين HTTPS
TELEGRAM_POLLING = os.environ.get("TELEGRAM_POLLING", "1") != "0"

def send_telegram_notification(message, chat_id=None):
    if not TELEGRAM_BOT_TOKEN:
        return False
    target_chat = chat_id if chat_id else TELEGRAM_CHAT_ID
    if not target_chat:
        return False
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": target_chat,
            "text": message,
            "parse_mode": "HTML"
        }
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code != 200:
            print(f"Telegram API Error {r.status_code}: {r.text[:300]}")
            return False
        return True
    except Exception as e:
        print(f"Telegram Notification Error: {e}")
        return False

# ============================================
# রেট লিমিট
# ============================================

class RateLimiter:
    def check_rate(self, server_id, limit_percent):
        if server_id not in CPU_HISTORY:
            CPU_HISTORY[server_id] = []
        users = load_users()
        server = None
        for uname, data in users.items():
            if uname == 'admin': continue
            servers = data.get('servers', [])
            if not isinstance(servers, list): continue
            for s in servers:
                if isinstance(s, dict) and s.get('server_id') == server_id:
                    server = s
                    break
        if not server or server.get('status') != 'running':
            return False, 0
        pid = server.get('pid')
        if not pid: return False, 0
        try:
            proc = psutil.Process(pid)
            cpu = proc.cpu_percent(interval=1)
            now = time.time()
            CPU_HISTORY[server_id].append({'time': now, 'cpu': cpu})
            CPU_HISTORY[server_id] = [h for h in CPU_HISTORY[server_id] if now - h['time'] < 30]
            recent = [h['cpu'] for h in CPU_HISTORY[server_id] if now - h['time'] < 10]
            if recent:
                avg_cpu = sum(recent) / len(recent)
                if avg_cpu > limit_percent:
                    return True, avg_cpu
        except: pass
        return False, 0

rate_limiter = RateLimiter()

# ============================================
# Google & Discord OAuth
# ============================================
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "384112659919-khoa42an789mirm3hq4ujk852usr8mms.apps.googleusercontent.com")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "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")
DISCORD_CLIENT_ID = os.environ.get("DISCORD_CLIENT_ID", "")
DISCORD_CLIENT_SECRET = os.environ.get("DISCORD_CLIENT_SECRET", "")
OAUTH_REDIRECT_BASE = os.environ.get("OAUTH_REDIRECT_BASE", "").strip().rstrip("/")
AD_FILE = "ad_config.json"

def load_ad():
    if os.path.exists(AD_FILE):
        try:
            with open(AD_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except: pass
    return {"text": "", "active": False}

def save_ad(text, active):
    with open(AD_FILE, "w", encoding="utf-8") as f:
        json.dump({"text": text, "active": bool(active)}, f, ensure_ascii=False)

def allocate_port(users=None):
    try:
        if users is None:
            users = load_users()
    except Exception:
        users = {}
    used = set()
    for uname, data in users.items():
        if uname == "admin": continue
        for s in data.get("servers", []) or []:
            if isinstance(s, dict) and s.get("port"):
                used.add(int(s["port"]))
    for _ in range(100):
        p = random.randint(3000, 9999)
        if p not in used:
            return p
    return random.randint(10000, 20000)



# ============================================
# অটো-রিস্টার্ট
# ============================================

def should_auto_restart(server_id):
    if server_id not in CRASH_COUNT:
        CRASH_COUNT[server_id] = {'count': 0, 'last_crash': time.time()}
    crash_info = CRASH_COUNT[server_id]
    if time.time() - crash_info['last_crash'] < 60:
        if crash_info['count'] >= 3:
            return False
    else:
        crash_info['count'] = 0
    crash_info['count'] += 1
    crash_info['last_crash'] = time.time()
    return True

# ============================================
# হেল্পার
# ============================================

def generate_random_password(length=10):
    chars = string.ascii_letters + string.digits
    return ''.join(random.choices(chars, k=length))

def load_users():
    if not os.path.exists(USERS_FILE):
        default = {"admin": {"password": "AMOR#2025", "role": "admin"}}
        save_users(default)
        return default
    with open(USERS_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if 'admin' not in data:
        data['admin'] = {"password": "AMOR#2025", "role": "admin"}
        save_users(data)
    return data

def save_users(data):
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def get_server_dir(server_id):
    server_dir = os.path.join(BOTS_DIR, server_id)
    os.makedirs(server_dir, exist_ok=True)
    return server_dir

def check_server_valid(server_id):
    users = load_users()
    for uname, data in users.items():
        if uname == 'admin': continue
        servers = data.get('servers', [])
        if not isinstance(servers, list): continue
        for s in servers:
            if isinstance(s, dict) and s.get('server_id') == server_id:
                expiry = s.get('expiry', '')
                if expiry:
                    try:
                        exp_date = datetime.strptime(expiry, '%Y-%m-%d %H:%M:%S.%f')
                        if datetime.now() > exp_date:
                            return False, "expired"
                    except: pass
                return True, s
    return False, "deleted"

def get_server_by_id(server_id):
    users = load_users()
    for uname, data in users.items():
        if uname == 'admin': continue
        servers = data.get('servers', [])
        if not isinstance(servers, list): continue
        for s in servers:
            if isinstance(s, dict) and s.get('server_id') == server_id:
                return s, uname
    return None, None


def user_owns_server(server_id):
    """هل المستخدم الحالي يملك هذا السيرفر أو أدمن؟"""
    if session.get('role') == 'admin' and session.get('user') in ('admin', 'AMOR'):
        return True
    if session.get('role') != 'user' or not session.get('user'):
        return False
    _ws, _wu = get_server_by_id(server_id)
    if _ws and _ws.get('kind') == 'vps':
        if _wu != session.get('user'):
            return False
        _o = next((x for x in load_vps_orders() if x.get('id') == _ws.get('vps_id')), None)
        return bool(_o and _o.get('status') == 'Active')
    if session.get('current_server_id') == server_id:
        return True
    server, uname = get_server_by_id(server_id)
    return bool(server and uname == session.get('user'))

def require_server_access(server_id):
    if not user_owns_server(server_id):
        return False
    return True

def safe_join_server(server_id, *parts):
    """Path inside the server folder only (blocks ../ and symlink escapes)."""
    base = os.path.realpath(get_server_dir(server_id))
    target = os.path.realpath(os.path.join(base, *[str(p).replace('\\', '/').lstrip('/') for p in parts if p]))
    if target == base or target.startswith(base + os.sep):
        return target
    return None

# امتدادات مسموح عرضها للعامة في /s/ (الموقع المنشور)
PUBLIC_SITE_EXTENSIONS = {
    '.html', '.htm', '.css', '.js', '.mjs', '.map',
    '.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.ico',
    '.woff', '.woff2', '.ttf', '.eot', '.otf',
    '.json', '.xml', '.txt', '.pdf', '.mp3', '.mp4', '.webm',
    '.wasm'
}
# ملفات ممنوعة حتى لو امتدادها يبدو آمن
BLOCKED_NAMES = {
    'output.log', 'github_deploy.log', 'users.json', '.env',
    'credentials.json', 'secret.key', 'id_rsa', 'id_rsa.pub'
}

LOGIN_ATTEMPTS = {}  # ip -> [timestamps]
PHONE_OTPS = {}  # phone_norm -> {code, exp, purpose}
PHONE_TG_FILE = "phone_telegram_links.json"
TG_USERS_FILE = "telegram_users.json"  # chat_id -> info

def load_phone_tg():
    if os.path.exists(PHONE_TG_FILE):
        try:
            with open(PHONE_TG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_phone_tg(data):
    with open(PHONE_TG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_tg_users():
    if os.path.exists(TG_USERS_FILE):
        try:
            with open(TG_USERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_tg_users(data):
    with open(TG_USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def check_login_rate():
    ip = request.remote_addr or 'unknown'
    now = time.time()
    attempts = [t for t in LOGIN_ATTEMPTS.get(ip, []) if now - t < 300]
    LOGIN_ATTEMPTS[ip] = attempts
    if len(attempts) >= 15:
        return False
    attempts.append(now)
    LOGIN_ATTEMPTS[ip] = attempts
    return True



# ============================================
# SMART PROJECT DETECTION (auto main file + type)
# ============================================
PY_ENTRIES   = ['main.py', 'app.py', 'bot.py', 'server.py', 'run.py', 'wsgi.py', 'manage.py', 'index.py']
NODE_ENTRIES = ['index.js', 'server.js', 'app.js', 'main.js', 'bot.js', 'index.mjs']
ENTRY_MARKERS = ['package.json', 'index.php', 'index.html', 'index.htm'] + PY_ENTRIES + NODE_ENTRIES
SKIP_DIRS = {'__macosx', 'node_modules', '.git', 'venv', '.venv', '__pycache__'}

def _is_default_main(path):
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read(40).startswith('# AMOR HOSTING - Default Bot')
    except Exception:
        return False

def _real_entries(d):
    found = []
    for m in ENTRY_MARKERS:
        p = os.path.join(d, m)
        if os.path.isfile(p) and not (m == 'main.py' and _is_default_main(p)):
            found.append(m)
    return found

def flatten_project_root(server_dir):
    """ZIP / folder uploads often have one wrapper folder. Move its content up one level."""
    shutil.rmtree(os.path.join(server_dir, '__MACOSX'), ignore_errors=True)
    if _real_entries(server_dir):
        return None
    subs = [x for x in os.listdir(server_dir)
            if os.path.isdir(os.path.join(server_dir, x)) and x.lower() not in SKIP_DIRS]
    cands = [x for x in subs if _real_entries(os.path.join(server_dir, x))]
    if len(cands) == 1:
        src = os.path.join(server_dir, cands[0])
        label = cands[0]
    else:
        deeper = []
        for x in subs:
            sub = os.path.join(server_dir, x)
            for y in os.listdir(sub):
                if os.path.isdir(os.path.join(sub, y)) and _real_entries(os.path.join(sub, y)):
                    deeper.append((x, y))
        if len(deeper) != 1:
            return None
        src = os.path.join(server_dir, deeper[0][0], deeper[0][1])
        label = deeper[0][0] + '/' + deeper[0][1]
    tmp = src + '.__amor_tmp__'
    os.rename(src, tmp)
    for item in os.listdir(tmp):
        dest = os.path.join(server_dir, item)
        if os.path.isdir(dest) and not os.path.islink(dest):
            shutil.rmtree(dest, ignore_errors=True)
        elif os.path.exists(dest):
            os.remove(dest)
        shutil.move(os.path.join(tmp, item), dest)
    shutil.rmtree(tmp, ignore_errors=True)
    return label

def detect_project(server_dir):
    """Returns {'type','main','req'} by inspecting the files. Order: Node, Python, PHP, static HTML, loose JS."""
    def has(n):
        return os.path.isfile(os.path.join(server_dir, n))
    if has('package.json'):
        main = None
        try:
            with open(os.path.join(server_dir, 'package.json'), 'r', encoding='utf-8') as f:
                pj = json.load(f)
            if (pj.get('scripts') or {}).get('start'):
                main = 'package.json'
            elif pj.get('main') and has(pj['main']):
                main = pj['main']
        except Exception:
            pass
        if not main:
            main = next((c for c in NODE_ENTRIES if has(c)), 'package.json')
        return {'type': 'node', 'main': main, 'req': ''}
    for c in PY_ENTRIES:
        if has(c) and not (c == 'main.py' and _is_default_main(os.path.join(server_dir, c))):
            return {'type': 'python', 'main': c, 'req': 'requirements.txt' if has('requirements.txt') else ''}
    if has('index.php'):
        return {'type': 'php', 'main': 'index.php', 'req': ''}
    for c in ('index.html', 'index.htm'):
        if has(c):
            return {'type': 'static', 'main': c, 'req': ''}
    for c in NODE_ENTRIES:
        if has(c):
            return {'type': 'node', 'main': c, 'req': ''}
    try:
        for fn in sorted(os.listdir(server_dir)):
            fl = fn.lower()
            if fl.endswith(('.html', '.htm')):
                return {'type': 'static', 'main': fn, 'req': ''}
            if fl.endswith('.py') and fl != 'main.py':
                return {'type': 'python', 'main': fn, 'req': 'requirements.txt' if has('requirements.txt') else ''}
            if fl.endswith('.js'):
                return {'type': 'node', 'main': fn, 'req': ''}
            if fl.endswith('.sh'):
                return {'type': 'shell', 'main': fn, 'req': ''}
    except Exception:
        pass
    return {'type': 'python', 'main': 'main.py', 'req': 'requirements.txt'}

def safe_extract_zip(zip_path, dest):
    """Zip-slip safe extraction."""
    base = os.path.abspath(dest)
    with zipfile.ZipFile(zip_path, 'r') as zf:
        for m in zf.infolist():
            target = os.path.abspath(os.path.join(base, m.filename))
            if target != base and not target.startswith(base + os.sep):
                continue
            zf.extract(m, base)

def build_run_command(server_id, server_dir, main_path, main_file, log, ts):
    """Pick the right runtime for the entry file. Returns (cmd, error)."""
    main_path = os.path.abspath(main_path)
    server_dir = os.path.abspath(server_dir)
    ext = os.path.splitext(main_file)[1].lower()
    server, _ = get_server_by_id(server_id)
    port = (server or {}).get('port') or 3000
    if main_file == 'package.json' or ext in ('.js', '.mjs', '.cjs'):
        node, npm = shutil.which('node'), shutil.which('npm')
        if not node:
            return None, 'Node.js is not installed on this machine'
        if os.path.isfile(os.path.join(server_dir, 'package.json')) and not os.path.isdir(os.path.join(server_dir, 'node_modules')):
            if npm:
                log(f"[{ts()}] Run: npm install")
                try:
                    r = subprocess.run([npm, 'install', '--no-audit', '--no-fund'], cwd=server_dir,
                                       capture_output=True, text=True, timeout=900)
                    for line in (r.stdout + r.stderr).strip().splitlines()[-12:]:
                        log(f"[{ts()}] {line}")
                except Exception as e:
                    log(f"[{ts()}] npm install error: {e}")
        if main_file == 'package.json':
            if not npm:
                return None, 'npm is not installed on this machine'
            log(f"[{ts()}] Run: npm start")
            return [npm, 'start'], None
        log(f"[{ts()}] Run: node {main_file}")
        return [node, main_path], None
    if ext == '.php':
        php = shutil.which('php')
        if not php:
            return None, 'PHP is not installed on this machine'
        log(f"[{ts()}] Run: php -S 0.0.0.0:{port}")
        return [php, '-S', f'0.0.0.0:{port}', '-t', server_dir], None
    if ext == '.sh':
        bash = shutil.which('bash')
        if not bash:
            return None, 'bash is not available on this machine'
        log(f"[{ts()}] Run: bash {main_file}")
        return [bash, main_path], None
    log(f"[{ts()}] Run: python {main_file}")
    log(f"[{ts()}] Python {sys.version.split()[0]}")
    return [sys.executable, main_path], None

def _update_server(server_id, **fields):
    users = load_users()
    for uname, data in users.items():
        if uname == 'admin': continue
        for sv in data.get('servers', []) or []:
            if isinstance(sv, dict) and sv.get('server_id') == server_id:
                sv.update(fields)
                save_users(users)
                return True
    return False

def start_server(server_id):
    """Start a project the right way. Static sites need no process. Returns (ok, message)."""
    server, _ = get_server_by_id(server_id)
    if not server:
        return False, 'Not found'
    main = server.get('main_file', 'main.py')
    log_file = os.path.join(get_server_dir(server_id), 'output.log')
    if main.lower().endswith(('.html', '.htm')):
        try:
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(f"[{datetime.now().strftime('%I:%M:%S %p')}] Static site is live: {server.get('public_url','')}\n")
        except Exception:
            pass
        _update_server(server_id, status='running', pid=None, started_at=str(datetime.now()),
                       rate_limit_exceeded=False, stopped_by_user=False)
        return True, 'Static site is live'
    pid, error = run_bot(server_id, main, server.get('requirements_file', 'requirements.txt'))
    if pid:
        _update_server(server_id, status='running', pid=pid, started_at=str(datetime.now()),
                       rate_limit_exceeded=False, stopped_by_user=False)
        threading.Thread(target=monitor_bot, args=(server_id, pid), daemon=True).start()
        return True, 'Started!'
    return False, error or 'Failed'

_HTML_URL_RE = None

def proxy_to_port(server_id, port, filepath):
    """Reverse-proxy /s/<id>/... to the project's own process (Flask / Node / PHP sites)."""
    from flask import Response
    import re as _re
    try:
        fwd = {k: v for k, v in request.headers if k.lower() not in ('host', 'content-length', 'connection', 'accept-encoding')}
        r = requests.request(request.method, f'http://127.0.0.1:{int(port)}/{filepath}', params=request.args,
                             data=request.get_data(), headers=fwd, allow_redirects=False, timeout=20)
    except Exception:
        return None
    skip = {'content-encoding', 'content-length', 'transfer-encoding', 'connection'}
    body = r.content
    prefix = f'/s/{server_id}'
    if 'text/html' in r.headers.get('content-type', ''):
        txt = body.decode(r.encoding or 'utf-8', errors='replace')
        pat = _re.compile("((?:src|href|action)\\s*=\\s*[\"'])/(?!/)")
        txt = pat.sub(lambda m: m.group(1) + prefix + '/', txt)
        body = txt.encode('utf-8')
    fixed = []
    for k, v in r.raw.headers.items():
        if k.lower() in skip:
            continue
        if k.lower() == 'location' and v.startswith('/') and not v.startswith('//'):
            v = prefix + v
        fixed.append((k, v))
    return Response(body, r.status_code, fixed)

def create_default_files(server_dir):
    main_py = os.path.join(server_dir, 'main.py')
    if not os.path.exists(main_py):
        with open(main_py, 'w', encoding='utf-8') as f:
            f.write('''# AMOR HOSTING - Default Bot
import time

print("=" * 40)
print("Bot is running on AMOR HOSTING")
print("Server is ready!")
print("=" * 40)

counter = 0
while True:
    counter += 1
    print(f"[{time.strftime('%H:%M:%S')}] Heartbeat #{counter} | Server active")
    time.sleep(10)
''')
    
    req_file = os.path.join(server_dir, 'requirements.txt')
    if not os.path.exists(req_file):
        with open(req_file, 'w', encoding='utf-8') as f:
            f.write('# Add your pip packages here\n')

# ============================================
# বট রান
# ============================================

def run_bot(server_id, main_file='main.py', requirements_file='requirements.txt'):
    server_dir = get_server_dir(server_id)
    main_path = os.path.join(server_dir, main_file)
    log_file = os.path.join(server_dir, 'output.log')
    python_exe = sys.executable
    
    def log(msg):
        try:
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(f"{msg}\n")
                f.flush()
        except: pass
    
    if not os.path.exists(main_path):
        return None, f"ERROR: {main_file} not found!"
    
    if os.path.exists(log_file):
        try: os.remove(log_file)
        except: open(log_file, 'w').close()
    
    ts = lambda: datetime.now().strftime('%I:%M:%S %p')
    
    server, _ = get_server_by_id(server_id)
    cpu_limit = server.get('cpu_limit', 80) if server else 80
    log(f"[{ts()}] Checking rate limit...")
    log(f"[{ts()}] Rate limit: {cpu_limit}%")
    log("")
    
    if requirements_file and requirements_file.strip():
        req_path = os.path.join(server_dir, requirements_file.strip())
        log(f"[{ts()}] Run: pip install -r {requirements_file}")
        log("")
        
        if os.path.exists(req_path):
            with open(req_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
            
            lines = [l.strip() for l in content.split('\n') if l.strip() and not l.strip().startswith('#')]
            
            if lines:
                try:
                    proc = subprocess.Popen(
                        [python_exe, '-m', 'pip', 'install', '-r', os.path.abspath(req_path), '--disable-pip-version-check'],
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        text=True, bufsize=1, universal_newlines=True,
                        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
                    )
                    
                    _pip_out = []
                    for line in iter(proc.stdout.readline, ''):
                        if line.strip():
                            _pip_out.append(line)
                            log(f"[{ts()}] {line.rstrip()}")
                    
                    proc.wait()
                    if proc.returncode != 0 and any('externally-managed' in l for l in _pip_out):
                        log(f"[{ts()}] Retrying pip with --break-system-packages ...")
                        _r = subprocess.run([python_exe, '-m', 'pip', 'install', '-r', os.path.abspath(req_path),
                                             '--disable-pip-version-check', '--break-system-packages'],
                                            capture_output=True, text=True)
                        for _l in (_r.stdout + _r.stderr).strip().splitlines()[-8:]:
                            log(f"[{ts()}] {_l}")
                        proc.returncode = _r.returncode
                    log("")
                    
                    if proc.returncode != 0:
                        log(f"[{ts()}] Some packages failed to install")
                    else:
                        log(f"[{ts()}] Requirements installation complete!")
                except Exception as e:
                    log(f"[{ts()}] pip error: {str(e)}")
            else:
                log(f"[{ts()}] {requirements_file} is empty, skipping...")
        else:
            log(f"[{ts()}] {requirements_file} not found, skipping...")
    else:
        log(f"[{ts()}] No requirements file set, skipping...")
    
    log("")
    cmd, cmd_err = build_run_command(server_id, server_dir, main_path, main_file, log, ts)
    if cmd is None:
        log(f"[{ts()}] ERROR: {cmd_err}")
        return None, cmd_err
    log("")
    
    try:
        main_path_abs = os.path.abspath(main_path)
        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'
        env['PYTHONUNBUFFERED'] = '1'
        if os.path.isdir(os.path.join(server_dir, '.pylibs')):
            env['PYTHONPATH'] = os.path.join(os.path.abspath(server_dir), '.pylibs') + os.pathsep + env.get('PYTHONPATH', '')
        env['PORT'] = str((server or {}).get('port') or 3000)
        
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            cwd=server_dir,
            text=True, encoding='utf-8', errors='replace',
            bufsize=1, env=env, universal_newlines=True,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        )
        
        log(f"[{ts()}] Server marked as running")
        log(f"[{ts()}] PID: {proc.pid}")
        log("")
        
        def rate_monitor():
            while proc.poll() is None:
                time.sleep(5)
                exceeded, avg_cpu = rate_limiter.check_rate(server_id, cpu_limit)
                if exceeded:
                    log(f"[{datetime.now().strftime('%I:%M:%S %p')}] CPU Limit! {avg_cpu:.1f}% > {cpu_limit}%")
                    proc.terminate()
                    time.sleep(2)
                    if proc.poll() is None: proc.kill()
                    
                    users = load_users()
                    for uname, data in users.items():
                        if uname == 'admin': continue
                        servers = data.get('servers', [])
                        if not isinstance(servers, list): continue
                        for s in servers:
                            if isinstance(s, dict) and s.get('server_id') == server_id:
                                s['status'] = 'stopped'
                                s['pid'] = None
                                s['rate_limit_exceeded'] = True
                                s['stopped_by_user'] = False
                                save_users(users)
                                break
                    break
        
        threading.Thread(target=rate_monitor, daemon=True).start()
        
        def stream_output():
            try:
                with open(log_file, 'a', encoding='utf-8') as f:
                    for line in iter(proc.stdout.readline, ''):
                        if line:
                            line = line.rstrip('\n\r')
                            if line:
                                f.write(f"[{datetime.now().strftime('%I:%M:%S %p')}] {line}\n")
                                f.flush()
            except: pass
        
        threading.Thread(target=stream_output, daemon=True).start()
        
        return proc.pid, None
        
    except Exception as e:
        log(f"[{ts()}] Error: {str(e)}")
        return None, str(e)

def stop_bot_process(pid):
    try:
        if sys.platform == 'win32':
            subprocess.run(['taskkill', '/F', '/PID', str(pid)], capture_output=True)
        else:
            os.kill(pid, 15)
        return True
    except: return False

def monitor_bot(server_id, pid):
    while True:
        try:
            if sys.platform == 'win32':
                result = subprocess.run(['tasklist', '/FI', f'PID eq {pid}'], capture_output=True, text=True)
                if str(pid) not in result.stdout:
                    break
            else:
                try: os.kill(pid, 0)
                except: break
        except: break
        time.sleep(5)
    
    server, _ = get_server_by_id(server_id)
    if not server: return
    if server.get('stopped_by_user'): return
    if server.get('rate_limit_exceeded'): return
    
    if should_auto_restart(server_id):
        time.sleep(3)
        new_pid, error = run_bot(server_id, server.get('main_file', 'main.py'), 
                                 server.get('requirements_file', 'requirements.txt'))
        if new_pid:
            users = load_users()
            for uname, data in users.items():
                if uname == 'admin': continue
                servers = data.get('servers', [])
                if not isinstance(servers, list): continue
                for s in servers:
                    if isinstance(s, dict) and s.get('server_id') == server_id:
                        s['status'] = 'running'
                        s['pid'] = new_pid
                        s['started_at'] = str(datetime.now())
                        s['rate_limit_exceeded'] = False
                        s['stopped_by_user'] = False
                        save_users(users)
                        break
            threading.Thread(target=monitor_bot, args=(server_id, new_pid), daemon=True).start()
    else:
        users = load_users()
        for uname, data in users.items():
            if uname == 'admin': continue
            servers = data.get('servers', [])
            if not isinstance(servers, list): continue
            for s in servers:
                if isinstance(s, dict) and s.get('server_id') == server_id:
                    s['status'] = 'stopped'
                    s['pid'] = None
                    save_users(users)
                    return

def get_process_stats(pid):
    try:
        proc = psutil.Process(pid)
        cpu = proc.cpu_percent(interval=0.5)
        mem = proc.memory_info()
        ram = mem.rss / (1024 * 1024)
        return {
            'cpu_percent': round(cpu, 1),
            'ram_mb': round(ram, 1),
            'ram_display': f"{ram:.1f} MB" if ram < 1024 else f"{ram/1024:.1f} GB",
        }
    except:
        return {'cpu_percent': 0, 'ram_mb': 0, 'ram_display': '0 MB'}

def get_network_stats(psutil_pid):
    try:
        proc = psutil.Process(psutil_pid)
        io = proc.io_counters()
        if io:
            read_kb = io.read_bytes / 1024
            write_kb = io.write_bytes / 1024
            return format_bytes(read_kb), format_bytes(write_kb)
    except: pass
    return "0 KB", "0 KB"

def format_bytes(kb):
    if kb < 1024: return f"{kb:.1f} KB"
    mb = kb / 1024
    if mb < 1024: return f"{mb:.1f} MB"
    gb = mb / 1024
    return f"{gb:.2f} GB"

# ============================================
# 🔥 পাবলিক API - সার্ভার তৈরি
# ============================================

@app.route('/api/create', methods=['GET'])
def api_create_server():
    username = request.args.get('username', '').strip()
    password = request.args.get('password', '').strip()
    server_type = request.args.get('type', 'python').strip()
    ram = request.args.get('ram', '1GB').strip()
    disk = request.args.get('disk', '1GB').strip()
    cpu_limit = int(request.args.get('cpu', '30'))
    days = int(request.args.get('days', '3'))
    
    if not password:
        password = generate_random_password(10)
    
    if not username:
        username = f"AMOR_CODEX{random.randint(10000, 99999)}"
    
    if len(username) < 3:
        return jsonify({'status': 'error', 'message': 'Username must be at least 3 characters!'}), 400
    
    if len(password) < 4:
        return jsonify({'status': 'error', 'message': 'Password must be at least 4 characters!'}), 400
    
    if cpu_limit < 10 or cpu_limit > 100:
        return jsonify({'status': 'error', 'message': 'CPU limit must be between 10 and 100!'}), 400
    
    if days < 1 or days > 365:
        return jsonify({'status': 'error', 'message': 'Days must be between 1 and 365!'}), 400
    
    users = load_users()
    
    if username in users:
        return jsonify({'status': 'error', 'message': f"Username '{username}' already exists!"}), 400
    
    server_id = str(uuid.uuid4())[:8]
    expiry_date = datetime.now() + timedelta(days=days)
    
    create_default_files(get_server_dir(server_id))
    
    host = request.host
    is_local = host.startswith('localhost') or host.startswith('127.0.0.1') or host.startswith('192.168')
    scheme = 'http' if is_local else 'https'
    full_url = f"{scheme}://{host}/{server_id}/login"
    
    port = allocate_port(users)
    public_url = f"{scheme}://{host}/s/{server_id}/"
    new_server = {
        'server_id': server_id,
        'login_url': f"/{server_id}/login",
        'dashboard_url': f"/{server_id}/home",
        'full_link': full_url,
        'type': server_type,
        'ram': ram, 'disk': disk,
        'status': 'stopped', 'pid': None,
        'created': str(datetime.now()),
        'expiry': str(expiry_date),
        'main_file': 'main.py',
        'requirements_file': 'requirements.txt',
        'cpu_limit': cpu_limit,
        'rate_limit_exceeded': False,
        'stopped_by_user': False,
        'port': port,
        'public_url': public_url
    }
    
    users[username] = {'password': password, 'role': 'user', 'servers': [new_server]}
    save_users(users)
    
    # إرسال إشعار تليجرام للأدمن عند إنشاء حساب جديد عبر API
    msg = (
        f"🚨 <b>حساب جديد تم إنشاؤه عبر API!</b>\n\n"
        f"👤 <b>اسم المستخدم:</b> <code>{username}</code>\n"
        f"🔑 <b>كلمة المرور:</b> <code>{password}</code>\n"
        f"🖥️ <b>نوع السيرفر:</b> {server_type}\n"
        f"⏳ <b>المدة:</b> {days} أيام\n"
        f"🔗 <b>رابط الدخول:</b> {full_url}"
    )
    send_telegram_notification(msg)
    
    return jsonify({
        'status': 'success',
        'message': 'Panel created successfully!',
        'username': username,
        'password': password,
        'server_type': server_type,
        'ram': ram,
        'disk': disk,
        'cpu_limit': cpu_limit,
        'validity': f'{days} days',
        'expiry_date': expiry_date.strftime('%Y-%m-%d'),
        'full_url': full_url,
        'server_id': server_id
    }), 200

# ============================================
# রাউটস
# ============================================

@app.route('/')
def index():
    return render_template('landing.html', vps_plans=vps_module.get_plans(), cfg=vps_module.get_cfg())

@app.route('/landing')
def landing():
    return render_template('landing.html', vps_plans=vps_module.get_plans(), cfg=vps_module.get_cfg())

def normalize_phone(phone=None, *args, **kwargs):
    """توحيد شكل رقم الهاتف للمقارنة — آمن لو اتنادى بدون معامل.
    أرقام مصر: 01xxxxxxxxx أو +201xxxxxxxxx → 201xxxxxxxxx
    """
    try:
        if phone is None:
            phone = ''
        if not phone:
            return ''
        s = str(phone).strip()
        digits = ''.join(ch for ch in s if ch.isdigit())
        if digits.startswith('00'):
            digits = digits[2:]
        # مصر: 01xxxxxxxxx (11 رقم) → 201xxxxxxxxx
        if len(digits) == 11 and digits.startswith('01'):
            digits = '20' + digits[1:]  # 01... → 201...
        # مصر: 1xxxxxxxxx بدون صفر (10 أرقام) → 201xxxxxxxxx
        elif len(digits) == 10 and digits.startswith('1'):
            digits = '20' + digits
        return digits
    except Exception:
        return ''

def phones_match(a, b):
    a, b = normalize_phone(a), normalize_phone(b)
    if not a or not b or len(a) < 8 or len(b) < 8:
        return False
    return a == b or a.endswith(b[-9:]) or b.endswith(a[-9:])

def find_user_by_login(login_id, users):
    """بحث باليوزر أو البريد أو رقم الهاتف"""
    raw = (login_id or '').strip()
    if not raw:
        return None, None
    login_lower = raw.lower()
    for uname, data in users.items():
        if uname == 'admin':
            continue
        if uname.lower() == login_lower:
            return uname, data
    for uname, data in users.items():
        if uname == 'admin':
            continue
        em = (data.get('email') or '').strip().lower()
        if em and em == login_lower:
            return uname, data
    phone_q = normalize_phone(raw)
    if len(phone_q) >= 8:
        for uname, data in users.items():
            if uname == 'admin':
                continue
            if phones_match(phone_q, data.get('phone') or ''):
                return uname, data
    return None, None

def session_login_user(uname, udata):
    if udata.get('suspended'):
        return None
    """تسجيل جلسة مستخدم وتوجيه لأول سيرفر"""
    if udata.get('role') == 'admin' or uname in ('admin', 'AMOR'):
        session['user'] = 'admin'
        session['role'] = 'admin'
        return redirect(url_for('admin_dashboard'))
    try:
        notify_vps_login(uname, udata)
    except Exception:
        pass
    servers = udata.get('servers') or []
    active = None
    for s in servers:
        if isinstance(s, dict) and s.get('server_id') and s.get('kind') != 'vps':
            active = s
            break
    if not active:
        if udata.get('vps_only') or any(isinstance(x, dict) and x.get('kind') == 'vps' for x in servers):
            session['user'] = uname
            session['role'] = 'user'
            session.pop('current_server_id', None)
            return redirect('/vps/panel')
        return None  # caller handles error
    sid = active['server_id']
    session['user'] = uname
    session['role'] = 'user'
    session['current_server_id'] = sid
    return redirect(url_for('server_home', server_id=sid))

def send_otp_sms(phone_display, code):
    """إرسال رمز OTP لصاحب الرقم فقط عبر تيليجرام المرتبط"""
    phone_n = normalize_phone(phone_display)
    links = load_phone_tg()
    chat_id = links.get(phone_n)
    # بحث مرن بآخر 9 أرقام
    if not chat_id:
        for ph, cid in links.items():
            if phones_match(ph, phone_n):
                chat_id = cid
                break
    msg = (
        f"🔐 <b>رمز التحقق — AMOR HOSTING</b>\n\n"
        f"الرمز: <code>{code}</code>\n"
        f"صالح لمدة 5 دقائق.\n\n"
        f"لا تشارك الرمز مع أحد."
    )
    if chat_id:
        ok = send_telegram_notification(msg, chat_id=chat_id)
        if ok:
            return True, 'user_telegram'
        return False, 'telegram_send_failed'
    # الرقم غير مربوط بالبوت
    return False, 'not_linked'

@app.route('/login', methods=['GET', 'POST'])
def login():
    oauth = {
        'google': bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET),
        'discord': bool(DISCORD_CLIENT_ID and DISCORD_CLIENT_SECRET),
    }
    if request.method == 'POST':
        if not check_login_rate():
            return render_template('login.html', error="Too many attempts. Please wait a moment.", **oauth)
        login_id = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        users = load_users()
        # أدمن
        admin_pass = users.get('admin', {}).get('password', '')
        if login_id in ('AMOR', 'admin') and password == admin_pass:
            session['user'] = 'admin'
            session['role'] = 'admin'
            return redirect(url_for('admin_dashboard'))
        uname, udata = find_user_by_login(login_id, users)
        if uname and udata and str(udata.get('password', '')) == str(password):
            result = session_login_user(uname, udata)
            if result is None:
                return render_template('login.html', error="No server is linked to this account. Contact the admin.", **oauth)
            return result
        return render_template('login.html', error="Incorrect login details. Use your username, email or phone together with your password.", **oauth)
    return render_template('login.html', error=None, **oauth)

@app.route('/api/phone/send_otp', methods=['POST'])
def api_phone_send_otp():
    data = request.get_json() or {}
    phone = (data.get('phone') or '').strip()
    purpose = data.get('purpose') or 'login'  # login | register
    phone_n = normalize_phone(phone)
    if len(phone_n) < 8:
        return jsonify({'ok': False, 'error': 'Invalid phone number'}), 400
    if not check_login_rate():
        return jsonify({'ok': False, 'error': 'Too many attempts'}), 429
    code = f"{random.randint(100000, 999999)}"
    PHONE_OTPS[phone_n] = {
        'code': code,
        'exp': time.time() + 300,
        'purpose': purpose,
        'phone': phone
    }
    ok, channel = send_otp_sms(phone if phone.startswith('+') else phone, code)
    if not ok:
        # احذف الرمز لو مفشش إرسال
        PHONE_OTPS.pop(phone_n, None)
        if channel == 'telegram_send_failed':
            return jsonify({
                'ok': False,
                'error': 'Could not send the code on Telegram. Open @AmorffBOT, press /start and try again.'
            }), 400
        return jsonify({
            'ok': False,
            'error': (
                'افتح بوت تيليجرام @AmorffBOT واضغط /start ثم أرسل رقمك هكذا:\n'
                '+20' + (phone_n[2:] if phone_n.startswith('20') else phone_n)
            ),
            'need_bind': True
        }), 400
    return jsonify({
        'ok': True,
        'msg': 'Verification code sent to your Telegram bot only ✅',
        'channel': channel
    })

@app.route('/api/phone/verify_otp', methods=['POST'])
def api_phone_verify_otp():
    data = request.get_json() or {}
    phone = (data.get('phone') or '').strip()
    code = (data.get('code') or '').strip()
    password = (data.get('password') or '').strip()
    username = (data.get('username') or '').strip()
    phone_n = normalize_phone(phone)
    entry = PHONE_OTPS.get(phone_n)
    if not entry or time.time() > entry.get('exp', 0):
        return jsonify({'ok': False, 'error': 'The code has expired or does not exist. Request a new one.'}), 400
    if str(entry.get('code')) != str(code):
        return jsonify({'ok': False, 'error': 'Incorrect verification code'}), 400
    users = load_users()
    uname, udata = find_user_by_login(phone_n, users)
    if uname and udata and entry.get('purpose') == 'register':
        return jsonify({'ok': False, 'error': 'الرقم ده مسجّل بالفعل — اضغط "تسجيل الدخول" تحت.'}), 400
    # حساب موجود → دخول
    if uname and udata:
        PHONE_OTPS.pop(phone_n, None)
        # لو بعت باسورد جديد يقدر يحدّثه
        if password and len(password) >= 4:
            users[uname]['password'] = password
            save_users(users)
            udata = users[uname]
        result = session_login_user(uname, udata)
        if result is None:
            return jsonify({'ok': False, 'error': 'No server found. Contact the admin.'}), 400
        sid = session.get('current_server_id')
        return jsonify({'ok': True, 'redirect': f'/{sid}/home'})
    # حساب جديد → إنشاء
    if not password or len(password) < 4:
        return jsonify({'ok': False, 'error': 'New account: please set a password (at least 4 characters).', 'need_password': True}), 400
    if not username:
        username = 'u' + phone_n[-8:]
    username = ''.join(c for c in username if c.isalnum() or c in '_-')[:20]
    if len(username) < 3:
        username = 'u' + phone_n[-8:]
    if username in users:
        username = username + str(random.randint(10, 99))
    server_id = str(uuid.uuid4())[:8]
    create_default_files(get_server_dir(server_id))
    port = allocate_port(users)
    public_url = request.host_url.rstrip('/') + f'/s/{server_id}/'
    new_server = {
        'server_id': server_id, 'login_url': f'/{server_id}/login',
        'dashboard_url': f'/{server_id}/home',
        'full_link': request.host_url.rstrip('/') + f'/{server_id}/home',
        'type': 'python', 'ram': '512MB', 'disk': '1GB',
        'status': 'stopped', 'pid': None,
        'created': str(datetime.now()),
        'expiry': str(datetime.now() + timedelta(days=12)),
        'main_file': 'main.py', 'requirements_file': 'requirements.txt',
        'cpu_limit': 40, 'rate_limit_exceeded': False, 'stopped_by_user': False,
        'port': port, 'public_url': public_url
    }
    users[username] = {
        'password': password, 'role': 'user', 'email': '',
        'phone': phone_n, 'servers': [new_server], 'oauth': 'phone'
    }
    save_users(users)
    PHONE_OTPS.pop(phone_n, None)
    send_telegram_notification(f"📱 <b>حساب هاتف جديد</b>\n👤 {username}\n📱 {phone}\n🆔 <code>{server_id}</code>")
    session['user'] = username
    session['role'] = 'user'
    session['current_server_id'] = server_id
    return jsonify({'ok': True, 'redirect': f'/{server_id}/home'})


@app.route('/register', methods=['GET', 'POST'])
def register():
    """تسجيل بالبريد أو الهاتف + كلمة مرور"""
    oauth = {
        'google': bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET),
        'discord': bool(DISCORD_CLIENT_ID and DISCORD_CLIENT_SECRET),
    }
    if request.method == 'POST':
        if not check_login_rate():
            return render_template('register.html', error="Too many attempts. Please try again later.", **oauth)
        email = request.form.get('email', '').strip().lower()
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '').strip()
        username = request.form.get('username', '').strip()
        phone_norm = normalize_phone(phone)
        if email and '@' not in email:
            return render_template('register.html', error="Invalid email address", **oauth)
        if phone and len(phone_norm) < 8:
            return render_template('register.html', error="Invalid phone number", **oauth)
        if len(password) < 4:
            return render_template('register.html', error="Password is too short (at least 4 characters)", **oauth)
        # يوزر + باسورد كافيين (البريد/الهاتف اختياري)
        if not username:
            if email:
                username = email.split('@')[0]
            elif phone_norm:
                username = 'u' + phone_norm[-8:]
            else:
                return render_template('register.html', error="Enter a username", **oauth)
        _typed_username = bool(request.form.get('username', '').strip())
        username = ''.join(c for c in username if c.isalnum() or c in '_-')[:20]
        if not _typed_username and len(username) < 3:
            username = (username + 'user' + str(random.randint(100, 999)))[:20]  # من البريد: اسم قصير → كمّله
        if not username or len(username) < 3:
            return render_template('register.html', error="Invalid username (at least 3 characters)", **oauth)
        users = load_users()
        if username in users:
            return render_template('register.html', error="This username is already taken", **oauth)
        for u, d in users.items():
            if email and (d.get('email') or '').lower() == email:
                return render_template('register.html', error="This email is already registered", **oauth)
            if phone_norm and normalize_phone(d.get('phone') or ''):
                existing = normalize_phone(d.get('phone') or '')
                if existing == phone_norm or existing.endswith(phone_norm[-9:]) or phone_norm.endswith(existing[-9:]):
                    return render_template('register.html', error="This phone number is already registered", **oauth)
        server_id = str(uuid.uuid4())[:8]
        create_default_files(get_server_dir(server_id))
        port = allocate_port(users)
        public_url = request.host_url.rstrip('/') + f'/s/{server_id}/'
        new_server = {
            'server_id': server_id, 'login_url': f'/{server_id}/login',
            'dashboard_url': f'/{server_id}/home',
            'full_link': request.host_url.rstrip('/') + f'/{server_id}/home',
            'type': 'python', 'ram': '512MB', 'disk': '1GB',
            'status': 'stopped', 'pid': None,
            'created': str(datetime.now()),
            'expiry': str(datetime.now() + timedelta(days=12)),
            'main_file': 'main.py', 'requirements_file': 'requirements.txt',
            'cpu_limit': 40, 'rate_limit_exceeded': False, 'stopped_by_user': False,
            'port': port, 'public_url': public_url
        }
        users[username] = {
            'password': password, 'role': 'user',
            'email': email or '', 'phone': phone_norm or phone,
            'servers': [new_server], 'oauth': ('phone' if phone_norm and not email else ('email' if email else 'password'))
        }
        save_users(users)
        send_telegram_notification(
            f"🆕 <b>تسجيل جديد</b>\n👤 {username}\n📧 {email or '—'}\n📱 {phone or '—'}\n🆔 <code>{server_id}</code>"
        )
        session['user'] = username
        session['role'] = 'user'
        session['current_server_id'] = server_id
        return redirect(url_for('server_home', server_id=server_id))
    return render_template('register.html', error=None, **oauth)

@app.route('/<server_id>/login', methods=['GET', 'POST'])
def server_login(server_id):
    valid, result = check_server_valid(server_id)
    if not valid:
        return render_template('error.html', error_type=result if result else "deleted", server_link=server_id)
    
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        users = load_users()
        for uname, data in users.items():
            if uname == 'AMOR#2025': continue
            servers = data.get('servers', [])
            if not isinstance(servers, list): continue
            for s in servers:
                if isinstance(s, dict) and s.get('server_id') == server_id:
                    if username == uname and password == data.get('password'):
                        session['user'] = uname
                        session['role'] = 'user'
                        session['current_server_id'] = server_id
                        return redirect(url_for('server_home', server_id=server_id))
                    else:
                        return render_template('login.html', error="Invalid credentials!")
        return render_template('login.html', error="Invalid login!")
    return render_template('login.html', error=None)

@app.route('/<server_id>/home')
def server_home(server_id):
    if 'user' not in session or session.get('role') != 'user':
        return redirect(url_for('server_login', server_id=server_id))
    if session.get('current_server_id') != server_id:
        session.clear()
        return redirect(url_for('server_login', server_id=server_id))
    
    _hs, _hu = get_server_by_id(server_id)
    if _hs and _hs.get('kind') == 'vps':
        return redirect('/vps/panel')
    valid, result = check_server_valid(server_id)
    if not valid:
        session.clear()
        return render_template('error.html', error_type=result if result else "deleted", server_link=server_id)
    
    return render_template('home.html', username=session['user'], current_server=result)

@app.route('/logout')
def logout():
    server_id = session.get('current_server_id')
    session.clear()
    if server_id:
        return redirect(url_for('server_login', server_id=server_id))
    return redirect(url_for('login'))

# ============================================
# অ্যাডমিন
# ============================================

@app.route('/admin')
def admin_dashboard():
    if 'user' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
    users = load_users()
    user_list = []
    total_servers = 0
    total_running = 0
    for uname, data in users.items():
        if uname == 'admin': continue
        servers = data.get('servers', [])
        if not isinstance(servers, list): servers = []
        running = sum(1 for s in servers if isinstance(s, dict) and s.get('status') == 'running')
        total_servers += len(servers)
        total_running += running
        user_list.append({
            'username': uname, 'password': data.get('password', ''),
            'servers': servers, 'server_count': len(servers), 'running_count': running
        })
    ad = load_ad()
    return render_template('admin.html', users=user_list, total_servers=total_servers, total_running=total_running, ad_text=ad.get('text',''))

@app.route('/admin/create_server', methods=['POST'])
def create_server():
    if 'user' not in session or session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    email = (data.get('email') or '').strip().lower()
    phone = (data.get('phone') or '').strip()
    phone_norm = normalize_phone(phone)
    server_type = data.get('server_type', 'python')
    ram = data.get('ram', '512MB')
    disk = data.get('disk', '1GB')
    expiry_days = int(data.get('expiry_days', 30))
    cpu_limit = int(data.get('cpu_limit', 80))
    
    if not username or not password:
        return jsonify({'error': 'Required!'}), 400
    if email and '@' not in email:
        return jsonify({'error': 'Invalid email address'}), 400
    if phone and len(phone_norm) < 8:
        return jsonify({'error': 'Invalid phone number'}), 400
    
    users = load_users()
    if email:
        for u, d in users.items():
            if (d.get('email') or '').lower() == email and u != username:
                return jsonify({'error': 'This email belongs to another account'}), 400
    if phone_norm:
        for u, d in users.items():
            if u == username: continue
            ep = normalize_phone(d.get('phone') or '')
            if ep and (ep == phone_norm or ep.endswith(phone_norm[-9:]) or phone_norm.endswith(ep[-9:])):
                return jsonify({'error': 'This phone number belongs to another account'}), 400
    server_id = str(uuid.uuid4())[:8]
    expiry_date = datetime.now() + timedelta(days=expiry_days)
    
    create_default_files(get_server_dir(server_id))
    
    port = allocate_port(users)
    public_url = request.host_url.rstrip('/') + f'/s/{server_id}/'
    new_server = {
        'server_id': server_id, 'link': server_id,
        'login_url': f"/{server_id}/login",
        'dashboard_url': f"/{server_id}/home",
        'full_link': request.host_url.rstrip('/') + f"/{server_id}/home",
        'type': server_type, 'ram': ram, 'disk': disk,
        'status': 'stopped', 'pid': None,
        'created': str(datetime.now()), 'expiry': str(expiry_date),
        'main_file': 'main.py', 'requirements_file': 'requirements.txt',
        'cpu_limit': cpu_limit, 'rate_limit_exceeded': False, 'stopped_by_user': False,
        'port': port, 'public_url': public_url
    }
    
    if username not in users:
        users[username] = {'password': password, 'role': 'user', 'servers': [], 'email': email or '', 'phone': phone_norm or phone or ''}
    else:
        if email: users[username]['email'] = email
        if phone_norm or phone: users[username]['phone'] = phone_norm or phone
    users[username]['password'] = password
    
    users[username]['servers'].append(new_server)
    save_users(users)
    
    # إرسال إشعار تليجرام للأدمن عند إنشاء حساب عبر لوحة الأدمن
    msg = (
        f"🚨 <b>حساب جديد تم إنشاؤه عبر لوحة الأدمن!</b>\n\n"
        f"👤 <b>اسم المستخدم:</b> <code>{username}</code>\n"
        f"🔑 <b>كلمة المرور:</b> <code>{password}</code>\n"
        f"🖥️ <b>نوع السيرفر:</b> {server_type}\n"
        f"⏳ <b>المدة:</b> {expiry_days} يوم\n"
        f"🔗 <b>رابط السيرفر:</b> {new_server['full_link']}"
    )
    send_telegram_notification(msg)
    
    return jsonify({
        'success': True, 'username': username, 'password': password,
        'login_url': new_server['login_url'],
        'hostname': new_server['full_link'],
        'server_id': server_id
    })

@app.route('/admin/set_rate_limit/<server_id>', methods=['POST'])
def set_rate_limit(server_id):
    if 'user' not in session or session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    cpu_limit = int(request.get_json().get('cpu_limit', 80))
    users = load_users()
    for uname, udata in users.items():
        if uname == 'admin': continue
        servers = udata.get('servers', [])
        if not isinstance(servers, list): continue
        for s in servers:
            if isinstance(s, dict) and s.get('server_id') == server_id:
                s['cpu_limit'] = cpu_limit
                save_users(users)
                return jsonify({'success': True, 'cpu_limit': cpu_limit})
    return jsonify({'error': 'Not found'}), 404

@app.route('/admin/delete_server/<username>/<server_id>', methods=['POST'])
def delete_server(username, server_id):
    if 'user' not in session or session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    users = load_users()
    if username in users:
        servers = users[username].get('servers', [])
        if not isinstance(servers, list): servers = []
        for s in servers:
            if isinstance(s, dict) and s.get('server_id') == server_id:
                if s.get('pid'): stop_bot_process(s['pid'])
                try: shutil.rmtree(get_server_dir(server_id))
                except: pass
                break
        users[username]['servers'] = [s for s in servers if isinstance(s, dict) and s.get('server_id') != server_id]
        if len(users[username]['servers']) == 0:
            del users[username]
        save_users(users)
    return jsonify({'success': True})

# ============================================
# لوحة تليجرام للتحقيق من حالة السيرفرات والأيم المفضلة (مع حماية الأدمن فقط)
# ============================================
USER_BOT_HELP = (
    "👋 <b>أهلاً بك في AMOR HOSTING</b>\n\n"
    "🤖 البوت ده وظيفته يبعتلك <b>كود التحقق</b> بتاع الموقع.\n\n"
    "<b>طريقة الاستخدام:</b>\n"
    "1️⃣ اربط رقمك: ابعت هنا\n<code>/bind 01012345678</code>\n(أو ابعت الرقم مباشرة)\n\n"
    "2️⃣ ارجع للموقع ← <b>إنشاء حساب</b> ← <b>برقم الهاتف</b> ← اكتب نفس الرقم واضغط <b>إرسال رمز التحقق</b>\n\n"
    "3️⃣ الكود (6 أرقام) هيوصلك <b>هنا في الشات</b> — اكتبه في الموقع وكمّل الحساب.\n\n"
    "⏱ الكود صالح 5 دقائق — لا تشاركه مع أحد.\n\n"
    "<b>أوامر:</b>\n/my — رقمك المربوط\n/unlink — إلغاء الربط\n/help — المساعدة"
)

@app.route('/telegram/webhook', methods=['POST'])
def telegram_webhook():
    if request.headers.get('X-Telegram-Bot-Api-Secret-Token', '') != TELEGRAM_WEBHOOK_SECRET:
        return jsonify({'status': 'forbidden'}), 403
    try:
        data = request.get_json()
        if not data:
            return jsonify({'status': 'ok'})
        message = data.get('message') or {}
        chat = message.get('chat') or {}
        chat_id = chat.get('id')
        text = (message.get('text') or '').strip()
        if not chat_id:
            return jsonify({'status': 'ok'})

        is_admin = (chat_id == ADMIN_TELEGRAM_ID)
        tg_users = load_tg_users()
        tg_users[str(chat_id)] = {
            'id': chat_id,
            'username': (message.get('from') or {}).get('username'),
            'name': ((message.get('from') or {}).get('first_name') or '')
        }
        save_tg_users(tg_users)

        # ----- أوامر عامة للمستخدمين (كود التحقق) -----
        # /start: للأدمن → لوحة أوامر الأدمن فقط | للمستخدم → تعليمات الربط
        if text.startswith('/start'):
            if is_admin:
                send_telegram_notification(
                    "🛠 <b>لوحة أدمن AMOR HOSTING</b>\n\n"
                    "/status — السيرفرات\n"
                    "/users — المستخدمون\n"
                    "/ad نص — إعلان الموقع\n"
                    "/ad off — إيقاف الإعلان\n"
                    "/broadcast نص — إعلان للمرتبطين\n"
                    "/links — الأرقام المربوطة\n"
                    "/help — المساعدة\n\n"
                    "للمستخدمين: /bind أو إرسال الرقم مباشرة (+20...)",
                    chat_id=chat_id
                )
            else:
                send_telegram_notification(USER_BOT_HELP, chat_id=chat_id)
            return jsonify({'status': 'ok'})

        def _do_bind_phone(raw_phone, chat_id):
            phone_n = normalize_phone(raw_phone)
            if len(phone_n) < 8:
                send_telegram_notification("❌ رقم غير صالح. مثال: <code>+201012345678</code>", chat_id=chat_id)
                return False
            links = load_phone_tg()
            # إزالة ربط قديم لنفس الشات + أي مفتاح قديم لنفس الرقم بأشكال مختلفة
            links = {
                ph: cid for ph, cid in links.items()
                if str(cid) != str(chat_id) and not phones_match(ph, phone_n)
            }
            links[phone_n] = chat_id
            save_phone_tg(links)
            send_telegram_notification(
                f"✅ تم ربط الرقم <code>{phone_n}</code> بهذا الحساب.\n"
                f"الآن اطلب الرمز من موقع AMOR HOSTING وسيصلك هنا فقط.\n"
                f"⏱ مدة الحساب عند التسجيل: 12 يوم.",
                chat_id=chat_id
            )
            return True

        if text.startswith('/bind'):
            parts = text.split(None, 1)
            if len(parts) < 2:
                send_telegram_notification(
                    "استخدم:\n<code>/bind +2010XXXXXXXXX</code>\nأو أرسل الرقم مباشرة مثل:\n<code>+201012345678</code>",
                    chat_id=chat_id
                )
                return jsonify({'status': 'ok'})
            _do_bind_phone(parts[1], chat_id)
            return jsonify({'status': 'ok'})

        # ربط بدون أمر: المستخدم يرسل الرقم فقط (+20... أو 01... أو 20...)
        _maybe_phone = text.replace(' ', '')
        if (_maybe_phone.startswith('+') or _maybe_phone.startswith('01') or _maybe_phone.startswith('20')) and any(c.isdigit() for c in _maybe_phone):
            digits_only = ''.join(ch for ch in _maybe_phone if ch.isdigit())
            if len(digits_only) >= 10:
                _do_bind_phone(_maybe_phone, chat_id)
                return jsonify({'status': 'ok'})

        if text.startswith('/unlink'):
            links = load_phone_tg()
            links = {ph: cid for ph, cid in links.items() if str(cid) != str(chat_id)}
            save_phone_tg(links)
            send_telegram_notification("✅ تم إلغاء ربط رقمك.", chat_id=chat_id)
            return jsonify({'status': 'ok'})

        if text in ('/my', 'رقمي'):
            links = load_phone_tg()
            mine = [ph for ph, cid in links.items() if str(cid) == str(chat_id)]
            send_telegram_notification(
                "📱 أرقامك المربوطة:\n" + ("\n".join(f"<code>{x}</code>" for x in mine) if mine else "لا يوجد — استخدم /bind"),
                chat_id=chat_id
            )
            return jsonify({'status': 'ok'})

        # ----- أوامر الأدمن فقط -----
        if not is_admin:
            send_telegram_notification(USER_BOT_HELP, chat_id=chat_id)
            return jsonify({'status': 'ok'})

        if text.startswith('/status') or text == 'حالة السيرفرات':
            users = load_users()
            total = running = stopped = 0
            details = []
            for uname, udata in users.items():
                if uname == 'admin':
                    continue
                for s in (udata.get('servers') or []):
                    if not isinstance(s, dict):
                        continue
                    total += 1
                    st = s.get('status', 'stopped')
                    if st == 'running':
                        running += 1
                    else:
                        stopped += 1
                    details.append(f"• {uname} | <code>{s.get('server_id')}</code> | {st}")
            send_telegram_notification(
                f"📊 <b>AMOR</b>\nالإجمالي: {total}\nشغالة: {running}\nمتوقفة: {stopped}\n\n" +
                ("\n".join(details[:30]) if details else "لا سيرفرات"),
                chat_id=chat_id
            )
        elif text.startswith('/users') or text == 'المستخدمون':
            users = load_users()
            lines = []
            for uname, udata in users.items():
                if uname == 'admin':
                    continue
                lines.append(f"👤 {uname} | 📧 {udata.get('email') or '—'} | 📱 {udata.get('phone') or '—'} | سيرفرات: {len(udata.get('servers') or [])}")
            send_telegram_notification("👥 <b>المستخدمون</b>\n\n" + ("\n".join(lines) if lines else "فارغ"), chat_id=chat_id)
        elif text.startswith('/ad '):
            ad_msg = text[4:].strip()
            if ad_msg in ('off', 'إيقاف', '0'):
                save_ad('', False)
                send_telegram_notification("🛑 تم إيقاف الإعلان في الموقع.", chat_id=chat_id)
            else:
                save_ad(ad_msg, True)
                send_telegram_notification(f"✅ إعلان الموقع:\n{ad_msg}", chat_id=chat_id)
        elif text.startswith('/ad') or text == 'الإعلان':
            ad = load_ad()
            st = 'مفعّل' if ad.get('active') and ad.get('text') else 'متوقف'
            send_telegram_notification(f"📢 الإعلان: {st}\n{ad.get('text') or '(فارغ)'}\n\n<code>/ad نص</code> | <code>/ad off</code>", chat_id=chat_id)
        elif text.startswith('/broadcast ') or text.startswith('/bc '):
            body = text.split(' ', 1)[1] if ' ' in text else ''
            if not body:
                send_telegram_notification("استخدم: /broadcast نص الإعلان لكل المرتبطين بالبوت", chat_id=chat_id)
            else:
                links = load_phone_tg()
                chat_ids = set(str(c) for c in links.values())
                n = 0
                for cid in chat_ids:
                    try:
                        send_telegram_notification(f"📢 <b>إعلان AMOR</b>\n\n{body}", chat_id=int(cid) if str(cid).lstrip('-').isdigit() else cid)
                        n += 1
                    except Exception:
                        pass
                send_telegram_notification(f"✅ تم إرسال الإعلان لـ {n} مستخدم", chat_id=chat_id)
        elif text.startswith('/links'):
            links = load_phone_tg()
            lines = [f"<code>{ph}</code> → {cid}" for ph, cid in list(links.items())[:40]]
            send_telegram_notification("🔗 ربط الهواتف:\n" + ("\n".join(lines) if lines else "لا يوجد"), chat_id=chat_id)
        elif text.startswith('/help') or text == 'مساعدة':
            send_telegram_notification(
                "🛠 <b>أوامر الأدمن</b>\n"
                "/status — السيرفرات\n"
                "/users — المستخدمون\n"
                "/ad نص — إعلان الموقع\n"
                "/ad off — إيقاف الإعلان\n"
                "/broadcast نص — إعلان لكل من ربط رقمه\n"
                "/links — قائمة الأرقام المربوطة\n"
                "/help — مساعدة\n\n"
                "للمستخدمين: /start /bind /my /unlink",
                chat_id=chat_id
            )
        elif text.startswith('/start'):
            send_telegram_notification("🤖 لوحة أدمن AMOR — اكتب /help", chat_id=chat_id)
        else:
            send_telegram_notification("أمر غير معروف. /help", chat_id=chat_id)

        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'msg': str(e)}), 500


# ============================================
# বট API
# ============================================

@app.route('/api/run/<server_id>', methods=['POST'])
def api_run(server_id):
    if not require_server_access(server_id):
        return jsonify({'error': 'Unauthorized'}), 403
    server, uname = get_server_by_id(server_id)
    if not server: return jsonify({'status': 'error', 'msg': 'Not found'})
    if server.get('status') == 'running': return jsonify({'status': 'error', 'msg': 'Already running!'})
    ok, msg = start_server(server_id)
    return jsonify({'status': 'success' if ok else 'error', 'msg': msg})

@app.route('/api/stop/<server_id>', methods=['POST'])
def api_stop(server_id):
    if not require_server_access(server_id):
        return jsonify({'error': 'Unauthorized'}), 403
    server, uname = get_server_by_id(server_id)
    if not server: return jsonify({'status': 'error', 'msg': 'Not found'})
    
    if server.get('pid'): stop_bot_process(server['pid'])
    
    users = load_users()
    for u, data in users.items():
        if u == 'admin': continue
        servers = data.get('servers', [])
        if not isinstance(servers, list): continue
        for s in servers:
            if isinstance(s, dict) and s.get('server_id') == server_id:
                s['status'] = 'stopped'
                s['pid'] = None
                s['stopped_by_user'] = True
                save_users(users)
                break
    
    log_file = os.path.join(get_server_dir(server_id), 'output.log')
    try:
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f"\n[{datetime.now().strftime('%I:%M:%S %p')}] Server stopped by user\n")
    except: pass
    
    # إشعار إيقاف السيرفر عبر تليجرام للأدمن
    return jsonify({'status': 'success', 'msg': 'Stopped'})

@app.route('/api/logs/<server_id>')
def api_logs(server_id):
    if not require_server_access(server_id):
        return jsonify({'error': 'Unauthorized'}), 403
    log_file = os.path.join(get_server_dir(server_id), 'output.log')
    if os.path.exists(log_file):
        with open(log_file, 'r', encoding='utf-8') as f: logs = f.read()
    else: logs = ""
    return jsonify({'logs': logs})

@app.route('/api/clear_logs/<server_id>', methods=['POST'])
def api_clear_logs(server_id):
    if not require_server_access(server_id):
        return jsonify({'error': 'Unauthorized'}), 403
    log_file = os.path.join(get_server_dir(server_id), 'output.log')
    try:
        if os.path.exists(log_file):
            try: os.remove(log_file)
            except: open(log_file, 'w').close()
        return jsonify({'status': 'success', 'msg': 'Cleared'})
    except: return jsonify({'status': 'error'}), 500

@app.route('/api/command', methods=['POST'])
def api_command():
    data = request.get_json()
    cmd = data.get('cmd', '')
    server_id = data.get('server_id', '')
    if not server_id or not require_server_access(server_id):
        return jsonify({'status': 'error', 'msg': 'Unauthorized'}), 403
    _cs, _cu = get_server_by_id(server_id)
    if _cs and _cs.get('kind') == 'vps':
        return jsonify({'status': 'error', 'msg': 'Use the VPS terminal'}), 403
    banned = ['rm -rf /', 'mkfs', 'shutdown', 'reboot', 'dd if=', ':(){']
    if any(b in (cmd or '') for b in banned):
        return jsonify({'status': 'error', 'msg': 'Command blocked'}), 400
    log_file = os.path.join(get_server_dir(server_id), 'output.log')
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=get_server_dir(server_id), timeout=30,
                              creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
        output = (result.stdout + result.stderr)[:2000]
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f"[{datetime.now().strftime('%I:%M:%S %p')}] $ {cmd}\n{output}\n")
        return jsonify({'status': 'success', 'output': output})
    except: return jsonify({'status': 'error', 'msg': 'Timeout'})

@app.route('/api/stats/<server_id>')
def api_stats(server_id):
    if not require_server_access(server_id):
        return jsonify({'error': 'Unauthorized'}), 403
    server, _ = get_server_by_id(server_id)
    if not server:
        return jsonify({'cpu': '0%', 'ram': '0 MB', 'uptime': '0h', 'status': 'unknown', 'cpu_limit': 80, 'net_in': '0 KB', 'net_out': '0 KB'})
    
    uptime, cpu, ram, net_in, net_out = "0h 0m", "0%", "0 MB", "0 KB", "0 KB"
    
    if server.get('status') == 'running' and server.get('pid'):
        stats = get_process_stats(server['pid'])
        cpu = f"{stats['cpu_percent']}%"
        ram = stats['ram_display']
        net_in, net_out = get_network_stats(server['pid'])
    
    if server.get('status') == 'running' and server.get('started_at'):
        try:
            start = datetime.strptime(server['started_at'], '%Y-%m-%d %H:%M:%S.%f')
            diff = datetime.now() - start
            if diff.days > 0: uptime = f"{diff.days}d {diff.seconds//3600}h"
            else:
                h, m, s = diff.seconds // 3600, (diff.seconds % 3600) // 60, diff.seconds % 60
                uptime = f"{h}h {m}m {s}s"
        except: pass
    
    return jsonify({
        'cpu': cpu, 'ram': ram, 'uptime': uptime, 'net_in': net_in, 'net_out': net_out,
        'cpu_limit': server.get('cpu_limit', 80), 'status': server.get('status', 'stopped'),
        'port': server.get('port'), 'public_url': server.get('public_url')
    })

# ============================================
# পাসওয়ার্ড চেঞ্জ
# ============================================

@app.route('/api/change_password/<server_id>', methods=['POST'])
def api_change_password(server_id):
    if not require_server_access(server_id):
        return jsonify({'error': 'Unauthorized'}), 403
    if 'user' not in session: return jsonify({'error': 'Please login first!'}), 403
    data = request.get_json()
    current_password = data.get('current_password', '')
    new_password = data.get('new_password', '')
    
    if not current_password or not new_password: return jsonify({'error': 'All fields are required!'})
    if len(new_password) < 4: return jsonify({'error': 'Password must be at least 4 characters!'})
    
    users = load_users()
    username = session.get('user')
    
    if username in users:
        if users[username].get('password') == current_password:
            users[username]['password'] = new_password
            save_users(users)
            return jsonify({'success': True, 'msg': 'Password changed!'})
        return jsonify({'error': 'Current password is incorrect!'})
    return jsonify({'error': 'User not found!'}), 404

# ============================================
# 🔥 GITHUB API (Git ছাড়া Python Download)
# ============================================

@app.route('/api/github/deploy/<server_id>', methods=['POST'])
def api_github_deploy(server_id):
    if not require_server_access(server_id):
        return jsonify({'error': 'Unauthorized'}), 403
    """Download GitHub repo without git - using Python requests"""
    data = request.get_json()
    repo_url = data.get('repo_url', '').strip()
    access_token = data.get('access_token', '').strip()
    is_private = data.get('is_private', False)
    
    if not repo_url:
        return jsonify({'status': 'error', 'msg': 'Repository URL is required!'}), 400
    
    server_dir = get_server_dir(server_id)
    log_file = os.path.join(server_dir, 'github_deploy.log')
    
    try:
        with open(log_file, 'w', encoding='utf-8') as f:
            f.write(f"[{datetime.now().strftime('%I:%M:%S %p')}] Starting GitHub deployment...\n")
            f.write(f"[{datetime.now().strftime('%I:%M:%S %p')}] Repository: {repo_url}\n")
            f.write(f"[{datetime.now().strftime('%I:%M:%S %p')}] Type: {'Private' if is_private else 'Public'}\n")
            f.write("─" * 40 + "\n")
    except:
        pass
    
    def deploy_thread():
        try:
            import requests
            import shutil
            
            def deploy_log(msg):
                try:
                    with open(log_file, 'a', encoding='utf-8') as f:
                        f.write(f"[{datetime.now().strftime('%I:%M:%S %p')}] {msg}\n")
                        f.flush()
                except:
                    pass
            
            deploy_log("Preparing deployment...")
            clean_url = repo_url.replace('.git', '').rstrip('/')
            
            if 'github.com' not in clean_url:
                deploy_log("❌ Error: Only GitHub URLs are supported!")
                return
            
            parts = clean_url.split('github.com/')[-1].split('/')
            
            if len(parts) < 2:
                deploy_log("❌ Error: Invalid GitHub URL format!")
                return
            
            owner = parts[0]
            repo = parts[1]
            branch = 'main'
            
            if len(parts) > 3 and parts[2] == 'tree':
                branch = parts[3]
            
            api_url = f"https://api.github.com/repos/{owner}/{repo}/zipball/{branch}"
            
            headers = {'Accept': 'application/vnd.github.v3+json'}
            if is_private and access_token:
                headers['Authorization'] = f'token {access_token}'
            
            response = requests.get(api_url, headers=headers, stream=True, timeout=60)
            
            if response.status_code == 200:
                deploy_log("✓ Repository downloaded successfully!")
                deploy_log("Extracting files...")
                
                temp_zip = os.path.join(server_dir, '_github_temp.zip')
                with open(temp_zip, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                try:
                    with zipfile.ZipFile(temp_zip, 'r') as zf:
                        for member in zf.namelist():
                            relative_path = '/'.join(member.split('/')[1:])
                            if not relative_path:
                                continue
                            
                            target_path = os.path.join(server_dir, relative_path)
                            
                            if member.endswith('/'):
                                os.makedirs(target_path, exist_ok=True)
                            else:
                                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                                with zf.open(member) as source, open(target_path, 'wb') as target:
                                    shutil.copyfileobj(source, target)
                                deploy_log(f"  ✓ {relative_path}")
                    
                    deploy_log("")
                    deploy_log("✅ Deployment completed successfully!")
                except Exception as e:
                    deploy_log(f"❌ Extraction error: {str(e)}")
                finally:
                    try:
                        os.remove(temp_zip)
                    except:
                        pass
                    
            elif response.status_code == 404:
                deploy_log("❌ Error: Repository not found!")
            else:
                deploy_log(f"❌ Error: HTTP {response.status_code}")
            
        except Exception as e:
            try:
                with open(log_file, 'a', encoding='utf-8') as f:
                    f.write(f"[{datetime.now().strftime('%I:%M:%S %p')}] ❌ Error: {str(e)}\n")
            except:
                pass
    
    threading.Thread(target=deploy_thread, daemon=True).start()
    return jsonify({'status': 'success', 'msg': 'Deployment started!'})

@app.route('/api/github/logs/<server_id>')
def api_github_logs(server_id):
    if not require_server_access(server_id):
        return jsonify({'error': 'Unauthorized'}), 403
    log_file = os.path.join(get_server_dir(server_id), 'github_deploy.log')
    if os.path.exists(log_file):
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                logs = f.read()
        except:
            logs = "> Ready for deployment..."
    else:
        logs = "> Ready for deployment..."
    return jsonify({'logs': logs})

@app.route('/api/github/clear_logs/<server_id>', methods=['POST'])
def api_github_clear_logs(server_id):
    if not require_server_access(server_id):
        return jsonify({'error': 'Unauthorized'}), 403
    log_file = os.path.join(get_server_dir(server_id), 'github_deploy.log')
    try:
        if os.path.exists(log_file):
            os.remove(log_file)
        return jsonify({'status': 'success'})
    except:
        return jsonify({'status': 'error'}), 500

# ============================================
# ফাইল API
# ============================================

@app.route('/api/files/<server_id>')
def api_files(server_id):
    if not require_server_access(server_id):
        return jsonify({'error': 'Unauthorized'}), 403
    folder = request.args.get('folder', '')
    server_dir = safe_join_server(server_id, folder)
    if not server_dir or not os.path.isdir(server_dir): return jsonify({'files': []})
    
    files = []
    try:
        for item in os.listdir(server_dir):
            item_path = os.path.join(server_dir, item)
            files.append({'name': item, 'is_dir': os.path.isdir(item_path), 'size': os.path.getsize(item_path) if os.path.isfile(item_path) else 0, 'modified': datetime.fromtimestamp(os.path.getmtime(item_path)).strftime('%Y-%m-%d %H:%M')})
    except: pass
    return jsonify({'files': files})

@app.route('/api/file/<server_id>', methods=['GET'])
def api_get_file(server_id):
    if not require_server_access(server_id):
        return jsonify({'error': 'Unauthorized'}), 403
    filename = request.args.get('filename', '')
    filepath = safe_join_server(server_id, filename)
    if filepath and os.path.isfile(filepath):
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f: return jsonify({'content': f.read()})
    return jsonify({'error': 'Not found'}), 404

@app.route('/api/file/<server_id>', methods=['POST'])
def api_save_file(server_id):
    if not require_server_access(server_id):
        return jsonify({'error': 'Unauthorized'}), 403
    data = request.get_json()
    filepath = safe_join_server(server_id, data.get('filename', ''))
    if not filepath or os.path.isdir(filepath): return jsonify({'error': 'Invalid path'}), 400
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f: f.write(data.get('content', ''))
    return jsonify({'success': True})

@app.route('/api/file/<server_id>', methods=['DELETE'])
def api_delete_file(server_id):
    if not require_server_access(server_id):
        return jsonify({'error': 'Unauthorized'}), 403
    data = request.get_json()
    filepath = safe_join_server(server_id, data.get('filename', ''))
    if filepath and filepath != os.path.realpath(get_server_dir(server_id)) and os.path.exists(filepath):
        if os.path.isdir(filepath): shutil.rmtree(filepath)
        else: os.remove(filepath)
    return jsonify({'success': True})

@app.route('/api/upload/<server_id>', methods=['POST'])
def api_upload(server_id):
    if not require_server_access(server_id):
        return jsonify({'error': 'Unauthorized'}), 403
    if 'file' not in request.files: return jsonify({'error': 'No file'}), 400
    folder = request.form.get('folder', '')
    file = request.files['file']
    target = safe_join_server(server_id, folder, file.filename)
    if not target or os.path.isdir(target): return jsonify({'error': 'Invalid path'}), 400
    os.makedirs(os.path.dirname(target), exist_ok=True)
    file.save(target)
    return jsonify({'success': True})

@app.route('/api/create_folder/<server_id>', methods=['POST'])
def api_create_folder(server_id):
    if not require_server_access(server_id):
        return jsonify({'error': 'Unauthorized'}), 403
    data = request.get_json()
    _t = safe_join_server(server_id, data.get('foldername', ''))
    if not _t: return jsonify({'error': 'Invalid path'}), 400
    os.makedirs(_t, exist_ok=True)
    return jsonify({'success': True})

@app.route('/api/rename/<server_id>', methods=['POST'])
def api_rename(server_id):
    if not require_server_access(server_id):
        return jsonify({'error': 'Unauthorized'}), 403
    d = request.get_json()
    old_path = safe_join_server(server_id, d.get('old_name', ''))
    new_path = safe_join_server(server_id, d.get('new_name', ''))
    if old_path and new_path and os.path.exists(old_path):
        os.rename(old_path, new_path)
        return jsonify({'success': True})
    return jsonify({'error': 'Not found'}), 404

@app.route('/api/unzip/<server_id>', methods=['POST'])
def api_unzip(server_id):
    if not require_server_access(server_id):
        return jsonify({'error': 'Unauthorized'}), 403
    data = request.get_json()
    zip_path = safe_join_server(server_id, data.get('filename', ''))
    if zip_path and os.path.exists(zip_path) and zip_path.endswith('.zip'):
        try:
            safe_extract_zip(zip_path, os.path.dirname(zip_path))
            return jsonify({'status': 'success', 'msg': 'Extracted!'})
        except Exception as e: return jsonify({'status': 'error', 'msg': str(e)})
    return jsonify({'status': 'error', 'msg': 'Invalid zip'}), 400

@app.route('/api/get_startup/<server_id>')
def api_get_startup(server_id):
    if not require_server_access(server_id):
        return jsonify({'error': 'Unauthorized'}), 403
    server, _ = get_server_by_id(server_id)
    if server: return jsonify({'main_file': server.get('main_file', 'main.py'), 'requirements_file': server.get('requirements_file', 'requirements.txt')})
    return jsonify({'main_file': 'main.py', 'requirements_file': 'requirements.txt'})

@app.route('/api/set_startup/<server_id>', methods=['POST'])
def api_set_startup(server_id):
    if not require_server_access(server_id):
        return jsonify({'error': 'Unauthorized'}), 403
    d = request.get_json() or {}
    if not safe_join_server(server_id, d.get('main_file') or 'main.py') or (d.get('requirements_file') and not safe_join_server(server_id, d.get('requirements_file'))):
        return jsonify({'error': 'Invalid file path'}), 400
    users = load_users()
    for uname, udata in users.items():
        if uname == 'admin': continue
        servers = udata.get('servers', [])
        if not isinstance(servers, list): continue
        for s in servers:
            if isinstance(s, dict) and s.get('server_id') == server_id:
                s['main_file'] = d.get('main_file', 'main.py')
                s['requirements_file'] = d.get('requirements_file')
                save_users(users)
                return jsonify({'success': True})
    return jsonify({'error': 'Not found'}), 404

# ============================================
# স্টার্ট
# ============================================


# ============================================
# AD + DEPLOY SITE + OAUTH
# ============================================

@app.route('/api/ad')
def api_ad():
    return jsonify(load_ad())

@app.route('/admin/set_ad', methods=['POST'])
def admin_set_ad():
    if 'user' not in session or session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    data = request.get_json() or {}
    save_ad(data.get('text', ''), data.get('active', False))
    return jsonify({'success': True})

@app.route('/api/deploy_site/<server_id>', methods=['POST'])
def api_deploy_site(server_id):
    """Upload a whole site/project (files, folders or ZIP). Extracts, finds the main file, installs, runs."""
    if not require_server_access(server_id):
        return jsonify({'error': 'Unauthorized'}), 403
    files = request.files.getlist('files') or request.files.getlist('file')
    if not files:
        return jsonify({'success': False, 'error': 'No files were uploaded'})
    server_dir = get_server_dir(server_id)
    log_file = os.path.join(server_dir, 'output.log')
    def log(msg):
        try:
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")
        except: pass
    # stop the running process before replacing files
    server, _ = get_server_by_id(server_id)
    if server and server.get('pid'):
        _update_server(server_id, stopped_by_user=True)
        stop_bot_process(server['pid'])
        time.sleep(1)
    log("[DEPLOY] Starting upload...")
    base = os.path.abspath(server_dir)
    count = 0
    for f in files:
        if not (f and f.filename):
            continue
        rel = f.filename.replace('\\', '/').lstrip('/')
        parts = [p for p in rel.split('/') if p and p not in ('.', '..')]
        if not parts:
            continue
        path = os.path.abspath(os.path.join(base, *parts))
        if not path.startswith(base + os.sep):
            continue
        os.makedirs(os.path.dirname(path), exist_ok=True)
        f.save(path)
        count += 1
        if len(files) <= 40:
            log(f"[DEPLOY] Uploaded: {'/'.join(parts)}")
        if parts[-1].lower().endswith('.zip') and len(parts) == 1:
            try:
                safe_extract_zip(path, server_dir)
                log(f"[DEPLOY] Extracted: {parts[-1]}")
            except Exception as e:
                log(f"[ERROR] Extract: {e}")
    wrapper = flatten_project_root(server_dir)
    if wrapper:
        log(f"[DEPLOY] Project root detected inside folder: {wrapper}")
    det = detect_project(server_dir)
    main, ptype = det['main'], det['type']
    manual = (request.form.get('main_file') or '').strip()
    if manual and os.path.isfile(os.path.join(server_dir, manual)):
        main = manual
        if main.lower().endswith(('.html', '.htm')):
            ptype = 'static'
    users = load_users()
    port = None
    public_url = request.host_url.rstrip('/') + f'/s/{server_id}/'
    for uname, data in users.items():
        if uname == 'admin': continue
        for s in data.get('servers', []) or []:
            if isinstance(s, dict) and s.get('server_id') == server_id:
                if not s.get('port'):
                    s['port'] = allocate_port(users)
                port = s['port']
                s['public_url'] = public_url
                s['main_file'] = main
                s['requirements_file'] = det['req']
                s['type'] = ptype
                s['stopped_by_user'] = False
                s['status'] = 'stopped'
                s['pid'] = None
                save_users(users)
                break
    log(f"[DEPLOY] {count} files | type={ptype} | main={main} | port={port}")
    ok, msg = start_server(server_id)
    log(f"[DEPLOY] {'AUTO-STARTED' if ok else 'START FAILED'}: {msg}")
    if ok:
        log(f"[SUCCESS] Live: {public_url}")
    return jsonify({'success': True, 'status': 'success', 'port': port, 'public_url': public_url,
                    'main_file': main, 'type': ptype, 'running': ok, 'msg': msg})

@app.route('/api/download/<server_id>')
def api_download(server_id):
    if not require_server_access(server_id):
        return jsonify({'error': 'Unauthorized'}), 403
    filename = request.args.get('filename', '')
    path = os.path.join(get_server_dir(server_id), filename)
    if os.path.isfile(path) and os.path.abspath(path).startswith(os.path.abspath(get_server_dir(server_id))):
        from flask import send_file
        return send_file(path, as_attachment=True)
    return jsonify({'error': 'Not found'}), 404

# --- Google OAuth ---
@app.route('/auth/google')
def auth_google():
    if not GOOGLE_CLIENT_ID:
        return render_template('login.html', error="Google sign-in is not enabled. Please use your username and password.", google=False, discord=bool(DISCORD_CLIENT_ID and DISCORD_CLIENT_SECRET))
    redirect_uri = (OAUTH_REDIRECT_BASE or request.host_url.rstrip('/')) + '/auth/google/callback'
    scope = 'openid email profile'
    url = (
        "https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={GOOGLE_CLIENT_ID}"
        f"&redirect_uri={_urlquote(redirect_uri, safe='')}"
        f"&response_type=code&scope={scope.replace(' ', '%20')}"
        "&access_type=online&prompt=select_account"
    )
    return redirect(url)

@app.route('/auth/google/callback')
def auth_google_callback():
    code = request.args.get('code')
    if not code or not GOOGLE_CLIENT_ID:
        _g_err = request.args.get('error')
        return render_template('login.html', error=("Google sign-in failed" + (f" ({_g_err})" if _g_err else "")))
    redirect_uri = (OAUTH_REDIRECT_BASE or request.host_url.rstrip('/')) + '/auth/google/callback'
    try:
        token_res = requests.post('https://oauth2.googleapis.com/token', data={
            'code': code,
            'client_id': GOOGLE_CLIENT_ID,
            'client_secret': GOOGLE_CLIENT_SECRET,
            'redirect_uri': redirect_uri,
            'grant_type': 'authorization_code'
        }, timeout=15)
        token_data = token_res.json()
        access = token_data.get('access_token')
        if not access:
            print(f"Google token error: {token_data}")
            return render_template('login.html', error="Could not get Google token: " + str(token_data.get('error_description') or token_data.get('error') or ''))
        info = requests.get('https://www.googleapis.com/oauth2/v2/userinfo',
                            headers={'Authorization': f'Bearer {access}'}, timeout=10).json()
        email = info.get('email', '')
        name = info.get('name', email.split('@')[0])
    except Exception as e:
        return render_template('login.html', error=f"Google error: {e}")
    # ابحث عن مستخدم مرتبط بالإيميل أو أنشئ pending
    users = load_users()
    for uname, data in users.items():
        if data.get('email') == email or uname == email.split('@')[0]:
            # إيجاد أول سيرفر
            servers = data.get('servers', [])
            if servers and isinstance(servers[0], dict):
                sid = servers[0]['server_id']
                session['user'] = uname
                session['role'] = 'user'
                session['current_server_id'] = sid
                return redirect(url_for('server_home', server_id=sid))
    # مستخدم جديد - يحتاج موافقة أدمن أو إنشاء تلقائي
    username = email.split('@')[0].replace('.', '_')[:20]
    if username in users:
        username = username + str(random.randint(10,99))
    password = generate_random_password(12)
    server_id = str(uuid.uuid4())[:8]
    create_default_files(get_server_dir(server_id))
    port = allocate_port(users)
    host = request.host.split(':')[0]
    public_url = f"http://{host}:{port}"
    new_server = {
        'server_id': server_id, 'login_url': f'/{server_id}/login',
        'dashboard_url': f'/{server_id}/home',
        'full_link': request.host_url.rstrip('/') + f'/{server_id}/home',
        'type': 'python', 'ram': '512MB', 'disk': '1GB',
        'status': 'stopped', 'pid': None,
        'created': str(datetime.now()),
        'expiry': str(datetime.now() + timedelta(days=7)),
        'main_file': 'main.py', 'requirements_file': 'requirements.txt',
        'cpu_limit': 50, 'rate_limit_exceeded': False, 'stopped_by_user': False,
        'port': port, 'public_url': public_url
    }
    users[username] = {'password': password, 'role': 'user', 'email': email, 'servers': [new_server], 'oauth': 'google'}
    save_users(users)
    send_telegram_notification(
        f"🆕 <b>تسجيل جوجل جديد</b>\n📧 {email}\n👤 {username}\n🔑 <code>{password}</code>\n🔗 /{server_id}/login"
    )
    session['user'] = username
    session['role'] = 'user'
    session['current_server_id'] = server_id
    return redirect(url_for('server_home', server_id=server_id))

# --- Discord OAuth ---
@app.route('/auth/discord')
def auth_discord():
    if not DISCORD_CLIENT_ID:
        return render_template('login.html', error="Discord sign-in is not enabled. Please use your username and password.", google=bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET), discord=False)
    redirect_uri = (OAUTH_REDIRECT_BASE or request.host_url.rstrip('/')) + '/auth/discord/callback'
    url = (
        "https://discord.com/api/oauth2/authorize"
        f"?client_id={DISCORD_CLIENT_ID}"
        f"&redirect_uri={redirect_uri}"
        "&response_type=code&scope=identify%20email"
        "&prompt=consent"
    )
    return redirect(url)

@app.route('/auth/discord/callback')
def auth_discord_callback():
    code = request.args.get('code')
    if not code or not DISCORD_CLIENT_ID:
        return render_template('login.html', error="Discord sign-in failed")
    redirect_uri = (OAUTH_REDIRECT_BASE or request.host_url.rstrip('/')) + '/auth/discord/callback'
    try:
        token_res = requests.post('https://discord.com/api/oauth2/token', data={
            'client_id': DISCORD_CLIENT_ID,
            'client_secret': DISCORD_CLIENT_SECRET,
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': redirect_uri
        }, headers={'Content-Type': 'application/x-www-form-urlencoded'}, timeout=15)
        access = token_res.json().get('access_token')
        if not access:
            return render_template('login.html', error="Discord token failed")
        info = requests.get('https://discord.com/api/users/@me',
                            headers={'Authorization': f'Bearer {access}'}, timeout=10).json()
        email = info.get('email') or f"{info.get('id')}@discord.local"
        name = info.get('username', 'discord_user')
    except Exception as e:
        return render_template('login.html', error=f"Discord error: {e}")
    users = load_users()
    for uname, data in users.items():
        if data.get('email') == email or data.get('discord_id') == info.get('id'):
            servers = data.get('servers', [])
            if servers and isinstance(servers[0], dict):
                sid = servers[0]['server_id']
                session['user'] = uname
                session['role'] = 'user'
                session['current_server_id'] = sid
                return redirect(url_for('server_home', server_id=sid))
    username = (name or 'discord')[:20].replace(' ', '_')
    if username in users:
        username = username + str(random.randint(10,99))
    password = generate_random_password(12)
    server_id = str(uuid.uuid4())[:8]
    create_default_files(get_server_dir(server_id))
    port = allocate_port(users)
    host = request.host.split(':')[0]
    public_url = f"http://{host}:{port}"
    new_server = {
        'server_id': server_id, 'login_url': f'/{server_id}/login',
        'dashboard_url': f'/{server_id}/home',
        'full_link': request.host_url.rstrip('/') + f'/{server_id}/home',
        'type': 'python', 'ram': '512MB', 'disk': '1GB',
        'status': 'stopped', 'pid': None,
        'created': str(datetime.now()),
        'expiry': str(datetime.now() + timedelta(days=7)),
        'main_file': 'main.py', 'requirements_file': 'requirements.txt',
        'cpu_limit': 50, 'rate_limit_exceeded': False, 'stopped_by_user': False,
        'port': port, 'public_url': public_url
    }
    users[username] = {
        'password': password, 'role': 'user', 'email': email,
        'discord_id': info.get('id'), 'servers': [new_server], 'oauth': 'discord'
    }
    save_users(users)
    send_telegram_notification(
        f"🆕 <b>تسجيل ديسكورد جديد</b>\n👤 {username}\n📧 {email}\n🔑 <code>{password}</code>"
    )
    session['user'] = username
    session['role'] = 'user'
    session['current_server_id'] = server_id
    return redirect(url_for('server_home', server_id=server_id))



# ============================================
# خدمة المواقع المرفوعة من داخل AMOR نفسه
# ============================================
@app.route('/s/<server_id>/', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'])
@app.route('/s/<server_id>/<path:filepath>', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'])
def serve_user_site(server_id, filepath='index.html'):
    """يفتح الموقع المنشور فقط — بدون تسريب كود بايثون أو لوجات"""
    from flask import send_from_directory, abort
    if not filepath:
        filepath = 'index.html'
    _srv, _ = get_server_by_id(server_id)
    if _srv and _srv.get('status') == 'running' and _srv.get('port') \
            and not str(_srv.get('main_file', '')).lower().endswith(('.html', '.htm')):
        _resp = proxy_to_port(server_id, _srv['port'], '' if (filepath == 'index.html' and request.path.endswith('/')) else filepath)
        if _resp is not None:
            return _resp
    if request.method != 'GET':
        abort(404)
    if '..' in filepath or filepath.startswith('/') or '\\' in filepath:
        abort(404)
    base_name = os.path.basename(filepath).lower()
    if base_name in BLOCKED_NAMES or base_name.startswith('.'):
        abort(404)
    ext = os.path.splitext(base_name)[1].lower()
    # منع تحميل السورس والكود الحساس من الرابط العام
    if ext in ('.py', '.pyc', '.pyo', '.env', '.log', '.db', '.sqlite', '.pem', '.key', '.crt'):
        abort(404)
    if ext and ext not in PUBLIC_SITE_EXTENSIONS:
        # امتداد غير معروف للمواقع العامة
        abort(404)
    target = safe_join_server(server_id, filepath)
    if not target:
        abort(404)
    if os.path.isdir(target):
        for idx in ('index.html', 'index.htm'):
            cand = os.path.join(target, idx)
            if os.path.isfile(cand):
                return send_from_directory(target, idx)
        abort(404)
    if not os.path.isfile(target):
        # افتراضي index
        if filepath in ('index.html', ''):
            for idx in ('index.html', 'index.htm'):
                cand = safe_join_server(server_id, idx)
                if cand and os.path.isfile(cand):
                    return send_from_directory(os.path.dirname(cand), idx)
        abort(404)
    return send_from_directory(os.path.dirname(target), os.path.basename(target))

# ============================================
# VPS ADMIN PANEL + CUSTOMER VPS ACCOUNTS
# ============================================
VPS_STATUSES = ['Pending', 'Active', 'Suspended', 'Cancelled']

def is_admin_session():
    return session.get('role') == 'admin' and session.get('user') in ('admin', 'AMOR')

@app.route('/vps')
def vps_page():
    cfg = vps_module.get_cfg()
    mine = []
    if session.get('user'):
        mine = [_vps_public(o) for o in load_vps_orders() if o.get('user') == session.get('user')][::-1]
    return render_template('vps.html', vps_plans=vps_module.get_plans(), vps_os=cfg['os'], vps_regions=cfg['regions'], my_orders=mine)

@app.route('/api/vps/order', methods=['POST'])
def api_vps_order():
    if not session.get('user'):
        return jsonify({'ok': False, 'error': 'Please sign in to order a VPS.'}), 401
    if not check_login_rate():
        return jsonify({'ok': False, 'error': 'Too many attempts. Please try again later.'}), 429
    d = request.get_json(silent=True) or {}
    cfg = vps_module.get_cfg()
    plan = next((p for p in vps_module.get_plans() if p['id'] == d.get('plan')), None)
    name = str(d.get('name', '')).strip()[:80]
    email = str(d.get('email', '')).strip()[:120]
    contact = str(d.get('contact', '')).strip()[:80]
    os_name = d.get('os'); region = d.get('region'); cycle = str(d.get('cycle', '1'))
    if not plan or os_name not in cfg['os'] or region not in cfg['regions'] or cycle not in cfg['cycles']:
        return jsonify({'ok': False, 'error': 'Please choose a plan, an operating system and a location.'}), 400
    if not name or '@' not in email or not contact:
        return jsonify({'ok': False, 'error': 'Please fill in your name, a valid email and a contact.'}), 400
    months = int(cycle)
    total = round(plan['price'] * months * cfg['cycles'][cycle], 2)
    order_id = 'VPS-' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    order = {'id': order_id, 'user': session.get('user') or '', 'name': name, 'email': email, 'contact': contact,
             'plan': plan['id'], 'plan_name': plan['name'], 'os': os_name, 'region': region, 'months': months,
             'total': total, 'note': str(d.get('note', ''))[:300], 'status': 'Pending', 'created': str(datetime.now()),
             'ip': '', 'ssh_user': '', 'ssh_pass': '', 'hostname': '', 'expires': ''}
    orders = load_vps_orders(); orders.append(order); save_vps_orders(orders)
    try:
        send_telegram_notification(
            f"🖥 <b>New VPS request</b>\n🆔 <code>{order_id}</code>\n📦 {plan['name']} ({plan['cpu']} vCPU / {plan['ram']} GB / {plan['disk']} GB)\n"
            f"💿 {os_name} · 📍 {region}\n⏱ {months} mo · 💵 ${total}\n👤 {name}\n📧 {email}\n📞 {contact}")
    except Exception:
        pass
    return jsonify({'ok': True, 'order_id': order_id, 'total': total})

def _vps_public(o):
    """Customer view of an order: credentials only when the service is active."""
    d = dict(o)
    if d.get('status') != 'Active':
        d['ip'] = d['ssh_user'] = d['ssh_pass'] = ''
    return d

def _vps_clean(d, order=None):
    """Validate/normalise editable fields coming from the admin panel."""
    out = {}
    if 'plan' in d:
        plan = next((p for p in vps_module.get_plans() if p['id'] == d['plan']), None)
        if not plan:
            raise ValueError('Unknown plan')
        out['plan'] = plan['id']; out['plan_name'] = plan['name']
    if 'os' in d:
        if d['os'] not in vps_module.get_cfg()['os']: raise ValueError('Unknown operating system')
        out['os'] = d['os']
    if 'region' in d:
        if d['region'] not in vps_module.get_cfg()['regions']: raise ValueError('Unknown location')
        out['region'] = d['region']
    if 'status' in d:
        if d['status'] not in VPS_STATUSES: raise ValueError('Unknown status')
        out['status'] = d['status']
    for k, n in (('name', 80), ('email', 120), ('contact', 80), ('ip', 64), ('ssh_user', 48),
                 ('ssh_pass', 80), ('note', 300), ('expires', 20), ('hostname', 64)):
        if k in d:
            out[k] = str(d[k]).strip()[:n]
    if 'months' in d:
        out['months'] = max(1, min(36, int(d['months'])))
    return out

@app.route('/api/vpsadmin/create', methods=['POST'])
def api_vpsadmin_create():
    _err = vps_module.guard()
    if _err: return _err
    d = request.get_json(silent=True) or {}
    try:
        f = _vps_clean(d)
        for req in ('plan', 'os', 'region'):
            if req not in f: raise ValueError('Missing ' + req)
        months = f.get('months', 1)
        plan = next(p for p in vps_module.get_plans() if p['id'] == f['plan'])
        customer = str(d.get('customer', '')).strip()
        if not customer:
            raise ValueError('Enter the customer username or email')
    except (ValueError, TypeError) as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    users = load_users()
    uname, udata = find_user_by_login(customer, users)
    new_login = None
    if not uname:
        # create a VPS-only customer account
        base = ''.join(c for c in customer.split('@')[0] if c.isalnum() or c in '_-')[:20] or 'client'
        uname = base if base not in users else f'{base}{random.randint(100, 999)}'
        new_login = generate_random_password(10)
        users[uname] = {'password': new_login, 'role': 'user', 'email': customer if '@' in customer else f.get('email', ''),
                        'phone': '', 'servers': [], 'vps_only': True, 'oauth': 'password'}
        save_users(users)
    cycle = str(months) if str(months) in vps_module.get_cfg()['cycles'] else '1'
    total = round(plan['price'] * months * vps_module.get_cfg()['cycles'].get(cycle, 1.0), 2)
    oid = 'VPS-' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    expires = f.get('expires') or (datetime.now() + timedelta(days=30 * months)).strftime('%Y-%m-%d')
    order = {'id': oid, 'user': uname, 'name': f.get('name', uname), 'email': f.get('email') or (users.get(uname, {}).get('email') or ''),
             'contact': f.get('contact', ''), 'plan': f['plan'], 'plan_name': f['plan_name'], 'os': f['os'], 'region': f['region'],
             'months': months, 'total': total, 'note': f.get('note', ''), 'status': f.get('status', 'Active'),
             'ip': f.get('ip', ''), 'ssh_user': f.get('ssh_user') or 'root', 'ssh_pass': f.get('ssh_pass') or generate_random_password(14),
             'hostname': f.get('hostname', ''), 'expires': expires, 'created': str(datetime.now()), 'created_by': 'admin'}
    orders = load_vps_orders(); orders.append(order); save_vps_orders(orders)
    return jsonify({'ok': True, 'order': order, 'customer': uname, 'new_login_password': new_login})

@app.route('/api/vpsadmin/update/<oid>', methods=['POST'])
def api_vpsadmin_update(oid):
    _err = vps_module.guard()
    if _err: return _err
    d = request.get_json(silent=True) or {}
    orders = load_vps_orders()
    for o in orders:
        if o.get('id') == oid:
            try:
                o.update(_vps_clean(d))
            except (ValueError, TypeError) as e:
                return jsonify({'ok': False, 'error': str(e)}), 400
            if d.get('clear_request'):
                o.pop('request', None)
            save_vps_orders(orders)
            return jsonify({'ok': True, 'order': o})
    return jsonify({'ok': False, 'error': 'Order not found'}), 404

@app.route('/api/vpsadmin/delete/<oid>', methods=['POST'])
def api_vpsadmin_delete(oid):
    _err = vps_module.guard()
    if _err: return _err
    orders = load_vps_orders()
    keep = [o for o in orders if o.get('id') != oid]
    if len(keep) == len(orders):
        return jsonify({'ok': False, 'error': 'Order not found'}), 404
    save_vps_orders(keep)
    return jsonify({'ok': True})

@app.route('/api/vps/request/<oid>', methods=['POST'])
def api_vps_request(oid):
    """Customer asks for a reboot / reinstall / cancellation of their own VPS."""
    if not session.get('user'):
        return jsonify({'ok': False, 'error': 'Please sign in'}), 401
    action = (request.get_json(silent=True) or {}).get('action')
    if action not in ('reboot', 'reinstall', 'cancel'):
        return jsonify({'ok': False, 'error': 'Invalid action'}), 400
    orders = load_vps_orders()
    for o in orders:
        if o.get('id') == oid and o.get('user') == session.get('user'):
            o['request'] = action
            save_vps_orders(orders)
            try:
                send_telegram_notification(f"🛠 <b>VPS request</b>\n🆔 <code>{oid}</code>\n👤 {o.get('user')}\n⚙️ {action}")
            except Exception:
                pass
            return jsonify({'ok': True})
    return jsonify({'ok': False, 'error': 'Not found'}), 404

@app.route('/vps/signup', methods=['GET', 'POST'])
def vps_signup():
    """Public registration for VPS customers (no hosting server is created)."""
    if request.method == 'POST':
        if not check_login_rate():
            return render_template('vps_signup.html', error='Too many attempts. Please try again later.')
        email = request.form.get('email', '').strip().lower()
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        if '@' not in email or '.' not in email.split('@')[-1]:
            return render_template('vps_signup.html', error='Invalid email address')
        if len(password) < 6:
            return render_template('vps_signup.html', error='Password must be at least 6 characters')
        username = ''.join(c for c in (username or email.split('@')[0]) if c.isalnum() or c in '_-')[:20]
        if len(username) < 3:
            return render_template('vps_signup.html', error='Username must be at least 3 characters')
        users = load_users()
        if username in users or username.lower() == 'admin':
            return render_template('vps_signup.html', error='This username is already taken')
        if any((u.get('email') or '').lower() == email for u in users.values() if isinstance(u, dict)):
            return render_template('vps_signup.html', error='This email is already registered. Please sign in.')
        users[username] = {'password': password, 'role': 'user', 'email': email, 'phone': '', 'servers': [],
                           'vps_only': True, 'oauth': 'password'}
        save_users(users)
        session['user'] = username; session['role'] = 'user'; session.pop('current_server_id', None)
        try:
            send_telegram_notification(f"👤 <b>New VPS customer</b>\n{username} · {email}")
        except Exception:
            pass
        return redirect('/vps/panel')
    return render_template('vps_signup.html', error=None)

@app.route('/vps/panel')
def vps_panel():
    if not session.get('user'):
        return redirect('/login')
    mine = [_vps_public(o) for o in load_vps_orders() if o.get('user') == session.get('user')][::-1]
    return render_template('vps_panel.html', items=mine, vps_only=bool((load_users().get(session['user']) or {}).get('vps_only')))

# ============================================
# VPS WORKSPACE: files + deploy + terminal (per active VPS)
# ============================================
import shlex

_TERM_TIMEOUT = 60
_TERM_MAX_OUT = 20000

def _ws_root(sid):
    return os.path.realpath(get_server_dir(sid))

def _ws_resolve(root, cwd, p):
    """Resolve a user path inside the workspace ('/' = workspace root). None if it escapes."""
    p = (p or '').replace('\\', '/')
    base = root if p.startswith('/') else os.path.join(root, cwd or '')
    full = os.path.realpath(os.path.join(base, p.lstrip('/')))
    if full == root or full.startswith(root + os.sep):
        return full
    return None

def _ws_vpath(root, full):
    rel = os.path.relpath(full, root)
    return '/' if rel == '.' else '/' + rel.replace(os.sep, '/')

def _term_env(root):
    env = {'PATH': os.environ.get('PATH', ''), 'HOME': root, 'LANG': 'C.UTF-8', 'PYTHONUNBUFFERED': '1',
           'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONPATH': os.path.join(root, '.pylibs'), 'PORT': '8080'}
    if os.name == 'nt':
        env['SYSTEMROOT'] = os.environ.get('SYSTEMROOT', '')
    return env

def _term_limits():
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_CPU, (_TERM_TIMEOUT, _TERM_TIMEOUT))
        resource.setrlimit(resource.RLIMIT_FSIZE, (512 * 1024 * 1024, 512 * 1024 * 1024))
    except Exception:
        pass

def _term_run(argv, cwd, root):
    try:
        kw = {'preexec_fn': _term_limits} if os.name != 'nt' else {}
        r = subprocess.run(argv, cwd=cwd, env=_term_env(root), capture_output=True, text=True,
                           timeout=_TERM_TIMEOUT, **kw)
        return (r.stdout or '') + (r.stderr or '')
    except subprocess.TimeoutExpired:
        return f'Command timed out after {_TERM_TIMEOUT}s. For long-running apps use the Run button.'
    except FileNotFoundError:
        return f'{argv[0]}: runtime is not installed on this machine'

def _fmt_size(n):
    for u in ('B', 'K', 'M', 'G'):
        if n < 1024 or u == 'G':
            return f'{n:.0f}{u}' if u == 'B' else f'{n:.1f}{u}'
        n /= 1024

def term_exec(sid, cwd_rel, line, who):
    """Restricted terminal: built-in file commands + python/pip/node/npm. No shell, no escapes."""
    root = _ws_root(sid)
    cwd = _ws_resolve(root, '', cwd_rel) or root
    if not os.path.isdir(cwd):
        cwd = root
    try:
        argv = shlex.split(line)
    except ValueError as e:
        return f'parse error: {e}', cwd
    if not argv:
        return '', cwd
    cmd, a = argv[0], argv[1:]
    R = lambda p: _ws_resolve(root, _ws_vpath(root, cwd).lstrip('/'), p)
    flags = {x for x in a if x.startswith('-') and len(x) > 1 and not x[1:].isdigit()}
    pos = [x for x in a if x not in flags]
    deny = 'Permission denied: path is outside your workspace'
    try:
        if cmd == 'help':
            return ('Built-in: ls cd pwd cat head tail mkdir touch rm cp mv echo unzip wc grep whoami uname date clear\n'
                    'Run:      python app.py | pip install pkg | pip install -r requirements.txt | node app.js | npm install\n'
                    'Tip: use the Run button for long-running apps (bots, servers).'), cwd
        if cmd == 'pwd':
            return _ws_vpath(root, cwd), cwd
        if cmd == 'cd':
            t = R(pos[0] if pos else '/')
            if t is None: return deny, cwd
            if not os.path.isdir(t): return f'cd: {pos[0]}: No such directory', cwd
            return '', t
        if cmd == 'ls':
            t = R(pos[0]) if pos else cwd
            if t is None: return deny, cwd
            if not os.path.exists(t): return f'ls: {pos[0]}: No such file or directory', cwd
            items = [t] if os.path.isfile(t) else sorted(os.listdir(t), key=str.lower)
            rows = []
            for n in items:
                fp = t if os.path.isfile(t) else os.path.join(t, n)
                if n.startswith('.') and '-a' not in flags and '-la' not in flags and '-al' not in flags:
                    continue
                nm = os.path.basename(fp) + ('/' if os.path.isdir(fp) else '')
                if '-l' in flags or '-la' in flags or '-al' in flags:
                    st = os.stat(fp)
                    rows.append(f"{_fmt_size(st.st_size):>8}  {datetime.fromtimestamp(st.st_mtime).strftime('%b %d %H:%M')}  {nm}")
                else:
                    rows.append(nm)
            return ('\n'.join(rows) if '-l' in flags or '-la' in flags or '-al' in flags else '  '.join(rows)), cwd
        if cmd in ('cat', 'head', 'tail', 'wc'):
            n = 10
            if '-n' in a:
                try:
                    n = int(a[a.index('-n') + 1]); pos = [x for x in pos if x != str(n)]
                except Exception:
                    pass
            out = []
            for pth in pos:
                t = R(pth)
                if t is None: return deny, cwd
                if not os.path.isfile(t): return f'{cmd}: {pth}: No such file', cwd
                with open(t, 'r', encoding='utf-8', errors='replace') as f:
                    txt = f.read(2_000_000)
                if cmd == 'cat': out.append(txt)
                elif cmd == 'head': out.append('\n'.join(txt.splitlines()[:n]))
                elif cmd == 'tail': out.append('\n'.join(txt.splitlines()[-n:]))
                else: out.append(f'{len(txt.splitlines())} lines  {len(txt.split())} words  {len(txt.encode())} bytes  {pth}')
            return '\n'.join(out), cwd
        if cmd == 'grep':
            if len(pos) < 2: return 'usage: grep PATTERN FILE', cwd
            t = R(pos[1])
            if t is None: return deny, cwd
            if not os.path.isfile(t): return f'grep: {pos[1]}: No such file', cwd
            with open(t, 'r', encoding='utf-8', errors='replace') as f:
                return '\n'.join(f'{i}: {l}' for i, l in enumerate(f.read(2_000_000).splitlines(), 1) if pos[0].lower() in l.lower()), cwd
        if cmd == 'mkdir':
            for pth in pos:
                t = R(pth)
                if t is None: return deny, cwd
                os.makedirs(t, exist_ok=True)
            return '', cwd
        if cmd == 'touch':
            for pth in pos:
                t = R(pth)
                if t is None: return deny, cwd
                os.makedirs(os.path.dirname(t), exist_ok=True)
                open(t, 'a').close()
            return '', cwd
        if cmd == 'rm':
            for pth in pos:
                t = R(pth)
                if t is None: return deny, cwd
                if t == root: return 'rm: refusing to remove the workspace root', cwd
                if os.path.isdir(t):
                    if not ({'-r', '-rf', '-fr', '-R'} & flags): return f'rm: {pth}: is a directory (use -r)', cwd
                    shutil.rmtree(t)
                elif os.path.exists(t): os.remove(t)
                elif '-f' not in flags and '-rf' not in flags: return f'rm: {pth}: No such file', cwd
            return '', cwd
        if cmd in ('cp', 'mv'):
            if len(pos) != 2: return f'usage: {cmd} SRC DST', cwd
            s_, d_ = R(pos[0]), R(pos[1])
            if s_ is None or d_ is None: return deny, cwd
            if not os.path.exists(s_): return f'{cmd}: {pos[0]}: No such file', cwd
            if os.path.isdir(d_): d_ = os.path.join(d_, os.path.basename(s_))
            if cmd == 'mv': shutil.move(s_, d_)
            elif os.path.isdir(s_): shutil.copytree(s_, d_)
            else: shutil.copy2(s_, d_)
            return '', cwd
        if cmd == 'echo':
            return ' '.join(a), cwd
        if cmd == 'unzip':
            t = R(pos[0]) if pos else None
            if t is None: return 'usage: unzip FILE.zip', cwd
            if not zipfile.is_zipfile(t): return f'unzip: {pos[0]}: not a zip file', cwd
            safe_extract_zip(t, os.path.dirname(t)); return 'Extracted.', cwd
        if cmd == 'whoami':
            return who, cwd
        if cmd == 'uname':
            return 'AMOR-VPS 1.0 (workspace)', cwd
        if cmd == 'date':
            return datetime.now().strftime('%a %b %d %H:%M:%S %Y'), cwd
        if cmd in ('python', 'python3', 'py'):
            if '--version' in a or '-V' in a:
                return f'Python {sys.version.split()[0]}', cwd
            if a[:2] == ['-m', 'pip']:
                return term_exec(sid, cwd_rel, 'pip ' + ' '.join(shlex.quote(x) for x in a[2:]), who)
            if not pos:
                return 'usage: python SCRIPT.py [args]', cwd
            t = R(pos[0])
            if t is None: return deny, cwd
            if not os.path.isfile(t): return f'python: can\'t open file {pos[0]}', cwd
            return _term_run([sys.executable, t] + pos[1:], cwd, root), cwd
        if cmd in ('pip', 'pip3'):
            if not pos or pos[0] not in ('install', 'list', 'show', 'freeze'):
                return 'supported: pip install PKG | pip install -r FILE | pip list', cwd
            if pos[0] == 'install':
                args = [sys.executable, '-m', 'pip', 'install', '--target', os.path.join(root, '.pylibs'),
                        '--disable-pip-version-check', '--no-input']
                rest = a[1:] if a and a[0] == 'install' else pos[1:]
                if '-r' in rest:
                    i = rest.index('-r'); t = R(rest[i + 1]) if i + 1 < len(rest) else None
                    if t is None or not os.path.isfile(t): return 'pip: requirements file not found', cwd
                    rest = rest[:i] + ['-r', t] + rest[i + 2:]
                if any(x.startswith('--target') or x.startswith('--prefix') or x.startswith('--root') for x in rest):
                    return 'pip: that option is not allowed here', cwd
                return _term_run(args + rest, cwd, root), cwd
            return _term_run([sys.executable, '-m', 'pip', pos[0], '--path', os.path.join(root, '.pylibs')], cwd, root), cwd
        if cmd in ('node', 'npm'):
            exe = shutil.which(cmd)
            if not exe: return f'{cmd}: not installed on this machine', cwd
            if cmd == 'node':
                if not pos: return 'usage: node SCRIPT.js', cwd
                t = R(pos[0])
                if t is None: return deny, cwd
                if not os.path.isfile(t): return f'node: cannot find {pos[0]}', cwd
                return _term_run([exe, t] + pos[1:], cwd, root), cwd
            if not pos or pos[0] not in ('install', 'i', 'run', 'start', 'ls', 'init'):
                return 'supported: npm install | npm run NAME | npm start | npm init -y', cwd
            return _term_run([exe] + a, cwd, root), cwd
    except Exception as e:
        return f'{cmd}: {e}', cwd
    return f'{cmd}: command not found. Type help.', cwd

def ensure_vps_workspace(order, base_url):
    """Each active VPS gets a private workspace (a managed server record with kind=vps)."""
    users = load_users()
    uname = order.get('user')
    ud = users.get(uname)
    if not ud:
        return None
    servers = ud.setdefault('servers', [])
    sid = order.get('workspace')
    if sid and any(isinstance(s, dict) and s.get('server_id') == sid for s in servers):
        return sid
    sid = 'v' + uuid.uuid4().hex[:7]
    create_default_files(get_server_dir(sid))
    servers.append({
        'server_id': sid, 'kind': 'vps', 'vps_id': order['id'], 'type': 'python',
        'ram': f"{order.get('ram', 1)}GB", 'disk': f"{order.get('disk', 10)}GB",
        'status': 'stopped', 'pid': None, 'created': str(datetime.now()), 'expiry': '',
        'main_file': 'main.py', 'requirements_file': 'requirements.txt', 'cpu_limit': 80,
        'rate_limit_exceeded': False, 'stopped_by_user': False, 'port': allocate_port(users),
        'public_url': base_url.rstrip('/') + f'/s/{sid}/'})
    save_users(users)
    orders = load_vps_orders()
    for o in orders:
        if o.get('id') == order['id']:
            o['workspace'] = sid
    save_vps_orders(orders)
    order['workspace'] = sid
    return sid

def _vps_order_for(oid):
    if not session.get('user') or session.get('role') != 'user':
        return None
    o = next((x for x in load_vps_orders() if x.get('id') == oid), None)
    if not o or o.get('user') != session['user'] or o.get('status') != 'Active':
        return None
    return o

@app.route('/vps/workspace/<oid>')
def vps_workspace(oid):
    if not session.get('user'):
        return redirect('/login')
    o = _vps_order_for(oid)
    if not o:
        return redirect('/vps/panel')
    sid = ensure_vps_workspace(o, request.host_url)
    if not sid:
        return redirect('/vps/panel')
    session['current_server_id'] = sid
    return render_template('vps_workspace.html', o=_vps_public(o), sid=sid, username=session['user'])

@app.route('/api/vps/<oid>/term', methods=['POST'])
def api_vps_term(oid):
    o = _vps_order_for(oid)
    if not o or not o.get('workspace'):
        return jsonify({'ok': False, 'out': 'Unauthorized'}), 403
    d = request.get_json(silent=True) or {}
    line = str(d.get('cmd', ''))[:600]
    out, cwd = term_exec(o['workspace'], str(d.get('cwd', '')), line, session['user'])
    root = _ws_root(o['workspace'])
    if len(out) > _TERM_MAX_OUT:
        out = out[:_TERM_MAX_OUT] + '\n… output truncated'
    return jsonify({'ok': True, 'out': out, 'cwd': _ws_vpath(root, cwd)})

_VPS_LOGIN_SEEN = {}

def notify_vps_login(uname, udata):
    """Telegram alert to the owner when a VPS customer signs in (username/email/IP only, never the password)."""
    has_vps = udata.get('vps_only') or any(o.get('user') == uname for o in load_vps_orders())
    if not has_vps:
        return
    now = time.time()
    if now - _VPS_LOGIN_SEEN.get(uname, 0) < 600:
        return
    _VPS_LOGIN_SEEN[uname] = now
    ip = (request.headers.get('X-Forwarded-For', request.remote_addr or '?')).split(',')[0].strip()
    try:
        send_telegram_notification(f"🔐 <b>VPS customer login</b>\n👤 {uname}\n📧 {udata.get('email') or '—'}\n🌐 {ip}\n🕒 {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    except Exception:
        pass


# ============================================
# ASSISTANT (any OpenAI-compatible chat API, configured via environment)
# ============================================
AI_API_URL = (os.environ.get('AI_API_URL') or '').rstrip('/')   # e.g. https://api.openai.com/v1
AI_API_KEY = os.environ.get('AI_API_KEY', '')
AI_MODEL = os.environ.get('AI_MODEL', 'gpt-4o-mini')
AI_DAILY_LIMIT = int(os.environ.get('AI_DAILY_LIMIT', '30'))
AI_USAGE_FILE = 'assistant_usage.json'
AI_SYSTEM = ("You are the built-in technical assistant of AMOR HOSTING. Help customers deploy websites and bots, "
             "configure Linux VPS servers, fix errors in their code and logs. Be concise and practical, use short "
             "code blocks when useful, and answer in the same language as the user.")

def _ai_usage_take(user, limit):
    today = datetime.now().strftime('%Y-%m-%d')
    try:
        with open(AI_USAGE_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        data = {}
    rec = data.get(user) or {}
    if rec.get('day') != today:
        rec = {'day': today, 'n': 0}
    if limit and rec['n'] >= limit:
        return False, 0
    rec['n'] += 1
    data[user] = rec
    with open(AI_USAGE_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f)
    return True, max(0, limit - rec['n']) if limit else -1

@app.route('/assistant')
def assistant_page():
    if not session.get('user'):
        return redirect(url_for('login'))
    return render_template('assistant.html', configured=bool(AI_API_URL and AI_API_KEY), limit=AI_DAILY_LIMIT)

@app.route('/api/assistant/chat', methods=['POST'])
def api_assistant_chat():
    if not session.get('user'):
        return jsonify({'ok': False, 'error': 'Please sign in'}), 401
    if not (AI_API_URL and AI_API_KEY):
        return jsonify({'ok': False, 'error': 'The assistant is not configured yet.'}), 503
    d = request.get_json(silent=True) or {}
    msgs = []
    for m in (d.get('messages') or [])[-12:]:
        if isinstance(m, dict) and m.get('role') in ('user', 'assistant') and isinstance(m.get('content'), str):
            msgs.append({'role': m['role'], 'content': m['content'][:4000]})
    if not msgs or msgs[-1]['role'] != 'user':
        return jsonify({'ok': False, 'error': 'Empty message'}), 400
    limit = 0 if is_admin_session() else AI_DAILY_LIMIT
    ok, left = _ai_usage_take(session['user'], limit)
    if not ok:
        return jsonify({'ok': False, 'error': 'Daily limit reached. Come back tomorrow.'}), 429
    try:
        r = requests.post(f'{AI_API_URL}/chat/completions', timeout=90,
                          headers={'Authorization': f'Bearer {AI_API_KEY}', 'Content-Type': 'application/json'},
                          json={'model': AI_MODEL, 'max_tokens': 1200, 'messages': [{'role': 'system', 'content': AI_SYSTEM}] + msgs})
        r.raise_for_status()
        text = r.json()['choices'][0]['message']['content']
    except Exception as e:
        print(f'[assistant] error: {e}')
        return jsonify({'ok': False, 'error': 'The assistant is unavailable right now. Please try again.'}), 502
    return jsonify({'ok': True, 'reply': text, 'left': left})

_TG_POLLING_STARTED = False

def telegram_polling_loop():
    """بوت تيليجرام بـ long-polling: يشتغل على localhost بدون دومين/webhook."""
    base = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
    try:
        requests.post(base + "/deleteWebhook", json={"drop_pending_updates": False}, timeout=15)
    except Exception as e:
        print(f"[BOT] deleteWebhook error: {e}")
    try:
        me = requests.get(base + "/getMe", timeout=15).json()
        if me.get('ok'):
            print(f"[BOT] ✅ @{me['result'].get('username')} شغال (polling)")
        else:
            print(f"[BOT] ❌ التوكن غير صالح: {me}")
    except Exception as e:
        print(f"[BOT] getMe error: {e}")
    client = app.test_client()
    offset = None
    while True:
        try:
            params = {"timeout": 30, "allowed_updates": json.dumps(["message"])}
            if offset is not None:
                params["offset"] = offset
            j = requests.get(base + "/getUpdates", params=params, timeout=45).json()
            if not j.get('ok'):
                print(f"[BOT] getUpdates error: {j}")
                time.sleep(10)
                continue
            for upd in j.get('result', []):
                offset = upd['update_id'] + 1
                try:
                    client.post('/telegram/webhook', json=upd,
                                headers={'X-Telegram-Bot-Api-Secret-Token': TELEGRAM_WEBHOOK_SECRET})
                except Exception as e:
                    print(f"[BOT] handler error: {e}")
        except Exception as e:
            print(f"[BOT] polling error: {e}")
            time.sleep(5)

def start_telegram_polling():
    global _TG_POLLING_STARTED
    if _TG_POLLING_STARTED or not TELEGRAM_POLLING or not TELEGRAM_BOT_TOKEN:
        return
    _TG_POLLING_STARTED = True
    threading.Thread(target=telegram_polling_loop, daemon=True).start()

def _host_admin_ok(u, p):
    return u in ('AMOR', 'admin') and bool(p) and p == load_users().get('admin', {}).get('password', '')

vps_module.init(app, notify=send_telegram_notification, rate=check_login_rate,
                load_users=load_users, save_users=save_users, host_admin_ok=_host_admin_ok)
assistant.init(app, vps_module.get_plans, vps_module.get_cfg)

if __name__ == '__main__':
    _PORT = int(os.environ.get("PORT") or os.environ.get("SERVER_PORT") or 26160)
    print("\n" + "=" * 50)
    print("🚀 AMOR HOSTING - FINAL (SECURE ADMIN TELEGRAM BOT)")
    print("=" * 50)
    print(f"📍 Landing: http://localhost:{_PORT}")
    print(f"📍 Admin: http://localhost:{_PORT}/login")
    print(f"🔗 API: http://localhost:{_PORT}/api/create")
    print("👤 Admin login: AMOR / (password in users.json)")
    print("=" * 50 + "\n")
    start_telegram_polling()
    app.run(debug=False, host='0.0.0.0', port=26160)
