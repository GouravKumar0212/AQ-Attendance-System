"""
Module A: Staff Permanent Campus QR Generator
Generates a Permanent Campus Attendance QR code with HMAC cryptographic signature,
college campus geofence coordinates, and metadata that never expires and works on any date.

Usage:
    python totp_generator.py --session SESS-CS101 --subject "Whole Day Attendance" --class "B.Tech CS" --dept "Computer Science"
"""

import time
import argparse
import sys
import os
import json

try:
    import qrcode
    HAS_QRCODE = True
except ImportError:
    HAS_QRCODE = False

from totp_engine import create_permanent_qr_payload, DEFAULT_CAMPUS_LAT, DEFAULT_CAMPUS_LNG

def run_staff_generator(session_id="SESS-CS101", subject="Whole Day Attendance", class_name="B.Tech CS", department="Computer Science", semester="Semester 3", teacher_name="Faculty Staff", output_file="permanent_campus_qr.png"):
    """
    Task: Generate permanent never-expiring campus QR code payload and save printable QR code PNG.
    """
    print("================================================================")
    print(" [AQ] Permanent Campus Attendance QR Generator (Module A)")
    print("================================================================")
    print(f" Session ID  : {session_id}")
    print(f" Subject     : {subject}")
    print(f" Class       : {class_name}")
    print(f" Department  : {department}")
    print(f" Semester    : {semester}")
    print(f" Validity    : PERMANENT (Never Expires - Valid on All Dates)")
    print(f" Geofence    : Campus Lat {DEFAULT_CAMPUS_LAT}, Lng {DEFAULT_CAMPUS_LNG}")
    print("================================================================")

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

    if HAS_QRCODE:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=10,
            border=4,
        )
        qr.add_data(json.dumps(payload))
        qr.make(fit=True)
        img = qr.make_image(fill_color="#0F172A", back_color="#FFFFFF")
        img.save(output_file)
        print(f"\n[+] Saved Permanent QR code image to: {os.path.abspath(output_file)}")
    else:
        print("\nNote: 'qrcode' Python package is not installed. To generate PNG image files, run:")
        print("      pip install qrcode pillow")

    return payload

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Module A: Staff Permanent Campus Attendance QR Code Generator")
    parser.add_argument('--session', default='SESS-CS101', help='Session ID')
    parser.add_argument('--subject', default='Whole Day Attendance', help='Subject Name')
    parser.add_argument('--class', dest='class_name', default='B.Tech CS', help='Class Name')
    parser.add_argument('--dept', default='Computer Science', help='Department')
    parser.add_argument('--semester', default='Semester 3', help='Semester')
    parser.add_argument('--teacher', default='Dr. Smith', help='Faculty Name')
    parser.add_argument('--output', default='permanent_campus_qr.png', help='Output PNG file')
    args = parser.parse_args()

    run_staff_generator(
        session_id=args.session,
        subject=args.subject,
        class_name=args.class_name,
        department=args.dept,
        semester=args.semester,
        teacher_name=args.teacher,
        output_file=args.output
    )

