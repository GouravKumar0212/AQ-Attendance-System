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
        """
        Task: Set up isolated temporary test database environment and seed initial test accounts.
        """
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
        """
        Task: Clean up temporary database files and environment overrides post test run.
        """
        os.close(self.db_fd)
        if 'TEST_DB_PATH' in os.environ:
            del os.environ['TEST_DB_PATH']
        if os.path.exists(self.db_path):
            try:
                os.unlink(self.db_path)
            except Exception:
                pass

    def login(self, username, password, role=None):
        """
        Task: Execute test client login request for a given user account.
        """
        payload = {'username': username, 'password': password}
        if role:
            payload['role'] = role
        return self.app.post('/api/login', data=json.dumps(payload), content_type='application/json')

    def logout(self):
        """
        Task: Execute test client logout request.
        """
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
        self.assertIn('latitude', data['attendance'])
        self.assertIn('longitude', data['attendance'])
        self.assertIn('distance_meters', data['attendance'])

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

    def test_11_permanent_qr_engine_and_api(self):
        """Test permanent QR generation, API payload, and geolocation validation."""
        from totp_engine import create_permanent_qr_payload, verify_totp_payload

        # 1. Staff GET /api/staff/totp-qr endpoint (Permanent QR)
        self.login('cs_faculty', 'staff123')
        res = self.app.get('/api/staff/totp-qr?session_id=PERM-CS-01&subject=Whole%20Day%20Attendance&department=Computer%20Science&class=B.Tech')
        self.assertEqual(res.status_code, 200)
        payload = json.loads(res.data)
        self.assertIn(payload['type'], ['aq_permanent_qr', 'aq_static_qr'])
        self.assertEqual(payload['session_id'], 'PERM-CS-01')
        self.assertTrue(payload.get('never_expires', False))
        self.assertIn('signature', payload)
        self.assertEqual(payload['campus_lat'], 24.495374689123384)
        self.assertEqual(payload['campus_lng'], 72.80818369745779)

        self.logout()

        # 2. Student scanning valid permanent QR payload with valid campus coordinates
        self.login('student2', 'student123')
        payload['lat'] = 24.495374689123384
        payload['lng'] = 72.80818369745779
        payload['date'] = '2026-08-18'
        mark_res = self.app.post('/api/student/mark-attendance', data=json.dumps(payload), content_type='application/json')
        self.assertEqual(mark_res.status_code, 200)
        self.assertTrue(json.loads(mark_res.data)['success'])

    def test_12_geolocation_rejection_off_campus(self):
        """Test rejection when student is outside campus radius."""
        self.login('student1', 'student123')

        off_campus_payload = {
            'type': 'aq_permanent_qr',
            'session_id': 'PERM-GEOLOC-99',
            'subject': 'Whole Day Attendance',
            'date': '2026-08-18',
            'lat': 28.6139, # Delhi lat (far off campus)
            'lng': 77.2090  # Delhi lng
        }
        res_invalid = self.app.post('/api/student/mark-attendance', data=json.dumps(off_campus_payload), content_type='application/json')
        self.assertEqual(res_invalid.status_code, 400)
        self.assertIn('campus', json.loads(res_invalid.data)['error'].lower())

    def test_13_multi_date_permanent_qr_attendance(self):
        """Test that the EXACT SAME permanent QR code works seamlessly across multiple different dates and enforces 1 scan per day."""
        self.login('student1', 'student123')

        # One single permanent QR code generated once for the classroom
        permanent_qr_payload = {
            'type': 'aq_permanent_qr',
            'session_id': 'PERM-CLASSROOM-CS-2026',
            'subject': 'Whole Day Attendance',
            'class': 'B.Tech CS',
            'department': 'Computer Science',
            'never_expires': True,
            'lat': 24.495374689123384, # On-campus GPS lat
            'lng': 72.80818369745779   # On-campus GPS lng
        }

        # --- DAY 1: 2026-08-18 ---
        permanent_qr_payload['date'] = '2026-08-18'
        permanent_qr_payload['time'] = '09:05:00 AM'
        res_day1 = self.app.post('/api/student/mark-attendance', data=json.dumps(permanent_qr_payload), content_type='application/json')
        self.assertEqual(res_day1.status_code, 200)
        data_day1 = json.loads(res_day1.data)
        self.assertTrue(data_day1['success'])
        self.assertEqual(data_day1['attendance']['date'], '2026-08-18')

        # Attempt duplicate scan on Day 1 (should be blocked)
        res_dup_day1 = self.app.post('/api/student/mark-attendance', data=json.dumps(permanent_qr_payload), content_type='application/json')
        self.assertEqual(res_dup_day1.status_code, 400)
        self.assertIn('already marked for today', json.loads(res_dup_day1.data)['error'].lower())

        # --- DAY 2: 2026-08-19 (Next Day - SAME Permanent QR Code) ---
        permanent_qr_payload['date'] = '2026-08-19'
        permanent_qr_payload['time'] = '09:12:00 AM'
        res_day2 = self.app.post('/api/student/mark-attendance', data=json.dumps(permanent_qr_payload), content_type='application/json')
        self.assertEqual(res_day2.status_code, 200)
        data_day2 = json.loads(res_day2.data)
        self.assertTrue(data_day2['success'])
        self.assertEqual(data_day2['attendance']['date'], '2026-08-19')

        # Duplicate scan on Day 2 should be blocked
        res_dup_day2 = self.app.post('/api/student/mark-attendance', data=json.dumps(permanent_qr_payload), content_type='application/json')
        self.assertEqual(res_dup_day2.status_code, 400)
        self.assertIn('already marked for today', json.loads(res_dup_day2.data)['error'].lower())

        # --- DAY 3: 2026-08-20 (Third Day - SAME Permanent QR Code) ---
        permanent_qr_payload['date'] = '2026-08-20'
        permanent_qr_payload['time'] = '09:02:00 AM'
        res_day3 = self.app.post('/api/student/mark-attendance', data=json.dumps(permanent_qr_payload), content_type='application/json')
        self.assertEqual(res_day3.status_code, 200)
        data_day3 = json.loads(res_day3.data)
        self.assertTrue(data_day3['success'])
        self.assertEqual(data_day3['attendance']['date'], '2026-08-20')

        # Verify that all 3 attendance records exist in the database for student1
        res_logs = self.app.get('/api/student/attendance')
        self.assertEqual(res_logs.status_code, 200)
        logs = json.loads(res_logs.data)['attendance']
        dates_recorded = [r['date'] for r in logs]
        self.assertIn('2026-08-18', dates_recorded)
        self.assertIn('2026-08-19', dates_recorded)
        self.assertIn('2026-08-20', dates_recorded)

    def test_14_missing_or_invalid_location(self):
        """Test rejection when GPS location coordinates are invalid or missing."""
        self.login('student1', 'student123')

        # Invalid out-of-bounds latitude
        invalid_coords_payload = {
            'type': 'aq_permanent_qr',
            'session_id': 'PERM-TEST-01',
            'subject': 'Whole Day Attendance',
            'date': '2026-08-25',
            'lat': 999.0,
            'lng': 72.8081
        }
        res_invalid = self.app.post('/api/student/mark-attendance', data=json.dumps(invalid_coords_payload), content_type='application/json')
        self.assertEqual(res_invalid.status_code, 400)

    def test_15_staff_student_list_semester_and_search_filters(self):
        """Test Staff Student List filtering by semester and search term."""
        self.login('cs_faculty', 'staff123')

        # 1. Filter by specific semester (Semester 4)
        res_sem = self.app.get('/api/staff/students?semester=Semester%204')
        self.assertEqual(res_sem.status_code, 200)
        data_sem = json.loads(res_sem.data)
        self.assertTrue(data_sem['success'])
        students = data_sem['students']
        self.assertTrue(len(students) > 0)
        for s in students:
            self.assertEqual(s['semester'], 'Semester 4')
            self.assertEqual(s['department'], 'Computer Science')

        # 2. Filter by semester that has no students (e.g. Semester 8)
        res_empty = self.app.get('/api/staff/students?semester=Semester%208')
        self.assertEqual(res_empty.status_code, 200)
        data_empty = json.loads(res_empty.data)
        self.assertEqual(len(data_empty['students']), 0)

        # 3. Search by student name
        res_search = self.app.get('/api/staff/students?search=Alice')
        self.assertEqual(res_search.status_code, 200)
        data_search = json.loads(res_search.data)
        self.assertTrue(any('Alice' in s['full_name'] for s in data_search['students']))

        # 4. Search by roll number
        res_roll = self.app.get('/api/staff/students?search=CS-101')
        self.assertEqual(res_roll.status_code, 200)
        data_roll = json.loads(res_roll.data)
        self.assertEqual(len(data_roll['students']), 1)
        self.assertEqual(data_roll['students'][0]['roll_no'], 'CS-101')

    def test_16_advanced_attendance_filters(self):
        """Test advanced attendance filtering by date range, status, class, and threshold."""
        self.login('admin', 'admin123')

        # Insert some test attendance rows across various dates
        with app.app_context():
            conn = get_db_connection()
            st = conn.execute("SELECT id FROM users WHERE username = 'student1'").fetchone()
            st_id = st['id']
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO attendance (student_id, student_name, roll_no, department, class_name, semester, subject, session_id, date, time, status)
                VALUES (?, 'Alice Smith', 'CS-101', 'Computer Science', 'B.Tech CS', 'Semester 4', 'Operating Systems', 'SESS-ADV', '2026-08-10', '10:00:00 AM', 'Present')
            ''', (st_id,))
            cursor.execute('''
                INSERT INTO attendance (student_id, student_name, roll_no, department, class_name, semester, subject, session_id, date, time, status)
                VALUES (?, 'Alice Smith', 'CS-101', 'Computer Science', 'B.Tech CS', 'Semester 4', 'Operating Systems', 'SESS-ADV', '2026-08-11', '10:00:00 AM', 'Absent')
            ''', (st_id,))
            conn.commit()
            conn.close()

        # Filter by date range (from_date & to_date)
        res_range = self.app.get('/api/admin/attendance?from_date=2026-08-10&to_date=2026-08-11')
        self.assertEqual(res_range.status_code, 200)
        data_range = json.loads(res_range.data)
        dates = [r['date'] for r in data_range['attendance']]
        self.assertIn('2026-08-10', dates)
        self.assertIn('2026-08-11', dates)

        # Filter by status = 'Absent'
        res_absent = self.app.get('/api/admin/attendance?status=Absent')
        self.assertEqual(res_absent.status_code, 200)
        data_absent = json.loads(res_absent.data)
        for r in data_absent['attendance']:
            self.assertEqual(r['status'], 'Absent')

        # Filter by class_name = 'B.Tech CS'
        res_class = self.app.get('/api/admin/attendance?class_name=B.Tech%20CS')
        self.assertEqual(res_class.status_code, 200)
        data_class = json.loads(res_class.data)
        for r in data_class['attendance']:
            self.assertEqual(r['class_name'], 'B.Tech CS')

    def test_17_export_csv_without_session_id(self):
        """Test export CSV endpoint excludes Session ID column as requested."""
        self.login('admin', 'admin123')

        res_csv = self.app.get('/api/admin/export-attendance?department=Computer%20Science')
        self.assertEqual(res_csv.status_code, 200)
        self.assertIn('text/csv', res_csv.headers['Content-Type'])
        csv_text = res_csv.data.decode('utf-8')
        
        # Check header
        first_line = csv_text.splitlines()[0]
        self.assertNotIn('Session ID', first_line)
        self.assertNotIn('Session Code', first_line)
        self.assertIn('Student Name', first_line)
        self.assertIn('Roll No', first_line)
        self.assertIn('Status', first_line)

    def test_18_share_attendance_report_email(self):
        """Test share report to any recipient email endpoint."""
        self.login('admin', 'admin123')

        payload = {
            'recipient_email': 'faculty_dean@university.edu',
            'subject': 'Monthly Attendance Summary - CS Dept',
            'notes': 'Please find the monthly report attached.',
            'department': 'Computer Science',
            'semester': 'Semester 4',
            'include_csv': True,
            'include_html': True
        }

        res = self.app.post('/api/attendance/share-email', data=json.dumps(payload), content_type='application/json')
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data)
        self.assertTrue(data['success'])
        self.assertEqual(data['recipient'], 'faculty_dean@university.edu')
        self.assertIn('records_count', data)

        # Missing recipient email should fail
        res_fail = self.app.post('/api/attendance/share-email', data=json.dumps({'recipient_email': ''}), content_type='application/json')
        self.assertEqual(res_fail.status_code, 400)

if __name__ == '__main__':
    import time
    unittest.main()


