# 🛠 Справочник Команд (COMMANDS.md)

Этот файл содержит все необходимые команды для управления ботом на сервере (VPS) и локально.

## 🖥️ 1. Подключение к серверу

```bash
ssh botuser@194.34.239.106
# Пароль: (ваш пароль)
```

---

## 📂 2. Структура Папок на Сервере

Важно понимать разницу между папками, чтобы изменения во фронтенде (HTML/JS) применялись корректно.

*   **`/home/botuser/time-tracker/`**
    *   **Что это:** Корневая папка проекта. Сюда скачиваются обновления из GitHub (`git pull`).
    *   **Что здесь лежит:** Python-код бота (`main.py`, `webhook_server.py`), `.env`, `requirements.txt`.
    *   **Важно:** Изменения HTML/JS файлов здесь **НЕ ВИДНЫ** в интернете сразу. Их нужно копировать в папку `www`.

*   **`/home/botuser/time-tracker/www/`**
    *   **Что это:** Папка для "публичных" файлов сайта (Frontend). Именно сюда смотрит Nginx и Интернет.
    *   **Что здесь лежит:** `index.html`, `app.js`, `logic.js`, `style.css`, `theme.css`.
    *   **Важно:** Если вы правите код интерфейса, он должен оказаться ЗДЕСЬ.

---

## 🚀 3. Обновление Бота (Деплой)

Полный цикл обновления кода на сервере.

### Шаг 1: Скачать обновления из GitHub
```bash
cd /home/botuser/time-tracker
git pull
```

### Шаг 2: Обновить Python-зависимости (если менялись)
```bash
source venv/bin/activate
pip install -r requirements.txt
deactivate
```

### Шаг 3: Обновить Фронтенд (ОБЯЗАТЕЛЬНО для HTML/JS)
Копируем свежие файлы из корня в папку `www`, чтобы Nginx их увидел.
```bash
# Копируем все файлы интерфейса в папку www
cp index.html app.js logic.js structure.js theme.css style.css www/ 2>/dev/null

# Выдаем правильные права (чтобы Nginx мог читать)
chmod -R 755 www
```

### Шаг 4: Перезапуск Сервисов
```bash
# Перезапуск бота и веб-сервера
sudo systemctl restart timetracker-bot timetracker-webhook

# Если меняли только фронтенд (HTML/JS), достаточно перезагрузить Nginx
sudo systemctl reload nginx
```

---

## ⚙️ 4. Управление Процессами (Systemd)

Команды для управления фоновыми процессами.

### Статус (Работает или нет?)
```bash
# Бот (Telegram логика)
sudo systemctl status timetracker-bot

# Вебхук (Сервер для фото и MiniApp)
sudo systemctl status timetracker-webhook

# Nginx (Веб-сервер, раздает HTML и SSL)
sudo systemctl status nginx
```

### Перезапуск (Restart)
```bash
sudo systemctl restart timetracker-bot
sudo systemctl restart timetracker-webhook
```

### Остановка (Stop)
```bash
sudo systemctl stop timetracker-bot
```

---

## 📜 5. Просмотр Логов (Ошибки)

Если что-то не работает, смотрите логи здесь.

### Логи Бота (Python)
Живой просмотр (нажмите `Ctrl+C` для выхода):
```bash
sudo journalctl -u timetracker-bot -f
```
Посмотреть последние 50 строк:
```bash
sudo journalctl -u timetracker-bot -n 50 --no-pager
```

### Логи Веб-сервера (Webhook / FastAPI)
Если не грузятся фото или ошибки 500:
```bash
sudo journalctl -u timetracker-webhook -f
```

### Логи Nginx (Проблемы с доступом к сайту)
```bash
sudo tail -n 20 /var/log/nginx/error.log
sudo tail -n 20 /var/log/nginx/timetracker_error.log
```

---

## 🛠️ 6. Полезные Команды "Скорой Помощи"

### Исправить права доступа (если "403 Forbidden")
```bash
chmod 755 /home/botuser/time-tracker
chmod -R 755 /home/botuser/time-tracker/www
```

### Быстрая правка конфига (если срочно нужно сменить URL)
```bash
nano /home/botuser/time-tracker/.env
# После правки обязательно:
sudo systemctl restart timetracker-bot timetracker-webhook
```

### Проверить, какие файлы реально лежат в Web-папке
```bash
ls -la /home/botuser/time-tracker/www/
```
