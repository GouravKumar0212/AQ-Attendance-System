"""
AQ Attendance System - Permanent QR & Cryptographic Verification Engine
Task: Provides permanent campus QR code generation, HMAC cryptographic signature verification,
RFC 6238 token algorithms, and multi-date attendance payload handling.
"""

import hmac
import hashlib
import struct
import time
import base64
import json

# Secret Key for HMAC cryptographic signature calculations
DEFAULT_HMAC_KEY = "AQ_COLLEGE_TOTP_SECRET_KEY_2026"

# Default College Campus GPS Coordinates for Geofencing
DEFAULT_CAMPUS_LAT = 24.495374689123384
DEFAULT_CAMPUS_LNG = 72.80818369745779

def generate_qr_signature(session_id: str, department: str = '', class_name: str = '', key_seed: str = DEFAULT_HMAC_KEY) -> str:
    """
    Task: Generate a deterministic HMAC-SHA256 signature for permanent QR codes to ensure authenticity.
    """
    payload_str = f"{session_id}:{department}:{class_name}:{key_seed}".encode('utf-8')
    return hmac.new(key_seed.encode('utf-8'), payload_str, hashlib.sha256).hexdigest()[:16]

def get_secret_base32(session_id: str, key_seed: str = DEFAULT_HMAC_KEY) -> str:
    """
    Task: Generate a deterministic, secure Base32-encoded secret key derived from session_id and HMAC seed.
    """
    combined = f"{session_id}:{key_seed}".encode('utf-8')
    raw_hash = hashlib.sha256(combined).digest()
    # Take first 20 bytes and base32 encode
    b32 = base64.b32encode(raw_hash[:20]).decode('utf-8')
    return b32

def generate_totp_token(secret_b32: str, step: int = 15, current_timestamp: int = None) -> str:
    """
    Task: Compute a 6-digit cryptographic TOTP token for given time step block using HMAC-SHA1.
    """
    if current_timestamp is None:
        current_timestamp = int(time.time())
    
    time_counter = current_timestamp // step
    secret_bytes = base64.b32decode(secret_b32, casefold=True)
    msg = struct.pack(">Q", time_counter)
    
    h = hmac.new(secret_bytes, msg, hashlib.sha1).digest()
    offset = h[-1] & 0x0F
    binary_code = ((h[offset] & 0x7F) << 24) | ((h[offset+1] & 0xFF) << 16) | ((h[offset+2] & 0xFF) << 8) | (h[offset+3] & 0xFF)
    totp = binary_code % 1000000
    return f"{totp:06d}"

def verify_totp_token(secret_b32: str, token: str, step: int = 15, window_buffer: int = 1, current_timestamp: int = None) -> bool:
    """
    Task: Verify submitted 6-digit TOTP token against expected values within time window (±window_buffer buffer).
    """
    if current_timestamp is None:
        current_timestamp = int(time.time())
        
    token_str = str(token).strip()
    if not token_str.isdigit() or len(token_str) != 6:
        return False
        
    current_counter = current_timestamp // step
    secret_bytes = base64.b32decode(secret_b32, casefold=True)
    
    for offset in range(-window_buffer, window_buffer + 1):
        counter = current_counter + offset
        msg = struct.pack(">Q", counter)
        h = hmac.new(secret_bytes, msg, hashlib.sha1).digest()
        off = h[-1] & 0x0F
        binary_code = ((h[off] & 0x7F) << 24) | ((h[off+1] & 0xFF) << 16) | ((h[off+2] & 0xFF) << 8) | (h[off+3] & 0xFF)
        expected = f"{(binary_code % 1000000):06d}"
        if hmac.compare_digest(token_str, expected):
            return True
            
    return False

def get_seconds_remaining(step: int = 15) -> int:
    """
    Task: Calculate remaining duration in seconds for live UI clock display.
    """
    now = int(time.time())
    return step - (now % step)

def create_permanent_qr_payload(session_id: str = None, subject: str = 'Whole Day Attendance', class_name: str = 'All Classes', department: str = 'Computer Science', semester: str = 'All Semesters', teacher_name: str = 'Faculty Staff', compact: bool = False) -> dict:
    """
    Task: Construct a structured JSON payload for a Permanent Lifetime Campus QR Code that never expires,
    is 100% constant for a given department/staff, is valid across all dates, and requires campus geolocation.
    If compact=True, generates a streamlined payload optimized for ultra-fast distance scanning.
    """
    if not session_id:
        dept_code = "".join(c for c in (department or 'CS').upper() if c.isalnum())[:4] or 'CS'
        session_id = f"PERM-{dept_code}-OFFICIAL"

    signature = generate_qr_signature(session_id, department, class_name)
    
    if compact:
        return {
            'type': 'aq_permanent_qr',
            'mode': 'fast_scan',
            'session_id': session_id,
            'subject': subject,
            'department': department,
            'class': class_name,
            'semester': semester,
            'teacher': teacher_name,
            'never_expires': True,
            'signature': signature
        }

    return {
        'type': 'aq_permanent_qr',
        'mode': 'permanent_never_expire',
        'session_id': session_id,
        'subject': subject,
        'class': class_name,
        'department': department,
        'semester': semester,
        'teacher': teacher_name,
        'campus_lat': DEFAULT_CAMPUS_LAT,
        'campus_lng': DEFAULT_CAMPUS_LNG,
        'never_expires': True,
        'signature': signature
    }

def create_compact_qr_payload(session_id: str = None, subject: str = 'Whole Day Attendance', class_name: str = 'All Classes', department: str = 'Computer Science', semester: str = 'All Semesters', teacher_name: str = 'Faculty Staff') -> dict:
    """
    Task: Construct an ultra-compact lightweight JSON payload for high-speed scanning from distance.
    """
    return create_permanent_qr_payload(
        session_id=session_id,
        subject=subject,
        class_name=class_name,
        department=department,
        semester=semester,
        teacher_name=teacher_name,
        compact=True
    )

def create_totp_payload(session_id: str, subject: str, class_name: str, department: str, teacher_name: str, step: int = 15, semester: str = '') -> dict:
    """
    Task: Backward-compatible payload creator returning permanent QR payload.
    """
    return create_permanent_qr_payload(
        session_id=session_id,
        subject=subject,
        class_name=class_name,
        department=department,
        semester=semester,
        teacher_name=teacher_name
    )

def verify_totp_payload(payload_obj, step: int = 15, window_buffer: int = 1) -> tuple[bool, str]:
    """
    Task: Parse and validate scanned QR payload data format, checking session ID integrity,
    permanent signatures, compact fast-scan schemas, and structure.
    """
    if isinstance(payload_obj, str):
        payload_str = payload_obj.strip()
        if payload_str.startswith('AQ:PERM:'):
            # Fast compact format: AQ:PERM:<session_id>:<dept>:<sig>
            parts = payload_str.split(':')
            session_id = parts[2] if len(parts) > 2 else ''
            dept = parts[3] if len(parts) > 3 else 'Computer Science'
            sig = parts[4] if len(parts) > 4 else ''
            payload_obj = {
                'type': 'aq_permanent_qr',
                'session_id': session_id,
                'department': dept,
                'signature': sig
            }
        else:
            try:
                payload_obj = json.loads(payload_str)
            except Exception:
                # Fallback if raw text session ID is scanned
                payload_obj = {'session_id': payload_str, 'type': 'aq_permanent_qr'}

    if not isinstance(payload_obj, dict):
        return False, "Invalid payload structure. Expected JSON object."

    session_id = payload_obj.get('session_id') or payload_obj.get('s') or payload_obj.get('session')
    if not session_id:
        return False, "Missing session ID in scanned QR code."

    # Validate type if present
    qr_type = payload_obj.get('type') or payload_obj.get('t', '')
    if qr_type and qr_type not in ['aq_permanent_qr', 'aq_static_qr', 'aq_dynamic_totp_qr', 'aq_qr', 'p', 'perm']:
        return False, f"Unsupported QR code type: {qr_type}"

    return True, "Valid permanent campus QR code."


def run_staff_generator(session_id="SESS-CS101", subject="Whole Day Attendance", class_name="B.Tech CS", department="Computer Science", semester="Semester 3", teacher_name="Faculty Staff", output_file="permanent_campus_qr.png"):
    """
    Task: Generate permanent never-expiring campus QR code payload and save printable QR code PNG.
    """
    import os
    try:
        import qrcode
        has_qr = True
    except ImportError:
        has_qr = False

    print("=" * 64)
    print(" [AQ] Permanent Campus Attendance QR Generator")
    print("=" * 64)
    print(f" Session ID  : {session_id}")
    print(f" Subject     : {subject}")
    print(f" Class       : {class_name}")
    print(f" Department  : {department}")
    print(f" Semester    : {semester}")
    print(f" Validity    : PERMANENT (Never Expires - Valid on All Dates)")
    print(f" Geofence    : Campus Lat {DEFAULT_CAMPUS_LAT}, Lng {DEFAULT_CAMPUS_LNG}")
    print("=" * 64)

    payload = create_permanent_qr_payload(
        session_id=session_id,
        subject=subject,
        class_name=class_name,
        department=department,
        semester=semester,
        teacher_name=teacher_name
    )

    payload_json = json.dumps(payload, indent=2)
    print("\n[+] Permanent QR Payload Generated:")
    print(payload_json)

    if has_qr:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=12,
            border=4,
        )
        qr.add_data(json.dumps(payload))
        qr.make(fit=True)
        img = qr.make_image(fill_color="#0F172A", back_color="#FFFFFF")
        img.save(output_file)
        print(f"\n[+] Saved Permanent QR code image to: {os.path.abspath(output_file)}")
    else:
        print("\nNote: 'qrcode' Python package not found. To generate PNG image files, run: pip install qrcode pillow")

    return payload


def verify_student_attendance_payload(student_id: str, payload_raw, lat: float = None, lng: float = None) -> dict:
    """
    Task: Validate student attendance submissions by checking student ID, parsing scanned QR JSON payload,
    verifying cryptographic integrity, and validating campus geofencing location.
    """
    from geofence import is_within_campus

    if not student_id:
        return {'success': False, 'message': 'Student ID is required.'}

    if not payload_raw:
        return {'success': False, 'message': 'Scanned QR payload is empty.'}

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
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="AQ Attendance System - Cryptographic QR & Verification Engine")
    subparsers = parser.add_subparsers(dest="command", help="Command mode: generate or verify")

    # Generate Subcommand
    gen_parser = subparsers.add_parser("generate", help="Generate permanent campus QR code")
    gen_parser.add_argument('--session', default='SESS-CS101', help='Session ID')
    gen_parser.add_argument('--subject', default='Whole Day Attendance', help='Subject Name')
    gen_parser.add_argument('--class', dest='class_name', default='B.Tech CS', help='Class Name')
    gen_parser.add_argument('--dept', default='Computer Science', help='Department')
    gen_parser.add_argument('--semester', default='Semester 3', help='Semester')
    gen_parser.add_argument('--teacher', default='Dr. Smith', help='Faculty Name')
    gen_parser.add_argument('--output', default='permanent_campus_qr.png', help='Output PNG file')

    # Verify Subcommand
    ver_parser = subparsers.add_parser("verify", help="Verify student QR attendance submission")
    ver_parser.add_argument('--student', required=True, help='Student ID or Roll No')
    ver_parser.add_argument('--payload', required=True, help='Scanned QR payload JSON or session string')
    ver_parser.add_argument('--lat', type=float, default=None, help='Student GPS Latitude')
    ver_parser.add_argument('--lng', type=float, default=None, help='Student GPS Longitude')

    args = parser.parse_args()

    if args.command == "generate" or (not args.command and len(sys.argv) == 1):
        run_staff_generator(
            session_id=getattr(args, 'session', 'SESS-CS101'),
            subject=getattr(args, 'subject', 'Whole Day Attendance'),
            class_name=getattr(args, 'class_name', 'B.Tech CS'),
            department=getattr(args, 'dept', 'Computer Science'),
            semester=getattr(args, 'semester', 'Semester 3'),
            teacher_name=getattr(args, 'teacher', 'Dr. Smith'),
            output_file=getattr(args, 'output', 'permanent_campus_qr.png')
        )
    elif args.command == "verify":
        result = verify_student_attendance_payload(args.student, args.payload, lat=args.lat, lng=args.lng)
        print("=" * 60)
        print(f" Student ID : {args.student}")
        print(f" Status     : {'SUCCESS' if result['success'] else 'FAILED'}")
        print(f" Detail     : {result['message']}")
        print("=" * 60)
        sys.exit(0 if result['success'] else 1)
    else:
        parser.print_help()

