import os, json, sqlite3, secrets
from flask import Flask, request, jsonify, session, send_from_directory, g

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'data', 'tp_report.db')
SEED_PATH = os.path.join(BASE_DIR, 'seed_data.json')
APP_PASSWORD = os.environ.get('TP_PASSWORD', 'TP26!')

os.makedirs(os.path.join(BASE_DIR, 'data'), exist_ok=True)

app = Flask(__name__, static_folder='static', template_folder='templates')
app.secret_key = os.environ.get('TP_SECRET_KEY', secrets.token_hex(32))

DATA_COLUMNS = ["year","week","total_in_work","avail_total","rushydro_hours","transneft_hours",
"roscosmos_hours","bryansk_hours","mchs_hours","internal_sales_hours","new_received","renewed",
"ratio_solved_received","altos_rusg_email","altos_rusg_tf","altos_other_email","altos_other_tf",
"altoffice_rusg_email","altoffice_rusg_tf","altoffice_other_email","altoffice_other_tf",
"projserver_taken","total_solved_week","altos_avg_time","altos_total","altos_1_2line","altos_3line",
"altoffice_avg_time","altoffice_total","altoffice_1_2line","altoffice_3line","projserver_solved",
"altos_avail_total","altos_avail_1_3","altos_avail_4_7","altos_avail_8_10","altoffice_avail_total",
"altoffice_avail_1_3","altoffice_avail_4_7","altoffice_avail_8_10","projserver_avail","extra","period"]

DEFAULT_TRAFFIC_RULES = {
  "total_in_work":{"direction":"less","green":180,"yellow":220,"enabled":True},
  "avail_total":{"direction":"less","green":350,"yellow":420,"enabled":True},
  "new_received":{"direction":"less","green":25,"yellow":35,"enabled":False},
  "total_solved_week":{"direction":"more","green":25,"yellow":18,"enabled":True},
  "ratio_solved_received":{"direction":"more","green":1,"yellow":0.8,"enabled":True},
  "altos_avg_time":{"direction":"less","green":24,"yellow":48,"enabled":True},
  "altoffice_avg_time":{"direction":"less","green":36,"yellow":72,"enabled":True},
  "altos_avail_total":{"direction":"more","green":90,"yellow":70,"enabled":False},
  "altoffice_avail_total":{"direction":"more","green":110,"yellow":90,"enabled":False}
}

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(exc):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    first_run = not os.path.exists(DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    cols_sql = ", ".join(f'"{c}" REAL' if c not in ('period',) else f'"{c}" TEXT' for c in DATA_COLUMNS)
    conn.execute(f'CREATE TABLE IF NOT EXISTS report_rows (id INTEGER PRIMARY KEY AUTOINCREMENT, {cols_sql})')
    conn.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)')
    conn.commit()
    if first_run:
        cur = conn.execute('SELECT COUNT(*) FROM report_rows')
        if cur.fetchone()[0] == 0 and os.path.exists(SEED_PATH):
            with open(SEED_PATH, encoding='utf-8') as f:
                seed = json.load(f)
            placeholders = ",".join(["?"] * len(DATA_COLUMNS))
            col_names = ",".join(f'"{c}"' for c in DATA_COLUMNS)
            for row in seed:
                vals = [row.get(c) for c in DATA_COLUMNS]
                conn.execute(f'INSERT INTO report_rows ({col_names}) VALUES ({placeholders})', vals)
            conn.commit()
        defaults = {
            'traffic_rules': DEFAULT_TRAFFIC_RULES,
            'block_settings': {},
            'color_palette': {}
        }
        for k, v in defaults.items():
            conn.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', (k, json.dumps(v)))
        conn.commit()
    conn.close()

init_db()

def row_to_dict(row):
    d = {c: row[c] for c in DATA_COLUMNS}
    d['id'] = row['id']
    return d

def require_auth():
    if not session.get('authorized'):
        return jsonify({'error': 'unauthorized'}), 401
    return None

@app.route('/')
def index():
    return send_from_directory(app.template_folder, 'index.html')

@app.route('/api/auth/login', methods=['POST'])
def login():
    body = request.get_json(silent=True) or {}
    if body.get('password') == APP_PASSWORD:
        session['authorized'] = True
        return jsonify({'ok': True})
    return jsonify({'ok': False, 'error': 'Неверный пароль'}), 401

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    session.pop('authorized', None)
    return jsonify({'ok': True})

@app.route('/api/auth/status')
def auth_status():
    return jsonify({'authorized': bool(session.get('authorized'))})

@app.route('/api/rows', methods=['GET'])
def get_rows():
    db = get_db()
    rows = db.execute('SELECT * FROM report_rows ORDER BY year, week').fetchall()
    return jsonify([row_to_dict(r) for r in rows])

@app.route('/api/rows', methods=['POST'])
def create_row():
    err = require_auth()
    if err: return err
    body = request.get_json(silent=True) or {}
    db = get_db()
    col_names = ",".join(f'"{c}"' for c in DATA_COLUMNS)
    placeholders = ",".join(["?"] * len(DATA_COLUMNS))
    vals = [body.get(c) for c in DATA_COLUMNS]
    cur = db.execute(f'INSERT INTO report_rows ({col_names}) VALUES ({placeholders})', vals)
    db.commit()
    row = db.execute('SELECT * FROM report_rows WHERE id=?', (cur.lastrowid,)).fetchone()
    return jsonify(row_to_dict(row)), 201

@app.route('/api/rows/<int:row_id>', methods=['PUT'])
def update_row(row_id):
    err = require_auth()
    if err: return err
    body = request.get_json(silent=True) or {}
    db = get_db()
    set_clause = ", ".join(f'"{c}"=?' for c in DATA_COLUMNS)
    vals = [body.get(c) for c in DATA_COLUMNS] + [row_id]
    db.execute(f'UPDATE report_rows SET {set_clause} WHERE id=?', vals)
    db.commit()
    row = db.execute('SELECT * FROM report_rows WHERE id=?', (row_id,)).fetchone()
    if not row:
        return jsonify({'error': 'not found'}), 404
    return jsonify(row_to_dict(row))

@app.route('/api/rows/<int:row_id>', methods=['DELETE'])
def delete_row(row_id):
    err = require_auth()
    if err: return err
    db = get_db()
    db.execute('DELETE FROM report_rows WHERE id=?', (row_id,))
    db.commit()
    return jsonify({'ok': True})

@app.route('/api/rows/bulk_import', methods=['POST'])
def bulk_import():
    err = require_auth()
    if err: return err
    body = request.get_json(silent=True) or {}
    rows = body.get('rows', [])
    db = get_db()
    db.execute('DELETE FROM report_rows')
    col_names = ",".join(f'"{c}"' for c in DATA_COLUMNS)
    placeholders = ",".join(["?"] * len(DATA_COLUMNS))
    for row in rows:
        vals = [row.get(c) for c in DATA_COLUMNS]
        db.execute(f'INSERT INTO report_rows ({col_names}) VALUES ({placeholders})', vals)
    db.commit()
    return jsonify({'ok': True, 'count': len(rows)})

def get_setting(key, default=None):
    db = get_db()
    row = db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
    if row:
        return json.loads(row['value'])
    return default

def set_setting(key, value):
    db = get_db()
    db.execute('INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, json.dumps(value)))
    db.commit()

@app.route('/api/settings/traffic_rules', methods=['GET'])
def get_traffic_rules():
    return jsonify({**DEFAULT_TRAFFIC_RULES, **get_setting('traffic_rules', {})})

@app.route('/api/settings/traffic_rules', methods=['PUT'])
def put_traffic_rules():
    err = require_auth()
    if err: return err
    body = request.get_json(silent=True) or {}
    set_setting('traffic_rules', body)
    return jsonify({'ok': True})

@app.route('/api/settings/block_settings', methods=['GET'])
def get_block_settings():
    return jsonify(get_setting('block_settings', {}))

@app.route('/api/settings/block_settings', methods=['PUT'])
def put_block_settings():
    err = require_auth()
    if err: return err
    body = request.get_json(silent=True) or {}
    set_setting('block_settings', body)
    return jsonify({'ok': True})

@app.route('/api/settings/color_palette', methods=['GET'])
def get_color_palette():
    return jsonify(get_setting('color_palette', {}))

@app.route('/api/settings/color_palette', methods=['PUT'])
def put_color_palette():
    err = require_auth()
    if err: return err
    body = request.get_json(silent=True) or {}
    set_setting('color_palette', body)
    return jsonify({'ok': True})

@app.route('/api/settings/color_palette', methods=['DELETE'])
def reset_color_palette():
    err = require_auth()
    if err: return err
    set_setting('color_palette', {})
    return jsonify({'ok': True})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=39664, debug=False)
