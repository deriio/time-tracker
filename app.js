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
    state.groupId = params.get("g");
    state.apiUrl = params.get("w"); // Checkin endpoint: .../api/checkin

    console.log("WebApp Init Starting...");

    if (!state.apiUrl) {
        showError("Критическая ошибка: отсутствует адрес API (параметр 'w'). Попросите админа пересоздать кнопку.");
        return;
    }

    try {
        // 1. Fetch Dynamic Config from our Server
        const configUrl = state.apiUrl.replace("/api/checkin", "/api/config");
        console.log("Fetching config from:", configUrl);

        const response = await fetch(configUrl, {
            headers: {
                'Bypass-Tunnel-Reminder': 'true',
                'ngrok-skip-browser-warning': 'true'
            }
        });

        if (!response.ok) throw new Error(`Server status: ${response.status}`);

        const config = await response.json();
        if (!config.ok) throw new Error(config.error || "Unknown server error");

        // 2. Map Data to State
        state.orphanList = config.orphans || [];
        const users = config.users || []; // [[id, name, role_char], ...]
        const myId = String(state.user.id);

        // 3. Identify User
        const me = users.find(u => String(u[0]) === myId);

        if (me) {
            state.employeeName = me[1];
            state.role = (me[2] === 's') ? 'supervisor' : 'employee';
            // For supervisor, we need the names of all employees
            state.employeeList = users.map(u => u[1]);
            console.log(`Identified as: ${state.employeeName} (${state.role})`);
        } else {
            // Not registered yet
            state.role = "orphan";
        }

        console.log("Init Complete. Role:", state.role);
        renderScreen();

    } catch (err) {
        console.error("Initialization Failed:", err);
        showError(`Ошибка загрузки данных: ${err.message}. Проверьте соединение с сервером.`);
    }
}

function initUnauthorizedScreen() {
    const app = document.getElementById("app");
    if (app) {
        app.innerHTML = `
            <div class="screen unauthorized-screen" style="text-align:center;">
                <h2 style="background:none;-webkit-text-fill-color:white;">⛔ Доступ ограничен</h2>
                <div class="subtitle">Ваш аккаунт не найден в системе.</div>
                <div style="margin: 20px 0; background:rgba(255,255,255,0.05); padding:15px; border-radius:12px;">
                    <p style="font-size:0.9em;color:var(--text-dim); margin-bottom:5px;">ID: ${state.user.id || 'Неизвестен'}</p>
                    <p style="font-size:0.9em;color:var(--text-dim);">Username: @${state.user.username || '?'}</p>
                </div>
                <button class="btn secondary" onclick="location.reload()">🔄 Попробовать снова</button>
            </div>
        `;
    }
}

/**
 * Premium Toast Notification
 */
function showToast(message, duration = 3000) {
    console.log("Toast:", message);
    let toast = document.querySelector('.toast');
    if (!toast) {
        toast = document.createElement('div');
        toast.className = 'toast';
        document.body.appendChild(toast);
    }

    toast.textContent = message;
    toast.classList.add('show');

    setTimeout(() => {
        toast.classList.remove('show');
    }, duration);
}

/**
 * Account Binding logic
 */
async function sendData(data, btn = null) {
    if (btn) {
        btn.disabled = true;
        btn._originalText = btn.textContent;
        btn.textContent = "⏳ Привязка...";
    }

    try {
        const payload = {
            ...data,
            user_id: state.user.id,
            group_id: state.groupId,
            username: state.user.username || "Unknown"
        };

        if (!state.apiUrl) throw new Error("API URL missing");

        const claimApiUrl = state.apiUrl.replace("/api/checkin", "/api/claim");
        console.log("Binding account via:", claimApiUrl);

        const response = await fetch(claimApiUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const result = await response.json();

        if (response.ok && result.ok) {
            console.log("Bind success:", result);

            // Standardize: ensure result.name is used to avoid undefined
            state.employeeName = result.name || data.full_name;
            state.role = (result.role === 'supervisor') ? 'supervisor' : 'employee';

            // Success Transition Overlay
            const overlay = document.createElement("div");
            overlay.className = "success-overlay";
            overlay.innerHTML = `
                <div style="font-size:80px; margin-bottom: 20px;">✅</div>
                <h2>Успешно!</h2>
                <p>Вы вошли как <b>${state.employeeName}</b></p>
            `;
            document.body.appendChild(overlay);

            setTimeout(() => {
                overlay.remove();
                renderScreen();
            }, 2000);

        } else {
            throw new Error(result.error || "Ошибка привязки");
        }
    } catch (e) {
        console.error("Bind error:", e);
        showToast(e.message);
        if (btn) {
            btn.disabled = false;
            btn.textContent = btn._originalText;
        }
    }
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
    if (state.role === "unauthorized") initUnauthorizedScreen();
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
        }, btn);
    });
}

// EMPLOYEE SCREEN
function initEmployeeScreen() {
    const greeting = document.getElementById("greeting");
    if (greeting) greeting.textContent = `Здравствуйте!`; // Simplified as requested

    setupCamera("camera-input", "photo-preview", "camera-placeholder", "btn-snap", "btn-retake", () => {
        document.getElementById("btn-check-in").disabled = false;
        document.getElementById("btn-check-out").disabled = false;
    });

    document.getElementById("btn-check-in").addEventListener("click", (e) => {
        submitData("check_in", null, e.currentTarget);
    });

    document.getElementById("btn-check-out").addEventListener("click", (e) => {
        submitData("check_out", null, e.currentTarget);
    });
}

// SUPERVISOR SCREEN
function initSupervisorScreen() {
    const select = document.getElementById("target-select");
    const btnIn = document.getElementById("btn-super-in");
    const btnOut = document.getElementById("btn-super-out");

    // Clear and Fill selection
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
        // Must select someone AND take a photo
        const ok = state.targetUserId && state.photoBase64;
        btnIn.disabled = !ok;
        btnOut.disabled = !ok;
    }

    btnIn.addEventListener("click", (e) => submitData("check_in", state.targetUserId, e.currentTarget));
    btnOut.addEventListener("click", (e) => submitData("check_out", state.targetUserId, e.currentTarget));
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
        showToast("Сначала сделайте фото!");
        return;
    }

    let originalText = "";
    if (btn) {
        originalText = btn.textContent;
        btn.disabled = true;
        btn.textContent = "⏳ Отправка...";
    }

    try {
        const payload = {
            action: action,
            photo: state.photoBase64,
            user_id: state.user.id,
            group_id: state.groupId,
            employee_name: targetId || state.employeeName || state.user.first_name,
            target_user_id: targetId
        };

        if (!state.apiUrl) {
            throw new Error("Webhook URL (w) missing");
        }

        console.log(`Submitting ${action} to: ${state.apiUrl}`);
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
            // Success screen
            document.body.innerHTML = `
                <div style="display:flex;flex-direction:column;justify-content:center;align-items:center;height:100vh;background-color:#0d0d12;color:white;text-align:center;">
                     <div style="font-size:100px; margin-bottom: 20px;">✅</div>
                     <h2 style="background:none;-webkit-text-fill-color:white;">Данные отправлены</h2>
                     <p style="opacity:0.8; margin-top: 10px;">Отчет сохранен в системе.</p>
                </div>
            `;

            setTimeout(() => {
                if (window.Telegram && window.Telegram.WebApp) {
                    window.Telegram.WebApp.close();
                } else {
                    window.close();
                }
            }, 1500);

        } else {
            const err = await response.text();
            console.error("Submit error:", err);
            showToast("Ошибка сервера: " + response.status);
            if (btn) {
                btn.disabled = false;
                btn.textContent = originalText;
            }
        }
    } catch (e) {
        console.error("Submit fetch error:", e);
        showToast("Ошибка сети: " + e.message);
        if (btn) {
            btn.disabled = false;
            btn.textContent = originalText;
        }
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
