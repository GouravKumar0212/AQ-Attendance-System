"""
Module B: Server Verifier (Permanent Campus QR & Geofence Validation Engine)
Receives scanned QR payload and student data, verifying HMAC signature, session integrity,
and campus geolocation.

Usage:
    python totp_verifier.py --student CS-101 --payload '{"session_id":"SESS-CS101","type":"aq_permanent_qr"}' --lat 24.495374 --lng 72.808183
"""

import sys
import json
import argparse
from totp_engine import verify_totp_payload
from geofence import is_within_campus

def verify_student_attendance_payload(student_id: str, payload_raw: str, lat: float = None, lng: float = None) -> dict:
    """
    Task: Validate student attendance submissions by checking student ID, parsing scanned QR JSON payload,
    verifying cryptographic integrity, and validating campus geofencing location.
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
            payload_data = {'session_id': payload_raw.strip(), 'type': 'aq_permanent_qr'}
    else:
        payload_data = payload_raw

    # 1. Verify QR Payload Authenticity
    is_valid, msg = verify_totp_payload(payload_data)
    if not is_valid:
        return {
            'success': False,
            'message': f"[REJECTED] Attendance REJECTED for Student {student_id}: {msg}",
            'student_id': student_id
        }

    # 2. Verify Campus Geofencing if coordinates provided
    if lat is not None and lng is not None:
        inside, dist = is_within_campus(lat, lng)
        if not inside:
            return {
                'success': False,
                'message': f"[REJECTED] Outside campus perimeter ({int(dist)}m away). Must be physically inside campus.",
                'student_id': student_id
            }

    return {
        'success': True,
        'message': f"[ACCEPTED] Attendance ACCEPTED for Student {student_id}! (Valid Permanent Campus QR)",
        'session_id': payload_data.get('session_id'),
        'subject': payload_data.get('subject', 'Whole Day Attendance'),
        'student_id': student_id
    }

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Module B: Server Permanent QR & Geofence Verifier")
    parser.add_argument('--student', required=True, help='Student ID or Roll No')
    parser.add_argument('--payload', required=True, help='Scanned QR payload JSON or session string')
    parser.add_argument('--lat', type=float, default=None, help='Student GPS Latitude')
    parser.add_argument('--lng', type=float, default=None, help='Student GPS Longitude')
    args = parser.parse_args()

    result = verify_student_attendance_payload(args.student, args.payload, lat=args.lat, lng=args.lng)
    print("==========================================================")
    print(" [AQ] Server Permanent QR Verifier Result (Module B)")
    print("==========================================================")
    print(f" Student ID : {args.student}")
    print(f" Status     : {'SUCCESS' if result['success'] else 'FAILED'}")
    print(f" Detail     : {result['message']}")
    print("==========================================================")
    sys.exit(0 if result['success'] else 1)

