# 🎓 AQ — Smart QR Code & Manual College Attendance System

A modern, responsive, and secure Web Application for managing college attendance across **Admin**, **Staff (Faculty)**, and **Student** portals. Built with Python (Flask), SQLite, and Vanilla HTML5/CSS3/JavaScript. Ready for deployment on **Vercel** and **GitHub**.

---

## 🌟 Key Features

### 👑 Admin Portal
- **Dashboard Analytics:** Live summary of Total Students, Total Staff, Today's Present Count, and Overall College Attendance Rate (%).
- **Low Attendance Alerts (< 45%):** Automated red warning banner identifying students falling below the mandatory 45% threshold.
- **User Management Hub:** Add, edit, or remove Admin, Staff, and Student user accounts.
- **Department & Semester Attendance Reports:** Filter attendance records by Department (*Computer Science, IT, BCA, Commerce, etc.*), Date (`YYYY-MM-DD`), and Semester (*Semester 1 - 8*).
- **Inline Status Overrides:** Security override to change student attendance status (`🟢 Present`, `🔴 Absent`, `🟡 Leave`, `🟣 Holiday`) directly from the table or card view.
- **Excel / CSV Report Export:** Download complete college attendance logs in standard CSV format.

### 👩‍🏫 Staff (Faculty) Portal
- **Dynamic QR Code Session Generator:** Generate high-resolution, anti-spoof QR codes with live countdown timers and refresh controls.
- **Manual Attendance Marking (`✏️ Mark Attendance`):** Compact 2-column modal interface allowing staff to select Department, Semester, Student, Date, Subject, and Status.
- **Department Attendance Log:** Real-time log of scanned attendance for faculty departments. Filter by Department, Date, Semester, and Subject/Student.
- **College Holiday Scheduler (`📅 Schedule Holiday`):** Set college-wide or department-specific holidays that automatically reflect across all student calendars.

### 🎓 Student Portal
- **Monthly Interactive Calendar View:** Dynamic 31-day visual calendar highlighting daily attendance status (`🟢 P`, `🔴 A`, `🟡 L`, `🟣 H`).
- **Drag & Touch Responsive Controls:** Fits all mobile devices, tablets, and desktop screens. Small touch-friendly `Prev` / `Next` month navigation buttons.
- **Live Attendance Rates:** Separate real-time calculations for **Monthly Attendance Rate (%)** and **Yearly Attendance Rate (%)** calculated using the exact formula:
  $$\text{Monthly \%} = \left( \frac{\text{Present}}{\text{Present} + \text{Absent}} \right) \times 100$$
- **Single Scan Per Day Rule:** Automated anti-cheat restriction enforcing that a student can only scan attendance **once per day**.
- **QR Code Scanner / Session Code Input:** Built-in mobile camera scanner and manual session code fallback input.

---

## 🛠️ Technology Stack

- **Backend:** Python 3.x, Flask, SQLite3
- **Frontend:** Vanilla HTML5, Vanilla CSS3 (Custom Glassmorphism Design System), JavaScript (ES6+)
- **Deployment:** Vercel Serverless Functions (`@vercel/python`)
- **Version Control:** Git / GitHub

---

## 🔑 Default Login Credentials

For testing and demonstration, use the following credentials:

| Role | Username | Password |
| :--- | :--- | :--- |
| 👑 **Administrator** | `admin` | `admin123` |
| 👩‍🏫 **Staff / Faculty** | `cs_faculty` | `staff123` |
| 🎓 **Student** | `sem4student` | `password123` |

---

## 🚀 Quickstart — Running Locally

### 1. Clone the Repository
```bash
git clone https://github.com/your-username/web_project.git
cd web_project/AQ
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Start the Local Server
```bash
python app.py
```

Open your browser and navigate to:
```
http://localhost:5000
```

---

## ☁️ Deploying to Vercel

This repository includes a pre-configured `vercel.json` and a serverless-safe SQLite handler (`/tmp/database.db`).

### Steps to Deploy via Vercel CLI / Web Dashboard:

1. Push your repository to **GitHub**:
   ```bash
   git init
   git add .
   git commit -m "Initial commit — AQ Attendance System Vercel Ready"
   git branch -M main
   git remote add origin https://github.com/YOUR_USERNAME/AQ-Attendance-System.git
   git push -u origin main
   ```

2. Log in to [Vercel Dashboard](https://vercel.com).
3. Click **Add New Project** and select your GitHub repository (`AQ-Attendance-System`).
4. Keep all default settings (Framework Preset: **Other**).
5. Click **Deploy**!

---

## 📁 Project Structure

```
AQ/
├── app.py                  # Main Flask Server & REST APIs
├── vercel.json             # Vercel Serverless Function Configuration
├── requirements.txt        # Python Dependencies
├── .gitignore              # Git Ignore Rules
├── database.db             # Pre-seeded SQLite Database
├── static/
│   ├── app.js              # Client-side Logic & Dynamic Controllers
│   └── style.css           # Modern Glassmorphism CSS Design System
└── templates/
    └── index.html          # Unified SPA Portal (Admin, Staff, Student)
```

---

## 📄 License
This project is open-source under the MIT License.
