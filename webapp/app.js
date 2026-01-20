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
    apiUrl: "https://ninety-dots-begin.loca.lt/api/checkin"
};

// Start
async function init() {
    const params = new URLSearchParams(window.location.search);
    const isDebug = params.get("debug") === "1";

    console.log("WebApp Init", state.user);

    // Bypass check if debug mode is on
    if (!state.user.id && !isDebug) {
        showError("Пожалуйста, откройте это приложение из Telegram.");
        return;
    }

    // Default mock user for debug
    if (!state.user.id && isDebug) {
        state.user = { id: 7042383572, first_name: "Admin", username: "test_user" };
    }

    // Identify user role and get initial lists
    const orphanData = params.get("orphans");
    const empData = params.get("employees");
    state.groupId = params.get("g");

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
    // Now state.employeeList contains strings (names), not objects.
    const isSupervisor = params.get("is_super") === "1";

    // Attempt to find current user's name if they are an employee
    // (Note: This is hard without ID mapping in URL, but we can assume if they aren't super/orphan, they check for themselves)
    // Actually, we'll use first_name as fallback if they aren't in any list.

    if (isSupervisor) {
        state.role = "supervisor";
    } else if (state.employeeList.length > 0) {
        state.role = "employee";
        state.employeeName = state.user.first_name || "Сотрудник";
    } else {
        state.role = "orphan";
    }

    // Attempt name detection if employee
    if (state.role === "employee" && state.user.id) {
        // Logic to find name from list can be added, but for now we use first_name
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
            const rawLen = (empData || "").length;
            debugP.textContent = `Внимание: Список пуст. Параметр: ${rawLen} байт.`;
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
        state.targetUserId = select.value;
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
    if (btn) btn.disabled = true;

    // We can't use tg.sendData because it fails in groups.
    // Instead, we call our own API.
    try {
        const payload = {
            action: action,
            photo: state.photoBase64,
            user_id: state.user.id,
            group_id: state.groupId,
            employee_name: targetId || state.employeeName || state.user.first_name,
            target_user_id: targetId
        };

        const response = await fetch(state.apiUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (response.ok) {
            tg.close();
        } else {
            alert("Ошибка сервера: " + response.status);
            if (btn) btn.disabled = false;
        }
    } catch (e) {
        alert("Ошибка сети: " + e.message);
        if (btn) btn.disabled = false;
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
