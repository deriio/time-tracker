# 📁 Структура проекта Time Tracker Bot

> Дата последнего обновления: 21.01.2026

## 🎯 Назначение проекта

Telegram бот для учета рабочего времени сотрудников с интеграцией Google Sheets и WebApp интерфейсом.

---

## 📂 Файловая структура

### **Backend (Python - Telegram Bot)**

#### Главные файлы:
- **`main.py`** - Главный файл бота, обрабатывает все Telegram события
  - Middleware авторизации
  - Обработчики команд (/start, /update, /setup_checkin)
  - Обработка WebApp данных
  - Логирование действий

- **`sheets_manager.py`** - Управление Google Sheets
  - Создание и обновление таблиц
  - Логирование приходов/уходов
  - Управление пользователями
  - Синхронизация данных

- **`webhook_server.py`** - FastAPI сервер для WebApp
  - `/api/upload` - загрузка фото на сервер
  - `/api/checkin` - обработка check-in/check-out
  - `/api/claim` - привязка аккаунта к сотруднику
  - `/api/photos/{filename}` - удаление фото после отправки

#### Вспомогательные файлы:
- **`validators.py`** - Валидация данных от WebApp
- **`make_token.py`** - Генерация OAuth токена для Google API
- **`image_uploader.py`** - Утилита загрузки изображений

---

### **Frontend (WebApp для Telegram)**

> 🌐 **Деплой:** GitHub Pages из ветки `main` (корневая папка)  
> 🔗 **URL:** https://deriio.github.io/time-tracker/

#### Основные файлы:
- **`index.html`** - Главная страница WebApp
  - Шаблоны для 3 ролей: employee, supervisor, orphan
  - Интеграция с Telegram WebApp API
  - Динамическая загрузка app.js с версионированием для обхода кеша

- **`app.js`** - Главная логика WebApp приложения
  - Определение роли пользователя (employee/supervisor/orphan)
  - Работа с камерой
  - Отправка данных в webhook сервер
  - Обработка claim flow для незарегистрированных пользователей

#### Стили:
- **`theme.css`** - Основная тема интерфейса (используется в index.html)
- **`style.css`** - Дополнительные стили (legacy, для совместимости)

#### Вспомогательные:
- **`structure.js`** - Google Apps Script для создания структуры таблиц (НЕ для WebApp!)

---

### **Конфигурация**

- **`.env`** - Переменные окружения (НЕ в git!)
  ```
  BOT_TOKEN=...
  GOOGLE_JSON_PATH=...
  DRIVE_FOLDER_ID=...
  TEMPLATE_FILE_ID=...
  ADMIN_IDS=...
  WEBAPP_URL=https://deriio.github.io/time-tracker/
  WEBHOOK_SERVER_URL=...
  ```

- **`.env.example`** - Пример конфигурации

- **`requirements.txt`** - Python зависимости
  ```
  aiogram
  python-dotenv
  google-api-python-client
  google-auth-httplib2
  google-auth-oauthlib
  ```

---

### **Документация**

- **`README.md`** / **`README_RU.md`** - Основная документация
- **`DEPLOYMENT_GUIDE_RU.md`** - Инструкция по деплою
- **`OAUTH_SETUP_GUIDE.md`** - Настройка OAuth для Google
- **`USER_INSTRUCTIONS.md`** - Инструкции для пользователей
- **`IMPLEMENTATION_PLAN.md`** - План реализации функционала
- **`PROJECT_STRUCTURE.md`** - Этот файл

---

### **Данные**

#### Google API Credentials (НЕ в git!):
- `credentials.json` / `oauth_credentials.json` - OAuth Client Secret
- `token.json` - Сгенерированный access token
- `timetrackingbot-*.json` - Service Account credentials
- `serious-cabinet-*.json` - Дополнительные credentials

#### Локальные данные:
- `users.json` - Кеш пользователей (legacy)
- `example.xlsx` - Пример Excel таблицы

---

### **Служебные папки**

- **`photos/`** - Временное хранилище фото (очищается автоматически)
- **`__pycache__/`** - Python кеш (игнорируется git)
- **`.git/`** - Git репозиторий

---

## 🔄 Workflow работы системы

### 1. **Инициализация бота**
```
main.py → GoogleSheetManager → Загрузка пользователей
```

### 2. **Создание терминала учета**
```
/setup_checkin → Генерация URL с параметрами → WebApp открывается
```

### 3. **Check-in/Check-out через WebApp**
```
app.js → Камера → Фото Base64 → webhook_server.py →
 ┌─→ Логирование в Google Sheets
 └─→ Отправка фото в группу Telegram
```

### 4. **Привязка аккаунта (Claim)**
```
Orphan user → Выбор ФИО → webhook_server → sheets_manager.bind_telegram_id()
```

---

## 🚀 Деплой и запуск

### Backend:
```bash
# Установка зависимостей
pip install -r requirements.txt

# Настройка OAuth
python make_token.py

# Запуск бота
python main.py

# Запуск webhook сервера (в отдельном терминале)
python webhook_server.py
```

### Frontend:
```bash
# Деплой на GitHub Pages происходит автоматически из ветки main
git push origin main
```

---

## 🔐 Безопасность

### ⚠️ **НЕ коммитить в git:**
- `.env`
- `*.json` (credentials, tokens)
- `bot.log`
- `photos/*`
- `cloudflared.exe`

### ✅ **Защита данных:**
- Все credentials в `.gitignore`
- OAuth 2.0 для Google API
- Middleware авторизации в боте
- Валидация данных от WebApp

---

## 📊 Роли пользователей

1. **Employee** - Обычный сотрудник
   - Отмечает свой приход/уход
   - Видит только свою камеру

2. **Supervisor** - Руководитель
   - Может отмечать приход/уход за других
   - Выбирает сотрудника из списка

3. **Orphan** - Незарегистрированный пользователь
   - Видит форму привязки аккаунта
   - Выбирает свое ФИО из списка неактивированных

---

## 🛠️ Технологии

### Backend:
- Python 3.10+
- aiogram (Telegram Bot API)
- FastAPI (Webhook Server)
- Google Sheets API
- Google Drive API

### Frontend:
- Vanilla JavaScript
- Telegram WebApp API
- HTML5 Camera API
- CSS3

### DevOps:
- GitHub Pages (static hosting)
- Cloudflare Tunnel (webhook server)
- Git (version control)

---

## 📝 История версий

### v8.0 (21.01.2026)
- ✅ Удалены дублирующиеся папки `webapp/` и `appv2/`
- ✅ Обновлен `.gitignore`
- ✅ Создана документация структуры проекта

### v7.x
- Переход на webhook сервер для загрузки фото
- ImgBB заменен на локальное хранилище

### v6.x
- Реализация WebApp интерфейса
- Добавлена роль Supervisor

---

## 🐛 Known Issues

1. `cloudflared.exe` и `bot.log` не удаляются (используются процессом)
2. Credentials файлы в истории git (требуется очистка истории)

---

## 📞 Контакты

- **GitHub:** https://github.com/deriio/time-tracker
- **WebApp:** https://deriio.github.io/time-tracker/
