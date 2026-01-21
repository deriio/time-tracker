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
    const userData = params.get("users");
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
        }
    }

    if (userData) {
        const decoded = robustDecode(userData);
        if (decoded) {
            try {
                const users = JSON.parse(decoded); // [[id, name, role], ...]
                const myId = String(state.user.id);

                // 1. Identify me in the list
                const me = users.find(u => String(u[0]) === myId);

                if (me) {
                    state.employeeName = me[1];
                    state.role = (me[2] === 's') ? 'supervisor' : 'employee';
                    // For supervisor, we need the list of ALL active names
                    state.employeeList = users.map(u => u[1]);
                    console.log(`Identified as: ${state.employeeName} (${state.role})`);
                } else {
                    // Not found in registered users -> must be orphan or unauthorized
                    state.role = "orphan";
                }
            } catch (e) {
                console.error("JSON error users", e);
            }
        }
    }

    // Fallback logic
    if (!state.role) {
        if (state.orphanList.length > 0) {
            state.role = "orphan";
        } else {
            state.role = "unauthorized"; // Show error if no roles found
        }
    }

    console.log("Final State:", { role: state.role, name: state.employeeName, orphans: state.orphanList.length });
    renderScreen();
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

        if (!state.apiUrl) {
            throw new Error("API URL missing (w param)");
        }

        const claimApiUrl = state.apiUrl.replace("/api/checkin", "/api/claim");
        console.log("Binding account via:", claimApiUrl);

        const response = await fetch(claimApiUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Bypass-Tunnel-Reminder': 'true',
                'ngrok-skip-browser-warning': 'true'
            },
            body: JSON.stringify(payload)
        });

        if (response.ok) {
            const result = await response.json();
            console.log("Bind success:", result);

            // Update state with new identity
            state.employeeName = result.name;
            state.role = (result.role === 'supervisor') ? 'supervisor' : 'employee';

            // Success Transition
            const overlay = document.createElement("div");
            overlay.style = "position:fixed;top:0;left:0;width:100%;height:100%;background:#0d0d12;display:flex;flex-direction:column;justify-content:center;align-items:center;z-index:9999;color:white;text-align:center;padding:20px;backdrop-filter:blur(20px);";
            overlay.innerHTML = `
                <div style="font-size:100px; margin-bottom: 20px; animation: scaleUp 0.5s ease-out;">✅</div>
                <h2 style="background:none;-webkit-text-fill-color:white;">Успешно!</h2>
                <p style="font-size:18px; opacity:0.8; margin-top:10px;">Аккаунт <b>${result.name}</b> привязан.<br>Загружаем терминал...</p>
            `;
            document.body.appendChild(overlay);

            setTimeout(() => {
                overlay.remove();
                renderScreen();
            }, 2000);

        } else {
            const errBody = await response.text();
            console.error("Bind failed:", errBody);
            showToast("Ошибка привязки. Проверьте список сотрудников.");
            if (btn) {
                btn.disabled = false;
                btn.textContent = btn._originalText;
            }
        }
    } catch (e) {
        console.error("Bind network error:", e);
        showToast("Ошибка сети: " + e.message);
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
    if (greeting) greeting.textContent = `Здравствуйте, ${state.employeeName}!`;

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
