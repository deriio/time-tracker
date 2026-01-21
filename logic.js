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

    // Fallback if no user data but orphans exist
    if (!state.role) {
        state.role = (state.orphanList.length > 0) ? "orphan" : "orphan";
    }

    renderScreen();
}

async function sendData(data) {
    // NEW: Use fetch to webhook server for claim action
    // because tg.sendData doesn't work in group inline buttons
    try {
        const btn = document.activeElement;
        if (btn) btn.disabled = true;

        const payload = {
            ...data,
            user_id: state.user.id,
            group_id: state.groupId,
            username: state.user.username || "Unknown"
        };

        const claimApiUrl = state.apiUrl.replace("/api/checkin", "/api/claim");

        const response = await fetch(claimApiUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (response.ok) {
            document.body.innerHTML = `
                <div style="display:flex;flex-direction:column;justify-content:center;align-items:center;height:100vh;background-color:#000;color:white;text-align:center;padding:20px;">
                     <div style="font-size:80px;">✅</div>
                     <h2 style="margin-top:20px;">Готово!</h2>
                     <p>Ваш аккаунт привязан. Теперь вы можете пользоваться терминалом.</p>
                </div>
            `;
            setTimeout(() => tg.close(), 3000);
        } else {
            alert("Ошибка привязки. Обратитесь к админу.");
            if (btn) btn.disabled = false;
        }
    } catch (e) {
        alert("Ошибка сети: " + e.message);
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



function showError(msg) {
    const app = document.getElementById("app");
    if (app) {
        app.innerHTML = `<div class="screen"><h2>❌</h2><p style="text-align:center">${msg}</p></div>`;
    }
}

// Start
init();
