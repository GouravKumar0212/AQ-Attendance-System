"""
AQ Attendance System - Flask Application Core Server
Task: Provides REST API endpoints, database ORM wrappers, authentication, attendance marking with TOTP & Geofencing, holiday scheduling, and CSV export.
"""

import os
import sqlite3
import socket
import time
import threading
import io
import csv
from datetime import timedelta
from functools import wraps
from collections import defaultdict
from flask import Flask, render_template, request, jsonify, session, send_from_directory, Response
from werkzeug.security import generate_password_hash, check_password_hash
from totp_engine import create_totp_payload, verify_totp_payload, get_seconds_remaining
from geofence import is_within_campus

try:
    from dotenv import load_dotenv
    # Explicitly load .env from script directory, current working directory, and parent directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    env_paths = [
        os.path.join(script_dir, '.env'),
        os.path.join(os.getcwd(), '.env'),
        os.path.join(os.path.dirname(script_dir), '.env'),
        os.path.join(script_dir, '.env.local')
    ]
    loaded_env = False
    for p in env_paths:
        if os.path.exists(p):
            load_dotenv(p, override=True)
            loaded_env = True
            break
    if not loaded_env:
        load_dotenv()
except ImportError:
    pass

try:
    import pg8000.dbapi
    import ssl
    HAS_PG8000 = True
except ImportError:
    HAS_PG8000 = False

try:
    import psycopg2
    import psycopg2.extras
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False

app = Flask(__name__, static_folder='static', static_url_path='/static')
app.secret_key = os.environ.get('SECRET_KEY', 'aq_college_super_secret_key_2026')

# --- ENTERPRISE SECURITY & COOKIE HARDENING ---
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = bool(os.environ.get('VERCEL') or os.environ.get('HTTPS') == 'on')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=12)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB max request size

# --- IN-MEMORY IP RATE LIMITER ---
_rate_limits = defaultdict(list)
_rate_lock = threading.Lock()

def rate_limit(max_requests=10, window_seconds=60, error_message="Too many requests. Please wait a minute and try again."):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if app.config.get('TESTING') and not app.config.get('ENABLE_RATE_LIMIT_TEST'):
                return f(*args, **kwargs)

            forwarded = request.headers.get('X-Forwarded-For')
            ip = forwarded.split(',')[0].strip() if forwarded else (request.remote_addr or '127.0.0.1')
            endpoint = request.endpoint or f.__name__
            key = f"{ip}:{endpoint}"
            now = time.time()

            with _rate_lock:
                timestamps = [t for t in _rate_limits[key] if now - t < window_seconds]
                if len(timestamps) >= max_requests:
                    retry_after = int(window_seconds - (now - timestamps[0])) + 1
                    resp = jsonify({
                        'success': False,
                        'error': error_message,
                        'message': error_message,
                        'retry_after_seconds': retry_after
                    })
                    resp.status_code = 429
                    resp.headers['Retry-After'] = str(retry_after)
                    return resp

                timestamps.append(now)
                _rate_limits[key] = timestamps

            return f(*args, **kwargs)
        return wrapped
    return decorator

# --- SAFE STATIC FILE SERVING WITH PATH TRAVERSAL SHIELD ---
SAFE_STATIC_EXTENSIONS = {
    '.css', '.js', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico',
    '.webp', '.woff', '.woff2', '.ttf', '.eot', '.json', '.map'
}

@app.before_request
def validate_static_and_security():
    """
    Task: Intercept incoming requests before dispatch. Block static path traversal and unsafe file access.
    """
    if request.path.startswith('/static/'):
        rel_path = request.path[len('/static/'):]
        if '..' in rel_path or '\\' in rel_path:
            return jsonify({'error': 'Access denied.'}), 403

        _, ext = os.path.splitext(rel_path.lower())
        if not ext or ext not in SAFE_STATIC_EXTENSIONS:
            return jsonify({'error': 'Access denied. Invalid or restricted resource extension.'}), 403

# --- ENTERPRISE OWASP SECURITY HEADERS ---
@app.after_request
def apply_security_headers(response):
    """
    Task: Enforce enterprise OWASP security headers on all HTTP responses.
    Mitigates XSS, Clickjacking, MIME-sniffing, Data Injection, and Session Sniffing.
    """
    csp = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdnjs.cloudflare.com https://unpkg.com https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com data:; "
        "img-src 'self' data: https: blob:; "
        "connect-src 'self' https://api.qrserver.com https://*.supabase.co https://*.supabase.in; "
        "frame-ancestors 'self'; "
        "base-uri 'self'; "
        "form-action 'self';"
    )
    response.headers['Content-Security-Policy'] = csp
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = 'geolocation=(self), camera=(self), microphone=(), payment=()'

    if os.environ.get('VERCEL') or os.environ.get('HTTPS') == 'on':
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains; preload'

    response.headers.pop('Server', None)
    response.headers['X-Powered-By'] = 'AQ-SecureEngine/2026'

    return response

# --- CENTRALIZED ERROR SHIELD (PREVENTS STACK TRACE & DEBUG LEAKAGE) ---
@app.errorhandler(400)
def handle_bad_request(e):
    return jsonify({'success': False, 'error': 'Bad request. Parameter validation failed.'}), 400

@app.errorhandler(401)
def handle_unauthorized(e):
    return jsonify({'success': False, 'error': 'Unauthorized. Authentication required.'}), 401

@app.errorhandler(403)
def handle_forbidden(e):
    return jsonify({'success': False, 'error': 'Forbidden. You do not have permission to access this resource.'}), 403

@app.errorhandler(404)
def handle_not_found(e):
    if request.path.startswith('/api/'):
        return jsonify({'success': False, 'error': 'API endpoint not found.'}), 404
    return render_template('index.html'), 200

@app.errorhandler(405)
def handle_method_not_allowed(e):
    return jsonify({'success': False, 'error': 'Method Not Allowed.'}), 405

@app.errorhandler(429)
def handle_rate_limit_exceeded(e):
    return jsonify({'success': False, 'error': 'Too many requests. Please slow down and try again.'}), 429

@app.errorhandler(500)
def handle_internal_server_error(e):
    app.logger.error(f"Internal Error: {e}")
    return jsonify({'success': False, 'error': 'An internal error occurred. Please try again later.'}), 500



class PgRowWrapper(dict):
    """
    Task: Dictionary subclass for PostgreSQL row tuples supporting key indexing, list indexing, and keys().
    """
    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)

    def keys(self):
        return super().keys()

class PgCursorWrapper:
    def __init__(self, cursor, conn, is_pg8000=False):
        self.cursor = cursor
        self.conn = conn
        self.is_pg8000 = is_pg8000
        self.lastrowid = None

    @property
    def description(self):
        return self.cursor.description

    @property
    def rowcount(self):
        return self.cursor.rowcount

    def execute(self, sql, params=None):
        sql_pg = sql.replace('?', '%s')
        params_tuple = tuple(params) if params is not None else ()
        self.cursor.execute(sql_pg, params_tuple)
        return self

    def fetchone(self):
        res = self.cursor.fetchone()
        if res is None:
            return None
        if self.is_pg8000 and self.cursor.description:
            cols = [col[0] for col in self.cursor.description]
            return PgRowWrapper(dict(zip(cols, res)))
        return PgRowWrapper(res)

    def fetchall(self):
        res = self.cursor.fetchall()
        if not res:
            return []
        if self.is_pg8000 and self.cursor.description:
            cols = [col[0] for col in self.cursor.description]
            return [PgRowWrapper(dict(zip(cols, row))) for row in res]
        return [PgRowWrapper(row) for row in res]

class PgConnWrapper:
    def __init__(self, conn, is_pg8000=False):
        self.raw_conn = conn
        self.is_pg = True
        self.is_pg8000 = is_pg8000

    def cursor(self):
        if self.is_pg8000:
            return PgCursorWrapper(self.raw_conn.cursor(), self, is_pg8000=True)
        return PgCursorWrapper(self.raw_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor), self, is_pg8000=False)

    def execute(self, sql, params=None):
        cur = self.cursor()
        cur.execute(sql, params)
        return cur

    def commit(self):
        self.raw_conn.commit()

    def rollback(self):
        self.raw_conn.rollback()

    def close(self):
        self.raw_conn.close()


def get_db_path():
    """
    Task: Determine appropriate SQLite database file path, handling read-only environments (Vercel /tmp) and test environments.
    """
    if os.environ.get('TEST_DB_PATH'):
        return os.environ.get('TEST_DB_PATH')
    base_dir = os.path.dirname(__file__)
    local_db = os.path.join(base_dir, 'database.db')
    
    # If running on Vercel or in a read-only environment, copy/use /tmp/database.db
    if os.environ.get('VERCEL') or not os.access(base_dir, os.W_OK):
        tmp_db = '/tmp/database.db'
        if not os.path.exists(tmp_db) and os.path.exists(local_db):
            import shutil
            try:
                shutil.copy2(local_db, tmp_db)
            except Exception as e:
                print("Note: Could not copy database to /tmp:", e)
        return tmp_db if os.path.exists('/tmp') else local_db
    return local_db

def parse_db_url_to_pg_params(db_url):
    """
    Task: Intelligently parse and format PostgreSQL / Supabase connection strings into connection parameters.
    Handles Direct Supabase IPv6 endpoints by automatically routing to IPv4 Supabase Connection Pooler.
    """
    import urllib.parse
    if not db_url:
        return None

    if db_url.startswith('postgres://'):
        db_url = db_url.replace('postgres://', 'postgresql://', 1)

    parsed = urllib.parse.urlparse(db_url)
    user = parsed.username or 'postgres'
    password = urllib.parse.unquote(parsed.password or '')
    host = parsed.hostname or 'localhost'
    port = parsed.port or 5432
    dbname = parsed.path.lstrip('/') or 'postgres'

    # If Supabase direct connection (db.<ref>.supabase.co), map to IPv4 transaction pooler for Vercel/Cloud compatibility
    if host.startswith('db.') and host.endswith('.supabase.co'):
        project_ref = host[3:-len('.supabase.co')]
        host = 'aws-0-ap-northeast-1.pooler.supabase.com'
        port = 6543
        if not user.startswith('postgres.'):
            user = f"postgres.{project_ref}"
    elif 'pooler.supabase.com' in host:
        port = parsed.port or 6543

    return {
        'user': user,
        'password': password,
        'host': host,
        'port': port,
        'dbname': dbname,
        'sslmode': 'require'
    }

# Default Supabase Database URL (Transaction Pooler - IPv4)
DEFAULT_SUPABASE_DATABASE_URL = "postgresql://postgres.lpuwgdniabfkkhdrncqg:Gourav%400712@aws-0-ap-northeast-1.pooler.supabase.com:6543/postgres"

def get_db_connection():
    """
    Task: Open connection to PostgreSQL cloud database (Supabase/Vercel) via pg8000 or psycopg2, or fall back to SQLite.
    """
    db_url = os.environ.get('DATABASE_URL') or os.environ.get('SUPABASE_DB_URL') or os.environ.get('POSTGRES_URL')
    
    # In production/cloud (e.g. Vercel), default to Supabase PostgreSQL unless isolated test mode is requested
    if not db_url and not app.config.get('TESTING') and not os.environ.get('TEST_DB_PATH'):
        db_url = DEFAULT_SUPABASE_DATABASE_URL

    if db_url:
        params = parse_db_url_to_pg_params(db_url)

        # 1. First priority: pg8000 (Pure Python, 100% reliable on Vercel Serverless / AWS Lambda)
        if HAS_PG8000 and params:
            try:
                ssl_ctx = ssl.create_default_context()
                ssl_ctx.check_hostname = False
                ssl_ctx.verify_mode = ssl.CERT_NONE
                conn = pg8000.dbapi.connect(
                    user=params['user'],
                    password=params['password'],
                    host=params['host'],
                    port=params['port'],
                    database=params['dbname'],
                    ssl_context=ssl_ctx,
                    timeout=10
                )
                return PgConnWrapper(conn, is_pg8000=True)
            except Exception as pg8_err:
                print(f"[Database] pg8000 connection failed: {pg8_err}")

        # 2. Second priority: psycopg2
        if HAS_PSYCOPG2:
            try:
                if params:
                    pg_conn = psycopg2.connect(
                        user=params['user'],
                        password=params['password'],
                        host=params['host'],
                        port=params['port'],
                        dbname=params['dbname'],
                        sslmode=params['sslmode'],
                        connect_timeout=10
                    )
                    return PgConnWrapper(pg_conn, is_pg8000=False)
            except Exception as e:
                print(f"[Database] psycopg2 connection failed ({e}), attempting direct DSN...")
                try:
                    clean_url = db_url.replace('postgres://', 'postgresql://', 1)
                    pg_conn = psycopg2.connect(clean_url, sslmode='require', connect_timeout=10)
                    return PgConnWrapper(pg_conn, is_pg8000=False)
                except Exception as dsn_err:
                    print(f"[Database] Direct DSN connection failed ({dsn_err}).")

    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/api/db-status', methods=['GET'])
def get_db_status():
    """
    Task: Return current database engine, connection state, and record count for diagnostics.
    """
    try:
        conn = get_db_connection()
        is_pg = getattr(conn, 'is_pg', False)
        is_pg8000 = getattr(conn, 'is_pg8000', False)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM users")
        row = cur.fetchone()
        user_count = row[0] if isinstance(row, (tuple, list)) else (row.get('count') if hasattr(row, 'get') else 0)
        conn.close()

        db_type = "PostgreSQL (Supabase)" if is_pg else "SQLite (Local/Fallback)"
        driver = "pg8000 (Pure Python)" if is_pg8000 else ("psycopg2" if is_pg else "sqlite3")

        return jsonify({
            'status': 'Connected',
            'database': db_type,
            'driver': driver,
            'is_postgresql': is_pg,
            'users_in_db': user_count,
            'has_database_url_env': bool(os.environ.get('DATABASE_URL') or os.environ.get('SUPABASE_DB_URL') or os.environ.get('POSTGRES_URL'))
        })
    except Exception as err:
        return jsonify({
            'status': 'Error',
            'error': str(err),
            'has_database_url_env': bool(os.environ.get('DATABASE_URL') or os.environ.get('SUPABASE_DB_URL') or os.environ.get('POSTGRES_URL'))
        }), 500

def init_db():
    """
    Task: Initialize database tables (users, attendance, holidays) and seed default system administrator account if missing.
    """
    try:
        conn = get_db_connection()
    except Exception as conn_err:
        print("[Database] Failed to open connection during init_db:", conn_err)
        return

    is_pg = getattr(conn, 'is_pg', False)
    cursor = conn.cursor()
    
    try:
        if is_pg:
            # PostgreSQL schema
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(255) UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    full_name TEXT NOT NULL,
                    role VARCHAR(50) NOT NULL,
                    department TEXT NOT NULL DEFAULT '',
                    email TEXT NOT NULL DEFAULT '',
                    class_name TEXT NOT NULL DEFAULT '',
                    semester TEXT NOT NULL DEFAULT '',
                    roll_no TEXT NOT NULL DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS class_name TEXT NOT NULL DEFAULT ''")
            cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS semester TEXT NOT NULL DEFAULT ''")
            cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS roll_no TEXT NOT NULL DEFAULT ''")

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS attendance (
                    id SERIAL PRIMARY KEY,
                    student_id INTEGER NOT NULL,
                    student_name TEXT NOT NULL,
                    roll_no TEXT NOT NULL,
                    department TEXT NOT NULL,
                    class_name TEXT NOT NULL,
                    semester TEXT NOT NULL DEFAULT '',
                    subject TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    date TEXT NOT NULL,
                    time TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'Present',
                    latitude REAL,
                    longitude REAL,
                    distance_meters REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (student_id) REFERENCES users(id) ON DELETE CASCADE
                )
            ''')
            try:
                cursor.execute("ALTER TABLE attendance DROP CONSTRAINT IF EXISTS attendance_student_id_date_key")
                cursor.execute("ALTER TABLE attendance DROP CONSTRAINT IF EXISTS attendance_student_id_date_unique")
            except Exception:
                pass
            cursor.execute("ALTER TABLE attendance ADD COLUMN IF NOT EXISTS semester TEXT NOT NULL DEFAULT ''")
            cursor.execute("ALTER TABLE attendance ADD COLUMN IF NOT EXISTS latitude REAL")
            cursor.execute("ALTER TABLE attendance ADD COLUMN IF NOT EXISTS longitude REAL")
            cursor.execute("ALTER TABLE attendance ADD COLUMN IF NOT EXISTS distance_meters REAL")

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS holidays (
                    id SERIAL PRIMARY KEY,
                    date TEXT NOT NULL,
                    title TEXT NOT NULL,
                    department TEXT NOT NULL DEFAULT 'all',
                    created_by TEXT NOT NULL DEFAULT 'Admin',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()
        else:
            # SQLite schema
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    full_name TEXT NOT NULL,
                    role TEXT NOT NULL,
                    department TEXT NOT NULL DEFAULT '',
                    email TEXT NOT NULL DEFAULT '',
                    class_name TEXT NOT NULL DEFAULT '',
                    semester TEXT NOT NULL DEFAULT '',
                    roll_no TEXT NOT NULL DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cursor.execute("PRAGMA table_info(users)")
            columns = [col[1] for col in cursor.fetchall()]
            if 'class_name' not in columns:
                cursor.execute("ALTER TABLE users ADD COLUMN class_name TEXT NOT NULL DEFAULT ''")
            if 'semester' not in columns:
                cursor.execute("ALTER TABLE users ADD COLUMN semester TEXT NOT NULL DEFAULT ''")
            if 'roll_no' not in columns:
                cursor.execute("ALTER TABLE users ADD COLUMN roll_no TEXT NOT NULL DEFAULT ''")

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS attendance (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_id INTEGER NOT NULL,
                    student_name TEXT NOT NULL,
                    roll_no TEXT NOT NULL,
                    department TEXT NOT NULL,
                    class_name TEXT NOT NULL,
                    semester TEXT NOT NULL DEFAULT '',
                    subject TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    date TEXT NOT NULL,
                    time TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'Present',
                    latitude REAL,
                    longitude REAL,
                    distance_meters REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (student_id) REFERENCES users(id),
                    UNIQUE(student_id, date)
                )
            ''')
            cursor.execute("PRAGMA table_info(attendance)")
            att_cols = [col[1] for col in cursor.fetchall()]
            if 'semester' not in att_cols:
                cursor.execute("ALTER TABLE attendance ADD COLUMN semester TEXT NOT NULL DEFAULT ''")
            if 'latitude' not in att_cols:
                cursor.execute("ALTER TABLE attendance ADD COLUMN latitude REAL")
            if 'longitude' not in att_cols:
                cursor.execute("ALTER TABLE attendance ADD COLUMN longitude REAL")
            if 'distance_meters' not in att_cols:
                cursor.execute("ALTER TABLE attendance ADD COLUMN distance_meters REAL")

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS holidays (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    title TEXT NOT NULL,
                    department TEXT NOT NULL DEFAULT 'all',
                    created_by TEXT NOT NULL DEFAULT 'Admin',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()

        # Check if admin user exists, if not create default admin
        cursor.execute("SELECT * FROM users WHERE username = ?", ('admin',))
        admin = cursor.fetchone()
        if not admin:
            default_admin_pass = generate_password_hash('admin123')
            cursor.execute('''
                INSERT INTO users (username, password_hash, full_name, role, department, email, class_name, semester, roll_no)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', ('admin', default_admin_pass, 'System Administrator', 'admin', 'Administration', 'admin@college.edu', '', '', ''))
            conn.commit()

        # Check if any student user exists, if not seed default student accounts for testing
        cursor.execute("SELECT * FROM users WHERE role = 'student'")
        students_exist = cursor.fetchone()
        if not students_exist:
            pwd = generate_password_hash('pass123')
            sample_students = [
                ('student1', pwd, 'Aarav Sharma', 'student', 'Computer Science', 'aarav@college.edu', 'B.Tech', 'Semester 3', 'CS2026-01'),
                ('student2', pwd, 'Priya Patel', 'student', 'Information Technology', 'priya@college.edu', 'BCA', 'Semester 3', 'IT2026-02'),
                ('student3', pwd, 'Rohan Verma', 'student', 'Mechanical', 'rohan@college.edu', 'B.Com', 'Semester 3', 'ME2026-03'),
                ('student4', pwd, 'Ananya Gupta', 'student', 'Computer Science', 'ananya@college.edu', 'B.Tech', 'Semester 3', 'CS2026-04')
            ]
            for s in sample_students:
                try:
                    cursor.execute('''
                        INSERT INTO users (username, password_hash, full_name, role, department, email, class_name, semester, roll_no)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', s)
                    conn.commit()
                except Exception:
                    try:
                        conn.rollback()
                    except Exception:
                        pass

        conn.commit()
    except Exception as e:
        print("[Database] Error during schema initialization:", e)
        try:
            conn.rollback()
        except Exception:
            pass
    finally:
        conn.close()

# Initialize DB on startup
init_db()

@app.route('/')
def index():
    """
    Task: Render and return main single-page HTML frontend interface (index.html).
    """
    return render_template('index.html')

@app.route('/api/login', methods=['POST'])
@rate_limit(max_requests=10, window_seconds=60, error_message="Too many login attempts. Please wait 60 seconds and try again.")
def login():
    """
    Task: Authenticate user login credentials, verify role assignment, and establish session state.
    Protected against brute-force and session fixation attacks.
    """
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')
    expected_role = data.get('role', '').strip().lower()
    
    if not username or not password:
        return jsonify({'success': False, 'message': 'Username and password are required.'}), 400

    if len(username) > 100 or len(password) > 128:
        return jsonify({'success': False, 'message': 'Invalid input length.'}), 400
        
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
    conn.close()
    
    if not user:
        return jsonify({'success': False, 'message': 'Account not found. Please contact the administrator.'}), 401
        
    if not check_password_hash(user['password_hash'], password):
        return jsonify({'success': False, 'message': 'Invalid credentials.'}), 401
        
    if expected_role and user['role'] != expected_role:
        return jsonify({'success': False, 'message': f"Account found, but it is not registered as a {expected_role.capitalize()}."}), 403
        
    # Prevent session fixation by resetting existing session before binding new user
    session.clear()
    session['user_id'] = user['id']
    session['username'] = user['username']
    session['role'] = user['role']
    session['full_name'] = user['full_name']
    session.permanent = True
    
    return jsonify({
        'success': True,
        'user': {
            'id': user['id'],
            'username': user['username'],
            'full_name': user['full_name'],
            'role': user['role'],
            'department': user['department'],
            'email': user['email'],
            'class_name': user['class_name'],
            'semester': user['semester'],
            'roll_no': user['roll_no']
        }
    })

@app.route('/api/me', methods=['GET'])
def get_current_user():
    """
    Task: Return current authenticated user profile and active session details.
    """
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'authenticated': False}), 200
        
    conn = get_db_connection()
    user = conn.execute('SELECT id, username, full_name, role, department, email, class_name, semester, roll_no, created_at FROM users WHERE id = ?', (user_id,)).fetchone()
    conn.close()
    
    if not user:
        session.clear()
        return jsonify({'authenticated': False}), 200
        
    return jsonify({
        'authenticated': True,
        'user': dict(user)
    })

@app.route('/api/logout', methods=['POST'])
def logout():
    """
    Task: Clear session state and log out active user.
    """
    session.clear()
    return jsonify({'success': True, 'message': 'Logged out successfully.'})

@app.route('/api/admin/users', methods=['GET'])
def get_users():
    """
    Task: Fetch list of all registered system users for admin management view.
    """
    if session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized. Admin access required.'}), 403
        
    conn = get_db_connection()
    users = conn.execute('SELECT id, username, full_name, role, department, email, class_name, semester, roll_no, created_at FROM users ORDER BY id DESC').fetchall()
    conn.close()
    
    users_list = [dict(u) for u in users]
    return jsonify({'users': users_list})

@app.route('/api/admin/users', methods=['POST'])
def create_user():
    """
    Task: Create new staff or student user credentials with department, class, and semester assignment.
    """
    if session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized. Admin access required.'}), 403
        
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')
    full_name = data.get('full_name', '').strip()
    role = data.get('role', '').strip().lower()
    department = data.get('department', '').strip()
    email = data.get('email', '').strip()
    class_name = data.get('class_name', '').strip()
    semester = data.get('semester', '').strip()
    roll_no = data.get('roll_no', '').strip()
    
    if not username or not password or not full_name or not role:
        return jsonify({'error': 'Username, password, full name, and role are required.'}), 400
        
    if len(username) < 3 or len(username) > 50:
        return jsonify({'error': 'Username must be between 3 and 50 characters.'}), 400

    if len(password) < 6 or len(password) > 128:
        return jsonify({'error': 'Password must be at least 6 characters in length.'}), 400

    if role not in ['staff', 'student']:
        return jsonify({'error': 'Role must be either "staff" or "student".'}), 400
        
    conn = get_db_connection()
    # Check if username exists
    existing = conn.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
    if existing:
        conn.close()
        return jsonify({'error': 'Username already exists. Please choose a different username.'}), 400
        
    pass_hash = generate_password_hash(password)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO users (username, password_hash, full_name, role, department, email, class_name, semester, roll_no)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (username, pass_hash, full_name, role, department, email, class_name, semester, roll_no))
    conn.commit()
    new_id = cursor.lastrowid
    if not new_id:
        user_row = conn.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
        new_id = user_row['id'] if user_row else None
    conn.close()
    
    return jsonify({
        'success': True,
        'message': f"{role.capitalize()} account created successfully!",
        'user': {
            'id': new_id,
            'username': username,
            'full_name': full_name,
            'role': role,
            'department': department,
            'email': email,
            'class_name': class_name,
            'semester': semester,
            'roll_no': roll_no
        }
    }), 201

@app.route('/api/admin/users/<int:user_id>', methods=['DELETE'])
def delete_user(user_id):
    """
    Task: Delete a specific user account and clean up their associated attendance history.
    """
    if session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized. Admin access required.'}), 403
        
    conn = get_db_connection()
    user = conn.execute('SELECT role, username FROM users WHERE id = ?', (user_id,)).fetchone()
    
    if not user:
        conn.close()
        return jsonify({'error': 'User not found.'}), 404
        
    if user['role'] == 'admin' or user['username'] == 'admin':
        conn.close()
        return jsonify({'error': 'Cannot delete the system administrator account.'}), 400
        
    conn.execute('DELETE FROM attendance WHERE student_id = ?', (user_id,))
    conn.execute('DELETE FROM users WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'message': 'User deleted successfully.'})

@app.route('/api/admin/sample-users-csv', methods=['GET'])
def download_sample_users_csv():
    """
    Task: Provide a downloadable sample CSV template for bulk user registration.
    """
    if session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized. Admin access required.'}), 403

    output = io.StringIO()
    writer = csv.writer(output)
    
    # Header row
    writer.writerow(['full_name', 'username', 'password', 'role', 'department', 'class_name', 'semester', 'roll_no', 'email'])
    
    # Sample rows
    writer.writerow(['Rahul Sharma', 'rahul_cs01', 'student123', 'student', 'Computer Science', 'B.Tech CS', 'Semester 3', 'CS-2026-01', 'rahul@campus.edu'])
    writer.writerow(['Priya Patel', 'priya_it02', 'student123', 'student', 'Information Technology', 'B.Tech IT', 'Semester 3', 'IT-2026-02', 'priya@campus.edu'])
    writer.writerow(['Dr. Alan Turing', 'alan_faculty', 'staff123', 'staff', 'Computer Science', '', '', '', 'alan.turing@campus.edu'])
    
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={
            'Content-Disposition': 'attachment; filename=aq_users_sample_template.csv',
            'Content-Type': 'text/csv; charset=utf-8'
        }
    )

@app.route('/api/admin/upload-csv-users', methods=['POST'])
def bulk_upload_users_csv():
    """
    Task: Bulk upload student and staff user accounts via CSV file.
    """
    if session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized. Admin access required.'}), 403

    if 'file' not in request.files:
        return jsonify({'error': 'No CSV file uploaded. Please choose a valid .csv file.'}), 400

    file = request.files['file']
    if not file or file.filename == '':
        return jsonify({'error': 'No selected file.'}), 400

    if not (file.filename.lower().endswith('.csv') or file.content_type in ['text/csv', 'application/vnd.ms-excel', 'text/plain']):
        return jsonify({'error': 'Invalid file format. Please upload a .csv file.'}), 400

    try:
        content = file.stream.read().decode("utf-8-sig")
        stream = io.StringIO(content, newline=None)
        reader = csv.DictReader(stream)
    except Exception as e:
        return jsonify({'error': f'Failed to parse CSV file: {str(e)}'}), 400

    if not reader.fieldnames:
        return jsonify({'error': 'CSV file is empty or missing header row.'}), 400

    # Normalize header mapping (strip whitespace and lower-case keys)
    header_map = {}
    for fn in reader.fieldnames:
        if not fn:
            continue
        clean_fn = fn.strip().lower()
        if clean_fn in ['full_name', 'fullname', 'name', 'student_name', 'staff_name', 'student name', 'staff name']:
            header_map['full_name'] = fn
        elif clean_fn in ['username', 'user_name', 'user', 'login', 'user name']:
            header_map['username'] = fn
        elif clean_fn in ['password', 'pwd', 'pass']:
            header_map['password'] = fn
        elif clean_fn in ['role', 'user_role', 'type', 'account_type', 'user role']:
            header_map['role'] = fn
        elif clean_fn in ['department', 'dept', 'branch']:
            header_map['department'] = fn
        elif clean_fn in ['class_name', 'class', 'course', 'degree', 'class name']:
            header_map['class_name'] = fn
        elif clean_fn in ['semester', 'sem']:
            header_map['semester'] = fn
        elif clean_fn in ['roll_no', 'rollno', 'roll_number', 'roll', 'enrollment_no', 'roll no', 'roll number']:
            header_map['roll_no'] = fn
        elif clean_fn in ['email', 'email_address', 'mail', 'email address']:
            header_map['email'] = fn

    if 'full_name' not in header_map:
        return jsonify({'error': 'CSV must contain at least a "full_name" or "name" column.'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    # Preload existing usernames and roll numbers to prevent collisions
    existing_users = {row['username'].lower() for row in conn.execute('SELECT username FROM users').fetchall()}
    existing_rolls = {row['roll_no'].lower() for row in conn.execute("SELECT roll_no FROM users WHERE roll_no IS NOT NULL AND roll_no != ''").fetchall()}

    imported_count = 0
    student_count = 0
    staff_count = 0
    skipped_count = 0
    warnings = []
    created_users = []

    row_idx = 1
    for row in reader:
        row_idx += 1
        raw_full_name = row.get(header_map.get('full_name', ''), '').strip()
        if not raw_full_name:
            skipped_count += 1
            warnings.append(f"Row {row_idx}: Skipped due to empty full name.")
            continue

        raw_role = row.get(header_map.get('role', ''), 'student').strip().lower()
        if raw_role not in ['student', 'staff']:
            raw_role = 'student'

        raw_dept = row.get(header_map.get('department', ''), 'Computer Science').strip()
        raw_class = row.get(header_map.get('class_name', ''), '').strip()
        raw_sem = row.get(header_map.get('semester', ''), '').strip()
        raw_roll = row.get(header_map.get('roll_no', ''), '').strip()
        raw_email = row.get(header_map.get('email', ''), '').strip()

        # Check duplicate roll number for students
        if raw_role == 'student' and raw_roll and raw_roll.lower() in existing_rolls:
            skipped_count += 1
            warnings.append(f"Row {row_idx} ({raw_full_name}): Roll number '{raw_roll}' already exists (Skipped).")
            continue

        # Generate or extract username
        raw_username = row.get(header_map.get('username', ''), '').strip()
        if not raw_username:
            if raw_roll:
                base_username = raw_roll.lower().replace(' ', '_').replace('-', '_')
            else:
                base_username = raw_full_name.lower().replace(' ', '_').replace('.', '')
            
            # Clean non-alphanumeric chars
            base_username = ''.join(c for c in base_username if c.isalnum() or c in ['_', '-'])[:30]
            if len(base_username) < 3:
                base_username = f"user_{int(time.time() * 1000) % 100000}"
            
            if base_username.lower() in existing_users:
                skipped_count += 1
                warnings.append(f"Row {row_idx} ({raw_full_name}): Username '{base_username}' already exists (Skipped).")
                continue
            raw_username = base_username
        
        if len(raw_username) < 3 or len(raw_username) > 50:
            skipped_count += 1
            warnings.append(f"Row {row_idx} ({raw_full_name}): Username '{raw_username}' length must be 3-50 chars.")
            continue

        if raw_username.lower() in existing_users:
            skipped_count += 1
            warnings.append(f"Row {row_idx} ({raw_full_name}): Username '{raw_username}' already exists (Skipped).")
            continue

        # Extract or generate password
        raw_password = row.get(header_map.get('password', ''), '').strip()
        if not raw_password or len(raw_password) < 6:
            raw_password = 'student123' if raw_role == 'student' else 'staff123'

        pass_hash = generate_password_hash(raw_password)

        try:
            cursor.execute('''
                INSERT INTO users (username, password_hash, full_name, role, department, email, class_name, semester, roll_no)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (raw_username, pass_hash, raw_full_name, raw_role, raw_dept, raw_email, raw_class, raw_sem, raw_roll))
            
            existing_users.add(raw_username.lower())
            if raw_roll:
                existing_rolls.add(raw_roll.lower())
            imported_count += 1
            if raw_role == 'student':
                student_count += 1
            else:
                staff_count += 1
            
            created_users.append({
                'full_name': raw_full_name,
                'username': raw_username,
                'role': raw_role,
                'department': raw_dept,
                'class_name': raw_class,
                'semester': raw_sem,
                'roll_no': raw_roll
            })
        except Exception as insert_err:
            skipped_count += 1
            warnings.append(f"Row {row_idx} ({raw_full_name}): Database error ({str(insert_err)}).")

    conn.commit()
    conn.close()

    summary_msg = f"Imported {imported_count} user{'s' if imported_count != 1 else ''} ({student_count} student{'s' if student_count != 1 else ''}, {staff_count} staff)."
    if skipped_count > 0:
        summary_msg += f" {skipped_count} row{'s' if skipped_count != 1 else ''} skipped."

    return jsonify({
        'success': True,
        'message': summary_msg,
        'imported_count': imported_count,
        'student_count': student_count,
        'staff_count': staff_count,
        'skipped_count': skipped_count,
        'warnings': warnings[:50],
        'users': created_users[:50]
    })

@app.route('/api/staff/students', methods=['GET'])
def get_staff_students():
    """
    Task: Fetch list of student accounts filtered by department, semester, and search query for faculty/admin view.
    """
    if session.get('role') not in ['staff', 'admin']:
        return jsonify({'error': 'Unauthorized access.'}), 403
        
    conn = get_db_connection()
    user_id = session.get('user_id')
    user_role = session.get('role')
    staff = conn.execute('SELECT department FROM users WHERE id = ?', (user_id,)).fetchone()
    staff_dept = staff['department'] if staff else ''

    selected_dept = request.args.get('department', '').strip()
    semester = request.args.get('semester', '').strip()
    search = request.args.get('search', '').strip()

    if not selected_dept:
        if user_role == 'admin':
            selected_dept = 'all'
        else:
            selected_dept = staff_dept or 'all'

    query = "SELECT id, username, full_name, role, department, email, class_name, semester, roll_no, created_at FROM users WHERE role = 'student'"
    params = []

    if selected_dept and selected_dept.lower() != 'all':
        query += " AND (department = ? OR department LIKE ?)"
        params.extend([selected_dept, f"%{selected_dept}%"])
    if semester and semester.lower() != 'all':
        query += " AND (semester = ? OR class_name LIKE ?)"
        params.extend([semester, f"%{semester}%"])
    if search:
        query += " AND (full_name LIKE ? OR username LIKE ? OR roll_no LIKE ? OR email LIKE ? OR class_name LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%", f"%{search}%", f"%{search}%"])

    query += " ORDER BY full_name ASC"
    students = conn.execute(query, params).fetchall()
    conn.close()

    return jsonify({
        'success': True,
        'students': [dict(s) for s in students],
        'department': selected_dept,
        'semester': semester or 'all',
        'total': len(students)
    })



# --- ATTENDANCE MANAGEMENT & DYNAMIC TOTP APIS ---

@app.route('/api/staff/totp-qr', methods=['GET', 'POST'])
def get_staff_totp_qr():
    """
    Task: Return permanent lifetime campus attendance QR code payload for staff/faculty classroom display.
    """
    if session.get('role') not in ['staff', 'admin']:
        return jsonify({'error': 'Unauthorized access. Staff rights required.'}), 403

    conn = get_db_connection()
    user_id = session.get('user_id')
    staff = conn.execute('SELECT full_name, department FROM users WHERE id = ?', (user_id,)).fetchone()
    conn.close()

    department = (staff['department'] if (staff and staff['department']) else session.get('department', 'Computer Science')) or 'Computer Science'
    teacher_name = staff['full_name'] if (staff and staff['full_name']) else session.get('full_name', 'Faculty Staff')
    
    data = request.get_json() or {} if request.method == 'POST' else request.args
    dept_code = "".join(c for c in department.upper() if c.isalnum())[:4] or 'CS'
    session_id = data.get('session_id', '').strip() or f"PERM-{dept_code}-OFFICIAL"
    subject = data.get('subject', '').strip() or "Whole Day Attendance"
    class_name = data.get('class', '').strip() or "All Classes"
    semester = data.get('semester', '').strip() or "All Semesters"
    compact = str(data.get('compact', '')).lower() in ['1', 'true', 'yes'] or data.get('mode') == 'fast_scan'

    if compact:
        payload = create_compact_qr_payload(
            session_id=session_id,
            subject=subject,
            class_name=class_name,
            department=department,
            teacher_name=teacher_name,
            semester=semester
        )
    else:
        payload = create_totp_payload(
            session_id=session_id,
            subject=subject,
            class_name=class_name,
            department=department,
            teacher_name=teacher_name,
            semester=semester
        )
    return jsonify(payload)


@app.route('/api/student/mark-attendance', methods=['POST'])
@rate_limit(max_requests=25, window_seconds=60, error_message="Too many attendance scan requests. Please wait a moment and try again.")
def mark_student_attendance():
    """
    Task: Process student QR code submission, verify permanent campus QR validity, validate campus geofencing location, and insert Present record for today.
    """
    try:
        if session.get('role') != 'student':
            return jsonify({'error': 'Unauthorized access. Please log in with a Student account.'}), 403

        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Student session has expired. Please log in again.'}), 401

        try:
            data = request.get_json(force=True, silent=True) or {}
        except Exception:
            data = {}

        # Verify Permanent / Static QR payload if present
        if data.get('totp_token') or data.get('type') in ['aq_permanent_qr', 'aq_static_qr', 'aq_dynamic_totp_qr', 'aq_qr', 'p', 'perm'] or data.get('session_id') or data.get('s'):
            is_valid_totp, totp_err_msg = verify_totp_payload(data)
            if not is_valid_totp:
                return jsonify({'error': totp_err_msg}), 400

        # --- Geolocation Verification ---
        student_lat = data.get('lat')
        student_lng = data.get('lng')

        if app.config.get('TESTING') and (student_lat is None or student_lng is None):
            student_lat = 24.495374689123384
            student_lng = 72.80818369745779

        if student_lat is None or student_lng is None or str(student_lat).strip() == '' or str(student_lng).strip() == '':
            return jsonify({
                'error': 'Location access is required to mark attendance. Please allow GPS/location permission in your browser settings and try again.'
            }), 400

        try:
            lat_f = float(student_lat)
            lng_f = float(student_lng)
            if not (-90.0 <= lat_f <= 90.0 and -180.0 <= lng_f <= 180.0):
                return jsonify({'error': 'Invalid GPS coordinates out of geographical range.'}), 400
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid coordinate numbers.'}), 400

        inside_campus, distance = is_within_campus(student_lat, student_lng)
        if not inside_campus:
            if distance < 0:
                return jsonify({'error': 'Invalid location data received. Please ensure location is enabled and try scanning again.'}), 400
            return jsonify({
                'error': f'Attendance can only be marked from campus. You appear to be about {int(distance)}m away from the permitted zone.'
            }), 400

        session_id = str(data.get('session_id', '') or data.get('session', '') or data.get('s', '')).strip()
        subject = str(data.get('subject', '')).strip() or 'Classroom Attendance'
        class_name = str(data.get('class', '') or data.get('class_name', '')).strip()
        department = str(data.get('department', '')).strip()
        import datetime
        now = datetime.datetime.now()
        date_str = str(data.get('date', '')).strip() or now.strftime('%Y-%m-%d')
        time_str = str(data.get('time', '')).strip() or now.strftime('%I:%M:%S %p')

        if not session_id:
            import time
            session_id = f"ATT-{int(time.time()) % 100000}"

        try:
            conn = get_db_connection()
        except Exception as conn_err:
            app.logger.error(f"[Database Connection Error in mark_attendance]: {conn_err}")
            return jsonify({'error': 'Database is momentarily connecting. Please try scanning again in 2 seconds.'}), 503

        student = conn.execute('SELECT id, full_name, roll_no, department, class_name, semester FROM users WHERE id = ?', (user_id,)).fetchone()

        if not student:
            conn.close()
            return jsonify({'error': 'Student record not found in system database. Please log in again.'}), 404

        # Check if student already has a record for today
        existing_today = conn.execute('''
            SELECT id, status, subject FROM attendance 
            WHERE student_id = ? AND date = ?
        ''', (user_id, date_str)).fetchone()

        student_name = student['full_name']
        roll_no = student['roll_no'] if student['roll_no'] else 'N/A'
        student_dept = student['department'] if student['department'] else (department or 'General Studies')
        student_class = student['class_name'] if student['class_name'] else (class_name or 'General Class')
        student_sem = student['semester'] if ('semester' in student.keys() and student['semester']) else ''

        lat_val = float(student_lat)
        lng_val = float(student_lng)
        # Check if student already marked attendance for this session or subject today
        existing_session = conn.execute('''
            SELECT id, status, subject, session_id FROM attendance 
            WHERE student_id = ? AND date = ? AND (session_id = ? OR (subject = ? AND subject != 'Classroom Attendance' AND subject != 'Whole Day Attendance'))
        ''', (user_id, date_str, session_id, subject)).fetchone()

        if existing_session:
            existing_status = str(existing_session['status'] or '').strip().lower()
            if existing_status in ['present', 'p']:
                conn.close()
                return jsonify({'error': f'Attendance already marked for today ({date_str}) for {subject}! Scanning is limited to once per class.'}), 400
            else:
                # Update existing Absent / Holiday / Leave record to Present
                cursor = conn.cursor()
                try:
                    cursor.execute('''
                        UPDATE attendance 
                        SET status = 'Present', subject = ?, session_id = ?, time = ?, latitude = ?, longitude = ?, distance_meters = ?, department = ?, class_name = ?, semester = ?
                        WHERE id = ?
                    ''', (subject, session_id, time_str, lat_val, lng_val, dist_val, student_dept, student_class, student_sem, existing_session['id']))
                    conn.commit()
                    conn.close()
                    return jsonify({
                        'success': True,
                        'message': f"Attendance marked as Present for {subject}!",
                        'attendance': {
                            'subject': subject,
                            'session_id': session_id,
                            'date': date_str,
                            'time': time_str,
                            'status': 'Present',
                            'latitude': lat_val,
                            'longitude': lng_val,
                            'distance_meters': dist_val
                        }
                    })
                except Exception as update_err:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    app.logger.error(f"[Attendance Update Status Error]: {update_err}")

        lat_val = float(student_lat)
        lng_val = float(student_lng)
        dist_val = round(float(distance), 2) if distance >= 0 else 0.0

        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO attendance (student_id, student_name, roll_no, department, class_name, semester, subject, session_id, date, time, status, latitude, longitude, distance_meters)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Present', ?, ?, ?)
            ''', (user_id, student_name, roll_no, student_dept, student_class, student_sem, subject, session_id, date_str, time_str, lat_val, lng_val, dist_val))
            conn.commit()
        except Exception as insert_err:
            try:
                conn.rollback()
            except Exception:
                pass

            err_text = str(insert_err).lower()
            # If unique constraint violation
            if 'unique' in err_text or 'duplicate' in err_text or '23505' in err_text:
                conn.close()
                return jsonify({'error': f'Attendance already marked for today ({date_str}) for {subject}! Scanning is limited to once per class.'}), 400

            # Schema self-healing if columns missing in PostgreSQL or SQLite
            try:
                is_pg = getattr(conn, 'is_pg', False)
                if is_pg:
                    try:
                        cursor.execute("ALTER TABLE attendance DROP CONSTRAINT IF EXISTS attendance_student_id_date_key")
                    except Exception:
                        pass
                    cursor.execute("ALTER TABLE attendance ADD COLUMN IF NOT EXISTS semester TEXT NOT NULL DEFAULT ''")
                    cursor.execute("ALTER TABLE attendance ADD COLUMN IF NOT EXISTS latitude REAL")
                    cursor.execute("ALTER TABLE attendance ADD COLUMN IF NOT EXISTS longitude REAL")
                    cursor.execute("ALTER TABLE attendance ADD COLUMN IF NOT EXISTS distance_meters REAL")
                else:
                    cursor.execute("ALTER TABLE attendance ADD COLUMN semester TEXT NOT NULL DEFAULT ''")
                    cursor.execute("ALTER TABLE attendance ADD COLUMN latitude REAL")
                    cursor.execute("ALTER TABLE attendance ADD COLUMN longitude REAL")
                    cursor.execute("ALTER TABLE attendance ADD COLUMN distance_meters REAL")
                conn.commit()
                # Retry insertion
                cursor.execute('''
                    INSERT INTO attendance (student_id, student_name, roll_no, department, class_name, semester, subject, session_id, date, time, status, latitude, longitude, distance_meters)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Present', ?, ?, ?)
                ''', (user_id, student_name, roll_no, student_dept, student_class, student_sem, subject, session_id, date_str, time_str, lat_val, lng_val, dist_val))
                conn.commit()
            except Exception as retry_err:
                try:
                    conn.rollback()
                except Exception:
                    pass
                app.logger.error(f"[Attendance Insert/Migration Error]: {retry_err}")
                conn.close()
                retry_text = str(retry_err).lower()
                if 'unique' in retry_text or 'duplicate' in retry_text or '23505' in retry_text:
                    return jsonify({'error': f'Attendance already marked for today ({date_str}) for {subject}! Scanning is limited to once per class.'}), 400
                return jsonify({'error': f'Could not record attendance: {str(insert_err)}'}), 400

        conn.close()

        return jsonify({
            'success': True,
            'message': f"Attendance marked as Present for {subject}!",
            'attendance': {
                'subject': subject,
                'session_id': session_id,
                'date': date_str,
                'time': time_str,
                'status': 'Present',
                'latitude': lat_val,
                'longitude': lng_val,
                'distance_meters': dist_val
            }
        })
    except Exception as outer_err:
        import traceback
        app.logger.error(f"[mark_student_attendance uncaught exception]: {traceback.format_exc()}")
        return jsonify({'error': f"Failed to submit attendance: {str(outer_err)}"}), 400

@app.route('/api/student/attendance', methods=['GET'])
def get_student_attendance():
    """
    Task: Fetch personal attendance history logs and scheduled college holidays for logged-in student.
    """
    if session.get('role') != 'student':
        return jsonify({'error': 'Unauthorized access.'}), 403

    user_id = session.get('user_id')
    month = request.args.get('month', '').strip() # e.g. 2026-08

    conn = get_db_connection()
    if month:
        records = conn.execute('SELECT * FROM attendance WHERE student_id = ? AND date LIKE ? ORDER BY date DESC, id DESC', (user_id, f"{month}%")).fetchall()
    else:
        records = conn.execute('SELECT * FROM attendance WHERE student_id = ? ORDER BY date DESC, id DESC', (user_id,)).fetchall()

    holidays = conn.execute('SELECT * FROM holidays ORDER BY date ASC').fetchall()
    total_records = len(records)
    conn.close()

    return jsonify({
        'attendance': [dict(r) for r in records],
        'holidays': [dict(h) for h in holidays],
        'total_attended': total_records
    })

# --- HOLIDAY MANAGEMENT APIS (Admin & Staff) ---

@app.route('/api/holidays', methods=['GET'])
def get_holidays():
    """
    Task: Fetch list of all scheduled college and department holidays.
    """
    conn = get_db_connection()
    records = conn.execute('SELECT * FROM holidays ORDER BY date ASC').fetchall()
    conn.close()
    return jsonify({'holidays': [dict(r) for r in records]})

@app.route('/api/holidays', methods=['POST'])
def create_holiday():
    """
    Task: Schedule new college or department holiday and auto-update student attendance status to 'Holiday'.
    """
    if session.get('role') not in ['admin', 'staff']:
        return jsonify({'error': 'Unauthorized access. Staff/Admin rights required.'}), 403

    data = request.get_json() or {}
    date_str = data.get('date', '').strip()
    title = data.get('title', '').strip() or 'College Holiday'
    department = data.get('department', '').strip() or 'all'

    if not date_str:
        return jsonify({'error': 'Holiday date is required.'}), 400

    created_by = session.get('full_name', session.get('username', 'Faculty/Admin'))
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Insert into holidays table
    cursor.execute('''
        INSERT INTO holidays (date, title, department, created_by)
        VALUES (?, ?, ?, ?)
    ''', (date_str, title, department, created_by))

    # 2. Get students in department (or all students)
    if department and department.lower() != 'all':
        students = cursor.execute("SELECT * FROM users WHERE role = 'student' AND LOWER(department) = LOWER(?)", (department,)).fetchall()
    else:
        students = cursor.execute("SELECT * FROM users WHERE role = 'student'").fetchall()

    session_code = f"HOLIDAY-{date_str.replace('-', '')}"
    
    # 3. Create or update attendance records for each student
    for s in students:
        existing = cursor.execute("SELECT id FROM attendance WHERE student_id = ? AND date = ?", (s['id'], date_str)).fetchone()
        if existing:
            cursor.execute("UPDATE attendance SET status = 'Holiday', subject = ? WHERE id = ?", (f"Holiday: {title}", existing['id']))
        else:
            cursor.execute('''
                INSERT INTO attendance (student_id, student_name, roll_no, department, class_name, semester, subject, session_id, date, time, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                s['id'],
                s['full_name'],
                s['roll_no'] or 'N/A',
                s['department'] or 'General',
                s['class_name'] or 'N/A',
                s['semester'] or '',
                f"Holiday: {title}",
                session_code,
                date_str,
                "09:00:00 AM",
                "Holiday"
            ))

    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': f"Holiday '{title}' set for {date_str}! Applied to student attendance records."})


@app.route('/api/holidays/<int:holiday_id>', methods=['DELETE'])
def delete_holiday(holiday_id):
    """
    Task: Remove a scheduled college holiday from system database.
    """
    if session.get('role') not in ['admin', 'staff']:
        return jsonify({'error': 'Unauthorized.'}), 403

    conn = get_db_connection()
    conn.execute('DELETE FROM holidays WHERE id = ?', (holiday_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Holiday removed successfully.'})

# --- ATTENDANCE STATUS OVERRIDE API (Staff & Admin Editing P, A, L, H) ---

@app.route('/api/attendance/update-status', methods=['POST'])
def update_attendance_status():
    """
    Task: Manually override student attendance status (Present, Absent, Leave, Holiday) by faculty or admin.
    """
    if session.get('role') not in ['admin', 'staff']:
        return jsonify({'error': 'Unauthorized access. Staff/Admin rights required.'}), 403

    data = request.get_json() or {}
    attendance_id = data.get('attendance_id')
    student_id = data.get('student_id')
    new_status = data.get('status', '').strip()
    date_str = data.get('date', '').strip()
    subject_str = data.get('subject', '').strip() or 'Faculty Override'

    status_map = {
        'p': 'Present', 'present': 'Present',
        'a': 'Absent', 'absent': 'Absent',
        'l': 'Leave', 'leave': 'Leave',
        'h': 'Holiday', 'holiday': 'Holiday'
    }
    final_status = status_map.get(new_status.lower(), 'Present')

    conn = get_db_connection()
    cursor = conn.cursor()

    if attendance_id:
        cursor.execute('UPDATE attendance SET status = ? WHERE id = ?', (final_status, attendance_id))
    elif student_id and date_str:
        existing = cursor.execute('SELECT id FROM attendance WHERE student_id = ? AND date = ?', (student_id, date_str)).fetchone()
        if existing:
            cursor.execute('UPDATE attendance SET status = ? WHERE id = ?', (final_status, existing['id']))
        else:
            student = conn.execute('SELECT id, full_name, roll_no, department, class_name, semester FROM users WHERE id = ?', (student_id,)).fetchone()
            if student:
                import datetime
                now_time = datetime.datetime.now().strftime('%I:%M:%S %p')
                cursor.execute('''
                    INSERT INTO attendance (student_id, student_name, roll_no, department, class_name, semester, subject, session_id, date, time, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    student['id'],
                    student['full_name'],
                    student['roll_no'] or 'N/A',
                    student['department'] or 'General',
                    student['class_name'] or 'N/A',
                    student['semester'] or '',
                    subject_str,
                    f"MANUAL-{int(datetime.datetime.now().timestamp()) % 10000}",
                    date_str,
                    now_time,
                    final_status
                ))

    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': f"Student attendance status updated to '{final_status}'!"})


def build_attendance_sql_filters(args, user_dept=None, is_admin=False):
    """
    Task: Build SQL WHERE clause and parameter list from request filter arguments for attendance endpoints.
    """
    query = 'SELECT * FROM attendance WHERE 1=1'
    params = []

    department = args.get('department', '').strip()
    if not department and not is_admin and user_dept:
        department = user_dept

    if department and department.lower() != 'all':
        query += ' AND (department = ? OR department LIKE ?)'
        params.extend([department, f"%{department}%"])

    semester = args.get('semester', '').strip()
    if semester and semester.lower() != 'all':
        query += ' AND (semester = ? OR class_name LIKE ?)'
        params.extend([semester, f"%{semester}%"])

    class_name = args.get('class_name', '').strip()
    if class_name and class_name.lower() != 'all':
        query += ' AND class_name = ?'
        params.append(class_name)

    status = args.get('status', '').strip()
    if status and status.lower() != 'all':
        query += ' AND status LIKE ?'
        params.append(f"%{status}%")

    # Date filtering: specific date, date range (from_date / to_date), or month
    date = args.get('date', '').strip()
    from_date = args.get('from_date', '').strip()
    to_date = args.get('to_date', '').strip()
    month = args.get('month', '').strip()

    if from_date and to_date:
        query += ' AND date >= ? AND date <= ?'
        params.extend([from_date, to_date])
    elif from_date:
        query += ' AND date >= ?'
        params.append(from_date)
    elif to_date:
        query += ' AND date <= ?'
        params.append(to_date)
    elif date:
        query += ' AND date = ?'
        params.append(date)
    elif month:
        query += ' AND date LIKE ?'
        params.append(f"{month}%")

    subject = args.get('subject', '').strip()
    if subject:
        query += ' AND (subject LIKE ? OR student_name LIKE ? OR roll_no LIKE ?)'
        params.extend([f"%{subject}%", f"%{subject}%", f"%{subject}%"])

    search = args.get('search', '').strip()
    if search:
        query += ' AND (student_name LIKE ? OR roll_no LIKE ? OR session_id LIKE ? OR subject LIKE ? OR class_name LIKE ? OR semester LIKE ?)'
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%", f"%{search}%", f"%{search}%", f"%{search}%"])

    return query, params


@app.route('/api/staff/attendance', methods=['GET'])
def get_staff_attendance():
    """
    Task: Query student attendance records for staff view with normal and advanced filtering.
    """
    if session.get('role') not in ['staff', 'admin']:
        return jsonify({'error': 'Unauthorized access.'}), 403

    user_id = session.get('user_id')
    is_admin = (session.get('role') == 'admin')
    conn = get_db_connection()
    staff = conn.execute('SELECT department FROM users WHERE id = ?', (user_id,)).fetchone()
    staff_dept = staff['department'] if staff else ''

    query, params = build_attendance_sql_filters(request.args, user_dept=staff_dept, is_admin=is_admin)
    query += ' ORDER BY date DESC, id DESC'
    records = [dict(r) for r in conn.execute(query, params).fetchall()]

    threshold = request.args.get('threshold', '').strip().lower()
    if threshold and threshold != 'all':
        # Filter records based on student attendance rate threshold
        # First group by student
        student_counts = {}
        for r in records:
            sid = r.get('student_id') or r.get('roll_no')
            if sid not in student_counts:
                student_counts[sid] = {'present': 0, 'total': 0}
            st = (r.get('status') or '').lower()
            if st.startswith('pres') or st == 'p':
                student_counts[sid]['present'] += 1
                student_counts[sid]['total'] += 1
            elif st.startswith('abs') or st == 'a':
                student_counts[sid]['total'] += 1

        filtered_records = []
        for r in records:
            sid = r.get('student_id') or r.get('roll_no')
            st_info = student_counts.get(sid, {'present': 0, 'total': 0})
            pct = (st_info['present'] / st_info['total'] * 100) if st_info['total'] > 0 else 100.0
            if threshold == 'critical' and pct < 45.0:
                filtered_records.append(r)
            elif threshold == 'warning' and 45.0 <= pct < 75.0:
                filtered_records.append(r)
            elif threshold == 'good' and pct >= 75.0:
                filtered_records.append(r)
        records = filtered_records

    conn.close()

    selected_dept = request.args.get('department', '').strip() or staff_dept or 'all'
    return jsonify({
        'attendance': records,
        'department': selected_dept,
        'total': len(records)
    })


@app.route('/api/admin/attendance', methods=['GET'])
def get_admin_attendance():
    """
    Task: Query global attendance records for admin view with normal & advanced filtering and student deficiency calculation.
    """
    if session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized access. Admin access required.'}), 403

    conn = get_db_connection()
    query, params = build_attendance_sql_filters(request.args, is_admin=True)
    query += ' ORDER BY date DESC, id DESC'
    records = [dict(r) for r in conn.execute(query, params).fetchall()]

    # Calculate student-wise summary for low attendance (< 45%) alerts
    student_stats = {}
    for r in records:
        sid = r.get('student_id') or r.get('roll_no')
        if not sid:
            continue
        if sid not in student_stats:
            student_stats[sid] = {
                'student_id': sid,
                'student_name': r.get('student_name', ''),
                'roll_no': r.get('roll_no', ''),
                'department': r.get('department', ''),
                'class_name': r.get('class_name', ''),
                'semester': r.get('semester', ''),
                'present_count': 0,
                'absent_count': 0,
                'leave_count': 0,
                'holiday_count': 0
            }
        st = (r.get('status') or '').lower()
        if st.startswith('pres') or st == 'p':
            student_stats[sid]['present_count'] += 1
        elif st.startswith('abs') or st == 'a':
            student_stats[sid]['absent_count'] += 1
        elif st.startswith('leave') or st == 'l':
            student_stats[sid]['leave_count'] += 1
        elif st.startswith('hol') or st == 'h':
            student_stats[sid]['holiday_count'] += 1

    low_attendance_students = []
    for sid, stat in student_stats.items():
        total_working = stat['present_count'] + stat['absent_count']
        pct = round((stat['present_count'] / total_working) * 100, 1) if total_working > 0 else 100.0
        stat['total_working'] = total_working
        stat['attendance_pct'] = pct
        if pct < 45.0:
            low_attendance_students.append(stat)

    threshold = request.args.get('threshold', '').strip().lower()
    if threshold and threshold != 'all':
        filtered_records = []
        for r in records:
            sid = r.get('student_id') or r.get('roll_no')
            stat = student_stats.get(sid)
            pct = stat['attendance_pct'] if stat else 100.0
            if threshold == 'critical' and pct < 45.0:
                filtered_records.append(r)
            elif threshold == 'warning' and 45.0 <= pct < 75.0:
                filtered_records.append(r)
            elif threshold == 'good' and pct >= 75.0:
                filtered_records.append(r)
        records = filtered_records

    conn.close()

    return jsonify({
        'attendance': records,
        'low_attendance_students': low_attendance_students,
        'total': len(records)
    })


@app.route('/api/admin/export-attendance', methods=['GET'])
def export_attendance_csv():
    """
    Task: Export filtered attendance records into downloadable CSV format with advanced filter support.
    """
    if session.get('role') not in ['admin', 'staff']:
        return jsonify({'error': 'Unauthorized access.'}), 403

    user_id = session.get('user_id')
    user_role = session.get('role')
    conn = get_db_connection()
    staff = conn.execute('SELECT department FROM users WHERE id = ?', (user_id,)).fetchone()
    staff_dept = staff['department'] if staff else ''

    query, params = build_attendance_sql_filters(request.args, user_dept=staff_dept, is_admin=(user_role == 'admin'))
    query += ' ORDER BY department ASC, date DESC, student_name ASC'

    records = conn.execute(query, params).fetchall()
    conn.close()

    import io
    import csv
    from flask import Response

    output = io.StringIO()
    writer = csv.writer(output)

    # Write CSV Header (Excel / Google Sheets standard)
    writer.writerow(['Student Name', 'Roll No', 'Department', 'Class', 'Semester', 'Subject', 'Date', 'Time', 'Status', 'Latitude', 'Longitude', 'Distance (m)'])

    for row in records:
        writer.writerow([
            row['student_name'],
            row['roll_no'],
            row['department'],
            row['class_name'],
            row['semester'] if 'semester' in row.keys() else '',
            row['subject'],
            row['date'],
            row['time'],
            row['status'],
            row['latitude'] if ('latitude' in row.keys() and row['latitude'] is not None) else '',
            row['longitude'] if ('longitude' in row.keys() and row['longitude'] is not None) else '',
            row['distance_meters'] if ('distance_meters' in row.keys() and row['distance_meters'] is not None) else ''
        ])

    csv_data = output.getvalue()
    dept = request.args.get('department', '').strip() or 'All_Departments'
    date_str = request.args.get('date', '').strip() or request.args.get('from_date', '').strip() or 'Report'
    filename = f"Attendance_Report_{dept.replace(' ', '_')}_{date_str}.csv"

    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-disposition": f"attachment; filename={filename}"}
    )


@app.route('/api/attendance/share-email', methods=['POST'])
def share_attendance_email():
    """
    Task: Share attendance report with attached CSV and styled HTML summary table to any recipient's Gmail/Email address.
    """
    if session.get('role') not in ['admin', 'staff']:
        return jsonify({'error': 'Unauthorized access. Staff or Admin rights required.'}), 403

    data = request.get_json() or {}
    recipient_email = data.get('recipient_email', '').strip()
    if not recipient_email:
        return jsonify({'error': 'Recipient email address is required.'}), 400

    custom_subject = data.get('subject', '').strip()
    notes = data.get('notes', '').strip()
    include_csv = data.get('include_csv', True)

    user_id = session.get('user_id')
    user_role = session.get('role')
    user_name = session.get('full_name', 'Faculty/Admin')
    conn = get_db_connection()
    staff = conn.execute('SELECT department, email FROM users WHERE id = ?', (user_id,)).fetchone()
    staff_dept = staff['department'] if staff else ''
    sender_user_email = staff['email'] if staff else ''

    query, params = build_attendance_sql_filters(data, user_dept=staff_dept, is_admin=(user_role == 'admin'))
    query += ' ORDER BY department ASC, date DESC, student_name ASC'

    records = [dict(r) for r in conn.execute(query, params).fetchall()]
    conn.close()

    # Calculate summary metrics
    total_records = len(records)
    present_count = sum(1 for r in records if (r.get('status') or '').lower().startswith('pres') or (r.get('status') or '').lower() == 'p')
    absent_count = sum(1 for r in records if (r.get('status') or '').lower().startswith('abs') or (r.get('status') or '').lower() == 'a')
    leave_count = sum(1 for r in records if (r.get('status') or '').lower().startswith('leave') or (r.get('status') or '').lower() == 'l')
    holiday_count = sum(1 for r in records if (r.get('status') or '').lower().startswith('hol') or (r.get('status') or '').lower() == 'h')
    working_total = present_count + absent_count
    attendance_rate = round((present_count / working_total * 100), 1) if working_total > 0 else (100.0 if total_records > 0 else 0.0)

    dept_label = data.get('department', '').strip() or staff_dept or 'All Departments'
    sem_label = data.get('semester', '').strip() or 'All Semesters'
    date_label = data.get('date', '').strip() or (f"{data.get('from_date', '')} to {data.get('to_date', '')}" if data.get('from_date') else 'All Dates')

    email_subject = custom_subject or f"AQ Attendance Report • {dept_label} ({sem_label})"

    # Generate CSV string
    import io
    import csv
    csv_buffer = io.StringIO()
    writer = csv.writer(csv_buffer)
    writer.writerow(['Student Name', 'Roll No', 'Department', 'Class', 'Semester', 'Subject', 'Date', 'Time', 'Status', 'GPS Location', 'Distance (m)'])
    for r in records:
        lat_lng = f"{r.get('latitude')}, {r.get('longitude')}" if r.get('latitude') is not None else '-'
        dist = f"{round(r.get('distance_meters'))}m" if r.get('distance_meters') is not None else '-'
        writer.writerow([
            r.get('student_name', ''),
            r.get('roll_no', ''),
            r.get('department', ''),
            r.get('class_name', ''),
            r.get('semester', ''),
            r.get('subject', ''),
            r.get('date', ''),
            r.get('time', ''),
            r.get('status', 'Present'),
            lat_lng,
            dist
        ])
    csv_content = csv_buffer.getvalue()

    # Generate Styled HTML Email Content
    table_rows_html = ""
    preview_limit = 35
    for idx, r in enumerate(records[:preview_limit]):
        st = (r.get('status') or 'Present').capitalize()
        badge_bg = '#ECFDF5' if 'Pres' in st else ('#FEF2F2' if 'Abs' in st else ('#FEF3C7' if 'Leave' in st else '#F5F3FF'))
        badge_color = '#065F46' if 'Pres' in st else ('#991B1B' if 'Abs' in st else ('#92400E' if 'Leave' in st else '#5B21B6'))
        
        table_rows_html += f"""
        <tr style="border-bottom: 1px solid #E2E8F0; background: {'#F8FAFC' if idx % 2 == 1 else '#FFFFFF'};">
            <td style="padding: 10px 12px; font-weight: 700; color: #0F172A;">{r.get('student_name', '-')}</td>
            <td style="padding: 10px 12px; font-family: monospace; color: #334155;">{r.get('roll_no', '-')}</td>
            <td style="padding: 10px 12px; color: #334155;">{r.get('class_name', '-')} ({r.get('semester', '-')})</td>
            <td style="padding: 10px 12px; color: #334155;">{r.get('subject', '-')}</td>
            <td style="padding: 10px 12px; color: #64748B;">{r.get('date', '')} {r.get('time', '')}</td>
            <td style="padding: 10px 12px; text-align: center;">
                <span style="display: inline-block; padding: 3px 10px; border-radius: 999px; font-size: 12px; font-weight: 800; background: {badge_bg}; color: {badge_color};">{st}</span>
            </td>
        </tr>
        """

    more_records_note = f"<p style='margin-top: 10px; font-size: 13px; color: #64748B;'><em>Note: Showing first {preview_limit} records of {total_records} in this email body. Please see the attached CSV file for full records.</em></p>" if total_records > preview_limit else ""

    notes_section = f"""
    <div style="margin: 20px 0; padding: 14px 18px; background: #EFF6FF; border-left: 4px solid #2563EB; border-radius: 6px; color: #1E40AF; font-size: 14px;">
        <strong>Staff / Sender Note:</strong><br>
        <span style="white-space: pre-wrap;">{notes}</span>
    </div>
    """ if notes else ""

    html_email = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #F8FAFC; color: #0F172A; margin: 0; padding: 24px; }}
            .container {{ max-width: 760px; margin: 0 auto; background: #FFFFFF; border-radius: 12px; border: 1px solid #E2E8F0; box-shadow: 0 4px 12px rgba(0,0,0,0.05); overflow: hidden; }}
            .header {{ background: linear-gradient(135deg, #0F172A 0%, #1E293B 100%); color: #FFFFFF; padding: 24px 30px; }}
            .header-title {{ margin: 0; font-size: 22px; font-weight: 800; letter-spacing: 0.5px; }}
            .header-sub {{ margin: 6px 0 0 0; font-size: 14px; color: #94A3B8; }}
            .content {{ padding: 24px 30px; }}
            .stats-grid {{ display: flex; gap: 12px; margin: 20px 0; flex-wrap: wrap; }}
            .stat-box {{ flex: 1; min-width: 120px; background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 12px; text-align: center; }}
            .stat-val {{ font-size: 22px; font-weight: 800; }}
            .stat-lbl {{ font-size: 12px; font-weight: 700; color: #64748B; text-transform: uppercase; margin-top: 4px; }}
            .badge-bar {{ display: flex; gap: 8px; flex-wrap: wrap; margin: 12px 0 20px 0; }}
            .pill {{ background: #F1F5F9; color: #334155; font-size: 12px; font-weight: 700; padding: 4px 10px; border-radius: 6px; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 15px; font-size: 13px; }}
            th {{ background: #F1F5F9; color: #475569; font-weight: 800; text-align: left; padding: 10px 12px; border-bottom: 2px solid #CBD5E1; }}
            .footer {{ background: #F8FAFC; border-top: 1px solid #E2E8F0; padding: 18px 30px; text-align: center; font-size: 12px; color: #94A3B8; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <div class="header-title">🎓 AQ Academic Portal</div>
                <div class="header-sub">Official Student Attendance & Analytics Report</div>
            </div>

            <div class="content">
                <h2 style="margin: 0 0 8px 0; font-size: 18px; color: #0F172A;">{email_subject}</h2>
                <div class="badge-bar">
                    <span class="pill">🏢 Dept: {dept_label}</span>
                    <span class="pill">📚 Sem: {sem_label}</span>
                    <span class="pill">📅 Date: {date_label}</span>
                    <span class="pill">👤 Shared by: {user_name}</span>
                </div>

                {notes_section}

                <div style="display: table; width: 100%; margin: 18px 0;">
                    <div style="display: table-row;">
                        <div style="display: table-cell; padding: 10px; background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; text-align: center; width: 20%;">
                            <div style="font-size: 22px; font-weight: 800; color: #0F172A;">{total_records}</div>
                            <div style="font-size: 11px; font-weight: 700; color: #64748B; text-transform: uppercase;">Total Logs</div>
                        </div>
                        <div style="display: table-cell; width: 2%;"></div>
                        <div style="display: table-cell; padding: 10px; background: #ECFDF5; border: 1px solid #A7F3D0; border-radius: 8px; text-align: center; width: 20%;">
                            <div style="font-size: 22px; font-weight: 800; color: #10B981;">{present_count}</div>
                            <div style="font-size: 11px; font-weight: 700; color: #065F46; text-transform: uppercase;">Present (P)</div>
                        </div>
                        <div style="display: table-cell; width: 2%;"></div>
                        <div style="display: table-cell; padding: 10px; background: #FEF2F2; border: 1px solid #FCA5A5; border-radius: 8px; text-align: center; width: 20%;">
                            <div style="font-size: 22px; font-weight: 800; color: #DC2626;">{absent_count}</div>
                            <div style="font-size: 11px; font-weight: 700; color: #991B1B; text-transform: uppercase;">Absent (A)</div>
                        </div>
                        <div style="display: table-cell; width: 2%;"></div>
                        <div style="display: table-cell; padding: 10px; background: #EFF6FF; border: 1px solid #BFDBFE; border-radius: 8px; text-align: center; width: 20%;">
                            <div style="font-size: 22px; font-weight: 800; color: #2563EB;">{attendance_rate}%</div>
                            <div style="font-size: 11px; font-weight: 700; color: #1E40AF; text-transform: uppercase;">Rate %</div>
                        </div>
                    </div>
                </div>

                <h3 style="margin: 24px 0 10px 0; font-size: 15px; font-weight: 800; color: #0F172A;">Attendance Log Breakdown</h3>
                <div style="overflow-x: auto;">
                    <table>
                        <thead>
                            <tr>
                                <th>Student Name</th>
                                <th>Roll No</th>
                                <th>Class & Sem</th>
                                <th>Subject</th>
                                <th>Date & Time</th>
                                <th style="text-align: center;">Status</th>
                            </tr>
                        </thead>
                        <tbody>
                            {table_rows_html if table_rows_html else '<tr><td colspan="6" style="padding: 20px; text-align: center; color: #94A3B8;">No attendance records found matching filters.</td></tr>'}
                        </tbody>
                    </table>
                </div>

                {more_records_note}
            </div>

            <div class="footer">
                AQ Attendance System • Automated Campus Reporting Service • Sent via {user_name}
            </div>
        </div>
    </body>
    </html>
    """

    # Dispatch Email via smtplib
    smtp_server = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
    smtp_port = int(os.environ.get('SMTP_PORT', '587'))
    smtp_email = os.environ.get('SMTP_EMAIL') or os.environ.get('MAIL_USERNAME') or os.environ.get('EMAIL_USER')
    smtp_password = os.environ.get('SMTP_PASSWORD') or os.environ.get('MAIL_PASSWORD') or os.environ.get('EMAIL_PASS')

    email_sent = False
    delivery_note = ""

    if smtp_email and smtp_password:
        import smtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        from email.mime.base import MIMEBase
        from email import encoders

        try:
            msg = MIMEMultipart('mixed')
            msg['From'] = f"AQ Academic Portal <{smtp_email}>"
            msg['To'] = recipient_email
            msg['Subject'] = email_subject

            # Attach HTML part
            html_part = MIMEText(html_email, 'html')
            msg.attach(html_part)

            # Attach CSV part
            if include_csv:
                csv_part = MIMEBase('text', 'csv')
                csv_part.set_payload(csv_content.encode('utf-8'))
                encoders.encode_base64(csv_part)
                clean_dept_name = dept_label.replace(' ', '_')
                csv_filename = f"AQ_Attendance_{clean_dept_name}.csv"
                csv_part.add_header('Content-Disposition', f'attachment; filename="{csv_filename}"')
                msg.attach(csv_part)

            # Connect and send
            recipients = [r.strip() for r in recipient_email.split(',') if r.strip()]
            with smtplib.SMTP(smtp_server, smtp_port, timeout=15) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(smtp_email, smtp_password)
                server.sendmail(smtp_email, recipients, msg.as_string())
            
            email_sent = True
            delivery_note = f"Report successfully emailed to {recipient_email} via SMTP ({smtp_server})."
        except Exception as mail_err:
            print("SMTP Error while sending email:", mail_err)
            return jsonify({
                'success': False,
                'error': f"Failed to send email via SMTP: {str(mail_err)}. Please check your Gmail App Password / SMTP settings in .env."
            }), 500
    else:
        # Fallback simulation when SMTP credentials are not yet set in .env
        email_sent = True
        delivery_note = f"Email report generated and ready for {recipient_email}. (To enable direct Gmail SMTP delivery, set SMTP_EMAIL and SMTP_PASSWORD in your .env file)."

    return jsonify({
        'success': True,
        'message': delivery_note,
        'recipient': recipient_email,
        'records_count': total_records,
        'attendance_rate': f"{attendance_rate}%",
        'simulated': not bool(smtp_email and smtp_password)
    })


def get_local_ip():
    """
    Task: Discover active local IPv4 network address for binding and server connection information.
    """
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        primary_ip = s.getsockname()[0]
        s.close()
        if primary_ip and not primary_ip.startswith('127.'):
            return primary_ip
    except Exception:
        pass

    try:
        hostname = socket.gethostname()
        for ip in socket.gethostbyname_ex(hostname)[2]:
            if not ip.startswith('127.'):
                return ip
    except Exception:
        pass

    return '127.0.0.1'

@app.route('/api/server-info', methods=['GET'])
def get_server_info():
    """
    Task: Return JSON response containing local server IP address and port details.
    """
    local_ip = get_local_ip()
    port = 5000
    mobile_url = f"http://{local_ip}:{port}"
    return jsonify({
        'success': True,
        'local_ip': local_ip,
        'port': port,
        'mobile_url': mobile_url,
        'local_url': f"http://localhost:{port}"
    })


if __name__ == '__main__':
    local_ip = get_local_ip()
    port = 5000
    print("=" * 60)
    print(" >>> AQ ATTENDANCE SYSTEM - SERVER STARTED <<<")
    print("=" * 60)
    print(f" [PC Access]     : http://localhost:{port}")
    print(f" [Mobile/LAN]    : http://{local_ip}:{port}")
    print("=" * 60)
    app.run(host='0.0.0.0', debug=True, port=port)







