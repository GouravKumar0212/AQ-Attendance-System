import unittest
import json
import os
import tempfile
import sys

# Unset external postgres environment variables for isolated SQLite test run
for env_key in ['DATABASE_URL', 'SUPABASE_DB_URL', 'POSTGRES_URL']:
    if env_key in os.environ:
        del os.environ[env_key]

# Ensure AQ directory is in path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app import app, init_db, get_db_connection
from werkzeug.security import generate_password_hash

class AQTestCase(unittest.TestCase):
    def setUp(self):
        # Ensure postgres env vars remain unset
        for env_key in ['DATABASE_URL', 'SUPABASE_DB_URL', 'POSTGRES_URL']:
            if env_key in os.environ:
                del os.environ[env_key]

        # Create a temporary database file for isolated testing
        self.db_fd, self.db_path = tempfile.mkstemp(suffix='.db')
        app.config['TESTING'] = True
        app.config['SECRET_KEY'] = 'test_secret_key_2026'
        
        # Override get_db_path logic for testing
        os.environ['TEST_DB_PATH'] = self.db_path
        
        self.app = app.test_client()
        
        # Initialize test DB schema via init_db
        with app.app_context():
            init_db()
            
            # Seed test users & data
            conn = get_db_connection()
            cursor = conn.cursor()

            admin_pass = generate_password_hash('admin123')
            staff_pass = generate_password_hash('staff123')
            student1_pass = generate_password_hash('student123')
            student2_pass = generate_password_hash('student123')

            # Clean users except default admin
            cursor.execute("DELETE FROM users WHERE username != 'admin'")

            cursor.execute('''
                INSERT INTO users (username, password_hash, full_name, role, department, email, class_name, semester, roll_no)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', ('cs_faculty', staff_pass, 'Dr. Smith', 'staff', 'Computer Science', 'smith@college.edu', 'B.Tech CS', 'Semester 4', 'FAC-01'))

            cursor.execute('''
                INSERT INTO users (username, password_hash, full_name, role, department, email, class_name, semester, roll_no)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', ('student1', student1_pass, 'Alice Johnson', 'student', 'Computer Science', 'alice@college.edu', 'B.Tech CS', 'Semester 4', 'CS-101'))

            cursor.execute('''
                INSERT INTO users (username, password_hash, full_name, role, department, email, class_name, semester, roll_no)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', ('student2', student2_pass, 'Bob Lee', 'student', 'Computer Science', 'bob@college.edu', 'B.Tech CS', 'Semester 4', 'CS-102'))

            conn.commit()
            conn.close()

    def tearDown(self):
        os.close(self.db_fd)
        if 'TEST_DB_PATH' in os.environ:
            del os.environ['TEST_DB_PATH']
        if os.path.exists(self.db_path):
            try:
                os.unlink(self.db_path)
            except Exception:
                pass

    def login(self, username, password, role=None):
        payload = {'username': username, 'password': password}
        if role:
            payload['role'] = role
        return self.app.post('/api/login', data=json.dumps(payload), content_type='application/json')

    def logout(self):
        return self.app.post('/api/logout')

    # --- TEST CASES ---

    def test_01_index_page(self):
        """Verify index.html route loads successfully."""
        response = self.app.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'AQ', response.data)

    def test_02_login_success(self):
        """Test successful authentication for Admin, Staff, Student."""
        res_admin = self.login('admin', 'admin123', 'admin')
        self.assertEqual(res_admin.status_code, 200)
        data = json.loads(res_admin.data)
        self.assertTrue(data['success'])
        self.assertEqual(data['user']['role'], 'admin')

        self.logout()

        res_staff = self.login('cs_faculty', 'staff123', 'staff')
        self.assertEqual(res_staff.status_code, 200)
        data = json.loads(res_staff.data)
        self.assertTrue(data['success'])

        self.logout()

        res_student = self.login('student1', 'student123', 'student')
        self.assertEqual(res_student.status_code, 200)
        data = json.loads(res_student.data)
        self.assertTrue(data['success'])

    def test_03_login_failures(self):
        """Test invalid credentials and role mismatch handling."""
        res_wrong_pass = self.login('admin', 'wrongpassword')
        self.assertEqual(res_wrong_pass.status_code, 401)

        res_wrong_user = self.login('nonexistent', 'pass')
        self.assertEqual(res_wrong_user.status_code, 401)

        res_wrong_role = self.login('student1', 'student123', 'admin')
        self.assertEqual(res_wrong_role.status_code, 403)

    def test_04_user_session_me(self):
        """Test /api/me endpoint."""
        # Unauthenticated
        res = self.app.get('/api/me')
        self.assertEqual(res.status_code, 200)
        self.assertFalse(json.loads(res.data)['authenticated'])

        # Authenticated
        self.login('student1', 'student123')
        res = self.app.get('/api/me')
        data = json.loads(res.data)
        self.assertTrue(data['authenticated'])
        self.assertEqual(data['user']['username'], 'student1')

    def test_05_admin_user_management(self):
        """Test Admin creating and deleting users."""
        self.login('admin', 'admin123')
        
        # Get users
        res = self.app.get('/api/admin/users')
        self.assertEqual(res.status_code, 200)
        users = json.loads(res.data)['users']
        self.assertGreaterEqual(len(users), 3)

        # Create user
        new_user = {
            'username': 'new_student',
            'password': 'password123',
            'full_name': 'Charlie Brown',
            'role': 'student',
            'department': 'IT',
            'email': 'charlie@college.edu',
            'class_name': 'B.Tech IT',
            'semester': 'Semester 2',
            'roll_no': 'IT-201'
        }
        res_create = self.app.post('/api/admin/users', data=json.dumps(new_user), content_type='application/json')
        self.assertEqual(res_create.status_code, 201)
        created = json.loads(res_create.data)
        new_id = created['user']['id']

        # Delete user
        res_delete = self.app.delete(f'/api/admin/users/{new_id}')
        self.assertEqual(res_delete.status_code, 200)

        # Attempt to delete admin user (should fail)
        res_del_admin = self.app.delete('/api/admin/users/1')
        self.assertEqual(res_del_admin.status_code, 400)

    def test_06_student_mark_attendance(self):
        """Test student QR attendance marking and once-per-day rule."""
        self.login('student1', 'student123')
        
        mark_data = {
            'session_id': 'TEST-SESS-001',
            'subject': 'Data Structures',
            'date': '2026-08-03',
            'time': '10:00:00 AM'
        }
        res = self.app.post('/api/student/mark-attendance', data=json.dumps(mark_data), content_type='application/json')
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data)
        self.assertTrue(data['success'])
        self.assertEqual(data['attendance']['status'], 'Present')

        # Try marking again for same date (Single scan per day rule enforcement)
        res_duplicate = self.app.post('/api/student/mark-attendance', data=json.dumps(mark_data), content_type='application/json')
        self.assertEqual(res_duplicate.status_code, 400)
        self.assertIn('already marked', json.loads(res_duplicate.data)['error'].lower())

    def test_07_holiday_management(self):
        """Test Staff/Admin creating holidays and auto-applying to students."""
        self.login('cs_faculty', 'staff123')
        
        holiday_data = {
            'date': '2026-08-15',
            'title': 'Independence Day',
            'department': 'Computer Science'
        }
        res = self.app.post('/api/holidays', data=json.dumps(holiday_data), content_type='application/json')
        self.assertEqual(res.status_code, 200)
        self.assertTrue(json.loads(res.data)['success'])

        # Verify holiday is in holidays list
        res_get = self.app.get('/api/holidays')
        holidays = json.loads(res_get.data)['holidays']
        self.assertTrue(any(h['title'] == 'Independence Day' for h in holidays))

    def test_08_attendance_status_override(self):
        """Test Staff/Admin updating student attendance status inline."""
        self.login('cs_faculty', 'staff123')

        # Get student ID for student2
        with app.app_context():
            conn = get_db_connection()
            st = conn.execute("SELECT id FROM users WHERE username = 'student2'").fetchone()
            st_id = st['id']
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO attendance (student_id, student_name, roll_no, department, class_name, semester, subject, session_id, date, time, status)
                VALUES (?, 'Bob Lee', 'CS-102', 'Computer Science', 'B.Tech CS', 'Semester 4', 'Algorithms', 'SESS-100', '2026-08-01', '09:00:00 AM', 'Present')
            ''', (st_id,))
            conn.commit()
            att_id = cursor.lastrowid
            conn.close()

        # Update status to Absent
        override_payload = {
            'attendance_id': att_id,
            'status': 'Absent'
        }
        res = self.app.post('/api/attendance/update-status', data=json.dumps(override_payload), content_type='application/json')
        self.assertEqual(res.status_code, 200)
        self.assertTrue(json.loads(res.data)['success'])

    def test_09_admin_dashboard_and_low_attendance_alerts(self):
        """Test Admin attendance retrieval and low attendance alert calculation."""
        self.login('admin', 'admin123')

        # Add 5 absent records for Alice to bring her rate under 45%
        with app.app_context():
            conn = get_db_connection()
            st = conn.execute("SELECT id FROM users WHERE username = 'student1'").fetchone()
            st_id = st['id']
            cursor = conn.cursor()
            for i in range(1, 6):
                cursor.execute('''
                    INSERT INTO attendance (student_id, student_name, roll_no, department, class_name, semester, subject, session_id, date, time, status)
                    VALUES (?, 'Alice Johnson', 'CS-101', 'Computer Science', 'B.Tech CS', 'Semester 4', 'DBMS', ?, ?, '09:00:00 AM', 'Absent')
                ''', (st_id, f'SESS-ABS-{i}', f'2026-07-0{i}'))
            conn.commit()
            conn.close()

        res = self.app.get('/api/admin/attendance')
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data)
        self.assertIn('attendance', data)
        self.assertIn('low_attendance_students', data)
        
        # Verify low attendance student detection (< 45%)
        low_st = data['low_attendance_students']
        self.assertTrue(len(low_st) > 0)
        self.assertEqual(low_st[0]['student_name'], 'Alice Johnson')

    def test_10_csv_export(self):
        """Test CSV Export endpoint."""
        self.login('admin', 'admin123')
        res = self.app.get('/api/admin/export-attendance?department=Computer%20Science')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.mimetype, 'text/csv')
        self.assertIn(b'Student Name,Roll No,Department', res.data)

    def test_11_totp_engine_and_api(self):
        """Test 15-second dynamic TOTP generation, API payload, and validation."""
        from totp_engine import generate_totp_token, verify_totp_token, create_totp_payload, verify_totp_payload, get_secret_base32

        # 1. Direct TOTP Token generation & verification
        secret = get_secret_base32("TEST-SESS-999")
        token = generate_totp_token(secret, step=15)
        self.assertEqual(len(token), 6)
        self.assertTrue(token.isdigit())
        self.assertTrue(verify_totp_token(secret, token, step=15))

        # 2. Staff GET /api/staff/totp-qr endpoint
        self.login('cs_faculty', 'staff123')
        res = self.app.get('/api/staff/totp-qr?session_id=SESS-TOTP-01&subject=Algorithms')
        self.assertEqual(res.status_code, 200)
        payload = json.loads(res.data)
        self.assertEqual(payload['type'], 'aq_dynamic_totp_qr')
        self.assertEqual(payload['session_id'], 'SESS-TOTP-01')
        self.assertIn('totp_token', payload)

        self.logout()

        # 3. Student scanning valid active TOTP payload
        self.login('student2', 'student123')
        mark_res = self.app.post('/api/student/mark-attendance', data=json.dumps(payload), content_type='application/json')
        self.assertEqual(mark_res.status_code, 200)
        self.assertTrue(json.loads(mark_res.data)['success'])

    def test_12_totp_rejection_after_expiration(self):
        """Test rejection of stale/invalid TOTP tokens (> 15 seconds old)."""
        from totp_engine import generate_totp_token, get_secret_base32

        self.login('student1', 'student123')

        secret = get_secret_base32("SESS-EXPIRED-99")
        # Token generated 45 seconds ago (3 steps back, beyond the 1-step buffer)
        stale_time = int(time.time()) - 45
        stale_token = generate_totp_token(secret, step=15, current_timestamp=stale_time)

        invalid_payload = {
            'type': 'aq_dynamic_totp_qr',
            'session_id': 'SESS-EXPIRED-99',
            'subject': 'Data Structures',
            'totp_token': '000000', # Invalid code
            'step': 15
        }
        res_invalid = self.app.post('/api/student/mark-attendance', data=json.dumps(invalid_payload), content_type='application/json')
        self.assertEqual(res_invalid.status_code, 400)
        self.assertIn('expired or invalid', json.loads(res_invalid.data)['error'].lower())

if __name__ == '__main__':
    import time
    unittest.main()
