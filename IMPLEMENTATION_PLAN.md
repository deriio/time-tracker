# 📋 ПЛАН ИМПЛЕМЕНТАЦИИ: Telegram Time Tracker v2.0

> **Цель**: Обновить бота для учёта рабочего времени с политикой "Только Камера" через Telegram Web App и улучшенным управлением пользователями.

---

## 📊 АНАЛИЗ ТЕКУЩЕЙ СИСТЕМЫ

### Что есть сейчас:
| Компонент | Файл | Функционал |
|-----------|------|------------|
| **Бот** | `main.py` | Aiogram 3.x, обработка фото в чате, авторизация по username |
| **Google Sheets** | `sheets_manager.py` | OAuth 2.0, создание месячных таблиц, логирование |
| **Структура таблиц** | `structure.js` | DB_Logs (логи), Отчет_Месяц (итоги с формулами) |

### Текущий Workflow:
```
Пользователь → Фото в чат → Бот проверяет username → Запись в Google Sheets
```

### Проблемы текущей версии:
1. ❌ Можно отправлять фото из галереи (фейковые отметки)
2. ❌ Авторизация по username (можно сменить в Telegram)
3. ❌ Нет самостоятельной регистрации пользователей
4. ❌ Ручное управление списком сотрудников

---

## 🎯 НОВЫЙ WORKFLOW

```
[Чат-группа]
     │
     ▼
┌─────────────────────────────┐
│  📌 ЗАКРЕПЛЁННОЕ СООБЩЕНИЕ  │
│  [📸 Отметить Приход/Уход]  │◄── Inline Button (WebApp)
└─────────────────────────────┘
     │
     ▼
┌─────────────────────────────┐
│     TELEGRAM WEB APP        │
│  ┌─────────────────────┐    │
│  │  📷 КАМЕРА (ТОЛЬКО!)│    │
│  └─────────────────────┘    │
│  [🟢 НАЧАЛ] [🔴 ЗАКОНЧИЛ]   │
└─────────────────────────────┘
     │
     ▼
┌─────────────────────────────┐
│  БОТ: Получает данные       │
│  → Загружает фото на хостинг│
│  → Постит в чат             │
│  → Пишет в Google Sheets    │
└─────────────────────────────┘
```

---

## 🏗️ АРХИТЕКТУРА РЕШЕНИЯ

### Новая структура файлов:
```
/Check in out BOT/
├── main.py              # [ИЗМЕНИТЬ] Новые обработчики
├── sheets_manager.py    # [ИЗМЕНИТЬ] Новые методы для управления пользователями
├── config.py            # [НОВЫЙ] Константы, списки админов/супервизоров
├── validators.py        # [НОВЫЙ] Валидация initData от Telegram
├── image_uploader.py    # [НОВЫЙ] Загрузка фото на ImgBB
│
├── webapp/              # [НОВАЯ ПАПКА] - Фронтенд
│   ├── index.html       # Главная страница
│   ├── style.css        # Стили
│   ├── app.js           # Основная логика
│   ├── camera.js        # Работа с камерой
│   └── api.js           # Коммуникация с ботом
│
├── requirements.txt     # [ИЗМЕНИТЬ] Добавить httpx для загрузки изображений
└── .env                 # [ИЗМЕНИТЬ] Добавить IMGBB_API_KEY, WEBAPP_URL
```

---

## 📝 ФАЗА 1: ПОДГОТОВКА BACKEND (Google Sheets)

### 1.1 Обновление схемы Config_Users

**Было:**
| A (ФИО) | B (Username) |
|---------|--------------|

**Стало:**
| A (ФИО) | B (Username) | C (Telegram ID) | D (Role) | E (Status) |
|---------|--------------|-----------------|----------|------------|
| Иванов И.И. | @ivanov | 123456789 | employee | active |
| Петров П.П. | @petrov | 987654321 | supervisor | active |
| Админ | @admin | 111222333 | admin | active |

> **Роли (Role):** `employee`, `supervisor`, `admin`  
> **Статус (Status):** `active`, `deleted`

### 1.2 Новые методы в `sheets_manager.py`

```python
# ДОБАВИТЬ в класс GoogleSheetManager:

def get_user_by_telegram_id(self, telegram_id: int) -> dict | None:
    """Поиск пользователя по Telegram ID"""
    pass

def get_all_active_employees(self) -> list[dict]:
    """Список всех активных сотрудников (для dropdown супервизора)"""
    pass

def register_new_user(self, telegram_id: int, full_name: str) -> bool:
    """Регистрация нового пользователя с добавлением в текущий месяц"""
    pass

def add_user_to_current_month(self, full_name: str) -> bool:
    """Добавить строку в текущий месячный отчёт (с копированием формул)"""
    pass

def soft_delete_user(self, telegram_id: int) -> bool:
    """Мягкое удаление: пометить deleted, но оставить в текущем месяце"""
    pass

def admin_add_user(self, full_name: str, telegram_id: int = None, role: str = "employee") -> bool:
    """Добавление пользователя админом"""
    pass
```

### 1.3 Изменение append_log()

**Было (DB_Logs):**
| Дата | Время | ФИО | Тип | Tg_Username |

**Стало:**
| Дата | Время | ФИО | Тип | Photo_URL | Submitted_By | Tg_ID |

```python
def append_log(self, user_name: str, telegram_id: int, action: str, 
               photo_url: str = None, submitted_by: str = None):
    """
    action: "check_in" или "check_out"
    photo_url: Ссылка на загруженное фото
    submitted_by: Если супервизор отметил за сотрудника
    """
    pass
```

---

## 📝 ФАЗА 2: ПОДГОТОВКА BACKEND (Bot Handlers)

### 2.1 Новый файл `config.py`

```python
import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBAPP_URL = os.getenv("WEBAPP_URL")  # https://your-domain.com/webapp
IMGBB_API_KEY = os.getenv("IMGBB_API_KEY")

# Жёстко закодированные списки (или из .env)
ADMIN_IDS = [7042383572]  # Telegram User IDs админов
SUPERVISOR_IDS = []       # Telegram User IDs супервизоров (или из Google Sheets)

# Google Sheets
GOOGLE_JSON_PATH = os.getenv("GOOGLE_JSON_PATH")
DRIVE_FOLDER_ID = os.getenv("DRIVE_FOLDER_ID")
TEMPLATE_FILE_ID = os.getenv("TEMPLATE_FILE_ID")
```

### 2.2 Новый файл `validators.py`

```python
import hashlib
import hmac
from urllib.parse import parse_qsl

def validate_webapp_data(init_data: str, bot_token: str) -> bool:
    """
    Проверка подписи initData от Telegram WebApp.
    Предотвращает подделку запросов.
    """
    parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = parsed.pop("hash", "")
    
    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(parsed.items())
    )
    
    secret_key = hmac.new(
        b"WebAppData", bot_token.encode(), hashlib.sha256
    ).digest()
    
    calculated_hash = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()
    
    return calculated_hash == received_hash
```

### 2.3 Новый файл `image_uploader.py`

```python
import httpx
import base64

async def upload_to_imgbb(image_base64: str, api_key: str) -> str | None:
    """
    Загружает Base64 изображение на ImgBB.
    Возвращает URL или None при ошибке.
    """
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.imgbb.com/1/upload",
            data={
                "key": api_key,
                "image": image_base64,
                "expiration": 15552000  # 180 дней
            }
        )
        if response.status_code == 200:
            return response.json()["data"]["url"]
    return None
```

### 2.4 Изменения в `main.py`

#### Добавить импорт:
```python
from aiogram.types import WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.types import Message
import json

from config import WEBAPP_URL, ADMIN_IDS, SUPERVISOR_IDS, IMGBB_API_KEY
from validators import validate_webapp_data
from image_uploader import upload_to_imgbb
```

#### Новая команда для создания кнопки WebApp:
```python
@dp.message(Command("setup_checkin"))
async def setup_checkin_button(message: Message):
    """Создаёт сообщение с кнопкой WebApp (для закрепления в чате)"""
    if message.from_user.id not in ADMIN_IDS:
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="📸 Отметить Приход/Уход",
            web_app=WebAppInfo(url=WEBAPP_URL)
        )]
    ])
    
    msg = await message.answer(
        "🕐 **Учёт Рабочего Времени**\n\n"
        "Нажмите кнопку ниже, чтобы отметить приход или уход.\n"
        "⚠️ Требуется сделать фото на камеру.",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    
    # Опционально: закрепить сообщение
    try:
        await msg.pin(disable_notification=True)
    except:
        pass
```

#### Обработчик данных от WebApp:
```python
@dp.message(F.web_app_data)
async def handle_webapp_data(message: Message):
    """Обрабатывает данные от Telegram Web App"""
    try:
        data = json.loads(message.web_app_data.data)
        user_id = message.from_user.id
        
        action = data.get("action")  # "check_in", "check_out", "register", "admin_*"
        
        if action == "check_in" or action == "check_out":
            await process_check_action(message, data, user_id)
        elif action == "register":
            await process_registration(message, data, user_id)
        elif action.startswith("admin_"):
            await process_admin_action(message, data, user_id)
        else:
            await message.answer("❌ Неизвестное действие")
            
    except Exception as e:
        logger.error(f"WebApp data error: {e}")
        await message.answer("❌ Ошибка обработки данных")


async def process_check_action(message: Message, data: dict, user_id: int):
    """Обработка Check-in / Check-out"""
    image_base64 = data.get("image")
    target_user_id = data.get("target_user_id", user_id)  # Для супервизора
    action = data["action"]
    
    # 1. Загрузить фото на хостинг
    photo_url = await upload_to_imgbb(image_base64, IMGBB_API_KEY)
    if not photo_url:
        await message.answer("❌ Ошибка загрузки фото")
        return
    
    # 2. Получить данные сотрудника
    user_info = sheet_manager.get_user_by_telegram_id(target_user_id)
    if not user_info:
        await message.answer("❌ Пользователь не найден")
        return
    
    employee_name = user_info["name"]
    
    # 3. Определить, кто отправил (супервизор?)
    submitted_by = None
    if target_user_id != user_id:
        submitter = sheet_manager.get_user_by_telegram_id(user_id)
        submitted_by = submitter["name"] if submitter else f"ID:{user_id}"
    
    # 4. Записать в Google Sheets
    sheet_manager.append_log(
        user_name=employee_name,
        telegram_id=target_user_id,
        action=action,
        photo_url=photo_url,
        submitted_by=submitted_by
    )
    
    # 5. Отправить уведомление в группу
    action_text = "🟢 НАЧАЛ РАБОТУ" if action == "check_in" else "🔴 ЗАКОНЧИЛ РАБОТУ"
    time_str = sheet_manager._get_moscow_time().strftime('%H:%M')
    
    caption = f"👤 **{employee_name}**\n{action_text}\n🕒 {time_str}"
    if submitted_by:
        caption += f"\n✅ _Подтверждено: {submitted_by}_"
    
    await bot.send_photo(
        chat_id=message.chat.id,
        photo=photo_url,
        caption=caption,
        parse_mode="Markdown"
    )


async def process_registration(message: Message, data: dict, user_id: int):
    """Обработка самостоятельной регистрации"""
    full_name = data.get("full_name", "").strip()
    
    if not full_name or len(full_name) < 3:
        await message.answer("❌ Введите корректное ФИО (минимум 3 символа)")
        return
    
    # Проверить, не зарегистрирован ли уже
    existing = sheet_manager.get_user_by_telegram_id(user_id)
    if existing:
        await message.answer(f"ℹ️ Вы уже зарегистрированы как {existing['name']}")
        return
    
    # Зарегистрировать
    success = sheet_manager.register_new_user(user_id, full_name)
    if success:
        await message.answer(f"✅ Регистрация успешна!\nДобро пожаловать, {full_name}!")
    else:
        await message.answer("❌ Ошибка регистрации. Обратитесь к администратору.")


async def process_admin_action(message: Message, data: dict, user_id: int):
    """Обработка административных действий"""
    if user_id not in ADMIN_IDS:
        await message.answer("⛔ Доступ запрещён")
        return
    
    action = data["action"]
    
    if action == "admin_list_users":
        users = sheet_manager.get_all_active_employees()
        # Отправить JSON обратно через sendData не получится - 
        # данные нужно встраивать в URL при открытии WebApp
        pass
    
    elif action == "admin_add_user":
        name = data.get("name")
        tg_id = data.get("telegram_id")
        success = sheet_manager.admin_add_user(name, tg_id)
        await message.answer("✅ Пользователь добавлен" if success else "❌ Ошибка")
    
    elif action == "admin_delete_user":
        tg_id = data.get("telegram_id")
        success = sheet_manager.soft_delete_user(tg_id)
        await message.answer("✅ Пользователь удалён" if success else "❌ Ошибка")
```

---

## 📝 ФАЗА 3: FRONTEND (Telegram Web App)

### 3.1 Файл `webapp/index.html`

```html
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
    <title>Учёт Времени</title>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <link rel="stylesheet" href="style.css">
</head>
<body>
    <div id="app">
        <!-- Динамически заполняется в app.js -->
        <div id="loading">
            <div class="spinner"></div>
            <p>Загрузка...</p>
        </div>
    </div>
    
    <!-- Шаблоны -->
    <template id="template-registration">
        <div class="screen registration-screen">
            <h2>👋 Добро пожаловать!</h2>
            <p>Для начала работы введите ваше ФИО:</p>
            <input type="text" id="reg-name" placeholder="Иванов Иван Иванович" maxlength="100">
            <button id="btn-register" class="btn primary">Зарегистрироваться</button>
        </div>
    </template>
    
    <template id="template-employee">
        <div class="screen employee-screen">
            <h2 id="greeting">Здравствуйте!</h2>
            <div class="camera-container">
                <input type="file" id="camera-input" accept="image/*" capture="environment" hidden>
                <div id="preview-container">
                    <img id="photo-preview" alt="Фото">
                    <button id="btn-retake" class="btn secondary">📷 Переснять</button>
                </div>
                <button id="btn-take-photo" class="btn secondary large">📷 Сделать Фото</button>
            </div>
            <div class="action-buttons">
                <button id="btn-check-in" class="btn success" disabled>🟢 НАЧАЛ РАБОТУ</button>
                <button id="btn-check-out" class="btn danger" disabled>🔴 ЗАКОНЧИЛ РАБОТУ</button>
            </div>
        </div>
    </template>
    
    <template id="template-supervisor">
        <div class="screen supervisor-screen">
            <h2>👷 Режим Бригадира</h2>
            <label>Выберите сотрудника:</label>
            <select id="employee-select">
                <option value="">-- Выберите --</option>
            </select>
            <div class="camera-container">
                <input type="file" id="camera-input-super" accept="image/*" capture="environment" hidden>
                <div id="preview-container-super">
                    <img id="photo-preview-super" alt="Фото">
                    <button id="btn-retake-super" class="btn secondary">📷 Переснять</button>
                </div>
                <button id="btn-take-photo-super" class="btn secondary large">📷 Сделать Фото</button>
            </div>
            <div class="action-buttons">
                <button id="btn-super-in" class="btn success" disabled>🟢 Приход</button>
                <button id="btn-super-out" class="btn danger" disabled>🔴 Уход</button>
            </div>
        </div>
    </template>
    
    <template id="template-admin">
        <div class="screen admin-screen">
            <div class="tabs">
                <button class="tab active" data-tab="users">👥 Пользователи</button>
                <button class="tab" data-tab="add">➕ Добавить</button>
            </div>
            <div id="tab-users" class="tab-content active">
                <div id="users-list"></div>
            </div>
            <div id="tab-add" class="tab-content">
                <input type="text" id="new-user-name" placeholder="ФИО">
                <input type="number" id="new-user-id" placeholder="Telegram ID (опционально)">
                <button id="btn-add-user" class="btn primary">Добавить</button>
            </div>
        </div>
    </template>
    
    <script src="app.js"></script>
</body>
</html>
```

### 3.2 Файл `webapp/style.css`

```css
:root {
    --tg-theme-bg-color: var(--tg-theme-bg-color, #ffffff);
    --tg-theme-text-color: var(--tg-theme-text-color, #000000);
    --tg-theme-button-color: var(--tg-theme-button-color, #3390ec);
    --tg-theme-button-text-color: var(--tg-theme-button-text-color, #ffffff);
    
    --success: #28a745;
    --danger: #dc3545;
    --secondary: #6c757d;
}

* {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
}

body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: var(--tg-theme-bg-color);
    color: var(--tg-theme-text-color);
    min-height: 100vh;
    padding: 16px;
}

#app {
    max-width: 400px;
    margin: 0 auto;
}

#loading {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 50vh;
}

.spinner {
    width: 40px;
    height: 40px;
    border: 4px solid #f3f3f3;
    border-top: 4px solid var(--tg-theme-button-color);
    border-radius: 50%;
    animation: spin 1s linear infinite;
}

@keyframes spin {
    to { transform: rotate(360deg); }
}

.screen {
    animation: fadeIn 0.3s ease;
}

@keyframes fadeIn {
    from { opacity: 0; transform: translateY(10px); }
    to { opacity: 1; transform: translateY(0); }
}

h2 {
    text-align: center;
    margin-bottom: 20px;
}

.btn {
    width: 100%;
    padding: 14px 20px;
    border: none;
    border-radius: 12px;
    font-size: 16px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s;
    margin-bottom: 10px;
}

.btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
}

.btn:active:not(:disabled) {
    transform: scale(0.98);
}

.btn.primary {
    background: var(--tg-theme-button-color);
    color: var(--tg-theme-button-text-color);
}

.btn.success {
    background: var(--success);
    color: white;
}

.btn.danger {
    background: var(--danger);
    color: white;
}

.btn.secondary {
    background: var(--secondary);
    color: white;
}

.btn.large {
    padding: 20px;
    font-size: 18px;
}

input, select {
    width: 100%;
    padding: 14px;
    border: 2px solid #ddd;
    border-radius: 10px;
    font-size: 16px;
    margin-bottom: 16px;
    background: var(--tg-theme-bg-color);
    color: var(--tg-theme-text-color);
}

input:focus, select:focus {
    border-color: var(--tg-theme-button-color);
    outline: none;
}

.camera-container {
    margin: 20px 0;
    text-align: center;
}

#photo-preview, #photo-preview-super {
    max-width: 100%;
    max-height: 300px;
    border-radius: 12px;
    display: none;
    margin-bottom: 10px;
}

#preview-container, #preview-container-super {
    display: none;
}

.action-buttons {
    display: flex;
    gap: 10px;
    margin-top: 20px;
}

.action-buttons .btn {
    flex: 1;
}

/* Tabs */
.tabs {
    display: flex;
    gap: 10px;
    margin-bottom: 20px;
}

.tab {
    flex: 1;
    padding: 10px;
    border: none;
    background: #eee;
    border-radius: 8px;
    cursor: pointer;
}

.tab.active {
    background: var(--tg-theme-button-color);
    color: white;
}

.tab-content {
    display: none;
}

.tab-content.active {
    display: block;
}

/* User list */
.user-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px;
    border-bottom: 1px solid #eee;
}

.user-item button {
    width: auto;
    padding: 8px 16px;
    margin: 0;
}
```

### 3.3 Файл `webapp/app.js`

```javascript
// Telegram WebApp API
const tg = window.Telegram.WebApp;
tg.expand();
tg.ready();

// Конфигурация (будет загружаться с сервера или из URL params)
const CONFIG = {
    ADMIN_IDS: [7042383572],      // Заменить на ваши ID
    SUPERVISOR_IDS: [],           // Загружаются динамически
    employees: []                 // Загружаются для супервизора
};

// Состояние приложения
const state = {
    user: tg.initDataUnsafe?.user || null,
    role: null,         // "employee", "supervisor", "admin", "new"
    photoBase64: null,
    selectedEmployeeId: null
};

// ===== ИНИЦИАЛИЗАЦИЯ =====
async function init() {
    if (!state.user) {
        showError("Не удалось получить данные пользователя");
        return;
    }
    
    // Парсим параметры из URL (для передачи данных)
    parseUrlParams();
    
    // Определяем роль пользователя
    state.role = detectRole(state.user.id);
    
    // Отображаем соответствующий интерфейс
    showScreen(state.role);
}

function parseUrlParams() {
    const params = new URLSearchParams(window.location.search);
    
    // Список сотрудников для супервизора (закодирован в URL)
    const employeesData = params.get("employees");
    if (employeesData) {
        try {
            CONFIG.employees = JSON.parse(atob(employeesData));
        } catch (e) {
            console.error("Failed to parse employees", e);
        }
    }
    
    // Список супервизоров
    const supervisorsData = params.get("supervisors");
    if (supervisorsData) {
        try {
            CONFIG.SUPERVISOR_IDS = JSON.parse(atob(supervisorsData));
        } catch (e) {}
    }
}

function detectRole(userId) {
    if (CONFIG.ADMIN_IDS.includes(userId)) return "admin";
    if (CONFIG.SUPERVISOR_IDS.includes(userId)) return "supervisor";
    
    // Проверяем, есть ли пользователь в списке сотрудников
    const employee = CONFIG.employees.find(e => e.id === userId);
    if (employee) {
        state.employeeName = employee.name;
        return "employee";
    }
    
    return "new"; // Новый пользователь - показать регистрацию
}

function showScreen(role) {
    const app = document.getElementById("app");
    const templateId = `template-${role === "new" ? "registration" : role}`;
    const template = document.getElementById(templateId);
    
    if (!template) {
        showError(`Шаблон ${templateId} не найден`);
        return;
    }
    
    app.innerHTML = "";
    app.appendChild(template.content.cloneNode(true));
    
    // Инициализируем обработчики в зависимости от роли
    switch(role) {
        case "new":
            initRegistration();
            break;
        case "employee":
            initEmployee();
            break;
        case "supervisor":
            initSupervisor();
            break;
        case "admin":
            initAdmin();
            break;
    }
}

function showError(message) {
    document.getElementById("app").innerHTML = `
        <div style="text-align:center; padding: 40px;">
            <h2>❌</h2>
            <p>${message}</p>
        </div>
    `;
}

// ===== РЕГИСТРАЦИЯ =====
function initRegistration() {
    const btnRegister = document.getElementById("btn-register");
    const inputName = document.getElementById("reg-name");
    
    btnRegister.addEventListener("click", () => {
        const name = inputName.value.trim();
        if (name.length < 3) {
            tg.showAlert("Введите корректное ФИО (минимум 3 символа)");
            return;
        }
        
        sendData({
            action: "register",
            full_name: name
        });
    });
}

// ===== СОТРУДНИК =====
function initEmployee() {
    const greeting = document.getElementById("greeting");
    greeting.textContent = `Здравствуйте, ${state.employeeName || state.user.first_name}!`;
    
    initCamera("camera-input", "photo-preview", "preview-container", "btn-take-photo", "btn-retake");
    
    const btnIn = document.getElementById("btn-check-in");
    const btnOut = document.getElementById("btn-check-out");
    
    btnIn.addEventListener("click", () => submitCheck("check_in"));
    btnOut.addEventListener("click", () => submitCheck("check_out"));
}

function submitCheck(action, targetUserId = null) {
    if (!state.photoBase64) {
        tg.showAlert("Сначала сделайте фото!");
        return;
    }
    
    const data = {
        action: action,
        image: state.photoBase64
    };
    
    if (targetUserId) {
        data.target_user_id = targetUserId;
    }
    
    sendData(data);
}

// ===== СУПЕРВИЗОР =====
function initSupervisor() {
    const select = document.getElementById("employee-select");
    
    // Заполняем dropdown
    CONFIG.employees.forEach(emp => {
        const option = document.createElement("option");
        option.value = emp.id;
        option.textContent = emp.name;
        select.appendChild(option);
    });
    
    select.addEventListener("change", () => {
        state.selectedEmployeeId = parseInt(select.value) || null;
        updateSupervisorButtons();
    });
    
    initCamera("camera-input-super", "photo-preview-super", "preview-container-super", 
               "btn-take-photo-super", "btn-retake-super");
    
    const btnIn = document.getElementById("btn-super-in");
    const btnOut = document.getElementById("btn-super-out");
    
    btnIn.addEventListener("click", () => {
        if (state.selectedEmployeeId) {
            submitCheck("check_in", state.selectedEmployeeId);
        }
    });
    
    btnOut.addEventListener("click", () => {
        if (state.selectedEmployeeId) {
            submitCheck("check_out", state.selectedEmployeeId);
        }
    });
}

function updateSupervisorButtons() {
    const hasPhoto = !!state.photoBase64;
    const hasEmployee = !!state.selectedEmployeeId;
    
    document.getElementById("btn-super-in").disabled = !(hasPhoto && hasEmployee);
    document.getElementById("btn-super-out").disabled = !(hasPhoto && hasEmployee);
}

// ===== АДМИН =====
function initAdmin() {
    // Tabs
    document.querySelectorAll(".tab").forEach(tab => {
        tab.addEventListener("click", () => {
            document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
            document.querySelectorAll(".tab-content").forEach(c => c.classList.remove("active"));
            
            tab.classList.add("active");
            document.getElementById(`tab-${tab.dataset.tab}`).classList.add("active");
        });
    });
    
    // Render users list
    renderUsersList();
    
    // Add user
    document.getElementById("btn-add-user").addEventListener("click", () => {
        const name = document.getElementById("new-user-name").value.trim();
        const tgId = document.getElementById("new-user-id").value.trim();
        
        if (!name) {
            tg.showAlert("Введите ФИО");
            return;
        }
        
        sendData({
            action: "admin_add_user",
            name: name,
            telegram_id: tgId ? parseInt(tgId) : null
        });
    });
}

function renderUsersList() {
    const container = document.getElementById("users-list");
    container.innerHTML = "";
    
    CONFIG.employees.forEach(emp => {
        const div = document.createElement("div");
        div.className = "user-item";
        div.innerHTML = `
            <span>${emp.name} (ID: ${emp.id || "N/A"})</span>
            <button class="btn danger" onclick="deleteUser(${emp.id})">🗑️</button>
        `;
        container.appendChild(div);
    });
}

function deleteUser(userId) {
    tg.showConfirm("Удалить пользователя?", (confirmed) => {
        if (confirmed) {
            sendData({
                action: "admin_delete_user",
                telegram_id: userId
            });
        }
    });
}

// ===== КАМЕРА =====
function initCamera(inputId, previewId, containerId, btnTakeId, btnRetakeId) {
    const input = document.getElementById(inputId);
    const preview = document.getElementById(previewId);
    const container = document.getElementById(containerId);
    const btnTake = document.getElementById(btnTakeId);
    const btnRetake = document.getElementById(btnRetakeId);
    
    btnTake.addEventListener("click", () => input.click());
    btnRetake.addEventListener("click", () => input.click());
    
    input.addEventListener("change", (e) => {
        const file = e.target.files[0];
        if (!file) return;
        
        const reader = new FileReader();
        reader.onload = (event) => {
            preview.src = event.target.result;
            preview.style.display = "block";
            container.style.display = "block";
            btnTake.style.display = "none";
            
            // Сохраняем base64 (без data:image/...;base64, prefix)
            state.photoBase64 = event.target.result.split(",")[1];
            
            // Активируем кнопки
            updateActionButtons();
        };
        reader.readAsDataURL(file);
    });
}

function updateActionButtons() {
    const hasPhoto = !!state.photoBase64;
    
    // Employee buttons
    const btnIn = document.getElementById("btn-check-in");
    const btnOut = document.getElementById("btn-check-out");
    if (btnIn) btnIn.disabled = !hasPhoto;
    if (btnOut) btnOut.disabled = !hasPhoto;
    
    // Supervisor buttons (also need selected employee)
    updateSupervisorButtons && updateSupervisorButtons();
}

// ===== ОТПРАВКА ДАННЫХ =====
function sendData(data) {
    tg.MainButton.showProgress();
    
    try {
        tg.sendData(JSON.stringify(data));
    } catch (e) {
        tg.showAlert("Ошибка отправки: " + e.message);
    }
    
    tg.MainButton.hideProgress();
    tg.close();
}

// ===== СТАРТ =====
init();
```

---

## 📝 ФАЗА 4: СИНХРОНИЗАЦИЯ GOOGLE SHEETS

### 4.1 Логика добавления пользователя

```
Admin нажимает "Добавить пользователя"
    │
    ▼
1. Добавить в Config_Users (шаблон):
   [ФИО, Username, Telegram_ID, Role, Status]
    │
    ▼
2. Проверить: существует ли месячный файл?
   ├─ ДА: Найти файл текущего месяца
   │       └─ Добавить строку в "Отчет_Месяц"
   │          └─ Скопировать формулы из предыдущей строки
   │
   └─ НЕТ: Ничего не делать (при создании файла
           все пользователи подтянутся из Config_Users)
```

### 4.2 Логика удаления пользователя (Soft Delete)

```
Admin нажимает "Удалить пользователя"
    │
    ▼
1. В Config_Users:
   └─ Поменять Status на "deleted"
      (НЕ удалять строку!)
    │
    ▼
2. В текущем месячном файле:
   └─ НЕ ТРОГАТЬ!
      Строка сотрудника остаётся для финального отчёта.
    │
    ▼
3. В следующем месяце:
   └─ При создании нового файла пользователь
      НЕ попадёт туда (т.к. Status = "deleted")
```

### 4.3 Новые методы в sheets_manager.py (полная реализация)

```python
def add_user_to_current_month(self, full_name: str) -> bool:
    """
    Добавляет нового сотрудника в текущий месячный отчёт.
    Копирует формулы из последней заполненной строки.
    """
    now = self._get_moscow_time()
    target_name = self._get_sheet_name(now)
    
    try:
        # 1. Найти файл текущего месяца
        query = f"name = '{target_name}' and '{self.drive_folder_id}' in parents and trashed = false"
        results = self.drive_service.files().list(q=query, fields="files(id)").execute()
        items = results.get('files', [])
        
        if not items:
            logger.info(f"Monthly file {target_name} not found, skip adding row")
            return True  # Не ошибка - файла ещё нет
        
        file_id = items[0]['id']
        sheet = self.gc.open_by_key(file_id)
        wks = sheet.worksheet("Отчет_Месяц")
        
        # 2. Найти последнюю строку с данными
        all_values = wks.col_values(1)  # Колонка A (ФИО)
        last_row = len(all_values)
        
        if last_row < 3:
            logger.warning("Report sheet has no employee rows to copy from")
            return False
        
        # 3. Добавить новую строку
        new_row = last_row + 1
        
        # 4. Скопировать формулы из предыдущей строки
        source_range = f"A{last_row}:DM{last_row}"  # До столбца DM (31 день * 3 + 2)
        dest_range = f"A{new_row}:DM{new_row}"
        
        wks.copy_range(source_range, dest_range)
        
        # 5. Заменить ФИО на нового сотрудника
        wks.update_acell(f"A{new_row}", full_name)
        
        logger.info(f"Added {full_name} to {target_name} at row {new_row}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to add user to monthly sheet: {e}")
        return False


def soft_delete_user(self, telegram_id: int) -> bool:
    """
    Мягкое удаление: ставит Status = 'deleted' в Config_Users.
    Не трогает текущий месячный отчёт.
    """
    try:
        sheet = self.gc.open_by_key(self.template_file_id)
        wks = sheet.worksheet("Config_Users")
        
        # Найти строку по Telegram ID (колонка C)
        cell = wks.find(str(telegram_id), in_column=3)
        if not cell:
            logger.warning(f"User with ID {telegram_id} not found")
            return False
        
        # Обновить Status (колонка E)
        wks.update_cell(cell.row, 5, "deleted")
        
        logger.info(f"Soft deleted user {telegram_id}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to soft delete user: {e}")
        return False
```

---

## 📝 ФАЗА 5: РАЗВЁРТЫВАНИЕ

### 5.1 Получение API ключа ImgBB
1. Зайти на https://api.imgbb.com/
2. Зарегистрироваться
3. Получить API Key
4. Добавить в `.env`:
   ```
   IMGBB_API_KEY=ваш_ключ
   ```

### 5.2 Хостинг Web App

**Вариант A: GitHub Pages (бесплатно)**
1. Создать репозиторий (например, `time-tracker-webapp`)
2. Загрузить папку `webapp/` в корень репозитория
3. В Settings → Pages включить GitHub Pages
4. URL будет: `https://deriio.github.io/time-tracker-webapp/`

**Вариант B: Vercel (бесплатно)**
1. Подключить репозиторий к Vercel
2. Деплой автоматический
3. URL будет: `https://time-tracker-webapp.vercel.app/`

### 5.3 Обновление .env
```ini
BOT_TOKEN=ваш_токен_бота
GOOGLE_JSON_PATH=credentials.json
DRIVE_FOLDER_ID=id_папки
TEMPLATE_FILE_ID=id_шаблона
ADMIN_IDS=7042383572
IMGBB_API_KEY=ваш_ключ_imgbb
WEBAPP_URL=https://deriio.github.io/time-tracker-webapp/
```

### 5.4 Обновление requirements.txt
```
aiogram>=3.0.0
gspread>=5.0.0
google-api-python-client>=2.0.0
google-auth>=2.0.0
google-auth-oauthlib>=1.0.0
python-dotenv>=1.0.0
pytz
httpx>=0.24.0
```

---

## ✅ ЧЕКЛИСТ ВЫПОЛНЕНИЯ

### Фаза 1: Backend (Google Sheets)
- [ ] Обновить Config_Users (добавить колонки C, D, E)
- [ ] Добавить `get_user_by_telegram_id()`
- [ ] Добавить `get_all_active_employees()`
- [ ] Добавить `register_new_user()`
- [ ] Добавить `add_user_to_current_month()`
- [ ] Добавить `soft_delete_user()`
- [ ] Обновить `append_log()` (photo_url, submitted_by)

### Фаза 2: Backend (Bot)
- [ ] Создать `config.py`
- [ ] Создать `validators.py`
- [ ] Создать `image_uploader.py`
- [ ] Добавить команду `/setup_checkin`
- [ ] Добавить обработчик `F.web_app_data`
- [ ] Реализовать `process_check_action()`
- [ ] Реализовать `process_registration()`
- [ ] Реализовать `process_admin_action()`

### Фаза 3: Frontend (Web App)
- [ ] Создать `webapp/index.html`
- [ ] Создать `webapp/style.css`
- [ ] Создать `webapp/app.js`
- [ ] Протестировать на мобильном устройстве

### Фаза 4: Deployment
- [ ] Получить ImgBB API Key
- [ ] Задеплоить Web App на GitHub Pages/Vercel
- [ ] Обновить `.env`
- [ ] Обновить `requirements.txt`
- [ ] Запустить и протестировать полный цикл

---

## 🔒 БЕЗОПАСНОСТЬ

1. **Валидация initData**: Всегда проверять подпись от Telegram (см. `validators.py`)
2. **HTTPS**: WebApp обязательно должен быть на HTTPS
3. **Не хранить токены в коде**: Использовать `.env` и `.gitignore`
4. **Rate Limiting**: Добавить защиту от спама (опционально)

---

## 📞 ВОПРОСЫ ДЛЯ УТОЧНЕНИЯ

Перед началом разработки уточните:

1. Где хостить Web App? (GitHub Pages / Vercel / свой сервер)
2. Нужен ли ImgBB или можно использовать другой хостинг изображений?
3. Какие именно Telegram ID должны быть супервизорами?
4. Нужна ли возможность временной блокировки пользователя (кроме удаления)?
5. Нужен ли функционал "отмены" последней отметки?

---

*План создан: 20.01.2026*  
*Версия: 1.0*
