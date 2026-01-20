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
    targetUserId: null
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

    if (orphanData) {
        try { state.orphanList = JSON.parse(atob(orphanData)); } catch (e) { console.error("Bad orphans data", e); }
    }
    if (empData) {
        try { state.employeeList = JSON.parse(atob(empData)); } catch (e) { console.error("Bad employees data", e); }
    }

    // Role detection logic
    const me = state.employeeList.find(e => Number(e.id) === state.user.id);
    const isSupervisor = params.get("is_super") === "1";

    if (isSupervisor) {
        state.role = "supervisor";
    } else if (me) {
        state.role = "employee";
        state.employeeName = me.name;
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
    if (state.role === "supervisor") initSupervisorScreen();
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

    state.employeeList.forEach(emp => {
        const opt = document.createElement("option");
        opt.value = emp.id;
        opt.textContent = emp.name;
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
function submitData(action, targetId = null) {
    if (!state.photoBase64) return;

    sendData({
        action: action,
        image: state.photoBase64,
        target_user_id: targetId || state.user.id
    });
}

function sendData(data) {
    console.log("Sending data to Telegram:", data);
    if (tg && tg.sendData) {
        tg.sendData(JSON.stringify(data));
        tg.close();
    } else {
        alert("Данные отправлены (Debug): " + data.action);
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
