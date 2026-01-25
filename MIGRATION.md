# 🔄 Migration Guide: Cloudflare → VPS

Краткое руководство по миграции с Cloudflare Tunnel на VPS.

## 📋 Что изменилось

### До (Cloudflare Tunnel)
```
Local Machine → Cloudflare Tunnel → Internet
- Фото хранятся локально
- Ручной запуск через Python
- Временный URL туннеля
```

### После (VPS + Nginx)
```
VPS → Nginx → Internet
- Фото на VPS с автоочисткой (5 мин TTL)
- Systemd автозапуск
- Постоянный домен с SSL
```

## ✨ Новые возможности

1. **Автоматическая очистка фото**:
   - Немедленное удаление после отправки
   - Фоновая задача очистки каждые 60 секунд
   - TTL: 5 минут

2. **Production-ready инфраструктура**:
   - Nginx reverse proxy
   - SSL/HTTPS через Let's Encrypt
   - Systemd для автозапуска
   - Централизованное логирование

3. **Мониторинг**:
   - Health check endpoint
   - Автоматические бэкапы
   - Скрипты мониторинга

## 🚀 Быстрая миграция

### 1. Подготовка (5 минут)

```bash
# На локальной машине - убедитесь, что все изменения закоммичены
git add .
git commit -m "Ready for VPS deployment"
git push origin main
```

### 2. Настройка VPS (30 минут)

```bash
# SSH на VPS
ssh root@YOUR_VPS_IP

# Создать пользователя
useradd -m -s /bin/bash botuser
passwd botuser

# Установить зависимости
apt update && apt upgrade -y
apt install -y python3.10 python3.10-venv python3-pip nginx certbot python3-certbot-nginx git htop curl build-essential fail2ban ufw

# Настроить firewall
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw enable

# Переключиться на botuser
su - botuser
```

### 3. Развертывание (15 минут)

```bash
# Клонировать репозиторий
git clone https://github.com/deriio/time-tracker.git
cd time-tracker

# Создать .env
cp deploy/.env.production.template .env
nano .env  # Заполнить значениями

# Запустить автоматическое развертывание
chmod +x deploy/scripts/deploy.sh
./deploy/scripts/deploy.sh
```

### 4. Настройка Nginx (10 минут)

```bash
# Скопировать конфигурацию
sudo cp deploy/nginx/timetracker.conf /etc/nginx/sites-available/timetracker

# Отредактировать домен
sudo nano /etc/nginx/sites-available/timetracker
# Заменить YOUR_DOMAIN.com на ваш домен

# Активировать
sudo ln -s /etc/nginx/sites-available/timetracker /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 5. SSL сертификат (5 минут)

```bash
sudo certbot --nginx -d YOUR_DOMAIN.com
```

### 6. Финальная настройка (5 минут)

```bash
# Обновить .env с доменом
nano .env
# Изменить: WEBHOOK_SERVER_URL=https://YOUR_DOMAIN.com

# Перезапустить сервисы
sudo systemctl restart timetracker-bot timetracker-webhook
```

### 7. Проверка (5 минут)

```bash
# Проверить сервисы
sudo systemctl status timetracker-bot
sudo systemctl status timetracker-webhook

# Проверить HTTP
curl https://YOUR_DOMAIN.com/health

# Проверить в Telegram
# /start → Сделать отчет → Сделать фото → Отправить
```

## 📊 Чеклист миграции

- [ ] VPS подготовлен (пользователь, пакеты, firewall)
- [ ] Репозиторий склонирован
- [ ] .env создан с правильными значениями
- [ ] credentials.json загружен на VPS
- [ ] Скрипт deploy.sh выполнен успешно
- [ ] Nginx настроен с вашим доменом
- [ ] SSL сертификат получен
- [ ] WEBHOOK_SERVER_URL обновлен в .env
- [ ] Сервисы перезапущены
- [ ] Бот отвечает на /start
- [ ] WebApp загружается
- [ ] Check-in/out работает
- [ ] Фото автоматически удаляются

## 🔧 Изменения в коде

### webhook_server.py
- ✅ Добавлен `asyncio` и `datetime` импорты
- ✅ Добавлены константы `PHOTO_TTL_MINUTES` и `CLEANUP_INTERVAL_SECONDS`
- ✅ Добавлена функция `cleanup_old_photos()`
- ✅ Добавлен `@app.on_event("startup")` для запуска фоновой задачи

### main.py
- ✅ Улучшена логика удаления фото после отправки
- ✅ Добавлена обработка ошибок при удалении
- ✅ Добавлено логирование успешной очистки

### Новые файлы
- ✅ `deploy/.env.production.template` - шаблон переменных окружения
- ✅ `deploy/nginx/timetracker.conf` - конфигурация Nginx
- ✅ `deploy/systemd/timetracker-bot.service` - systemd сервис бота
- ✅ `deploy/systemd/timetracker-webhook.service` - systemd сервис webhook
- ✅ `deploy/scripts/deploy.sh` - скрипт автоматического развертывания
- ✅ `deploy/scripts/healthcheck.sh` - скрипт проверки здоровья
- ✅ `deploy/scripts/backup.sh` - скрипт резервного копирования
- ✅ `deploy/README.md` - полная документация по развертыванию

## 🆘 Troubleshooting

### Проблема: Бот не отвечает
```bash
sudo systemctl status timetracker-bot
sudo journalctl -u timetracker-bot -n 50
```

### Проблема: 502 Bad Gateway
```bash
sudo systemctl status timetracker-webhook
curl localhost:8000/health
sudo systemctl restart timetracker-webhook
```

### Проблема: Фото не загружаются
```bash
ls -la /home/botuser/time-tracker/photos/
chmod 755 /home/botuser/time-tracker/photos/
sudo nginx -t
```

## 📞 Поддержка

Полная документация:
- **Развертывание**: [`deploy/README.md`](deploy/README.md)
- **Технический план**: [`Technical Deployment plan.md`](Technical%20Deployment%20plan.md)
- **Основная документация**: [`README.md`](README.md)

## ⏱️ Общее время миграции

**Примерно 75 минут** (1 час 15 минут):
- Подготовка VPS: 30 мин
- Развертывание: 15 мин
- Nginx: 10 мин
- SSL: 5 мин
- Финальная настройка: 5 мин
- Проверка: 5 мин
- Резерв на troubleshooting: 5 мин

**Downtime: 0 минут** (если Cloudflare Tunnel работает во время настройки)
