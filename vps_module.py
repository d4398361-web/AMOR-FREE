"""VPS extension: editable plans/settings, a separate VPS-only admin login + panel, customer management.
Works on top of the existing data model (users.json with `vps_only` customers, vps_orders.json orders)."""
import json, os, re, secrets, string, threading
from functools import wraps

from flask import jsonify, redirect, render_template, request, session
from werkzeug.security import check_password_hash, generate_password_hash

LOCK = threading.RLock()
F_ORDERS, F_PLANS, F_CFG, F_ADMIN = 'vps_orders.json', 'vps_plans.json', 'vps_config.json', 'vps_admin.json'
STATUSES = ['Pending', 'Active', 'Suspended', 'Cancelled']

DEFAULT_PLANS = [
    {'id': 'nova',   'name': 'Nova',   'price': 5,  'cpu': 1, 'ram': 2,  'disk': 40,  'bw': '2 TB',  'hot': False, 'enabled': True},
    {'id': 'quasar', 'name': 'Quasar', 'price': 12, 'cpu': 2, 'ram': 4,  'disk': 80,  'bw': '5 TB',  'hot': True,  'enabled': True},
    {'id': 'pulsar', 'name': 'Pulsar', 'price': 24, 'cpu': 4, 'ram': 8,  'disk': 160, 'bw': '10 TB', 'hot': False, 'enabled': True},
    {'id': 'nebula', 'name': 'Nebula', 'price': 48, 'cpu': 8, 'ram': 16, 'disk': 320, 'bw': 'Unmetered', 'hot': False, 'enabled': True},
]
DEFAULT_CFG = {
    'os': ['Ubuntu 24.04', 'Ubuntu 22.04', 'Debian 12', 'CentOS Stream 9', 'Windows Server'],
    'regions': ['Frankfurt', 'Amsterdam', 'London', 'New York', 'Singapore', 'Dubai'],
    'cycles': {'1': 1.0, '3': 0.95, '12': 0.85},
    'support_email': 'support@example.com',
}


def _load(path, default):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default


def _save(path, data):
    tmp = path + '.tmp'
    with LOCK:
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)


def load_orders():
    return _load(F_ORDERS, [])


def save_orders(orders):
    _save(F_ORDERS, orders)


def get_plans(include_disabled=False):
    plans = _load(F_PLANS, None)
    if not isinstance(plans, list) or not plans:
        plans = DEFAULT_PLANS
    return [p for p in plans if include_disabled or p.get('enabled', True)]


def get_cfg():
    cfg = json.loads(json.dumps(DEFAULT_CFG))
    cfg.update(_load(F_CFG, {}) or {})
    return cfg


def _admin_init():
    data = _load(F_ADMIN, None)
    if isinstance(data, dict) and data.get('hash'):
        return
    user = os.environ.get('VPS_ADMIN_USER', 'vpsadmin')
    pw = os.environ.get('VPS_ADMIN_PASS') or ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(14))
    _save(F_ADMIN, {'user': user, 'hash': generate_password_hash(pw)})
    print('\n' + '=' * 56 + f'\n  VPS ADMIN PANEL  ->  /vps-admin\n  username: {user}\n  password: {pw}\n  (shown once - you can change it inside the panel)\n' + '=' * 56 + '\n')


def is_vps_admin():
    """VPS admin (own credentials) or the hosting owner."""
    return bool(session.get('vps_admin')) or (session.get('role') == 'admin' and session.get('user') in ('admin', 'AMOR'))


def guard():
    """Returns an error response, or None when the request is an authorised admin request."""
    if not is_vps_admin():
        return jsonify({'ok': False, 'error': 'Unauthorized'}), 403
    if request.method != 'GET':
        if not session.get('vps_csrf') or request.headers.get('X-CSRF') != session.get('vps_csrf'):
            return jsonify({'ok': False, 'error': 'Session expired - reload the page.'}), 403
    return None


def init(app, notify, rate, load_users, save_users, host_admin_ok):
    _admin_init()

    def admin_required(fn):
        @wraps(fn)
        def wrap(*a, **k):
            err = guard()
            return err if err else fn(*a, **k)
        return wrap

    @app.route('/vps-admin')
    def vps_admin():
        if not is_vps_admin():
            return render_template('vps_admin_login.html', error=None)
        session.setdefault('vps_csrf', secrets.token_hex(16))
        return render_template('vps_admin.html', csrf=session['vps_csrf'], who=session.get('user') if session.get('role') == 'admin' else 'VPS admin')

    @app.route('/vps-admin/login', methods=['POST'])
    def vps_admin_login():
        if not rate():
            return render_template('vps_admin_login.html', error='Too many attempts. Try again later.')
        u, p = request.form.get('username', '').strip(), request.form.get('password', '')
        adm = _load(F_ADMIN, {})
        ok = u == adm.get('user') and check_password_hash(adm.get('hash', ''), p)
        if ok:
            session['vps_admin'] = True
        elif host_admin_ok(u, p):
            session['user'], session['role'] = 'admin', 'admin'
        else:
            return render_template('vps_admin_login.html', error='Incorrect username or password.')
        session['vps_csrf'] = secrets.token_hex(16)
        return redirect('/vps-admin')

    @app.route('/vps-admin/logout')
    def vps_admin_logout():
        session.pop('vps_admin', None); session.pop('vps_csrf', None)
        return redirect('/vps-admin')

    @app.route('/vps-admin/api/state')
    @admin_required
    def vps_admin_state():
        orders, users = load_orders(), load_users()
        counts = {s: sum(1 for o in orders if o.get('status') == s) for s in STATUSES}
        mrr = round(sum(float(o.get('total', 0)) / max(1, int(o.get('months', 1))) for o in orders if o.get('status') == 'Active'), 2)
        owners = {o.get('user') for o in orders}
        customers = [{'username': n, 'email': d.get('email', ''), 'vps_only': bool(d.get('vps_only')), 'suspended': bool(d.get('suspended')),
                      'orders': sum(1 for o in orders if o.get('user') == n)}
                     for n, d in users.items() if n != 'admin' and (d.get('vps_only') or n in owners)]
        return jsonify({'ok': True, 'orders': orders[::-1], 'customers': customers, 'plans': get_plans(True), 'cfg': get_cfg(),
                        'stats': {'counts': counts, 'mrr': mrr, 'customers': len(customers), 'orders': len(orders)}})

    @app.route('/vps-admin/api/customer', methods=['POST'])
    @admin_required
    def vps_admin_customer():
        d = request.get_json(silent=True) or {}
        name, action = str(d.get('username', '')), d.get('action')
        users = load_users()
        u = users.get(name)
        if not u or name == 'admin':
            return jsonify({'ok': False, 'error': 'Customer not found'}), 404
        if action == 'toggle':
            u['suspended'] = not u.get('suspended', False)
        elif action == 'reset':
            temp = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(10))
            u['password'] = temp
            save_users(users)
            return jsonify({'ok': True, 'password': temp})
        elif action == 'delete':
            if any(o.get('user') == name and o.get('status') == 'Active' for o in load_orders()):
                return jsonify({'ok': False, 'error': 'This customer still has an active VPS.'}), 400
            if u.get('servers'):
                return jsonify({'ok': False, 'error': 'This account also owns a hosting server - delete it from the hosting admin.'}), 400
            users.pop(name)
        else:
            return jsonify({'ok': False, 'error': 'Unknown action'}), 400
        save_users(users)
        return jsonify({'ok': True})

    @app.route('/vps-admin/api/plans', methods=['POST'])
    @admin_required
    def vps_admin_plans():
        raw = (request.get_json(silent=True) or {}).get('plans')
        if not isinstance(raw, list) or not raw:
            return jsonify({'ok': False, 'error': 'Plans list is empty'}), 400
        out, seen = [], set()
        try:
            for p in raw:
                pid = re.sub(r'[^a-z0-9-]', '', str(p.get('id', '')).lower())[:20]
                if len(pid) < 2 or pid in seen:
                    return jsonify({'ok': False, 'error': 'Each plan needs a unique id (2+ letters/numbers).'}), 400
                seen.add(pid)
                out.append({'id': pid, 'name': str(p.get('name', pid))[:24] or pid, 'price': round(max(0.5, float(p['price'])), 2),
                            'cpu': max(1, int(p['cpu'])), 'ram': max(1, int(p['ram'])), 'disk': max(5, int(p['disk'])),
                            'bw': str(p.get('bw', ''))[:16], 'hot': bool(p.get('hot')), 'enabled': bool(p.get('enabled', True))})
        except (KeyError, ValueError, TypeError):
            return jsonify({'ok': False, 'error': 'Please check the numbers in your plans.'}), 400
        if not any(p['enabled'] for p in out):
            return jsonify({'ok': False, 'error': 'At least one plan must stay enabled.'}), 400
        _save(F_PLANS, out)
        return jsonify({'ok': True, 'plans': out})

    @app.route('/vps-admin/api/settings', methods=['POST'])
    @admin_required
    def vps_admin_settings():
        d = request.get_json(silent=True) or {}
        clean = lambda lst: [str(x).strip()[:40] for x in (lst or []) if str(x).strip()][:20]
        os_l, reg = clean(d.get('os')), clean(d.get('regions'))
        if not os_l or not reg:
            return jsonify({'ok': False, 'error': 'Add at least one OS and one location.'}), 400
        cfg = get_cfg()
        cfg.update({'os': os_l, 'regions': reg, 'support_email': str(d.get('support_email', cfg['support_email']))[:80]})
        _save(F_CFG, cfg)
        return jsonify({'ok': True})

    @app.route('/vps-admin/api/password', methods=['POST'])
    @admin_required
    def vps_admin_password():
        d = request.get_json(silent=True) or {}
        adm = _load(F_ADMIN, {})
        if not check_password_hash(adm.get('hash', ''), d.get('old', '')):
            return jsonify({'ok': False, 'error': 'Current password is incorrect.'}), 400
        if len(d.get('new', '')) < 8:
            return jsonify({'ok': False, 'error': 'Use at least 8 characters.'}), 400
        adm['hash'] = generate_password_hash(d['new'])
        _save(F_ADMIN, adm)
        return jsonify({'ok': True})
