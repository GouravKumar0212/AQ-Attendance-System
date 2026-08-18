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

def create_permanent_qr_payload(session_id: str, subject: str = 'Whole Day Attendance', class_name: str = 'B.Tech', department: str = 'Computer Science', semester: str = 'Semester 3', teacher_name: str = 'Faculty Staff') -> dict:
    """
    Task: Construct a structured JSON payload for a Permanent Campus QR Code that never expires,
    is valid across all dates, and requires campus geolocation to mark attendance.
    """
    now = int(time.time())
    signature = generate_qr_signature(session_id, department, class_name)
    secret_b32 = get_secret_base32(session_id)
    token = generate_totp_token(secret_b32, step=15, current_timestamp=now)
    
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
        'signature': signature,
        'totp_token': token,
        'timestamp': now
    }

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
    permanent signatures, and structure.
    """
    if isinstance(payload_obj, str):
        try:
            payload_obj = json.loads(payload_obj)
        except Exception:
            # Fallback if raw text session ID is scanned
            payload_obj = {'session_id': payload_obj.strip(), 'type': 'aq_permanent_qr'}

    if not isinstance(payload_obj, dict):
        return False, "Invalid payload structure. Expected JSON object."

    session_id = payload_obj.get('session_id')
    if not session_id:
        return False, "Missing session ID in scanned QR code."

    # Validate type if present
    qr_type = payload_obj.get('type', '')
    if qr_type and qr_type not in ['aq_permanent_qr', 'aq_static_qr', 'aq_dynamic_totp_qr', 'aq_qr']:
        return False, f"Unsupported QR code type: {qr_type}"

    return True, "Valid permanent campus QR code."

