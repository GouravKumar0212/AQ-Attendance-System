"""
Module B: Server Verifier (15-Second TOTP Validation Engine)
Receives the scanned QR payload string/JSON and a Student ID. Recalculates valid TOTP tokens
for the current 15-second time window (allowing a 1-slot ±15s network latency buffer) to accept
or reject student attendance.

Usage:
    python totp_verifier.py --student CS-101 --payload '{"session_id":"SESS-CS101","totp_token":"123456"}'
"""

import sys
import json
import argparse
from totp_engine import verify_totp_payload, get_secret_base32, verify_totp_token

def verify_student_attendance_payload(student_id: str, payload_raw: str, step: int = 15, window_buffer: int = 1) -> dict:
    """
    Module B Core Function: Validate Student ID and TOTP payload for 15-second window.
    """
    if not student_id:
        return {'success': False, 'message': 'Student ID is required.'}

    if not payload_raw:
        return {'success': False, 'message': 'Scanned QR payload is empty.'}

    # Parse JSON if payload is string
    if isinstance(payload_raw, str):
        try:
            payload_data = json.loads(payload_raw)
        except Exception:
            # Fallback for plain TOTP token or simple session string
            payload_data = {'session_id': 'DEFAULT-SESSION', 'totp_token': payload_raw.strip()}
    else:
        payload_data = payload_raw

    is_valid, msg = verify_totp_payload(payload_data, step=step, window_buffer=window_buffer)

    if is_valid:
        return {
            'success': True,
            'message': f"🟢 Attendance ACCEPTED for Student {student_id}! (Valid 15s TOTP Window)",
            'session_id': payload_data.get('session_id'),
            'subject': payload_data.get('subject', 'Classroom Attendance'),
            'student_id': student_id
        }
    else:
        return {
            'success': False,
            'message': f"🔴 Attendance REJECTED for Student {student_id}: {msg}",
            'student_id': student_id
        }

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Module B: Server TOTP Attendance Verifier")
    parser.add_argument('--student', required=True, help='Student ID or Roll No')
    parser.add_argument('--payload', required=True, help='Scanned QR payload JSON or TOTP token')
    parser.add_argument('--buffer', type=int, default=1, help='Time window buffer (+/- 1 slot = 15s)')
    args = parser.parse_args()

    result = verify_student_attendance_payload(args.student, args.payload, window_buffer=args.buffer)
    print("==========================================================")
    print(" 🎓 AQ Server TOTP Verifier Result (Module B)")
    print("==========================================================")
    print(f" Student ID : {args.student}")
    print(f" Status     : {'SUCCESS' if result['success'] else 'FAILED'}")
    print(f" Detail     : {result['message']}")
    print("==========================================================")
    sys.exit(0 if result['success'] else 1)
