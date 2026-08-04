import os
import sqlite3
from flask import Flask, render_template, request, jsonify, session, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from totp_engine import create_totp_payload, verify_totp_payload, get_seconds_remaining
from geofence import is_within_campus

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    import psycopg2
    import psycopg2.extras
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False

app = Flask(__name__, static_folder='static', static_url_path='/static')
app.secret_key = os.environ.get('SECRET_KEY', 'aq_college_super_secret_key_2026')

@app.route('/static/<path:filename>')
def serve_static(filename):
    static_dir = os.path.join(os.path.dirname(__file__), 'static')
    mimetype = 'text/css' if filename.endswith('.css') else ('application/javascript' if filename.endswith('.js') else None)
    return send_from_directory(static_dir, filename, mimetype=mimetype)


class PgRowWrapper(dict):
    """Dict subclass for PostgreSQL rows to support key indexing, list indexing, and keys()."""
    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)

    def keys(self):
        return super().keys()

class PgCursorWrapper:
    def __init__(self, cursor, conn):
        self.cursor = cursor
        self.conn = conn
        self.lastrowid = None

    def execute(self, sql, params=None):
        sql_pg = sql.replace('?', '%s')
        params_tuple = tuple(params) if params is not None else ()
        
        is_insert = sql.strip().upper().startswith('INSERT')
        if is_insert and 'RETURNING' not in sql.upper():
            query_with_returning = sql_pg + ' RETURNING id'
            try:
                self.cursor.execute(query_with_returning, params_tuple)
                res = self.cursor.fetchone()
                if res:
                    if isinstance(res, (tuple, list)) and len(res) > 0:
                        self.lastrowid = res[0]
                    elif hasattr(res, 'get'):
                        self.lastrowid = res.get('id')
                return self
            except Exception as e:
                try:
                    self.conn.rollback()
                except Exception:
                    pass

        self.cursor.execute(sql_pg, params_tuple)
        return self

    def fetchone(self):
        res = self.cursor.fetchone()
        if res is None:
            return None
        return PgRowWrapper(res)

    def fetchall(self):
        res = self.cursor.fetchall()
        return [PgRowWrapper(row) for row in res]

class PgConnWrapper:
    def __init__(self, conn):
        self.raw_conn = conn
        self.is_pg = True

    def cursor(self):
        return PgCursorWrapper(self.raw_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor), self)

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

def get_db_connection():
    db_url = os.environ.get('DATABASE_URL') or os.environ.get('SUPABASE_DB_URL') or os.environ.get('POSTGRES_URL')
    
    if db_url and HAS_PSYCOPG2:
        if db_url.startswith('postgres://'):
            db_url = db_url.replace('postgres://', 'postgresql://', 1)
        try:
            pg_conn = psycopg2.connect(db_url, sslmode='require' if 'supabase' in db_url or 'vercel-storage' in db_url else 'prefer')
            return PgConnWrapper(pg_conn)
        except Exception as e:
            print("PostgreSQL connection error, falling back to SQLite:", e)

    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    is_pg = getattr(conn, 'is_pg', False)
    cursor = conn.cursor()
    
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (student_id) REFERENCES users(id),
                UNIQUE(student_id, session_id)
            )
        ''')
        cursor.execute("ALTER TABLE attendance ADD COLUMN IF NOT EXISTS semester TEXT NOT NULL DEFAULT ''")

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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (student_id) REFERENCES users(id),
                UNIQUE(student_id, session_id)
            )
        ''')
        cursor.execute("PRAGMA table_info(attendance)")
        att_cols = [col[1] for col in cursor.fetchall()]
        if 'semester' not in att_cols:
            cursor.execute("ALTER TABLE attendance ADD COLUMN semester TEXT NOT NULL DEFAULT ''")

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
    
    conn.close()

# Initialize DB on startup
init_db()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')
    expected_role = data.get('role', '').strip().lower()
    
    if not username or not password:
        return jsonify({'success': False, 'message': 'Username and password are required.'}), 400
        
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
    conn.close()
    
    if not user:
        return jsonify({'success': False, 'message': 'Account not found. Please contact the administrator.'}), 401
        
    if not check_password_hash(user['password_hash'], password):
        return jsonify({'success': False, 'message': 'Invalid credentials.'}), 401
        
    if expected_role and user['role'] != expected_role:
        return jsonify({'success': False, 'message': f"Account found, but it is not registered as a {expected_role.capitalize()}."}), 403
        
    session['user_id'] = user['id']
    session['username'] = user['username']
    session['role'] = user['role']
    session['full_name'] = user['full_name']
    
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
    session.clear()
    return jsonify({'success': True, 'message': 'Logged out successfully.'})

@app.route('/api/admin/users', methods=['GET'])
def get_users():
    if session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized. Admin access required.'}), 403
        
    conn = get_db_connection()
    users = conn.execute('SELECT id, username, full_name, role, department, email, class_name, semester, roll_no, created_at FROM users ORDER BY id DESC').fetchall()
    conn.close()
    
    users_list = [dict(u) for u in users]
    return jsonify({'users': users_list})

@app.route('/api/admin/users', methods=['POST'])
def create_user():
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
        
    conn.execute('DELETE FROM users WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'message': 'User deleted successfully.'})

@app.route('/api/staff/students', methods=['GET'])
def get_staff_students():
    if session.get('role') not in ['staff', 'admin']:
        return jsonify({'error': 'Unauthorized access.'}), 403
        
    conn = get_db_connection()
    user_id = session.get('user_id')
    staff = conn.execute('SELECT department FROM users WHERE id = ?', (user_id,)).fetchone()
    staff_dept = staff['department'] if staff else ''

    selected_dept = request.args.get('department', '').strip()
    semester = request.args.get('semester', '').strip()

    if not selected_dept:
        selected_dept = staff_dept

    query = "SELECT id, username, full_name, role, department, email, class_name, semester, roll_no, created_at FROM users WHERE role = 'student'"
    params = []

    if selected_dept and selected_dept.lower() != 'all':
        query += " AND (department = ? OR department LIKE ?)"
        params.extend([selected_dept, f"%{selected_dept}%"])
    if semester and semester.lower() != 'all':
        query += " AND (semester = ? OR class_name LIKE ?)"
        params.extend([semester, f"%{semester}%"])

    query += " ORDER BY full_name ASC"
    students = conn.execute(query, params).fetchall()
    conn.close()
    return jsonify({'students': [dict(s) for s in students], 'department': selected_dept})


# --- ATTENDANCE MANAGEMENT & DYNAMIC TOTP APIS ---

@app.route('/api/staff/totp-qr', methods=['GET', 'POST'])
def get_staff_totp_qr():
    if session.get('role') not in ['staff', 'admin']:
        return jsonify({'error': 'Unauthorized access. Staff rights required.'}), 403

    data = request.get_json() or {} if request.method == 'POST' else request.args
    session_id = data.get('session_id', '').strip() or request.args.get('session_id', '').strip() or 'SESS-CS101'
    subject = data.get('subject', '').strip() or request.args.get('subject', '').strip() or 'Classroom Session'
    class_name = data.get('class', '').strip() or request.args.get('class', '').strip() or 'General Section'

    conn = get_db_connection()
    user_id = session.get('user_id')
    staff = conn.execute('SELECT full_name, department FROM users WHERE id = ?', (user_id,)).fetchone()
    conn.close()

    department = staff['department'] if (staff and staff['department']) else 'Computer Science'
    teacher_name = staff['full_name'] if (staff and staff['full_name']) else session.get('full_name', 'Faculty Staff')

    payload = create_totp_payload(
        session_id=session_id,
        subject=subject,
        class_name=class_name,
        department=department,
        teacher_name=teacher_name,
        step=15
    )
    return jsonify(payload)


@app.route('/api/student/mark-attendance', methods=['POST'])
def mark_student_attendance():
    if session.get('role') != 'student':
        return jsonify({'error': 'Unauthorized access. Student account required.'}), 403

    user_id = session.get('user_id')
    data = request.get_json() or {}

    # Verify 15-Second Dynamic TOTP Token if TOTP payload present
    if data.get('totp_token') or data.get('type') == 'aq_dynamic_totp_qr':
        is_valid_totp, totp_err_msg = verify_totp_payload(data, step=15, window_buffer=1)
        if not is_valid_totp:
            return jsonify({'error': totp_err_msg}), 400

    # --- Geolocation Verification ---
    # Require the student's device to report GPS coordinates and confirm
    # they are physically within the campus radius before accepting the
    # scan. This blocks QR codes forwarded off-campus (e.g. via WhatsApp)
    # from being scanned remotely, since a phone at home will fail the
    # distance check even with a perfectly valid, unexpired TOTP token.
    student_lat = data.get('lat')
    student_lng = data.get('lng')

    if student_lat is None or student_lng is None:
        return jsonify({
            'error': 'Location access is required to mark attendance. Please allow location permission and try again.'
        }), 400

    inside_campus, distance = is_within_campus(student_lat, student_lng)
    if not inside_campus:
        if distance < 0:
            return jsonify({'error': 'Invalid location data received. Please try scanning again.'}), 400
        return jsonify({
            'error': f'Attendance can only be marked from campus. You appear to be about {int(distance)}m away from the permitted zone.'
        }), 400

    session_id = data.get('session_id', '').strip() or data.get('session', '').strip()
    subject = data.get('subject', '').strip() or 'Classroom Attendance'
    class_name = data.get('class', '').strip() or data.get('class_name', '').strip()
    department = data.get('department', '').strip()
    date_str = data.get('date', '').strip()
    time_str = data.get('time', '').strip()

    if not session_id:
        import time
        session_id = f"ATT-{int(time.time()) % 100000}"

    conn = get_db_connection()
    student = conn.execute('SELECT id, full_name, roll_no, department, class_name, semester FROM users WHERE id = ?', (user_id,)).fetchone()

    if not student:
        conn.close()
        return jsonify({'error': 'Student record not found.'}), 404

    import datetime
    now = datetime.datetime.now()
    if not date_str:
        date_str = now.strftime('%Y-%m-%d')
    if not time_str:
        time_str = now.strftime('%I:%M:%S %p')

    # Check if student already has a Present record or scanned QR for today
    existing_today = conn.execute('''
        SELECT id, status, subject FROM attendance 
        WHERE student_id = ? AND date = ?
    ''', (user_id, date_str)).fetchone()

    if existing_today:
        conn.close()
        return jsonify({'error': f'Attendance already marked for today ({date_str})! QR code scanning is restricted to once per day.'}), 400

    student_name = student['full_name']
    roll_no = student['roll_no'] if student['roll_no'] else 'N/A'
    student_dept = student['department'] if student['department'] else (department or 'General Studies')
    student_class = student['class_name'] if student['class_name'] else (class_name or 'General Class')
    student_sem = student['semester'] if ('semester' in student.keys() and student['semester']) else ''

    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO attendance (student_id, student_name, roll_no, department, class_name, semester, subject, session_id, date, time, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Present')
    ''', (user_id, student_name, roll_no, student_dept, student_class, student_sem, subject, session_id, date_str, time_str))
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
            'status': 'Present'
        }
    })

@app.route('/api/student/attendance', methods=['GET'])
def get_student_attendance():
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
    conn = get_db_connection()
    records = conn.execute('SELECT * FROM holidays ORDER BY date ASC').fetchall()
    conn.close()
    return jsonify({'holidays': [dict(r) for r in records]})

@app.route('/api/holidays', methods=['POST'])
def create_holiday():
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


@app.route('/api/staff/attendance', methods=['GET'])
def get_staff_attendance():
    if session.get('role') not in ['staff', 'admin']:
        return jsonify({'error': 'Unauthorized access.'}), 403

    user_id = session.get('user_id')
    conn = get_db_connection()
    staff = conn.execute('SELECT department FROM users WHERE id = ?', (user_id,)).fetchone()
    dept = staff['department'] if staff else ''

    selected_dept = request.args.get('department', '').strip()
    if not selected_dept:
        selected_dept = dept

    subject = request.args.get('subject', '').strip()
    date_filter = request.args.get('date', '').strip()
    month = request.args.get('month', '').strip()
    semester = request.args.get('semester', '').strip()

    query = 'SELECT * FROM attendance WHERE 1=1'
    params = []

    if selected_dept and selected_dept.lower() != 'all':
        query += ' AND (department = ? OR department LIKE ?)'
        params.extend([selected_dept, f"%{selected_dept}%"])
    if subject:
        query += ' AND (subject LIKE ? OR student_name LIKE ? OR roll_no LIKE ?)'
        params.extend([f"%{subject}%", f"%{subject}%", f"%{subject}%"])
    if date_filter:
        query += ' AND date = ?'
        params.append(date_filter)
    elif month:
        query += ' AND date LIKE ?'
        params.append(f"{month}%")
    if semester and semester.lower() != 'all':
        query += ' AND (semester = ? OR class_name LIKE ?)'
        params.extend([semester, f"%{semester}%"])

    query += ' ORDER BY date DESC, id DESC'
    records = conn.execute(query, params).fetchall()
    conn.close()

    return jsonify({
        'attendance': [dict(r) for r in records],
        'department': selected_dept
    })





@app.route('/api/admin/attendance', methods=['GET'])
def get_admin_attendance():
    if session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized access. Admin access required.'}), 403

    department = request.args.get('department', '').strip()
    subject = request.args.get('subject', '').strip()
    date = request.args.get('date', '').strip()
    month = request.args.get('month', '').strip()
    semester = request.args.get('semester', '').strip()
    search = request.args.get('search', '').strip()

    query = 'SELECT * FROM attendance WHERE 1=1'
    params = []

    if department and department.lower() != 'all':
        query += ' AND department = ?'
        params.append(department)
    if subject:
        query += ' AND subject LIKE ?'
        params.append(f"%{subject}%")
    if date:
        query += ' AND date = ?'
        params.append(date)
    elif month:
        query += ' AND date LIKE ?'
        params.append(f"{month}%")
    if semester and semester.lower() != 'all':
        query += ' AND (semester = ? OR class_name LIKE ?)'
        params.extend([semester, f"%{semester}%"])
    if search:
        query += ' AND (student_name LIKE ? OR roll_no LIKE ? OR session_id LIKE ? OR subject LIKE ? OR class_name LIKE ? OR semester LIKE ?)'
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%", f"%{search}%", f"%{search}%", f"%{search}%"])

    query += ' ORDER BY date DESC, id DESC'
    conn = get_db_connection()
    records = [dict(r) for r in conn.execute(query, params).fetchall()]

    # Calculate student-wise summary for low attendance (< 45%) alerts
    student_stats = {}
    for r in records:
        sid = r.get('student_id')
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
                'absent_count': 0
            }
        st = (r.get('status') or '').lower()
        if st.startswith('pres') or st == 'p':
            student_stats[sid]['present_count'] += 1
        elif st.startswith('abs') or st == 'a':
            student_stats[sid]['absent_count'] += 1

    low_attendance_students = []
    for sid, stat in student_stats.items():
        total_working = stat['present_count'] + stat['absent_count']
        pct = round((stat['present_count'] / total_working) * 100, 1) if total_working > 0 else 100.0
        stat['total_working'] = total_working
        stat['attendance_pct'] = pct
        if pct < 45.0:
            low_attendance_students.append(stat)

    conn.close()

    return jsonify({
        'attendance': records,
        'low_attendance_students': low_attendance_students
    })


@app.route('/api/admin/export-attendance', methods=['GET'])
def export_attendance_csv():
    if session.get('role') not in ['admin', 'staff']:
        return jsonify({'error': 'Unauthorized access.'}), 403

    department = request.args.get('department', '').strip()
    date = request.args.get('date', '').strip()
    month = request.args.get('month', '').strip()
    semester = request.args.get('semester', '').strip()

    query = 'SELECT student_name, roll_no, department, class_name, semester, subject, date, time, session_id, status FROM attendance WHERE 1=1'
    params = []

    if department and department.lower() != 'all':
        query += ' AND department = ?'
        params.append(department)
    if date:
        query += ' AND date = ?'
        params.append(date)
    elif month:
        query += ' AND date LIKE ?'
        params.append(f"{month}%")
    if semester and semester.lower() != 'all':
        query += ' AND (semester = ? OR class_name LIKE ?)'
        params.extend([semester, f"%{semester}%"])

    query += ' ORDER BY department ASC, date DESC, student_name ASC'

    conn = get_db_connection()
    records = conn.execute(query, params).fetchall()
    conn.close()

    import io
    import csv
    from flask import Response

    output = io.StringIO()
    writer = csv.writer(output)

    # Write CSV Header (Excel / Google Sheets standard)
    writer.writerow(['Student Name', 'Roll No', 'Department', 'Class', 'Semester', 'Subject', 'Date', 'Time', 'Session ID', 'Status'])

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
            row['session_id'],
            row['status']
        ])


    csv_data = output.getvalue()
    dept_label = department if (department and department.lower() != 'all') else 'All_Departments'
    filename = f"Attendance_Report_{dept_label}_{month or 'All'}.csv"

    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-disposition": f"attachment; filename={filename}"}
    )

def get_local_ip():
    """Find local network IPv4 address for mobile/LAN access."""
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
    print(f" [Mobile Access] : Connect phone to the same Wi-Fi network and open:")
    print(f"                   http://{local_ip}:{port}")
    print("=" * 60)
    app.run(host='0.0.0.0', debug=True, port=port)







