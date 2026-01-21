const tg = window.Telegram.WebApp;
if (tg) {
    tg.expand();
    tg.ready();
}

// State
const state = {
    user: tg?.initDataUnsafe?.user || {},
    role: null, // "employee", "supervisor", "orphan"
    photoBase64: null,
    orphanList: [],
    employeeList: [],
    targetUserId: null,
    groupId: null,
    employeeName: null,
    apiUrl: null // Will be set from URL params (w parameter)
};

// Start
async function init() {
    const params = new URLSearchParams(window.location.search);
    const isDebug = params.get("debug") === "1";

    console.log("WebApp Init", state.user);

    // Mock user REMOVED to prevent 999999 ID issue.
    // If no user, state.user.id will be undefined.

    // Identify user role and get initial lists
    const orphanData = params.get("orphans");
    const empData = params.get("employees");
    state.groupId = params.get("g");
    state.apiUrl = params.get("w"); // Webhook server URL

    // Safe decoding: tries decodeURIComponent, fallback to B64
    function robustDecode(str) {
        if (!str) return null;
        try {
            // Try simple URL decode first
            const decoded = decodeURIComponent(str);
            if (decoded.startsWith('[') || decoded.startsWith('{')) return decoded;
        } catch (e) { }

        try {
            const b64 = str.replace(/-/g, '+').replace(/_/g, '/');
            const bin = atob(b64);
            const bytes = Uint8Array.from(bin, c => c.charCodeAt(0));
            return new TextDecoder().decode(bytes);
        } catch (e) {
            console.error("Decode error", e);
            return null;
        }
    }

    if (orphanData) {
        const decoded = robustDecode(orphanData);
        if (decoded) {
            try { state.orphanList = JSON.parse(decoded); } catch (e) { console.error("JSON error orphans", e); }
        } else {
            showError("Ошибка декодирования orphans");
        }
    }
    if (empData) {
        const decoded = robustDecode(empData);
        if (decoded) {
            try {
                state.employeeList = JSON.parse(decoded);
                console.log("Employees loaded:", state.employeeList.length);
            } catch (e) {
                console.error("JSON error employees", e);
                showError("Ошибка JSON employees: " + e.message);
            }
        } else {
            showError("Ошибка декодирования employees");
        }
    }

    // DEBUG: Show count
    if (params.get("debug_info") === "1") {
        alert(`Loaded: ${state.employeeList.length} employees, ${state.orphanList.length} orphans`);
    }

    // Role detection logic
    const isSupervisor = params.get("is_super") === "1";

    if (isSupervisor) {
        state.role = "supervisor";
    } else if (state.employeeList.length > 0) {
        state.role = "employee";
        state.employeeName = state.user.first_name || "Сотрудник";
    } else {
        state.role = "orphan";
    }

    renderScreen();
}

function renderScreen() {
    const app = document.getElementById("app");
    const templateId = `template-${state.role}`;
    const template = document.getElementById(templateId);

    if (!template) {
        showError(`Ошибка загрузки экрана: ${state.role}`);
        return;
    }

    app.innerHTML = "";
    app.appendChild(template.content.cloneNode(true));

    if (state.role === "orphan") initOrphanScreen();
    if (state.role === "employee") initEmployeeScreen();
    if (state.role === "supervisor") {
        initSupervisorScreen();
        // Inline Debug if empty
        if (state.employeeList.length === 0) {
            const select = document.getElementById("target-select");
            const debugP = document.createElement("p");
            debugP.style.color = "orange";
            debugP.style.fontSize = "10px";
            debugP.style.marginTop = "5px";
            const rawLen = (params.get("employees") || "").length;
            debugP.textContent = `Внимание: Список пуст.`;
            select.parentNode.appendChild(debugP);
        }
    }
}

// ORPHAN SCREEN
function initOrphanScreen() {
    const select = document.getElementById("orphan-select");
    const btn = document.getElementById("btn-claim");

    state.orphanList.forEach(name => {
        const opt = document.createElement("option");
        opt.value = name;
        opt.textContent = name;
        select.appendChild(opt);
    });

    select.addEventListener("change", () => {
        btn.disabled = !select.value;
    });

    btn.addEventListener("click", () => {
        sendData({
            action: "claim",
            full_name: select.value
        });
    });
}

// EMPLOYEE SCREEN
function initEmployeeScreen() {
    const greeting = document.getElementById("greeting");
    if (greeting) greeting.textContent = `Здравствуйте, ${state.employeeName}!`;

    setupCamera("camera-input", "photo-preview", "camera-placeholder", "btn-snap", "btn-retake", () => {
        document.getElementById("btn-check-in").disabled = false;
        document.getElementById("btn-check-out").disabled = false;
    });

    document.getElementById("btn-check-in").addEventListener("click", () => {
        submitData("check_in");
    });

    document.getElementById("btn-check-out").addEventListener("click", () => {
        submitData("check_out");
    });
}

// SUPERVISOR SCREEN
function initSupervisorScreen() {
    const select = document.getElementById("target-select");
    const btnIn = document.getElementById("btn-super-in");
    const btnOut = document.getElementById("btn-super-out");

    // Clear existing
    select.innerHTML = '<option value="">-- Выберите сотрудника --</option>';

    state.employeeList.forEach(name => {
        const opt = document.createElement("option");
        opt.value = name;
        opt.textContent = name;
        select.appendChild(opt);
    });

    select.addEventListener("change", () => {
        state.targetUserId = select.value; // Here we use Name as ID because we don't have map
        validateSupervisor();
    });

    setupCamera("camera-input-super", "photo-preview-super", "camera-placeholder-super", "btn-snap-super", null, () => {
        validateSupervisor();
    });

    function validateSupervisor() {
        const ok = state.targetUserId && state.photoBase64;
        btnIn.disabled = !ok;
        btnOut.disabled = !ok;
    }

    btnIn.addEventListener("click", () => submitData("check_in", state.targetUserId));
    btnOut.addEventListener("click", () => submitData("check_out", state.targetUserId));
}

// CAMERA HELPER
function setupCamera(inputId, imgId, placeholderId, btnId, retakeId, onCapture) {
    const input = document.getElementById(inputId);
    const img = document.getElementById(imgId);
    const placeholder = document.getElementById(placeholderId);
    const btn = document.getElementById(btnId);
    const retake = retakeId ? document.getElementById(retakeId) : null;

    if (!btn || !input) return;

    btn.addEventListener("click", () => input.click());
    if (retake) retake.addEventListener("click", () => input.click());

    input.addEventListener("change", (e) => {
        const file = e.target.files[0];
        if (!file) return;

        const reader = new FileReader();
        reader.onload = (event) => {
            state.photoBase64 = event.target.result.split(",")[1];
            img.src = event.target.result;
            img.style.display = "block";
            placeholder.style.display = "none";
            if (retake) retake.style.display = "inline-block";
            if (onCapture) onCapture();
        };
        reader.readAsDataURL(file);
    });
}

// COMMUNICATION
async function submitData(action, targetId = null) {
    if (!state.photoBase64) return;

    const btn = document.activeElement;
    let originalText = "";
    let originalColor = "";

    // 1. Visual feedback on BUTTON ONLY
    if (btn) {
        originalText = btn.textContent;
        originalColor = btn.style.backgroundColor;

        btn.disabled = true;
        btn.textContent = "⏳";
        btn.style.backgroundColor = "#555"; // Grey deactived
    }

    try {
        const payload = {
            action: action,
            photo: state.photoBase64,
            user_id: state.user.id, // Will be undefined if NO initData
            group_id: state.groupId,
            employee_name: targetId || state.employeeName || state.user.first_name,
            target_user_id: targetId
        };

        const response = await fetch(state.apiUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Bypass-Tunnel-Reminder': 'true',
                'ngrok-skip-browser-warning': 'true'
            },
            body: JSON.stringify(payload)
        });

        if (response.ok) {
            // 2. Success Feedback (Only NOW replace screen)
            document.body.innerHTML = `
                <div style="display:flex;flex-direction:column;justify-content:center;align-items:center;height:100vh;background-color:#000;color:white;">
                     <div style="font-size:80px;">✅</div>
                     <h2 style="margin-top:20px;">Готово!</h2>
                </div>
            `;

            // 3. Close Logic
            setTimeout(() => {
                if (window.Telegram && window.Telegram.WebApp) {
                    window.Telegram.WebApp.close();
                } else {
                    window.close();
                }
            }, 1000);

        } else {
            // Error: Restore button
            alert("Ошибка сервера: " + response.status);
            if (btn) {
                btn.disabled = false;
                btn.textContent = originalText;
                btn.style.backgroundColor = originalColor;
            }
        }
    } catch (e) {
        alert("Ошибка сети: " + e.message);
        if (btn) {
            btn.disabled = false;
            btn.textContent = originalText;
            btn.style.backgroundColor = originalColor;
        }
    }
}

function sendData(data) {
    // Legacy support for claim
    if (tg && tg.sendData) {
        tg.sendData(JSON.stringify(data));
        tg.close();
    }
}

function showError(msg) {
    const app = document.getElementById("app");
    if (app) {
        app.innerHTML = `<div class="screen"><h2>❌</h2><p style="text-align:center">${msg}</p></div>`;
    }
}

// Start
init();
