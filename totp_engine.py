"""
TOTP Engine (RFC 6238 Standard Implementation with 15-Second Time Step)
Provides stateless Time-Based One-Time Password generation and verification
for AQ Dynamic Rolling QR Code Attendance System.
"""

import hmac
import hashlib
import struct
import time
import base64
import json

# Secret Key for TOTP signature calculations
DEFAULT_HMAC_KEY = "AQ_COLLEGE_TOTP_SECRET_KEY_2026"

def get_secret_base32(session_id: str, key_seed: str = DEFAULT_HMAC_KEY) -> str:
    """Generate a stable Base32 secret for a specific attendance session_id."""
    combined = f"{session_id}:{key_seed}".encode('utf-8')
    raw_hash = hashlib.sha256(combined).digest()
    # Take first 20 bytes and base32 encode
    b32 = base64.b32encode(raw_hash[:20]).decode('utf-8')
    return b32

def generate_totp_token(secret_b32: str, step: int = 15, current_timestamp: int = None) -> str:
    """
    Generate a 6-digit TOTP token for the specified time step block (default 15s).
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
    Verify a TOTP token against the current 15-second time window (with ±window_buffer allowance).
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
    """Returns number of seconds remaining in current 15-second window block."""
    now = int(time.time())
    return step - (now % step)

def create_totp_payload(session_id: str, subject: str, class_name: str, department: str, teacher_name: str, step: int = 15) -> dict:
    """
    Build a dynamic QR payload dictionary containing session info and the active 15s TOTP token.
    """
    now = int(time.time())
    secret_b32 = get_secret_base32(session_id)
    token = generate_totp_token(secret_b32, step=step, current_timestamp=now)
    time_remaining = step - (now % step)
    
    return {
        'type': 'aq_dynamic_totp_qr',
        'session_id': session_id,
        'subject': subject,
        'class': class_name,
        'department': department,
        'teacher': teacher_name,
        'totp_token': token,
        'step': step,
        'time_remaining': time_remaining,
        'timestamp': now
    }

def verify_totp_payload(payload_obj, step: int = 15, window_buffer: int = 1) -> tuple[bool, str]:
    """
    Validate a scanned payload object against the active 15s TOTP window.
    Returns (is_valid, error_or_success_message).
    """
    if isinstance(payload_obj, str):
        try:
            payload_obj = json.loads(payload_obj)
        except Exception:
            return False, "Invalid payload format. Expected JSON string or object."

    if not isinstance(payload_obj, dict):
        return False, "Invalid payload structure."

    session_id = payload_obj.get('session_id')
    totp_token = payload_obj.get('totp_token')

    if not session_id or not totp_token:
        return False, "Missing session ID or TOTP token in scanned QR code."

    secret_b32 = get_secret_base32(session_id)
    valid = verify_totp_token(secret_b32, totp_token, step=step, window_buffer=window_buffer)

    if not valid:
        return False, "Expired or invalid QR code! Dynamic QR codes refresh every 15 seconds."

    return True, "Valid TOTP token."
