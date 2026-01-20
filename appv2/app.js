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
    imgbbKey: null
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

    // Optimized parameter handling
    const orphanData = params.get("o") || params.get("orphans");
    const empData = params.get("e") || params.get("employees");
    state.imgbbKey = params.get("b") || params.get("imgbb");

    // Safe decoding: tries B64 first (more common now), then decodeURIComponent
    function robustDecode(str) {
        if (!str) return null;

        // Try Base64 first (new optimized way)
        try {
            const b64 = str.replace(/-/g, '+').replace(/_/g, '/');
            const bin = atob(b64);
            const bytes = Uint8Array.from(bin, c => c.charCodeAt(0));
            const decoded = new TextDecoder().decode(bytes);
            if (decoded.startsWith('[') || decoded.startsWith('{')) return decoded;
        } catch (e) { }

        try {
            // Try simple URL decode fallback
            const decoded = decodeURIComponent(str);
            if (decoded.startsWith('[') || decoded.startsWith('{')) return decoded;
        } catch (e) { }

        return null;
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
    const isSupervisor = params.get("s") === "1" || params.get("is_super") === "1";

    // Attempt to find current user's name if they are an employee
    // (Note: This is hard without ID mapping in URL, but we can assume if they aren't super/orphan, they check for themselves)
    // Actually, we'll use first_name as fallback if they aren't in any list.

    if (isSupervisor) {
        state.role = "supervisor";
    } else if (state.employeeList.length > 0) {
        // Simple heuristic: if we have employees and not a supervisor, we are an employee
        // We'll use the TG first_name or placeholder
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

    const btnInEmp = document.getElementById("btn-check-in");
    const btnOutEmp = document.getElementById("btn-check-out");

    document.getElementById("btn-check-in").addEventListener("click", () => {
        submitData("check_in", null, btnInEmp);
    });

    document.getElementById("btn-check-out").addEventListener("click", () => {
        submitData("check_out", null, btnOutEmp);
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

    btnIn.addEventListener("click", () => submitData("check_in", state.targetUserId, btnIn));
    btnOut.addEventListener("click", () => submitData("check_out", state.targetUserId, btnOut));
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
async function submitData(action, targetId = null, btn = null) {
    if (!state.photoBase64) {
        alert("Пожалуйста, сначала сделайте фото.");
        return;
    }

    let originalText = "";
    if (btn) {
        originalText = btn.textContent;
        btn.textContent = "⌛ Загрузка...";
        btn.disabled = true;
    }

    try {
        let payloadImage = null;

        // Force upload to ImgBB
        if (!state.imgbbKey) {
            throw new Error("Отсутствует ключ API для загрузки фото.");
        }

        console.log("Uploading to ImgBB...");
        const uploadedUrl = await uploadToImgBB(state.photoBase64, state.imgbbKey);

        if (uploadedUrl) {
            payloadImage = uploadedUrl;
            console.log("Upload Success:", payloadImage);
        } else {
            throw new Error("Не удалось загрузить фотографию на сервер (ImgBB). Проверьте интернет или настройки.");
        }

        if (btn) btn.textContent = "⌛ Отправка...";

        sendData({
            action: action,
            image: payloadImage,
            target_user_id: targetId || state.user.id
        });
    } catch (e) {
        console.error("Submit error", e);
        alert("Ошибка: " + e.message);
        if (btn) {
            btn.textContent = originalText;
            btn.disabled = false;
        }
    }
}

async function uploadToImgBB(base64, key) {
    try {
        const formData = new FormData();
        formData.append("key", key);
        formData.append("image", base64);

        const response = await fetch("https://api.imgbb.com/1/upload", {
            method: "POST",
            body: formData
        });

        if (response.ok) {
            const data = await response.json();
            return data.data.url;
        }
    } catch (e) {
        console.error("ImgBB upload failed", e);
    }
    return null;
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
