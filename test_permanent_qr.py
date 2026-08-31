import unittest
import json
import os
import tempfile
import sys

# Unset external postgres environment variables for isolated SQLite test run
for env_key in ['DATABASE_URL', 'SUPABASE_DB_URL', 'POSTGRES_URL']:
    if env_key in os.environ:
        del os.environ[env_key]

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app import app, init_db, get_db_connection
from werkzeug.security import generate_password_hash
from geofence import is_within_campus, distance_meters, COLLEGE_LATITUDE, COLLEGE_LONGITUDE, MAX_RADIUS_METERS
from totp_engine import (
    create_permanent_qr_payload,
    verify_totp_payload,
    run_staff_generator,
    verify_student_attendance_payload
)

class PermanentQRFullSuite(unittest.TestCase):
    def setUp(self):
        for env_key in ['DATABASE_URL', 'SUPABASE_DB_URL', 'POSTGRES_URL']:
            if env_key in os.environ:
                del os.environ[env_key]

        self.db_fd, self.db_path = tempfile.mkstemp(suffix='.db')
        app.config['TESTING'] = True
        app.config['SECRET_KEY'] = 'test_secret_2026'
        os.environ['TEST_DB_PATH'] = self.db_path
        self.client = app.test_client()

        with app.app_context():
            init_db()
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("DELETE FROM attendance")
            c.execute("DELETE FROM users WHERE username IN ('st1', 'st2')")
            pwd = generate_password_hash('student123')
            c.execute("INSERT INTO users (username, password_hash, full_name, role, department, class_name, semester, roll_no) VALUES ('st1', ?, 'Student One', 'student', 'Computer Science', 'B.Tech', 'Semester 3', 'CS-01')", (pwd,))
            c.execute("INSERT INTO users (username, password_hash, full_name, role, department, class_name, semester, roll_no) VALUES ('st2', ?, 'Student Two', 'student', 'Computer Science', 'B.Tech', 'Semester 3', 'CS-02')", (pwd,))
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

    def login(self, username, password):
        return self.client.post('/api/login', data=json.dumps({'username': username, 'password': password}), content_type='application/json')

    def test_geofence_calculations(self):
        # 1. Exact center
        inside, dist = is_within_campus(COLLEGE_LATITUDE, COLLEGE_LONGITUDE)
        self.assertTrue(inside)
        self.assertAlmostEqual(dist, 0.0, places=1)

        # 2. Point ~150m away
        inside_close, dist_close = is_within_campus(COLLEGE_LATITUDE + 0.001, COLLEGE_LONGITUDE)
        self.assertTrue(inside_close)
        self.assertLess(dist_close, MAX_RADIUS_METERS)

        # 3. Far point (Delhi: ~28.6139, 77.2090)
        inside_far, dist_far = is_within_campus(28.6139, 77.2090)
        self.assertFalse(inside_far)
        self.assertGreater(dist_far, 100000) # > 100km

    def test_five_consecutive_days_with_same_permanent_qr(self):
        self.login('st1', 'student123')

        permanent_payload = create_permanent_qr_payload(
            session_id='PERM-WALL-POSTER-ROOM-101',
            subject='Operating Systems',
            class_name='B.Tech CS',
            department='Computer Science',
            semester='Semester 3',
            teacher_name='Prof. Alan Turing'
        )

        dates = ['2026-08-18', '2026-08-19', '2026-08-20', '2026-08-21', '2026-08-22']

        for date_str in dates:
            scan_data = dict(permanent_payload)
            scan_data['lat'] = COLLEGE_LATITUDE
            scan_data['lng'] = COLLEGE_LONGITUDE
            scan_data['date'] = date_str
            scan_data['time'] = '09:00:00 AM'

            # 1. Scan on date -> MUST succeed
            res = self.client.post('/api/student/mark-attendance', data=json.dumps(scan_data), content_type='application/json')
            self.assertEqual(res.status_code, 200, f"Failed on date {date_str}: {res.data}")
            body = json.loads(res.data)
            self.assertTrue(body['success'])
            self.assertEqual(body['attendance']['date'], date_str)

            # 2. Rescan on SAME date -> MUST fail
            dup_res = self.client.post('/api/student/mark-attendance', data=json.dumps(scan_data), content_type='application/json')
            self.assertEqual(dup_res.status_code, 400)
            self.assertIn('already marked for today', json.loads(dup_res.data)['error'].lower())

        # Check records count
        att_res = self.client.get('/api/student/attendance')
        records = json.loads(att_res.data)['attendance']
        self.assertEqual(len(records), 5)
        recorded_dates = [r['date'] for r in records]
        for d in dates:
            self.assertIn(d, recorded_dates)

    def test_multi_student_scanning(self):
        # Student 1 scans for 2026-08-18
        self.login('st1', 'student123')
        payload = {
            'type': 'aq_permanent_qr',
            'session_id': 'PERM-ROOM-102',
            'subject': 'Database Systems',
            'lat': COLLEGE_LATITUDE,
            'lng': COLLEGE_LONGITUDE,
            'date': '2026-08-18'
        }
        res1 = self.client.post('/api/student/mark-attendance', data=json.dumps(payload), content_type='application/json')
        self.assertEqual(res1.status_code, 200)
        self.client.post('/api/logout')

        # Student 2 scans same QR for same day 2026-08-18
        self.login('st2', 'student123')
        res2 = self.client.post('/api/student/mark-attendance', data=json.dumps(payload), content_type='application/json')
        self.assertEqual(res2.status_code, 200)

    def test_cli_verifier_function(self):
        payload = create_permanent_qr_payload('PERM-CLI-TEST')
        payload_str = json.dumps(payload)

        # On-campus test
        v_ok = verify_student_attendance_payload('CS-01', payload_str, lat=COLLEGE_LATITUDE, lng=COLLEGE_LONGITUDE)
        self.assertTrue(v_ok['success'])

        # Off-campus test
        v_fail = verify_student_attendance_payload('CS-01', payload_str, lat=28.6139, lng=77.2090)
        self.assertFalse(v_fail['success'])
    def test_compact_fast_scan_payload(self):
        from totp_engine import create_compact_qr_payload

        compact_payload = create_compact_qr_payload(
            session_id='PERM-FAST-01',
            department='Computer Science',
            subject='Fast Attendance'
        )
        self.assertEqual(compact_payload['mode'], 'fast_scan')
        self.assertEqual(compact_payload['session_id'], 'PERM-FAST-01')

        # Test verification of compact dict
        valid, msg = verify_totp_payload(compact_payload)
        self.assertTrue(valid)

        # Test verification of compact string format AQ:PERM:PERM-FAST-01:Computer Science:SIG123
        compact_str = "AQ:PERM:PERM-FAST-01:Computer Science:SIG123"
        valid_str, msg_str = verify_totp_payload(compact_str)
        self.assertTrue(valid_str)

        # Test marking attendance with compact payload
        self.login('st1', 'student123')
        scan_data = {
            'type': 'aq_permanent_qr',
            'session_id': 'PERM-FAST-01',
            'department': 'Computer Science',
            'lat': COLLEGE_LATITUDE,
            'lng': COLLEGE_LONGITUDE,
            'date': '2026-08-30'
        }
        res = self.client.post('/api/student/mark-attendance', data=json.dumps(scan_data), content_type='application/json')
        self.assertEqual(res.status_code, 200)
        self.assertTrue(json.loads(res.data)['success'])

if __name__ == '__main__':
    unittest.main()
