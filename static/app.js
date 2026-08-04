document.addEventListener('DOMContentLoaded', () => {
    // --- State Management ---
    let selectedRole = 'admin';
    let activeFilter = 'all';
    let currentUser = null;
    let cachedUsers = [];

    // --- DOM Elements ---
    const views = {
        login: document.getElementById('loginView'),
        admin: document.getElementById('adminDashboardView'),
        staff: document.getElementById('staffDashboardView'),
        student: document.getElementById('studentDashboardView')
    };

    // Header Elements
    const userHeaderProfile = document.getElementById('userHeaderProfile');
    const headerRoleBadge = document.getElementById('headerRoleBadge');
    const headerUserName = document.getElementById('headerUserName');
    const logoutBtn = document.getElementById('logoutBtn');

    // Login Elements
    const roleTabs = document.querySelectorAll('.role-tab');
    const roleNoticeText = document.getElementById('roleNoticeText');
    const loginForm = document.getElementById('loginForm');
    const loginUsername = document.getElementById('loginUsername');
    const loginPassword = document.getElementById('loginPassword');
    const loginError = document.getElementById('loginError');

    // Admin View Elements
    const statTotalStaff = document.getElementById('statTotalStaff');
    const statTotalStudents = document.getElementById('statTotalStudents');
    const userTableBody = document.getElementById('userTableBody');
    const userMobileCardsContainer = document.getElementById('userMobileCardsContainer');
    const noUsersState = document.getElementById('noUsersState');
    const userSearchInput = document.getElementById('userSearchInput');
    const filterPills = document.querySelectorAll('.filter-pill');

    // Modal Elements
    const createUserModal = document.getElementById('createUserModal');
    const openCreateUserModalBtn = document.getElementById('openCreateUserModalBtn');
    const closeModalBtn = document.getElementById('closeModalBtn');
    const cancelModalBtn = document.getElementById('cancelModalBtn');
    const createUserForm = document.getElementById('createUserForm');
    const modalError = document.getElementById('modalError');
    const newRoleSelect = document.getElementById('newRole');
    const studentFieldsContainer = document.getElementById('studentFieldsContainer');

    // Staff Elements
    const staffFullName = document.getElementById('staffFullName');
    const staffDepartment = document.getElementById('staffDepartment');
    const staffEmail = document.getElementById('staffEmail');
    const staffStudentTableBody = document.getElementById('staffStudentTableBody');
    const staffStudentMobileCardsContainer = document.getElementById('staffStudentMobileCardsContainer');
    const noStaffStudentsState = document.getElementById('noStaffStudentsState');

    // Student Elements
    const studentFullName = document.getElementById('studentFullName');
    const studentDepartment = document.getElementById('studentDepartment');
    const studentEmail = document.getElementById('studentEmail');
    const studentRollNo = document.getElementById('studentRollNo');
    const studentClass = document.getElementById('studentClass');
    const studentSemester = document.getElementById('studentSemester');

    // Password Visibility Toggles
    const togglePasswordBtns = document.querySelectorAll('.btn-toggle-password');
    togglePasswordBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const targetId = btn.dataset.target;
            const inputEl = document.getElementById(targetId);
            if (inputEl) {
                const isPassword = inputEl.type === 'password';
                inputEl.type = isPassword ? 'text' : 'password';
                btn.style.color = isPassword ? 'var(--color-blue-accent)' : 'var(--color-text-muted)';
            }
        });
    });

    // --- Check Auth Session on Load ---
    checkAuthSession();

    // --- Event Listeners ---

    // Role Tab Switching
    roleTabs.forEach(tab => {
        tab.addEventListener('click', () => {
            roleTabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            selectedRole = tab.dataset.role;
            updateRoleNotice();
            hideError(loginError);
        });
    });

    // Login Form Submit
    if (loginForm) {
        loginForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            hideError(loginError);

            const username = loginUsername.value.trim();
            const password = loginPassword.value;

            if (!username || !password) {
                showError(loginError, 'Please enter both username and password.');
                return;
            }

            const loginBtnText = document.getElementById('loginBtnText');
            if (loginBtnText) loginBtnText.textContent = 'Authenticating...';

            try {
                const response = await fetch('/api/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username, password, role: selectedRole })
                });

                const data = await response.json();

                if (response.ok && data.success) {
                    currentUser = data.user;
                    showToast(`Welcome back, ${currentUser.full_name}!`, 'success');
                    loginForm.reset();
                    renderUserSession();
                } else {
                    showError(loginError, data.message || 'Login failed.');
                }
            } catch (err) {
                showError(loginError, 'Network error. Could not connect to server.');
            } finally {
                if (loginBtnText) loginBtnText.textContent = 'Sign In to AQ';
            }
        });
    }

    // Logout
    if (logoutBtn) {
        logoutBtn.addEventListener('click', async () => {
            try { await fetch('/api/logout', { method: 'POST' }); } catch (e) { }
            currentUser = null;
            showToast('Logged out successfully', 'success');
            renderUserSession();
        });
    }

    // Admin Filter Pills
    filterPills.forEach(pill => {
        pill.addEventListener('click', () => {
            filterPills.forEach(p => p.classList.remove('active'));
            pill.classList.add('active');
            activeFilter = pill.dataset.filter;
            applyUserFilters();
        });
    });

    // Admin Live Search Input
    if (userSearchInput) {
        userSearchInput.addEventListener('input', applyUserFilters);
    }

    function applyUserFilters() {
        const query = userSearchInput ? userSearchInput.value.toLowerCase().trim() : '';
        const filtered = cachedUsers.filter(u => {
            const matchesFilter = (activeFilter === 'all') || (u.role === activeFilter);
            const matchesQuery = !query || (
                u.full_name.toLowerCase().includes(query) ||
                u.username.toLowerCase().includes(query) ||
                u.department.toLowerCase().includes(query) ||
                u.email.toLowerCase().includes(query) ||
                (u.roll_no && u.roll_no.toLowerCase().includes(query)) ||
                (u.class_name && u.class_name.toLowerCase().includes(query))
            );
            return matchesFilter && matchesQuery;
        });

        renderUserDirectory(filtered);
    }

    // Modal Role Selector
    if (newRoleSelect && studentFieldsContainer) {
        newRoleSelect.addEventListener('change', () => {
            if (newRoleSelect.value === 'student') {
                studentFieldsContainer.classList.remove('hidden');
            } else {
                studentFieldsContainer.classList.add('hidden');
            }
        });
    }

    // Modal Open/Close Controls
    if (openCreateUserModalBtn) {
        openCreateUserModalBtn.addEventListener('click', () => {
            createUserForm.reset();
            hideError(modalError);
            if (newRoleSelect.value === 'student') {
                studentFieldsContainer.classList.remove('hidden');
            } else {
                studentFieldsContainer.classList.add('hidden');
            }
            createUserModal.classList.remove('hidden');
        });
    }

    if (closeModalBtn) closeModalBtn.addEventListener('click', () => createUserModal.classList.add('hidden'));
    if (cancelModalBtn) cancelModalBtn.addEventListener('click', () => createUserModal.classList.add('hidden'));
    if (createUserModal) {
        createUserModal.addEventListener('click', (e) => {
            if (e.target === createUserModal) createUserModal.classList.add('hidden');
        });
    }

    // Create User Form Submit
    if (createUserForm) {
        createUserForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            hideError(modalError);

            const roleVal = newRoleSelect.value;
            const payload = {
                full_name: document.getElementById('newFullName').value.trim(),
                username: document.getElementById('newUsername').value.trim(),
                role: roleVal,
                department: document.getElementById('newDepartment').value.trim(),
                email: document.getElementById('newEmail').value.trim(),
                password: document.getElementById('newPassword').value,
                roll_no: roleVal === 'student' ? document.getElementById('newRollNo').value.trim() : '',
                class_name: roleVal === 'student' ? document.getElementById('newClass').value.trim() : '',
                semester: roleVal === 'student' ? document.getElementById('newSemester').value : ''
            };

            try {
                const response = await fetch('/api/admin/users', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });

                const data = await response.json();

                if (response.ok && data.success) {
                    showToast(data.message, 'success');
                    createUserModal.classList.add('hidden');
                    loadAdminUsers();
                } else {
                    showError(modalError, data.error || 'Failed to create user account.');
                }
            } catch (err) {
                showError(modalError, 'Error connecting to server.');
            }
        });
    }

    // --- Helper Functions ---

    function updateRoleNotice() {
        if (selectedRole === 'admin') {
            roleNoticeText.textContent = 'System Administrator Login';
        } else if (selectedRole === 'staff') {
            roleNoticeText.textContent = 'Faculty & Staff Login (Requires Admin Account)';
        } else if (selectedRole === 'student') {
            roleNoticeText.textContent = 'Student Portal Login (Requires Admin Account)';
        }
    }

    async function checkAuthSession() {
        try {
            const response = await fetch('/api/me');
            const data = await response.json();
            if (data.authenticated && data.user) {
                currentUser = data.user;
            } else {
                currentUser = null;
            }
        } catch (e) {
            currentUser = null;
        }
        renderUserSession();
    }

    function renderUserSession() {
        Object.values(views).forEach(view => {
            if (view) {
                view.classList.add('hidden');
                view.classList.remove('active');
            }
        });

        // Always hide QR scanner modal and stop camera on view switch/login
        const scanModal = document.getElementById('scanQrModal');
        if (scanModal) scanModal.classList.add('hidden');
        if (typeof stopCameraScan === 'function') stopCameraScan();

        if (!currentUser) {
            if (views.login) {
                views.login.classList.remove('hidden');
                views.login.classList.add('active');
            }
            if (userHeaderProfile) userHeaderProfile.classList.add('hidden');
            return;
        }

        if (userHeaderProfile) userHeaderProfile.classList.remove('hidden');
        if (headerUserName) headerUserName.textContent = currentUser.full_name;
        if (headerRoleBadge) {
            headerRoleBadge.textContent = currentUser.role.toUpperCase();
            headerRoleBadge.className = 'role-badge badge ' + 
                (currentUser.role === 'admin' ? 'badge-admin' : 
                 currentUser.role === 'staff' ? 'badge-staff' : 'badge-student');
        }

        if (currentUser.role === 'admin' && views.admin) {
            views.admin.classList.remove('hidden');
            views.admin.classList.add('active');
            loadAdminUsers();
            fetchAdminAttendance();
        } else if (currentUser.role === 'staff' && views.staff) {
            views.staff.classList.remove('hidden');
            views.staff.classList.add('active');
            renderStaffDashboard();
            fetchStaffAttendance();
        } else if (currentUser.role === 'student' && views.student) {
            views.student.classList.remove('hidden');
            views.student.classList.add('active');
            renderStudentDashboard();
            fetchStudentAttendance();
        }
    }

    // Load Admin Directory & Stats
    async function loadAdminUsers() {
        try {
            const response = await fetch('/api/admin/users');
            if (!response.ok) return;

            const data = await response.json();
            cachedUsers = data.users || [];

            const staffCount = cachedUsers.filter(u => u.role === 'staff').length;
            const studentCount = cachedUsers.filter(u => u.role === 'student').length;

            animateCounter(statTotalStaff, staffCount);
            animateCounter(statTotalStudents, studentCount);

            applyUserFilters();
        } catch (e) {
            console.error('Failed to load admin user directory:', e);
        }
    }

    function renderUserDirectory(users) {
        userTableBody.innerHTML = '';
        userMobileCardsContainer.innerHTML = '';

        const displayUsers = users.filter(u => u.username !== 'admin');

        if (displayUsers.length === 0) {
            noUsersState.classList.remove('hidden');
            userTableBody.parentElement.classList.add('hidden');
            userMobileCardsContainer.classList.add('hidden');
            return;
        }

        noUsersState.classList.add('hidden');
        userTableBody.parentElement.classList.remove('hidden');
        userMobileCardsContainer.classList.remove('hidden');

        displayUsers.forEach(user => {
            const createdDate = new Date(user.created_at || Date.now()).toLocaleDateString('en-US', {
                month: 'short', day: 'numeric', year: 'numeric'
            });

            const roleBadgeClass = user.role === 'staff' ? 'badge-staff' : 'badge-student';
            const rollNoText = user.role === 'student' ? (escapeHtml(user.roll_no) || '-') : '-';
            const classSemText = user.role === 'student' 
                ? `${escapeHtml(user.class_name || '-')}` + (user.semester ? ` (${escapeHtml(user.semester)})` : '')
                : '-';

            // 1. Desktop Table Row
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>
                    <strong>${escapeHtml(user.full_name)}</strong><br>
                    <small style="color: var(--color-text-muted);">@${escapeHtml(user.username)}</small>
                </td>
                <td><span class="badge ${roleBadgeClass}">${user.role}</span></td>
                <td><code>${rollNoText}</code></td>
                <td>${classSemText}</td>
                <td>${escapeHtml(user.department || '-')}</td>
                <td>${escapeHtml(user.email || '-')}</td>
                <td>${createdDate}</td>
                <td>
                    <button class="btn-delete" data-id="${user.id}" title="Delete Account">Delete</button>
                </td>
            `;

            tr.querySelector('.btn-delete').addEventListener('click', () => deleteUser(user.id, user.full_name));
            userTableBody.appendChild(tr);

            // 2. Mobile Responsive Card
            const card = document.createElement('div');
            card.className = 'user-mobile-card';
            card.innerHTML = `
                <div class="mobile-card-row">
                    <div>
                        <div class="mobile-card-title">${escapeHtml(user.full_name)}</div>
                        <small style="color: var(--color-text-muted);">@${escapeHtml(user.username)}</small>
                    </div>
                    <span class="badge ${roleBadgeClass}">${user.role}</span>
                </div>
                ${user.role === 'student' ? `
                    <div class="mobile-card-detail">
                        <strong>Roll No:</strong> <code>${rollNoText}</code> | <strong>Class:</strong> ${classSemText}
                    </div>
                ` : ''}
                <div class="mobile-card-detail">
                    <strong>Dept:</strong> ${escapeHtml(user.department || '-')} | <strong>Email:</strong> ${escapeHtml(user.email || '-')}
                </div>
                <div class="mobile-card-row" style="margin-top: 0.25rem;">
                    <small style="color: var(--color-text-light);">${createdDate}</small>
                    <button class="btn-delete" data-id="${user.id}">Delete</button>
                </div>
            `;

            card.querySelector('.btn-delete').addEventListener('click', () => deleteUser(user.id, user.full_name));
            userMobileCardsContainer.appendChild(card);
        });
    }

    async function deleteUser(userId, name) {
        if (!confirm(`Are you sure you want to delete the account for "${name}"?`)) return;

        try {
            const response = await fetch(`/api/admin/users/${userId}`, { method: 'DELETE' });
            const data = await response.json();

            if (response.ok && data.success) {
                showToast(`Deleted account for ${name}`, 'success');
                loadAdminUsers();
            } else {
                showToast(data.error || 'Failed to delete user', 'error');
            }
        } catch (e) {
            showToast('Network error deleting user', 'error');
        }
    }

    // Render Staff View
    async function renderStaffDashboard() {
        staffFullName.textContent = currentUser.full_name;
        staffDepartment.textContent = currentUser.department || 'General Faculty';
        staffEmail.textContent = currentUser.email || 'N/A';

        try {
            const response = await fetch('/api/staff/students');
            if (response.ok) {
                const data = await response.json();
                const students = data.students || [];

                staffStudentTableBody.innerHTML = '';
                staffStudentMobileCardsContainer.innerHTML = '';

                if (students.length === 0) {
                    noStaffStudentsState.classList.remove('hidden');
                    staffStudentTableBody.parentElement.classList.add('hidden');
                    staffStudentMobileCardsContainer.classList.add('hidden');
                } else {
                    noStaffStudentsState.classList.add('hidden');
                    staffStudentTableBody.parentElement.classList.remove('hidden');
                    staffStudentMobileCardsContainer.classList.remove('hidden');

                    students.forEach(s => {
                        // Table row
                        const tr = document.createElement('tr');
                        tr.innerHTML = `
                            <td><strong>${escapeHtml(s.full_name)}</strong></td>
                            <td><code>${escapeHtml(s.roll_no || '-')}</code></td>
                            <td>${escapeHtml(s.class_name || '-')}</td>
                            <td>${escapeHtml(s.semester || '-')}</td>
                            <td>${escapeHtml(s.department || '-')}</td>
                            <td>${escapeHtml(s.email || '-')}</td>
                            <td><span class="badge badge-active">Enrolled</span></td>
                        `;
                        staffStudentTableBody.appendChild(tr);

                        // Mobile card
                        const card = document.createElement('div');
                        card.className = 'user-mobile-card';
                        card.innerHTML = `
                            <div class="mobile-card-row">
                                <div class="mobile-card-title">${escapeHtml(s.full_name)}</div>
                                <span class="badge badge-active">Enrolled</span>
                            </div>
                            <div class="mobile-card-detail">
                                <strong>Roll No:</strong> <code>${escapeHtml(s.roll_no || '-')}</code> | <strong>Class:</strong> ${escapeHtml(s.class_name || '-')} (${escapeHtml(s.semester || '-')})
                            </div>
                            <div class="mobile-card-detail">
                                <strong>Dept:</strong> ${escapeHtml(s.department || '-')} | <strong>Email:</strong> ${escapeHtml(s.email || '-')}
                            </div>
                        `;
                        staffStudentMobileCardsContainer.appendChild(card);
                    });
                }
            }
        } catch (e) {
            console.error('Failed to load department students:', e);
        }
    }

    // Render Student View
    function renderStudentDashboard() {
        studentFullName.textContent = currentUser.full_name;
        studentDepartment.textContent = currentUser.department || 'General Studies';
        studentEmail.textContent = currentUser.email || 'N/A';
        if (studentRollNo) studentRollNo.textContent = currentUser.roll_no || 'N/A';
        if (studentClass) studentClass.textContent = currentUser.class_name || 'N/A';
        if (studentSemester) studentSemester.textContent = currentUser.semester || 'N/A';
        fetchStudentAttendance();
    }

    // --- Student Scan QR & Attendance Controller ---
    const openScanQrBtn = document.getElementById('openScanQrBtn');
    const scanQrModal = document.getElementById('scanQrModal');
    const closeScanQrModalBtn = document.getElementById('closeScanQrModalBtn');
    const cancelScanQrModalBtn = document.getElementById('cancelScanQrModalBtn');
    const startCameraScanBtn = document.getElementById('startCameraScanBtn');
    const qrScanStatusMsg = document.getElementById('qrScanStatusMsg');
    const scanQrForm = document.getElementById('scanQrForm');
    const qrPayloadInput = document.getElementById('qrPayloadInput');
    const studentMonthFilter = document.getElementById('studentMonthFilter');

    let html5QrScannerInstance = null;

    const stopCameraScan = async () => {
        if (html5QrScannerInstance) {
            try {
                await html5QrScannerInstance.stop();
                html5QrScannerInstance.clear();
            } catch (e) {
                console.warn('Camera stop error:', e);
            }
            html5QrScannerInstance = null;
        }
        const placeholder = document.getElementById('qr-reader-placeholder');
        if (placeholder) placeholder.style.display = 'block';
    };

    const startCameraScan = async () => {
        if (typeof Html5Qrcode === 'undefined') {
            if (qrScanStatusMsg) qrScanStatusMsg.textContent = 'Camera scanner library loading... please wait.';
            return;
        }
        const placeholder = document.getElementById('qr-reader-placeholder');
        if (placeholder) placeholder.style.display = 'none';

        if (qrScanStatusMsg) qrScanStatusMsg.textContent = 'Requesting camera permission...';

        try {
            if (html5QrScannerInstance) {
                await stopCameraScan();
            }
            html5QrScannerInstance = new Html5Qrcode("qr-reader");
            const qrConfig = { fps: 10, qrbox: { width: 220, height: 220 } };

            const onScanSuccess = (decodedText) => {
                if (qrPayloadInput) qrPayloadInput.value = decodedText;
                if (qrScanStatusMsg) qrScanStatusMsg.textContent = '✅ QR Code Scanned Successfully!';
                showToast('QR Code Scanned! Submitting attendance...', 'success');
                stopCameraScan();
                if (scanQrForm) {
                    scanQrForm.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
                }
            };

            // Attempt Camera 1: Rear Environment Camera
            try {
                await html5QrScannerInstance.start({ facingMode: "environment" }, qrConfig, onScanSuccess, () => {});
            } catch (errRear) {
                console.warn('Rear camera unavailable, trying front camera:', errRear);
                // Attempt Camera 2: Front User Camera
                try {
                    await html5QrScannerInstance.start({ facingMode: "user" }, qrConfig, onScanSuccess, () => {});
                } catch (errFront) {
                    console.warn('Front camera unavailable, checking camera list:', errFront);
                    // Attempt Camera 3: Enumerate camera list
                    const cameras = await Html5Qrcode.getCameras();
                    if (cameras && cameras.length > 0) {
                        await html5QrScannerInstance.start(cameras[0].id, qrConfig, onScanSuccess, () => {});
                    } else {
                        throw errFront;
                    }
                }
            }

            if (qrScanStatusMsg) qrScanStatusMsg.textContent = '📷 Camera Active: Align QR Code within frame';
        } catch (err) {
            console.error('Camera Scanner Error:', err);
            if (placeholder) placeholder.style.display = 'block';

            const isHttpRemote = (window.location.protocol === 'http:' && window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1');
            if (isHttpRemote) {
                const httpsUrl = `https://${window.location.hostname}:5000`;
                if (qrScanStatusMsg) {
                    qrScanStatusMsg.innerHTML = `🔒 Mobile Chrome/Safari restricts camera to HTTPS. <a href="${httpsUrl}" target="_blank" style="color: #F59E0B; text-decoration: underline; font-weight: 800;">Open HTTPS (${httpsUrl})</a> or tap Snap / Upload QR.`;
                }
            } else {
                if (qrScanStatusMsg) {
                    qrScanStatusMsg.textContent = '⚠️ Camera unavailable or permission denied. Tap Snap / Upload QR to select a photo.';
                }
            }
        }
    };


    if (openScanQrBtn) {
        openScanQrBtn.addEventListener('click', (e) => {
            if (e) e.preventDefault();
            if (!currentUser || currentUser.role !== 'student') {
                showToast('QR attendance scanner is only accessible on Student accounts.', 'error');
                return;
            }
            if (scanQrForm) scanQrForm.reset();
            if (scanQrModal) scanQrModal.classList.remove('hidden');
            startCameraScan();
        });
    }


    if (startCameraScanBtn) {
        startCameraScanBtn.addEventListener('click', (e) => {
            e.preventDefault();
            startCameraScan();
        });
    }

    const qrFileInput = document.getElementById('qrFileInput');
    if (qrFileInput) {
        qrFileInput.addEventListener('change', async (e) => {
            if (e.target.files && e.target.files.length > 0) {
                const file = e.target.files[0];
                if (qrScanStatusMsg) qrScanStatusMsg.textContent = '🔍 Decoding QR Code from photo...';
                try {
                    const tempScanner = new Html5Qrcode("qr-reader");
                    const decodedText = await tempScanner.scanFile(file, true);
                    if (qrPayloadInput) qrPayloadInput.value = decodedText;
                    if (qrScanStatusMsg) qrScanStatusMsg.textContent = '✅ QR Code Read Successfully!';
                    showToast('QR Code Read! Submitting attendance...', 'success');
                    if (scanQrForm) {
                        scanQrForm.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
                    }
                } catch (err) {
                    console.error('File QR Scan Error:', err);
                    showToast('Could not read QR code from image. Please upload a clear QR photo.', 'error');
                    if (qrScanStatusMsg) qrScanStatusMsg.textContent = '⚠️ Could not read QR image. Please upload a clear QR photo.';
                }
            }
        });
    }


    const closeScanQrModal = () => {
        stopCameraScan();
        if (scanQrModal) scanQrModal.classList.add('hidden');
    };

    if (closeScanQrModalBtn) closeScanQrModalBtn.addEventListener('click', closeScanQrModal);
    if (cancelScanQrModalBtn) cancelScanQrModalBtn.addEventListener('click', closeScanQrModal);

    // Wraps the browser Geolocation API in a Promise so it can be awaited
    // before submitting the scan. Requires HTTPS (or localhost) to work,
    // since browsers block geolocation on plain HTTP origins.
    const getCurrentLocation = () => {
        return new Promise((resolve, reject) => {
            if (!navigator.geolocation) {
                reject(new Error('Geolocation is not supported by this browser.'));
                return;
            }
            navigator.geolocation.getCurrentPosition(
                (position) => resolve({
                    lat: position.coords.latitude,
                    lng: position.coords.longitude
                }),
                (err) => reject(err),
                { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
            );
        });
    };

    if (scanQrForm) {
        scanQrForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const rawVal = qrPayloadInput ? qrPayloadInput.value.trim() : '';
            if (!rawVal) {
                showToast('Please scan a live QR code or upload a QR image first.', 'error');
                if (qrScanStatusMsg) qrScanStatusMsg.textContent = '⚠️ No QR code detected. Align QR code within frame or tap Snap / Upload.';
                return;
            }

            let payloadObj = {};
            try {
                if (rawVal.startsWith('{')) {
                    payloadObj = JSON.parse(rawVal);
                } else {
                    payloadObj = { session_id: rawVal, subject: 'Classroom Attendance' };
                }
            } catch (err) {
                payloadObj = { session_id: rawVal, subject: 'Classroom Attendance' };
            }

            // --- Geolocation capture ---
            // Fetch the student's current GPS position and attach it to the
            // payload so the server can confirm they are on campus. If the
            // student denies permission or location can't be acquired, we
            // block the submission rather than send attendance without it.
            if (qrScanStatusMsg) qrScanStatusMsg.textContent = '📍 Verifying your location…';
            try {
                const coords = await getCurrentLocation();
                payloadObj.lat = coords.lat;
                payloadObj.lng = coords.lng;
            } catch (locErr) {
                let msg = 'Location access is required to mark attendance. Please enable location and try again.';
                if (locErr && locErr.code === 1) {
                    msg = 'Location permission denied. Please allow location access in your browser settings to mark attendance.';
                } else if (locErr && locErr.code === 3) {
                    msg = 'Could not get your location in time. Please try again with GPS/location services turned on.';
                }
                showToast(msg, 'error');
                if (qrScanStatusMsg) qrScanStatusMsg.textContent = '⚠️ ' + msg;
                return;
            }

            try {
                const res = await fetch('/api/student/mark-attendance', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payloadObj)
                });
                const data = await res.json();

                if (!res.ok) {
                    showToast(data.error || 'Failed to mark attendance.', 'error');
                    return;
                }

                showToast(data.message || 'Attendance marked as Present!', 'success');
                closeScanQrModal();
                fetchStudentAttendance();
            } catch (err) {
                showToast('Network error marking attendance.', 'error');
            }
        });
    }

    // --- Student Calendar & Attendance Controller ---
    const prevCalMonthBtn = document.getElementById('prevCalMonthBtn');
    const nextCalMonthBtn = document.getElementById('nextCalMonthBtn');
    const calCurrentMonthLabel = document.getElementById('calCurrentMonthLabel');
    const studentCalendarGrid = document.getElementById('studentCalendarGrid');

    let calYear = new Date().getFullYear();
    let calMonth = new Date().getMonth(); // 0 - 11
    let studentAllRecords = [];
    let studentHolidays = [];

    if (prevCalMonthBtn) {
        if (prevCalMonthBtn) prevCalMonthBtn.addEventListener('click', () => {
            calMonth--;
            if (calMonth < 0) {
                calMonth = 11;
                calYear--;
            }
            renderStudentMonthlyCalendar();
        });
    }

    if (nextCalMonthBtn) {
        if (nextCalMonthBtn) nextCalMonthBtn.addEventListener('click', () => {
            calMonth++;
            if (calMonth > 11) {
                calMonth = 0;
                calYear++;
            }
            renderStudentMonthlyCalendar();
        });
    }

    // --- Draggable & Touch Swipe Gesture Support for Monthly Calendar ---
    const calContainer = document.getElementById('studentCalendarCardContainer');
    if (calContainer) {
        let touchStartX = 0;
        let touchStartY = 0;
        let isSwiping = false;

        calContainer.addEventListener('touchstart', (e) => {
            if (e.touches && e.touches.length === 1) {
                touchStartX = e.touches[0].clientX;
                touchStartY = e.touches[0].clientY;
                isSwiping = true;
            }
        }, { passive: true });

        calContainer.addEventListener('touchend', (e) => {
            if (!isSwiping) return;
            isSwiping = false;
            if (e.changedTouches && e.changedTouches.length === 1) {
                const diffX = touchStartX - e.changedTouches[0].clientX;
                const diffY = touchStartY - e.changedTouches[0].clientY;

                if (Math.abs(diffX) > 35 && Math.abs(diffX) > Math.abs(diffY)) {
                    if (diffX > 0 && nextCalMonthBtn) {
                        nextCalMonthBtn.click();
                    } else if (diffX < 0 && prevCalMonthBtn) {
                        prevCalMonthBtn.click();
                    }
                }
            }
        }, { passive: true });

        let mouseStartX = 0;
        let isMouseDown = false;

        calContainer.addEventListener('mousedown', (e) => {
            mouseStartX = e.clientX;
            isMouseDown = true;
        });

        calContainer.addEventListener('mouseup', (e) => {
            if (!isMouseDown) return;
            isMouseDown = false;
            const diffX = mouseStartX - e.clientX;
            if (Math.abs(diffX) > 45) {
                if (diffX > 0 && nextCalMonthBtn) {
                    nextCalMonthBtn.click();
                } else if (diffX < 0 && prevCalMonthBtn) {
                    prevCalMonthBtn.click();
                }
            }
        });
    }


    if (studentMonthFilter) {
        if (studentMonthFilter) studentMonthFilter.addEventListener('change', fetchStudentAttendance);
    }

    async function fetchStudentAttendance() {
        if (!currentUser || currentUser.role !== 'student') return;
        const monthFilterVal = studentMonthFilter ? studentMonthFilter.value : '';

        try {
            const res = await fetch(`/api/student/attendance`);
            const data = await res.json();
            if (!res.ok) return;

            studentAllRecords = data.attendance || [];
            studentHolidays = data.holidays || [];
            
            // Filter records for table
            let filteredRecords = studentAllRecords;
            if (monthFilterVal) {
                filteredRecords = studentAllRecords.filter(r => r.date && r.date.startsWith(monthFilterVal));
            }
            renderStudentAttendanceRecords(filteredRecords);

            // Render Interactive Calendar
            renderStudentMonthlyCalendar();
        } catch (err) {
            console.error('Error fetching student attendance', err);
        }
    }

    function renderStudentMonthlyCalendar() {
        if (!studentCalendarGrid) return;

        const dateObj = new Date(calYear, calMonth, 1);
        const monthNames = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
        if (calCurrentMonthLabel) {
            calCurrentMonthLabel.textContent = `${monthNames[calMonth]} ${calYear}`;
        }

        // Map attendance by date "YYYY-MM-DD"
        const attendanceByDate = {};
        studentAllRecords.forEach(r => {
            if (r.date) {
                if (!attendanceByDate[r.date]) attendanceByDate[r.date] = [];
                attendanceByDate[r.date].push(r);
            }
        });

        // Map holidays by date "YYYY-MM-DD"
        const holidayByDate = {};
        studentHolidays.forEach(h => {
            if (h.date) holidayByDate[h.date] = h;
        });

        const firstDayOfWeek = dateObj.getDay(); // 0 (Sun) - 6 (Sat)
        const daysInMonth = new Date(calYear, calMonth + 1, 0).getDate();
        const daysInPrevMonth = new Date(calYear, calMonth, 0).getDate();

        const now = new Date();
        const todayStr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
        
        let countP = 0;
        let countA = 0;
        let countL = 0;
        let countH = 0;

        let gridHtml = '';

        // Previous Month Padding Days
        for (let i = firstDayOfWeek - 1; i >= 0; i--) {
            const dayNum = daysInPrevMonth - i;
            gridHtml += `
                <div class="calendar-day-box other-month">
                    <span class="calendar-day-number">${dayNum}</span>
                </div>
            `;
        }

        // Current Month Days
        for (let day = 1; day <= daysInMonth; day++) {
            const monthPadded = String(calMonth + 1).padStart(2, '0');
            const dayPadded = String(day).padStart(2, '0');
            const dateKey = `${calYear}-${monthPadded}-${dayPadded}`;
            const thisDayDate = new Date(calYear, calMonth, day);
            const dayOfWeek = thisDayDate.getDay(); // 0 = Sun, 6 = Sat

            const dayRecords = attendanceByDate[dateKey] || [];
            const hasAttended = dayRecords.length > 0;
            const holidayObj = holidayByDate[dateKey];
            const isToday = (dateKey === todayStr);

            let statusType = '';
            let boxClass = 'calendar-day-box';
            if (isToday) boxClass += ' is-today';

            // Determine status type from attendance record status or holiday schedule
            const recStatus = dayRecords.length > 0 ? (dayRecords[0].status || '').toLowerCase() : '';

            if (recStatus.includes('hol') || recStatus === 'h' || (dayRecords.length === 0 && holidayObj)) {
                statusType = 'H';
                boxClass += ' day-holiday';
                countH++;
            } else if (recStatus.includes('pres') || recStatus === 'p') {
                statusType = 'P';
                boxClass += ' day-present';
                countP++;
            } else if (recStatus.includes('abs') || recStatus === 'a') {
                statusType = 'A';
                boxClass += ' day-absent';
                countA++;
            } else if (recStatus.includes('leave') || recStatus === 'l') {
                statusType = 'L';
                boxClass += ' day-leave';
                countL++;
            } else if (dateKey <= todayStr) {
                // Past or today date with no attendance record
                if (dayOfWeek === 0 || dayOfWeek === 6) {
                    statusType = 'L'; // Weekend / Off
                    boxClass += ' day-leave';
                    countL++;
                } else {
                    statusType = 'A'; // Absent on weekday
                    boxClass += ' day-absent';
                    countA++;
                }
            }



            let badgeHtml = '';
            if (statusType === 'P') {
                const firstSubj = dayRecords[0] ? dayRecords[0].subject : 'Class';
                badgeHtml = `<div class="cal-badge cal-badge-p" title="Present: ${escapeHtml(firstSubj)}">P</div>`;
            } else if (statusType === 'A') {
                badgeHtml = `<div class="cal-badge cal-badge-a" title="Absent">A</div>`;
            } else if (statusType === 'L') {
                badgeHtml = `<div class="cal-badge cal-badge-l" title="Leave / Off Day">L</div>`;
            } else if (statusType === 'H') {
                const hTitle = holidayObj ? holidayObj.title : 'College Holiday';
                badgeHtml = `<div class="cal-badge cal-badge-h" title="Holiday: ${escapeHtml(hTitle)}">H</div>`;
            }

            gridHtml += `
                <div class="${boxClass}" data-date="${dateKey}" data-status="${statusType}">
                    <span class="calendar-day-number">${day}</span>
                    ${badgeHtml}
                </div>
            `;
        }

        // Next Month Padding Days
        const totalCells = firstDayOfWeek + daysInMonth;
        const nextMonthPadding = (7 - (totalCells % 7)) % 7;
        for (let i = 1; i <= nextMonthPadding; i++) {
            gridHtml += `
                <div class="calendar-day-box other-month">
                    <span class="calendar-day-number">${i}</span>
                </div>
            `;
        }

        studentCalendarGrid.innerHTML = gridHtml;

        // Update Summary Counters
        const calCountP = document.getElementById('calCountP');
        const calCountA = document.getElementById('calCountA');
        const calCountL = document.getElementById('calCountL');
        const calCountH = document.getElementById('calCountH');
        if (calCountP) calCountP.textContent = countP;
        if (calCountA) calCountA.textContent = countA;
        if (calCountL) calCountL.textContent = countL;
        if (calCountH) calCountH.textContent = countH;

        // Update Top Dashboard Stats Badges
        const totalAttendedEl = document.getElementById('studentTotalAttendedCount');
        const monthlyBadgeEl = document.getElementById('studentMonthlyPctBadge');
        const yearlyBadgeEl = document.getElementById('studentYearlyPctBadge');
        const legacyPctBadge = document.getElementById('studentAttendancePctBadge');
        const statusRatingEl = document.getElementById('studentAttendanceStatusRating');

        // 1. Calculate Yearly / Overall Attendance across ALL logged student records
        let yearlyPresent = 0;
        let yearlyAbsent = 0;
        (studentAllRecords || []).forEach(r => {
            const st = (r.status || '').toLowerCase();
            if (st.includes('pres') || st === 'p') yearlyPresent++;
            else if (st.includes('abs') || st === 'a') yearlyAbsent++;
        });

        const yearlyWorking = yearlyPresent + yearlyAbsent;
        const yearlyRateVal = yearlyWorking > 0 ? (yearlyPresent / yearlyWorking) * 100 : 0;
        const yearlyRateStr = yearlyRateVal % 1 === 0 ? yearlyRateVal.toFixed(0) + '%' : yearlyRateVal.toFixed(1) + '%';

        // 2. Calculate Monthly Attendance for the active calendar month
        const monthlyWorking = countP + countA;
        const monthlyRateVal = monthlyWorking > 0 ? (countP / monthlyWorking) * 100 : 0;
        const monthlyRateStr = monthlyRateVal % 1 === 0 ? monthlyRateVal.toFixed(0) + '%' : monthlyRateVal.toFixed(1) + '%';

        // Update Total Attended Count
        if (totalAttendedEl) totalAttendedEl.textContent = countP;

        // Update Monthly Attendance Badge
        if (monthlyBadgeEl) {
            monthlyBadgeEl.textContent = monthlyWorking > 0 ? monthlyRateStr : '0%';
            monthlyBadgeEl.style.color = monthlyRateVal >= 75 ? '#10B981' : (monthlyRateVal >= 45 ? '#F59E0B' : '#EF4444');
        }
        if (legacyPctBadge) {
            legacyPctBadge.textContent = monthlyWorking > 0 ? monthlyRateStr : yearlyRateStr;
        }

        // Update Yearly Attendance Badge
        if (yearlyBadgeEl) {
            yearlyBadgeEl.textContent = yearlyWorking > 0 ? yearlyRateStr : '0%';
            yearlyBadgeEl.style.color = yearlyRateVal >= 75 ? '#10B981' : (yearlyRateVal >= 45 ? '#F59E0B' : '#EF4444');
        }

        // Determine Effective Rate for Eligibility Status & Shortage Alert
        const effectiveRate = monthlyWorking > 0 ? monthlyRateVal : yearlyRateVal;
        const effectiveRateStr = monthlyWorking > 0 ? monthlyRateStr : yearlyRateStr;
        const isShortage = (monthlyWorking > 0 && monthlyRateVal < 45.0) || (yearlyWorking > 0 && yearlyRateVal < 45.0);

        if (statusRatingEl) {
            if (isShortage) {
                statusRatingEl.innerHTML = '<span style="color: #EF4444;">🚨 Shortage (&lt;45%)</span>';
            } else if (effectiveRate >= 75) {
                statusRatingEl.innerHTML = '<span style="color: #10B981;">🟢 Good</span>';
            } else {
                statusRatingEl.innerHTML = '<span style="color: #F59E0B;">🟡 Warning</span>';
            }
        }

        // Student Low Attendance Warning Alert (< 45%)
        const studentAlertBox = document.getElementById('studentLowAttendanceAlert');
        const studentLowPctEl = document.getElementById('studentLowAttPct');
        if (studentAlertBox) {
            if (isShortage) {
                studentAlertBox.classList.remove('hidden');
                if (studentLowPctEl) studentLowPctEl.textContent = effectiveRateStr;
            } else {
                studentAlertBox.classList.add('hidden');
            }
        }





        // Add Click Handler for Days
        studentCalendarGrid.querySelectorAll('.calendar-day-box').forEach(box => {
            box.addEventListener('click', () => {
                const date = box.dataset.date;
                const status = box.dataset.status;
                if (!date || !status) return;

                if (status === 'P') {
                    const recs = attendanceByDate[date] || [];
                    const details = recs.map(r => `• ${r.subject} (Session: ${r.session_id} at ${r.time})`).join('\n');
                    showToast(`🟢 [P] Present on ${date}:\n${details}`, 'success');
                } else if (status === 'H') {
                    const h = holidayByDate[date];
                    const title = h ? h.title : 'College Holiday';
                    showToast(`🟣 [H] Holiday on ${date}: ${title}`, 'info');
                } else if (status === 'A') {
                    showToast(`🔴 [A] Absent on ${date} (No class attendance logged)`, 'error');
                } else if (status === 'L') {
                    showToast(`🟡 [L] Leave / Off Day on ${date}`, 'info');
                }
            });
        });
    }



    function renderDynamicStatusBadge(status) {
        const s = (status || 'Present').toLowerCase();
        if (s.includes('hol') || s === 'h') {
            return `<span class="badge" style="background: rgba(139, 92, 246, 0.15); color: #8B5CF6; border: 1px solid rgba(139, 92, 246, 0.35); font-weight: 700;">🟣 Holiday</span>`;
        } else if (s.includes('abs') || s === 'a') {
            return `<span class="badge" style="background: rgba(239, 68, 68, 0.15); color: #EF4444; border: 1px solid rgba(239, 68, 68, 0.35); font-weight: 700;">🔴 Absent</span>`;
        } else if (s.includes('leave') || s === 'l') {
            return `<span class="badge" style="background: rgba(245, 158, 11, 0.15); color: #F59E0B; border: 1px solid rgba(245, 158, 11, 0.35); font-weight: 700;">🟡 Leave</span>`;
        } else {
            return `<span class="badge badge-student" style="background: rgba(16, 185, 129, 0.15); color: #10B981; border: 1px solid rgba(16, 185, 129, 0.35); font-weight: 700;">🟢 Present</span>`;
        }
    }

    function renderStudentAttendanceRecords(records) {
        const tbody = document.getElementById('studentAttendanceTableBody');
        const cards = document.getElementById('studentAttendanceMobileCards');
        const emptyState = document.getElementById('noStudentAttendanceState');
        const totalCountEl = document.getElementById('studentTotalAttendedCount');
        const pctBadge = document.getElementById('studentAttendancePctBadge');

        const presentCount = records.filter(r => (r.status || 'Present').toLowerCase().includes('pres')).length;
        if (totalCountEl) totalCountEl.textContent = presentCount;

        if (pctBadge) {
            const rate = records.length > 0 ? Math.round((presentCount / records.length) * 100) : 100;
            pctBadge.textContent = `${rate}%`;
        }

        if (!records || records.length === 0) {
            if (tbody) tbody.innerHTML = '';
            if (cards) cards.innerHTML = '';
            if (emptyState) emptyState.classList.remove('hidden');
            return;
        }

        if (emptyState) emptyState.classList.add('hidden');

        if (tbody) {
            tbody.innerHTML = records.map(r => `
                <tr>
                    <td><strong>${escapeHtml(r.subject)}</strong></td>
                    <td>${escapeHtml(r.class_name)}</td>
                    <td><span class="badge badge-staff">${escapeHtml(r.session_id)}</span></td>
                    <td>${escapeHtml(r.date)}</td>
                    <td>${escapeHtml(r.time)}</td>
                    <td>${renderDynamicStatusBadge(r.status)}</td>
                </tr>
            `).join('');
        }

        if (cards) {
            cards.innerHTML = records.map(r => `
                <div class="user-card" style="margin-bottom: 0.75rem;">
                    <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.5rem;">
                        <h4 style="font-size: 1.05rem; font-weight: 700; color: var(--color-navy-dark);">${escapeHtml(r.subject)}</h4>
                        ${renderDynamicStatusBadge(r.status)}
                    </div>
                    <div style="font-size: 0.85rem; color: var(--color-text-muted); display: grid; gap: 0.25rem;">
                        <div><strong>Class:</strong> ${escapeHtml(r.class_name)}</div>
                        <div><strong>Session:</strong> ${escapeHtml(r.session_id)}</div>
                        <div><strong>Date & Time:</strong> ${escapeHtml(r.date)} at ${escapeHtml(r.time)}</div>
                    </div>
                </div>
            `).join('');
        }
    }



    // --- Staff Department Attendance Controller ---
    const staffAttendanceDeptFilter = document.getElementById('staffAttendanceDeptFilter');
    const staffAttendanceDateFilter = document.getElementById('staffAttendanceDateFilter');
    const staffAttendanceSemesterFilter = document.getElementById('staffAttendanceSemesterFilter');
    const staffAttendanceSubjectFilter = document.getElementById('staffAttendanceSubjectFilter');
    const staffExportCsvBtn = document.getElementById('staffExportCsvBtn');

    if (staffAttendanceDeptFilter) staffAttendanceDeptFilter.addEventListener('change', fetchStaffAttendance);
    if (staffAttendanceDateFilter) staffAttendanceDateFilter.addEventListener('change', fetchStaffAttendance);
    if (staffAttendanceSemesterFilter) staffAttendanceSemesterFilter.addEventListener('change', fetchStaffAttendance);
    if (staffAttendanceSubjectFilter) staffAttendanceSubjectFilter.addEventListener('input', fetchStaffAttendance);

    if (staffExportCsvBtn) {
        if (staffExportCsvBtn) staffExportCsvBtn.addEventListener('click', () => {
            const dept = staffAttendanceDeptFilter ? staffAttendanceDeptFilter.value : ((currentUser && currentUser.department) ? currentUser.department : 'all');
            const semester = staffAttendanceSemesterFilter ? staffAttendanceSemesterFilter.value : 'all';
            window.location.href = `/api/admin/export-attendance?department=${encodeURIComponent(dept)}&semester=${encodeURIComponent(semester)}`;
            showToast('Downloading Department Attendance Report...', 'success');
        });
    }

    async function fetchStaffAttendance() {
        if (!currentUser || (currentUser.role !== 'staff' && currentUser.role !== 'admin')) return;
        const dept = staffAttendanceDeptFilter ? staffAttendanceDeptFilter.value : '';
        const date = staffAttendanceDateFilter ? staffAttendanceDateFilter.value : '';
        const semester = staffAttendanceSemesterFilter ? staffAttendanceSemesterFilter.value : 'all';
        const subject = staffAttendanceSubjectFilter ? staffAttendanceSubjectFilter.value.trim() : '';

        try {
            const res = await fetch(`/api/staff/attendance?department=${encodeURIComponent(dept)}&date=${encodeURIComponent(date)}&semester=${encodeURIComponent(semester)}&subject=${encodeURIComponent(subject)}`);
            const data = await res.json();
            if (!res.ok) return;

            renderStaffAttendanceRecords(data.attendance || []);
        } catch (err) {
            console.error('Error fetching staff attendance', err);
        }
    }




    function renderStatusOverrideSelect(r) {
        const s = (r.status || 'Present').toLowerCase();
        const isP = s.includes('pres') || s === 'p';
        const isA = s.includes('abs') || s === 'a';
        const isL = s.includes('leave') || s === 'l';
        const isH = s.includes('hol') || s === 'h';

        return `
            <select class="status-select-override" data-id="${r.id}" title="Security Override Status (P, A, L, H)" style="padding: 0.25rem 0.5rem; font-weight: 800; border-radius: 6px; border: 1.5px solid var(--color-border); font-size: 0.8rem; cursor: pointer; background: #FFFFFF; color: var(--color-navy-dark);">
                <option value="Present" ${isP ? 'selected' : ''} style="color: #10B981; font-weight: 700;">🟢 P (Present)</option>
                <option value="Absent" ${isA ? 'selected' : ''} style="color: #EF4444; font-weight: 700;">🔴 A (Absent)</option>
                <option value="Leave" ${isL ? 'selected' : ''} style="color: #F59E0B; font-weight: 700;">🟡 L (Leave)</option>
                <option value="Holiday" ${isH ? 'selected' : ''} style="color: #8B5CF6; font-weight: 700;">🟣 H (Holiday)</option>
            </select>
        `;
    }

    document.addEventListener('change', async (e) => {
        if (e.target && e.target.classList.contains('status-select-override')) {
            const attendanceId = e.target.dataset.id;
            const newStatus = e.target.value;
            try {
                const res = await fetch('/api/attendance/update-status', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ attendance_id: attendanceId, status: newStatus })
                });
                const data = await res.json();
                if (res.ok) {
                    showToast(data.message || `Status updated to ${newStatus}`, 'success');
                    if (currentUser) {
                        if (currentUser.role === 'staff') fetchStaffAttendance();
                        if (currentUser.role === 'admin') fetchAdminAttendance();
                        if (currentUser.role === 'student') fetchStudentAttendance();
                    }
                } else {
                    showToast(data.error || 'Failed to update status', 'error');
                }
            } catch (err) {
                showToast('Error updating attendance status.', 'error');
            }
        }
    });


    // --- Manual Attendance Modal Controller (Staff & Admin) ---
    const manualAttendanceModal = document.getElementById('manualAttendanceModal');
    const manualAttendanceForm = document.getElementById('manualAttendanceForm');
    const closeManualAttModalBtn = document.getElementById('closeManualAttModalBtn');
    const cancelManualAttBtn = document.getElementById('cancelManualAttBtn');
    const manualAttDept = document.getElementById('manualAttDept');
    const manualAttSemester = document.getElementById('manualAttSemester');
    const manualAttStudentId = document.getElementById('manualAttStudentId');
    const manualAttDate = document.getElementById('manualAttDate');

    async function loadManualModalStudents() {
        if (!manualAttStudentId) return;
        const dept = manualAttDept ? manualAttDept.value : 'all';
        const semester = manualAttSemester ? manualAttSemester.value : 'all';

        try {
            const res = await fetch(`/api/staff/students?department=${encodeURIComponent(dept)}&semester=${encodeURIComponent(semester)}`);
            const data = await res.json();
            if (!res.ok) return;

            const students = data.students || [];
            if (students.length === 0) {
                manualAttStudentId.innerHTML = '<option value="">-- No Students Found --</option>';
            } else {
                manualAttStudentId.innerHTML = '<option value="">-- Select Student --</option>' +
                    students.map(s => `<option value="${s.id}">${escapeHtml(s.full_name)} (${escapeHtml(s.roll_no || 'N/A')}) - ${escapeHtml(s.semester || 'N/A')}</option>`).join('');
            }
        } catch (err) {
            console.error('Error loading students for manual modal', err);
        }
    }

    if (manualAttDept) manualAttDept.addEventListener('change', loadManualModalStudents);
    if (manualAttSemester) manualAttSemester.addEventListener('change', loadManualModalStudents);

    document.addEventListener('click', (e) => {
        const btn = e.target ? (e.target.classList.contains('open-manual-att-modal-btn') ? e.target : e.target.closest('.open-manual-att-modal-btn')) : null;
        if (btn) {
            e.preventDefault();
            e.stopPropagation();
            if (manualAttendanceModal) {
                if (manualAttDate && !manualAttDate.value) {
                    manualAttDate.value = new Date().toISOString().split('T')[0];
                }
                if (manualAttDept && currentUser && currentUser.department && currentUser.department !== 'Administration') {
                    manualAttDept.value = currentUser.department;
                }
                loadManualModalStudents();
                manualAttendanceModal.classList.remove('hidden');
            }
        }
    });

    if (closeManualAttModalBtn) closeManualAttModalBtn.addEventListener('click', () => manualAttendanceModal.classList.add('hidden'));
    if (cancelManualAttBtn) cancelManualAttBtn.addEventListener('click', () => manualAttendanceModal.classList.add('hidden'));

    if (manualAttendanceForm) {
        manualAttendanceForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const student_id = manualAttStudentId ? manualAttStudentId.value : '';
            const date = manualAttDate ? manualAttDate.value : '';
            const subject = document.getElementById('manualAttSubject') ? document.getElementById('manualAttSubject').value.trim() : '';
            const status = document.getElementById('manualAttStatus') ? document.getElementById('manualAttStatus').value : 'Present';

            if (!student_id || !date || !subject) {
                showToast('Please select a student, date, and subject.', 'error');
                return;
            }

            try {
                const res = await fetch('/api/attendance/update-status', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ student_id, date, subject, status })
                });
                const data = await res.json();
                if (res.ok) {
                    showToast(data.message || 'Attendance saved successfully!', 'success');
                    manualAttendanceModal.classList.add('hidden');
                    manualAttendanceForm.reset();

                    // Refresh everywhere
                    if (currentUser) {
                        if (currentUser.role === 'staff') fetchStaffAttendance();
                        if (currentUser.role === 'admin') fetchAdminAttendance();
                        if (currentUser.role === 'student') fetchStudentAttendance();
                    }
                } else {
                    showToast(data.error || 'Failed to save attendance.', 'error');
                }
            } catch (err) {
                showToast('Error saving attendance.', 'error');
            }
        });
    }

    // --- Holiday Modal Controller (Admin & Staff) ---
    const createHolidayModal = document.getElementById('createHolidayModal');

    const createHolidayForm = document.getElementById('createHolidayForm');
    const closeHolidayModalBtn = document.getElementById('closeHolidayModalBtn');
    const cancelHolidayBtn = document.getElementById('cancelHolidayBtn');
    const holidayDateInput = document.getElementById('holidayDate');

    document.addEventListener('click', (e) => {
        const btn = e.target ? (e.target.classList.contains('open-holiday-modal-btn') ? e.target : e.target.closest('.open-holiday-modal-btn')) : null;
        if (btn) {
            e.preventDefault();
            e.stopPropagation();
            if (createHolidayModal) {
                if (holidayDateInput && !holidayDateInput.value) {
                    const todayStr = new Date().toISOString().split('T')[0];
                    holidayDateInput.value = todayStr;
                }
                createHolidayModal.classList.remove('hidden');
            }
        }
    });

    if (closeHolidayModalBtn) closeHolidayModalBtn.addEventListener('click', () => createHolidayModal.classList.add('hidden'));
    if (cancelHolidayBtn) cancelHolidayBtn.addEventListener('click', () => createHolidayModal.classList.add('hidden'));


    if (createHolidayForm) {
        createHolidayForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const date = document.getElementById('holidayDate').value;
            const title = document.getElementById('holidayTitle').value.trim();
            const department = document.getElementById('holidayDepartment').value;

            try {
                const res = await fetch('/api/holidays', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ date, title, department })
                });
                const data = await res.json();
                if (res.ok) {
                    showToast(data.message || 'Holiday scheduled successfully!', 'success');
                    createHolidayModal.classList.add('hidden');
                    createHolidayForm.reset();

                    if (currentUser) {
                        if (currentUser.role === 'staff') fetchStaffAttendance();
                        else if (currentUser.role === 'admin') fetchAdminAttendance();
                        else if (currentUser.role === 'student') fetchStudentAttendance();
                    }
                } else {
                    showToast(data.error || 'Failed to schedule holiday.', 'error');
                }

            } catch (err) {
                showToast('Error creating holiday.', 'error');
            }
        });
    }

    function renderStaffAttendanceRecords(records) {
        const tbody = document.getElementById('staffAttendanceTableBody');
        const cards = document.getElementById('staffAttendanceMobileCards');
        const emptyState = document.getElementById('noStaffAttendanceState');

        if (!records || records.length === 0) {
            if (tbody) tbody.innerHTML = '';
            if (cards) cards.innerHTML = '';
            if (emptyState) emptyState.classList.remove('hidden');
            return;
        }

        if (emptyState) emptyState.classList.add('hidden');

        if (tbody) {
            tbody.innerHTML = records.map(r => `
                <tr>
                    <td><strong>${escapeHtml(r.student_name)}</strong></td>
                    <td>${escapeHtml(r.roll_no)}</td>
                    <td>${escapeHtml(r.class_name)}</td>
                    <td>${escapeHtml(r.semester || '-')}</td>
                    <td>${escapeHtml(r.subject)}</td>
                    <td><span class="badge badge-staff">${escapeHtml(r.session_id)}</span></td>
                    <td>${escapeHtml(r.date)} • ${escapeHtml(r.time)}</td>
                    <td>${renderStatusOverrideSelect(r)}</td>
                </tr>
            `).join('');
        }

        if (cards) {
            cards.innerHTML = records.map(r => `
                <div class="user-card" style="margin-bottom: 0.75rem;">
                    <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.5rem;">
                        <h4 style="font-size: 1.05rem; font-weight: 700; color: var(--color-navy-dark);">${escapeHtml(r.student_name)} (${escapeHtml(r.roll_no)})</h4>
                        <div>${renderStatusOverrideSelect(r)}</div>
                    </div>
                    <div style="font-size: 0.85rem; color: var(--color-text-muted); display: grid; gap: 0.25rem;">
                        <div><strong>Class & Semester:</strong> ${escapeHtml(r.class_name)} (${escapeHtml(r.semester || '-')}) • ${escapeHtml(r.subject)}</div>
                        <div><strong>Session ID:</strong> ${escapeHtml(r.session_id)}</div>
                        <div><strong>Date & Time:</strong> ${escapeHtml(r.date)} at ${escapeHtml(r.time)}</div>
                    </div>
                </div>
            `).join('');
        }
    }


    // --- Admin Attendance Reports & Export Hub ---
    const adminDeptFilter = document.getElementById('adminDeptFilter');
    const adminDateFilter = document.getElementById('adminDateFilter');
    const adminSemesterFilter = document.getElementById('adminSemesterFilter');
    const adminAttendanceSearch = document.getElementById('adminAttendanceSearch');
    const exportCsvBtn = document.getElementById('exportCsvBtn');

    if (adminDeptFilter) adminDeptFilter.addEventListener('change', fetchAdminAttendance);
    if (adminDateFilter) adminDateFilter.addEventListener('change', fetchAdminAttendance);
    if (adminSemesterFilter) adminSemesterFilter.addEventListener('change', fetchAdminAttendance);
    if (adminAttendanceSearch) adminAttendanceSearch.addEventListener('input', fetchAdminAttendance);

    if (exportCsvBtn) {
        if (exportCsvBtn) exportCsvBtn.addEventListener('click', () => {
            const dept = adminDeptFilter ? adminDeptFilter.value : 'all';
            const date = adminDateFilter ? adminDateFilter.value : '';
            const semester = adminSemesterFilter ? adminSemesterFilter.value : 'all';
            window.location.href = `/api/admin/export-attendance?department=${encodeURIComponent(dept)}&date=${encodeURIComponent(date)}&semester=${encodeURIComponent(semester)}`;
            showToast('Downloading Excel / CSV Attendance Report...', 'success');
        });
    }


    async function fetchAdminAttendance() {
        if (!currentUser || currentUser.role !== 'admin') return;
        const dept = adminDeptFilter ? adminDeptFilter.value : 'all';
        const date = adminDateFilter ? adminDateFilter.value : '';
        const semester = adminSemesterFilter ? adminSemesterFilter.value : 'all';
        const search = adminAttendanceSearch ? adminAttendanceSearch.value.trim() : '';

        try {
            const res = await fetch(`/api/admin/attendance?department=${encodeURIComponent(dept)}&date=${encodeURIComponent(date)}&semester=${encodeURIComponent(semester)}&search=${encodeURIComponent(search)}`);
            const data = await res.json();
            if (!res.ok) return;

            // Handle Low Attendance Alerts (< 45%) for Admin
            const alertBox = document.getElementById('adminLowAttendanceAlert');
            const alertCount = document.getElementById('adminLowAttendanceCount');
            const alertList = document.getElementById('adminLowAttendanceList');

            const lowStudents = data.low_attendance_students || [];
            if (alertBox && alertCount && alertList) {
                if (lowStudents.length > 0) {
                    alertBox.classList.remove('hidden');
                    alertCount.textContent = lowStudents.length;
                    alertList.innerHTML = lowStudents.map(s => `
                        <div style="background: #FFF; border: 1px solid #FCA5A5; border-radius: 6px; padding: 0.35rem 0.65rem; color: #991B1B; font-weight: 700; display: inline-flex; align-items: center; gap: 0.4rem;">
                            <span>🚨 ${escapeHtml(s.student_name)} (${escapeHtml(s.roll_no)})</span>
                            <span style="background: #DC2626; color: #FFF; padding: 0.1rem 0.4rem; border-radius: 4px; font-size: 0.75rem;">${s.attendance_pct}%</span>
                        </div>
                    `).join('');
                } else {
                    alertBox.classList.add('hidden');
                }
            }

            renderAdminAttendanceRecords(data.attendance || []);
        } catch (err) {
            console.error('Error fetching admin attendance', err);
        }
    }


    function renderAdminAttendanceRecords(records) {
        const tbody = document.getElementById('adminAttendanceTableBody');
        const cards = document.getElementById('adminAttendanceMobileCards');
        const emptyState = document.getElementById('noAdminAttendanceState');

        if (!records || records.length === 0) {
            if (tbody) tbody.innerHTML = '';
            if (cards) cards.innerHTML = '';
            if (emptyState) emptyState.classList.remove('hidden');
            return;
        }

        if (emptyState) emptyState.classList.add('hidden');

        if (tbody) {
            tbody.innerHTML = records.map(r => `
                <tr>
                    <td><strong>${escapeHtml(r.student_name)}</strong></td>
                    <td>${escapeHtml(r.roll_no)}</td>
                    <td><span class="badge badge-staff">${escapeHtml(r.department)}</span></td>
                    <td>${escapeHtml(r.class_name)}</td>
                    <td>${escapeHtml(r.semester || '-')}</td>
                    <td>${escapeHtml(r.subject)}</td>
                    <td>${escapeHtml(r.date)} • ${escapeHtml(r.time)}</td>
                    <td><span class="badge badge-secondary">${escapeHtml(r.session_id)}</span></td>
                    <td>${renderStatusOverrideSelect(r)}</td>
                </tr>
            `).join('');
        }

        if (cards) {
            cards.innerHTML = records.map(r => `
                <div class="user-card" style="margin-bottom: 0.75rem;">
                    <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.5rem;">
                        <div>
                            <h4 style="font-size: 1.05rem; font-weight: 700; color: var(--color-navy-dark);">${escapeHtml(r.student_name)}</h4>
                            <span class="badge badge-staff">${escapeHtml(r.department)} • ${escapeHtml(r.roll_no)}</span>
                        </div>
                        <div>${renderStatusOverrideSelect(r)}</div>
                    </div>
                    <div style="font-size: 0.85rem; color: var(--color-text-muted); display: grid; gap: 0.25rem;">
                        <div><strong>Class & Semester:</strong> ${escapeHtml(r.class_name)} (${escapeHtml(r.semester || '-')}) • ${escapeHtml(r.subject)}</div>
                        <div><strong>Session ID:</strong> ${escapeHtml(r.session_id)}</div>
                        <div><strong>Date & Time:</strong> ${escapeHtml(r.date)} at ${escapeHtml(r.time)}</div>
                    </div>
                </div>
            `).join('');
        }
    }



    // --- Teacher Attendance QR Code Generator & Security Controller ---
    const generateQrModal = document.getElementById('generateQrModal');
    const openGenerateQrModalBtn = document.getElementById('openGenerateQrModalBtn');
    const closeQrModalBtn = document.getElementById('closeQrModalBtn');
    const cancelQrModalBtn = document.getElementById('cancelQrModalBtn');
    const generateQrForm = document.getElementById('generateQrForm');
    const qrResultContainer = document.getElementById('qrResultContainer');
    const qrcodeCanvas = document.getElementById('qrcodeCanvas');
    const qrDisplaySubject = document.getElementById('qrDisplaySubject');
    const qrDisplayMeta = document.getElementById('qrDisplayMeta');
    const qrSessionCode = document.getElementById('qrSessionCode');
    const qrLiveDateDisplay = document.getElementById('qrLiveDateDisplay');
    const qrLiveTimeDisplay = document.getElementById('qrLiveTimeDisplay');
    const qrSecurityOverlay = document.getElementById('qrSecurityOverlay');
    const qrWatermarkText = document.getElementById('qrWatermarkText');

    let liveClockInterval = null;
    let totpRefreshInterval = null;
    let activeTotpSession = null;

    function startLiveClockAndTotpLoop(subject, className, duration) {
        if (liveClockInterval) clearInterval(liveClockInterval);
        if (totpRefreshInterval) clearInterval(totpRefreshInterval);
        
        const sessionId = activeTotpSession ? activeTotpSession.sessionId : ('ATT-' + Math.floor(10000 + Math.random() * 90000));
        activeTotpSession = { sessionId, subject, className, duration };

        const fetchAndRenderTotpQr = async () => {
            try {
                const res = await fetch(`/api/staff/totp-qr?session_id=${encodeURIComponent(sessionId)}&subject=${encodeURIComponent(subject)}&class=${encodeURIComponent(className)}`);
                const payload = await res.json();

                if (!res.ok) return;

                if (qrcodeCanvas) qrcodeCanvas.innerHTML = '';

                try {
                    if (typeof QRCode !== 'undefined') {
                        new QRCode(qrcodeCanvas, {
                            text: JSON.stringify(payload),
                            width: 190,
                            height: 190,
                            colorDark: "#0F172A",
                            colorLight: "#ffffff",
                            correctLevel: QRCode.CorrectLevel.H
                        });
                    } else {
                        const encodedData = encodeURIComponent(JSON.stringify(payload));
                        qrcodeCanvas.innerHTML = `<img src="https://api.qrserver.com/v1/create-qr-code/?size=190x190&data=${encodedData}" alt="Dynamic TOTP QR Code" style="max-width: 190px; border-radius: 8px;">`;
                    }
                } catch (err) {
                    const encodedData = encodeURIComponent(JSON.stringify(payload));
                    qrcodeCanvas.innerHTML = `<img src="https://api.qrserver.com/v1/create-qr-code/?size=190x190&data=${encodedData}" alt="Dynamic TOTP QR Code" style="max-width: 190px; border-radius: 8px;">`;
                }

                if (qrSessionCode) qrSessionCode.textContent = sessionId;
                if (qrDisplaySubject) qrDisplaySubject.textContent = subject;
                const teacherName = currentUser ? currentUser.full_name : 'Faculty Staff';
                if (qrDisplayMeta) qrDisplayMeta.textContent = `${className} • Faculty: ${teacherName} (Dynamic TOTP 15s)`;

            } catch (e) {
                console.error('Error fetching TOTP QR:', e);
            }
        };

        // Render immediately
        fetchAndRenderTotpQr();

        // Update clock and 15s countdown every 1 second
        const updateTick = () => {
            const now = new Date();
            const dateStr = now.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' });
            const timeStr = now.toLocaleTimeString('en-US', { hour12: true, hour: '2-digit', minute: '2-digit', second: '2-digit' });
            
            if (qrLiveDateDisplay) qrLiveDateDisplay.textContent = dateStr;
            if (qrLiveTimeDisplay) qrLiveTimeDisplay.textContent = timeStr;

            // 15-second countdown calculation
            const epochSec = Math.floor(now.getTime() / 1000);
            const secLeft = 15 - (epochSec % 15);
            const totpSecRemaining = document.getElementById('totpSecRemaining');
            const totpProgressBar = document.getElementById('totpProgressBar');

            if (totpSecRemaining) totpSecRemaining.textContent = secLeft;
            if (totpProgressBar) {
                const pct = (secLeft / 15) * 100;
                totpProgressBar.style.width = pct + '%';
                totpProgressBar.style.background = secLeft <= 3 ? '#EF4444' : (secLeft <= 6 ? '#F59E0B' : 'linear-gradient(90deg, #10B981 0%, #3B82F6 100%)');
            }

            // Refresh QR code on boundary (when secLeft is 15)
            if (secLeft === 15) {
                fetchAndRenderTotpQr();
            }
        };

        updateTick();
        liveClockInterval = setInterval(updateTick, 1000);
    }

    if (openGenerateQrModalBtn) {
        openGenerateQrModalBtn.addEventListener('click', () => {
            const staffQrDashboardCard = document.getElementById('staffQrDashboardCard');
            if (staffQrDashboardCard) {
                staffQrDashboardCard.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
            const qrSubject = document.getElementById('qrSubject');
            if (qrSubject) qrSubject.focus();

            const qrClassInput = document.getElementById('qrClass');
            if (qrClassInput && currentUser && currentUser.department && !qrClassInput.value) {
                qrClassInput.value = `${currentUser.department} - Section A`;
            }
        });
    }

    const closeQrModal = () => {
        if (qrResultContainer) qrResultContainer.classList.add('hidden');
        if (liveClockInterval) clearInterval(liveClockInterval);
        if (totpRefreshInterval) clearInterval(totpRefreshInterval);
        activeTotpSession = null;
    };

    if (closeQrModalBtn) closeQrModalBtn.addEventListener('click', closeQrModal);
    if (cancelQrModalBtn) cancelQrModalBtn.addEventListener('click', closeQrModal);

    if (generateQrForm) {
        generateQrForm.addEventListener('submit', (e) => {
            e.preventDefault();
            const subject = document.getElementById('qrSubject').value.trim();
            const className = document.getElementById('qrClass').value.trim();
            const duration = document.getElementById('qrValidity').value;

            if (!subject || !className) {
                showToast('Please fill out Subject and Class fields.', 'error');
                return;
            }

            activeTotpSession = null; // Fresh new session ID
            startLiveClockAndTotpLoop(subject, className, duration);

            if (qrResultContainer) {
                qrResultContainer.classList.remove('hidden');
                setTimeout(() => {
                    qrResultContainer.scrollIntoView({ behavior: 'smooth', block: 'center' });
                }, 100);
            }
            showToast('⚡ Live 15-Second Dynamic TOTP QR Active!', 'success');
        });
    }

    // Interactive Quick Action Event Handlers (Re-Generate & Close Buttons on QR Result Box)
    const regenQrBtn = document.getElementById('regenQrBtn');
    const closeQrResultBtn = document.getElementById('closeQrResultBtn');

    if (regenQrBtn) {
        if (regenQrBtn) regenQrBtn.addEventListener('click', () => {
            if (generateQrForm) {
                // Trigger form submission to re-generate fresh QR session with new session ID
                generateQrForm.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
                showToast('QR Code Re-Generated! New Session Active', 'success');
            }
        });
    }

    if (closeQrResultBtn) {
        if (closeQrResultBtn) closeQrResultBtn.addEventListener('click', closeQrModal);
    }

    // --- Mobile & Universal Anti-Screenshot Security Controller ---
    function isQrCodeActive() {
        return qrResultContainer && !qrResultContainer.classList.contains('hidden');
    }

    function showMobileSecurityBlur(reason = 'Screenshots and screen recording are disabled.') {
        if (isQrCodeActive() && qrSecurityOverlay) {
            qrSecurityOverlay.classList.remove('hidden');
            if (reason) showToast(reason, 'error');
        }
    }

    function hideMobileSecurityBlur() {
        if (qrSecurityOverlay) {
            qrSecurityOverlay.classList.add('hidden');
        }
    }

    // Tap to Resume View Button Handlers for Mobile & Desktop Touch
    const resumeQrSecurityBtn = document.getElementById('resumeQrSecurityBtn');
    
    const handleResumeTap = (e) => {
        if (e) {
            e.stopPropagation();
            if (e.cancelable) e.preventDefault();
        }
        hideMobileSecurityBlur();
    };

    if (resumeQrSecurityBtn) {
        resumeQrSecurityBtn.addEventListener('touchstart', handleResumeTap, { passive: false });
        resumeQrSecurityBtn.addEventListener('click', handleResumeTap);
    }

    if (qrSecurityOverlay) {
        qrSecurityOverlay.addEventListener('touchstart', handleResumeTap, { passive: false });
        qrSecurityOverlay.addEventListener('click', handleResumeTap);
    }

    if (qrResultContainer) {
        // Prevent Right Click, Drag, Text Selection, Long Press
        qrResultContainer.addEventListener('contextmenu', (e) => e.preventDefault());
        qrResultContainer.addEventListener('dragstart', (e) => e.preventDefault());
        qrResultContainer.addEventListener('selectstart', (e) => e.preventDefault());

        // Mobile Multi-Touch Screenshot Gesture Protection (e.g. 3-finger swipe or multi-touch hardware capture)
        qrResultContainer.addEventListener('touchstart', (e) => {
            if (e.touches && e.touches.length >= 2) {
                showMobileSecurityBlur('Multi-touch screenshot gesture blocked!');
            }
        }, { passive: true });

        qrResultContainer.addEventListener('touchcancel', () => {
            showMobileSecurityBlur('Screen capture gesture interrupted!');
        });
    }

    // Mobile & Desktop Window State / App Switcher / Screenshot Detection Events
    window.addEventListener('blur', () => showMobileSecurityBlur());
    window.addEventListener('focusout', () => showMobileSecurityBlur());
    window.addEventListener('pagehide', () => showMobileSecurityBlur());
    window.addEventListener('orientationchange', () => showMobileSecurityBlur('Screen orientation changed!'));

    document.addEventListener('visibilitychange', () => {
        if (document.hidden && isQrCodeActive()) {
            showMobileSecurityBlur();
        } else if (!document.hidden && qrSecurityOverlay) {
            hideMobileSecurityBlur();
        }
    });

    // Universal Keyboard Shortcut Protection (Windows, Mac, Mobile Web)
    document.addEventListener('keydown', (e) => {
        if (!isQrCodeActive()) return;

        const key = e.key.toLowerCase();

        // PrintScreen, Windows+Shift+S, Cmd+Shift+3, Cmd+Shift+4
        if (e.key === 'PrintScreen' || e.keyCode === 44 || (e.metaKey && e.shiftKey)) {
            e.preventDefault();
            showMobileSecurityBlur('Screenshots are disabled for attendance QR codes!');
        }

        // Ctrl+P (Print), Ctrl+S (Save), Ctrl+U (Source), F12 / Ctrl+Shift+I (DevTools)
        if ((e.ctrlKey && ['p', 's', 'u'].includes(key)) ||
            (e.ctrlKey && e.shiftKey && ['i', 'c', 'j'].includes(key)) ||
            e.key === 'F12') {
            e.preventDefault();
            showMobileSecurityBlur('Security Blocked: Printing and saving are prohibited.');
        }
    });

    // Toast Notification System
    function showToast(message, type = 'success') {
        const toastContainer = document.getElementById('toastContainer');
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.innerHTML = `
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                ${type === 'success' 
                    ? '<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline>'
                    : '<circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line>'}
            </svg>
            <span>${escapeHtml(message)}</span>
        `;
        toastContainer.appendChild(toast);
        setTimeout(() => toast.remove(), 3500);
    }

    function animateCounter(element, targetValue) {
        let current = 0;
        const duration = 400;
        const stepTime = 20;
        const steps = duration / stepTime;
        const increment = targetValue / steps;

        const timer = setInterval(() => {
            current += increment;
            if (current >= targetValue) {
                element.textContent = targetValue;
                clearInterval(timer);
            } else {
                element.textContent = Math.ceil(current);
            }
        }, stepTime);
    }

    function showError(element, message) {
        element.textContent = message;
        element.classList.remove('hidden');
    }

    function hideError(element) {
        element.textContent = '';
        element.classList.add('hidden');
    }

    // --- Movable Drag & Drop Controller for QR Screen & Modal ---
    function makeElementDraggable(dragHandleEl, targetContainerEl) {
        if (!dragHandleEl || !targetContainerEl) return;

        let isDragging = false;
        let startX = 0, startY = 0;
        let currentTranslateX = 0, currentTranslateY = 0;

        const onDragStart = (e) => {
            if (e.target.closest('button, input, select, a')) return;

            isDragging = true;
            const clientX = e.touches ? e.touches[0].clientX : e.clientX;
            const clientY = e.touches ? e.touches[0].clientY : e.clientY;

            startX = clientX - currentTranslateX;
            startY = clientY - currentTranslateY;

            document.addEventListener('mousemove', onDragMove);
            document.addEventListener('mouseup', onDragEnd);
            document.addEventListener('touchmove', onDragMove, { passive: false });
            document.addEventListener('touchend', onDragEnd);
        };

        const onDragMove = (e) => {
            if (!isDragging) return;
            if (e.cancelable && e.touches) e.preventDefault();

            const clientX = e.touches ? e.touches[0].clientX : e.clientX;
            const clientY = e.touches ? e.touches[0].clientY : e.clientY;

            currentTranslateX = clientX - startX;
            currentTranslateY = clientY - startY;

            targetContainerEl.style.transform = `translate3d(${currentTranslateX}px, ${currentTranslateY}px, 0)`;
        };

        const onDragEnd = () => {
            isDragging = false;
            document.removeEventListener('mousemove', onDragMove);
            document.removeEventListener('mouseup', onDragEnd);
            document.removeEventListener('touchmove', onDragMove);
            document.removeEventListener('touchend', onDragEnd);
        };

        dragHandleEl.addEventListener('mousedown', onDragStart);
        dragHandleEl.addEventListener('touchstart', onDragStart, { passive: false });
    }

    const qrModalDragHeader = document.getElementById('qrModalDragHeader');
    const qrModalContainer = document.getElementById('qrModalContainer');
    const qrCardDragHandle = document.getElementById('qrCardDragHandle');

    makeElementDraggable(qrModalDragHeader, qrModalContainer);
    makeElementDraggable(qrCardDragHandle, qrModalContainer);

    // --------------------------------------------------------------------------
    // Mobile Connect Modal & Server Info Handler
    // --------------------------------------------------------------------------
    const mobileConnectBtn = document.getElementById('mobileConnectBtn');
    const mobileConnectModal = document.getElementById('mobileConnectModal');
    const closeMobileModalBtn = document.getElementById('closeMobileModalBtn');
    const cancelMobileModalBtn = document.getElementById('cancelMobileModalBtn');
    const mobileQrContainer = document.getElementById('mobileQrContainer');
    const mobileUrlInput = document.getElementById('mobileUrlInput');
    const copyMobileUrlBtn = document.getElementById('copyMobileUrlBtn');

    if (mobileConnectBtn && mobileConnectModal) {
        mobileConnectBtn.addEventListener('click', async () => {
            mobileConnectModal.classList.remove('hidden');
            if (mobileUrlInput) mobileUrlInput.value = 'Fetching network IP...';
            if (mobileQrContainer) mobileQrContainer.innerHTML = '<span style="color:#666;">Loading QR Code...</span>';

            try {
                const res = await fetch('/api/server-info');
                const data = await res.json();
                if (data.success && data.mobile_url) {
                    const mobileUrl = data.mobile_url;
                    if (mobileUrlInput) mobileUrlInput.value = mobileUrl;
                    if (mobileQrContainer) {
                        mobileQrContainer.innerHTML = '';
                        if (typeof QRCode !== 'undefined') {
                            new QRCode(mobileQrContainer, {
                                text: mobileUrl,
                                width: 180,
                                height: 180,
                                colorDark: "#0F172A",
                                colorLight: "#FFFFFF",
                                correctLevel: QRCode.CorrectLevel.H
                            });
                        } else {
                            mobileQrContainer.innerHTML = `<img src="https://api.qrserver.com/v1/create-qr-code/?size=180x180&data=${encodeURIComponent(mobileUrl)}" alt="Mobile QR Code">`;
                        }
                    }
                } else {
                    const fallbackUrl = `http://${window.location.hostname}:5000`;
                    if (mobileUrlInput) mobileUrlInput.value = fallbackUrl;
                }
            } catch (err) {
                console.error("Error fetching mobile server info:", err);
                const fallbackUrl = `http://${window.location.hostname}:5000`;
                if (mobileUrlInput) mobileUrlInput.value = fallbackUrl;
                if (mobileQrContainer && typeof QRCode !== 'undefined') {
                    mobileQrContainer.innerHTML = '';
                    new QRCode(mobileQrContainer, {
                        text: fallbackUrl,
                        width: 180,
                        height: 180
                    });
                }
            }
        });

        const closeMobileModal = () => {
            mobileConnectModal.classList.add('hidden');
        };

        if (closeMobileModalBtn) closeMobileModalBtn.addEventListener('click', closeMobileModal);
        if (cancelMobileModalBtn) cancelMobileModalBtn.addEventListener('click', closeMobileModal);

        if (copyMobileUrlBtn && mobileUrlInput) {
            copyMobileUrlBtn.addEventListener('click', () => {
                const url = mobileUrlInput.value;
                if (url && navigator.clipboard) {
                    navigator.clipboard.writeText(url).then(() => {
                        showToast('Mobile LAN address copied to clipboard!', 'success');
                    }).catch(() => {
                        showToast('Could not copy link automatically.', 'error');
                    });
                }
            });
        }
    }

    function escapeHtml(str) {
        if (!str) return '';
        return str.replace(/[&<>"']/g, function(m) {
            return {
                '&': '&amp;',
                '<': '&lt;',
                '>': '&gt;',
                '"': '&quot;',
                "'": '&#039;'
            }[m];
        });
    }
});

