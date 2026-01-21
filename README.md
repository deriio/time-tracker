# Time Tracker Bot 🕐

Telegram бот для автоматизированного учета рабочего времени сотрудников с интеграцией Google Sheets и WebApp интерфейсом.

---

## 🚀 Быстрый старт

### Для пользователей:
1. Откройте группу в Telegram
2. Найдите закрепленное сообщение с кнопкой **"📸 Открыть терминал учета"**
3. Нажмите кнопку и следуйте инструкциям

### Для администраторов:
```bash
# 1. Установите зависимости
pip install -r requirements.txt

# 2. Настройте .env (скопируйте из .env.example)
cp .env.example .env
# Заполните BOT_TOKEN, GOOGLE_JSON_PATH и другие

# 3. Запустите OAuth авторизацию
python make_token.py

# 4. Запустите бот
python main.py

# 5. В отдельном терминале запустите webhook сервер
python webhook_server.py

# 6. В группе Telegram отправьте команду /setup_checkin
```

---

## 📁 Структура проекта

```
time-tracker/
├── 🐍 Backend (Python)
│   ├── main.py              - Telegram бот
│   ├── sheets_manager.py    - Google Sheets API
│   ├── webhook_server.py    - FastAPI сервер
│   └── validators.py        - Валидация данных
│
├── 🌐 Frontend (WebApp)
│   ├── index.html          - HTML интерфейс
│   ├── app.js              - Логика приложения
│   └── theme.css           - Стили
│
├── 📚 Документация
│   ├── PROJECT_STRUCTURE.md - Подробное описание
│   └── TODO.md             - Задачи и рекомендации
│
└── ⚙️ Конфигурация
    ├── .env               - Переменные окружения
    └── requirements.txt   - Python зависимости
```

**Подробная структура:** См. [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md)

---

## ✨ Возможности

### Для сотрудников:
- 📸 Отметка прихода/ухода через фото
- 🎯 Автоматическое определение роли
- 📱 Работа через Telegram WebApp
- ⚡ Мгновенная обратная связь

### Для руководителей:
- 👥 Отметка за других сотрудников
- 📊 Выбор сотрудника из выпадающего списка
- ✅ Подтверждение действий

### Для системы:
- 📋 Автоматическое логирование в Google Sheets
- 🔐 OAuth 2.0 авторизация
- 🌐 Деплой на GitHub Pages
- 🔄 Обход кеша через версионирование

---

## 🛠️ Технологии

| Компонент | Технология |
|-----------|-----------|
| **Backend** | Python 3.10+, aiogram, FastAPI |
| **Frontend** | Vanilla JS, HTML5, CSS3 |
| **Database** | Google Sheets API |
| **Hosting** | GitHub Pages (WebApp) |
| **Auth** | OAuth 2.0, Telegram WebApp Auth |

---

## 📊 Workflow

```
1. Пользователь открывает WebApp
   ↓
2. Определение роли (Employee/Supervisor/Orphan)
   ↓
3. Камера → Захват фото → Base64
   ↓
4. Отправка на webhook_server.py
   ↓
5. Логирование в Google Sheets
   ↓
6. Отправка фото в группу Telegram
   ↓
7. Закрытие WebApp с успешным сообщением
```

---

## 🔑 Роли пользователей

### 👤 **Employee** (Сотрудник)
- Может отмечать только себя
- Видит интерфейс с одной камерой
- Две кнопки: "НАЧАЛ РАБОТУ" и "ЗАКОНЧИЛ РАБОТУ"

### 👷 **Supervisor** (Бригадир)
- Может отмечать любого сотрудника
- Выпадающий список сотрудников
- Камера для подтверждения

### 🔍 **Orphan** (Незарегистрированный)
- Видит форму привязки аккаунта
- Выбирает свое ФИО из списка
- После привязки получает доступ

---

## 📝 Переменные окружения (.env)

```ini
# Telegram Bot
BOT_TOKEN=your_bot_token_here
ADMIN_IDS=123456789,987654321

# Google API
GOOGLE_JSON_PATH=path/to/credentials.json
DRIVE_FOLDER_ID=your_folder_id
TEMPLATE_FILE_ID=your_template_id

# WebApp
WEBAPP_URL=https://yourusername.github.io/time-tracker/
WEBHOOK_SERVER_URL=https://your-tunnel-url.com
```

---

## 🔐 Безопасность

### ⚠️ КРИТИЧНО:
Никогда не коммитьте в git:
- `.env` файл
- `*.json` credentials
- `token.json`
- `bot.log`

Все эти файлы уже в `.gitignore`, но проверьте историю git!

### ✅ Рекомендации:
1. Используйте разные токены для dev/prod
2. Регулярно обновляйте OAuth токены
3. Ограничивайте ADMIN_IDS только доверенными лицами
4. Используйте HTTPS для webhook сервера

---

## 📋 Команды администратора

| Команда | Описание |
|---------|----------|
| `/setup_checkin` | Создать терминал учета в группе |
| `/update` | Обновить список пользователей из Google Sheets |
| `/debug_users` | Показать всех пользователей в логе |

---

## 🐛 Известные проблемы

1. **Кеширование Telegram WebApp**: Решено через динамическую загрузку с параметром `?v=`
2. **Группы используют URL кнопки вместо WebApp**: Нормальное поведение Telegram API

---

## 📞 Поддержка

- **GitHub Issues**: https://github.com/deriio/time-tracker/issues
- **Документация**: См. [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md)
- **TODO List**: См. [TODO.md](TODO.md)

---

## 📜 Лицензия

MIT License - свободно используйте в своих проектах

---

## 🎯 Следующие шаги

После установки:

1. ✅ Протестируйте функционал
2. 📖 Прочитайте [TODO.md](TODO.md) для рекомендаций
3. 🔐 Удалите credentials из истории git (см. TODO.md)
4. 🚀 Наслаждайтесь автоматизацией!

---

**Версия:** 8.1  
**Дата:** 21.01.2026  
**Статус:** ✅ Production Ready
