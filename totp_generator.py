"""
Module A: Staff Dynamic QR Generator (15-Second TOTP Rolling QR Code)
Generates a unique TOTP token using a shared secret and the current 15-second timestamp block.
Converts the token & payload into a QR code image (using the 'qrcode' library) and refreshes
every 15 seconds.

Usage:
    python totp_generator.py --session CS302-SEC1 --subject "Data Structures" --class "B.Tech CS"
"""

import time
import argparse
import sys
import os

try:
    import qrcode
    HAS_QRCODE = True
except ImportError:
    HAS_QRCODE = False

from totp_engine import create_totp_payload, get_seconds_remaining, generate_totp_token, get_secret_base32

def run_staff_generator(session_id="SESS-CS101", subject="Computer Science", class_name="B.Tech CS", department="CS", teacher_name="Faculty"):
    print("================================================================")
    print(" 🎓 AQ Staff Dynamic 15-Second TOTP QR Code Generator (Module A)")
    print("================================================================")
    print(f" Session ID  : {session_id}")
    print(f" Subject     : {subject}")
    print(f" Class       : {class_name}")
    print(f" Refresh Rate: Every 15 seconds (RFC 6238 TOTP)")
    print("================================================================")
    if not HAS_QRCODE:
        print("Note: 'qrcode' Python package is not installed. To generate PNG image files, run:")
        print("      pip install qrcode pillow")
        print("Continuing with console ASCII QR payload display...\n")

    output_filename = "active_session_qr.png"

    try:
        while True:
            payload = create_totp_payload(
                session_id=session_id,
                subject=subject,
                class_name=class_name,
                department=department,
                teacher_name=teacher_name,
                step=15
            )

            token = payload['totp_token']
            sec_left = payload['time_remaining']
            payload_str = str(payload)

            print(f"\n[{time.strftime('%H:%M:%S')}] 🟢 Active TOTP Token: {token} | Valid for next {sec_left}s")
            print(f" Payload: {payload_str}")

            if HAS_QRCODE:
                qr = qrcode.QRCode(
                    version=1,
                    error_correction=qrcode.constants.ERROR_CORRECT_H,
                    box_size=10,
                    border=4,
                )
                import json
                qr.add_data(json.dumps(payload))
                qr.make(fit=True)
                img = qr.make_image(fill_color="#0F172A", back_color="#FFFFFF")
                img.save(output_filename)
                print(f" 🖼️  Saved active 15s QR code image to: {os.path.abspath(output_filename)}")

            # Sleep until the end of current 15-second block
            time.sleep(sec_left if sec_left > 0 else 1)

    except KeyboardInterrupt:
        print("\n\n⏹️  Staff QR Generator stopped.")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Module A: Staff Dynamic 15-Second TOTP QR Code Generator")
    parser.add_argument('--session', default='SESS-CS101', help='Session ID')
    parser.add_argument('--subject', default='Data Structures', help='Subject Name')
    parser.add_argument('--class', dest='class_name', default='B.Tech CS - Sem 4', help='Class Name')
    parser.add_argument('--dept', default='Computer Science', help='Department')
    parser.add_argument('--teacher', default='Dr. Smith', help='Faculty Name')
    args = parser.parse_args()

    run_staff_generator(
        session_id=args.session,
        subject=args.subject,
        class_name=args.class_name,
        department=args.dept,
        teacher_name=args.teacher
    )
