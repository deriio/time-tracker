const tg = window.Telegram.WebApp;
if (tg) {
    tg.expand();
    tg.ready();
}

// State
const state = {
    user: tg?.initDataUnsafe?.user || {},
    initData: tg?.initData || "",
    role: null, // "employee", "supervisor", "orphan"
    photoBase64: null,
    orphanList: [],
    employeeList: [],
    targetUserId: null,
    groupId: null,
    employeeName: null,
    apiUrl: null
};

// Start with Retries and Dual-Source ID Tracking
async function init(retryCount = 0) {
    const params = new URLSearchParams(window.location.search);
    state.groupId = params.get("g");
    state.apiUrl = params.get("w");
    const fallbackId = params.get("u");

    console.log(`[Init] Attempt ${retryCount + 1}. SDK ID: ${state.user?.id}, Fallback ID: ${fallbackId}`);

    // If SDK is empty but URL has the ID, use it as a reliable fallback
    if (!state.user?.id && fallbackId) {
        state.user = state.user || {};
        state.user.id = fallbackId;
        console.log("Identity secured via URL fallback.");
    }

    // Guard: Retry if user data is still missing (common on iOS)
    if (!state.user?.id && retryCount < 3) {
        console.warn(`[Retry ${retryCount + 1}] Waiting for Telegram user data...`);
        await new Promise(r => setTimeout(r, 1000));
        state.user = window.Telegram?.WebApp?.initDataUnsafe?.user || state.user || {};
        state.initData = window.Telegram?.WebApp?.initData || "";
        return init(retryCount + 1);
    }

    updateDebugFooter();

    if (!state.apiUrl) {
        showError("Критическая ошибка: отсутствует адрес API.");
        return;
    }

    try {
        const configUrl = state.apiUrl.replace("/api/checkin", "/api/config");
        const response = await fetch(configUrl, {
            headers: {
                'X-Telegram-Init-Data': state.initData || "",
                'Bypass-Tunnel-Reminder': 'true'
            }
        });

        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const config = await response.json();
        if (!config.ok) throw new Error(config.error || "Server error");

        state.orphanList = config.orphans || [];
        const users = config.users || [];
        const myId = String(state.user?.id || "");
        const me = users.find(u => String(u[0]) === myId);

        if (me) {
            state.employeeName = me[1];
            state.role = (me[2] === 's') ? 'supervisor' : 'employee';
            state.employeeList = users.map(u => u[1]);
        } else {
            state.role = "orphan";
        }
        renderScreen();
    } catch (err) {
        console.error("Init Error:", err);
        showError(`Ошибка загрузки: ${err.message}`);
    }
}

function updateDebugFooter() {
    let footer = document.getElementById("debug-footer");
    if (!footer) {
        footer = document.createElement("div");
        footer.id = "debug-footer";
        footer.style = "position:fixed;bottom:2px;left:0;width:100%;text-align:center;font-size:9px;color:rgba(255,255,255,0.15);pointer-events:none;z-index:9999;font-family:monospace;";
        document.body.appendChild(footer);
    }
    footer.innerText = `ID: ${state.user.id || 'N/A'} | SDK: ${tg.version} | ${new Date().toLocaleTimeString()}`;
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
            _initData: state.initData, // Secure transmission in Body
            user_id: state.user.id,
            group_id: state.groupId,
            username: state.user.username || "Unknown"
        };

        if (!state.apiUrl) throw new Error("API URL missing");

        const claimApiUrl = state.apiUrl.replace("/api/checkin", "/api/claim");
        console.log("Binding account via:", claimApiUrl);

        const response = await fetch(claimApiUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Telegram-Init-Data': state.initData
            },
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
            _initData: state.initData, // Secure transmission in Body
            photo: state.photoBase64,
            user_id: state.user.id,
            group_id: state.groupId,
            employee_name: (state.role === 'supervisor') ? "" : state.employeeName,
            target_user_id: (state.role === 'supervisor') ? state.targetUserId : ""
        };

        if (!state.apiUrl) {
            throw new Error("Webhook URL (w) missing");
        }

        console.log(`Submitting ${action} to: ${state.apiUrl}`);
        const response = await fetch(state.apiUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Telegram-Init-Data': state.initData
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
