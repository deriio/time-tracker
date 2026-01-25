# 🚀 Deployment Guide

Этот каталог содержит все необходимые файлы для развертывания Time Tracker Bot на VPS.

## 📁 Структура

```
deploy/
├── .env.production.template    # Шаблон переменных окружения
├── nginx/
│   └── timetracker.conf        # Конфигурация Nginx
├── systemd/
│   ├── timetracker-bot.service     # Systemd сервис для бота
│   └── timetracker-webhook.service # Systemd сервис для webhook
├── scripts/
│   ├── deploy.sh              # Основной скрипт развертывания
│   ├── healthcheck.sh         # Скрипт проверки здоровья системы
│   └── backup.sh              # Скрипт резервного копирования
└── README.md                  # Этот файл
```

## 🎯 Быстрый старт

### 1. Подготовка VPS

```bash
# Обновление системы
sudo apt update && sudo apt upgrade -y

# Установка необходимых пакетов
sudo apt install -y python3.10 python3.10-venv python3-pip nginx certbot python3-certbot-nginx git htop curl build-essential fail2ban ufw

# Настройка firewall
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw enable
```

### 2. Создание пользователя

```bash
# Создать пользователя botuser
sudo useradd -m -s /bin/bash botuser
sudo passwd botuser

# Переключиться на botuser
su - botuser
```

### 3. Загрузка конфигурационных файлов

**С локальной машины:**

```bash
# Загрузить credentials
scp credentials.json botuser@YOUR_VPS_IP:/home/botuser/
scp token.json botuser@YOUR_VPS_IP:/home/botuser/
scp oauth_credentials.json botuser@YOUR_VPS_IP:/home/botuser/
```

### 4. Запуск автоматического развертывания

```bash
# На VPS как botuser
cd /home/botuser
git clone https://github.com/deriio/time-tracker.git
cd time-tracker

# Создать .env файл
cp deploy/.env.production.template .env
nano .env  # Заполнить реальными значениями

# Переместить credentials
mv /home/botuser/credentials.json .
mv /home/botuser/token.json .
mv /home/botuser/oauth_credentials.json .

# Запустить развертывание
chmod +x deploy/scripts/deploy.sh
./deploy/scripts/deploy.sh
```

### 5. Настройка Nginx

```bash
# Скопировать конфигурацию
sudo cp deploy/nginx/timetracker.conf /etc/nginx/sites-available/timetracker

# Отредактировать YOUR_DOMAIN.com на ваш реальный домен
sudo nano /etc/nginx/sites-available/timetracker

# Проверить конфигурацию
sudo nginx -t

# Создать symlink
sudo ln -s /etc/nginx/sites-available/timetracker /etc/nginx/sites-enabled/

# Удалить default site (опционально)
sudo rm /etc/nginx/sites-enabled/default

# Перезагрузить Nginx
sudo systemctl reload nginx
```

### 6. Настройка SSL

```bash
# Получить SSL сертификат
sudo certbot --nginx -d YOUR_DOMAIN.com

# Проверить автообновление
sudo certbot renew --dry-run
```

### 7. Обновление .env с доменом

```bash
# Обновить WEBHOOK_SERVER_URL
nano .env
# Изменить: WEBHOOK_SERVER_URL=https://YOUR_DOMAIN.com

# Перезапустить сервисы
sudo systemctl restart timetracker-bot timetracker-webhook
```

## 🔧 Управление сервисами

### Просмотр логов

```bash
# Логи бота (real-time)
sudo journalctl -u timetracker-bot -f

# Логи webhook (real-time)
sudo journalctl -u timetracker-webhook -f

# Последние 100 строк
sudo journalctl -u timetracker-bot -n 100

# Поиск ошибок
sudo journalctl -u timetracker-webhook | grep ERROR
```

### Перезапуск сервисов

```bash
# Перезапустить бота
sudo systemctl restart timetracker-bot

# Перезапустить webhook
sudo systemctl restart timetracker-webhook

# Перезапустить оба
sudo systemctl restart timetracker-bot timetracker-webhook
```

### Остановка/Запуск

```bash
# Остановить
sudo systemctl stop timetracker-bot timetracker-webhook

# Запустить
sudo systemctl start timetracker-webhook
sleep 3
sudo systemctl start timetracker-bot

# Проверить статус
sudo systemctl status timetracker-bot
sudo systemctl status timetracker-webhook
```

## 📊 Мониторинг

### Health Check

```bash
# Запустить проверку здоровья
./deploy/scripts/healthcheck.sh

# Добавить в crontab для автоматической проверки каждые 15 минут
crontab -e
# Добавить: */15 * * * * /home/botuser/time-tracker/deploy/scripts/healthcheck.sh >> /home/botuser/logs/health.log 2>&1
```

### Резервное копирование

```bash
# Запустить резервное копирование
./deploy/scripts/backup.sh

# Добавить в crontab для ежедневного бэкапа в 3:00
crontab -e
# Добавить: 0 3 * * * /home/botuser/time-tracker/deploy/scripts/backup.sh
```

## 🧪 Тестирование

### Проверка HTTP endpoints

```bash
# Health check
curl https://YOUR_DOMAIN.com/health

# Config endpoint
curl https://YOUR_DOMAIN.com/api/config

# Проверка времени ответа
curl -o /dev/null -s -w "%{time_total}\n" https://YOUR_DOMAIN.com/api/config
```

### Проверка портов

```bash
# Проверить, что webhook слушает на 8000
sudo netstat -tlnp | grep 8000

# Проверить Nginx
sudo netstat -tlnp | grep nginx
```

## 🔄 Обновление кода

```bash
# Переключиться на botuser
su - botuser
cd /home/botuser/time-tracker

# Получить последние изменения
git pull

# Обновить зависимости (если изменились)
source venv/bin/activate
pip install -r requirements.txt

# Перезапустить сервисы
sudo systemctl restart timetracker-bot timetracker-webhook
```

## 🆘 Troubleshooting

### Бот не отвечает

```bash
# Проверить статус
sudo systemctl status timetracker-bot

# Проверить логи
sudo journalctl -u timetracker-bot -n 50

# Проверить BOT_TOKEN в .env
cat .env | grep BOT_TOKEN
```

### 502 Bad Gateway

```bash
# Проверить webhook сервис
sudo systemctl status timetracker-webhook

# Проверить, слушает ли на порту 8000
curl localhost:8000/health

# Перезапустить webhook
sudo systemctl restart timetracker-webhook
```

### Фото не загружаются

```bash
# Проверить права на папку photos
ls -la /home/botuser/time-tracker/photos/

# Исправить права
chmod 755 /home/botuser/time-tracker/photos/

# Проверить Nginx конфигурацию
sudo nginx -t
```

### SSL ошибки

```bash
# Проверить сертификаты
sudo certbot certificates

# Обновить сертификат
sudo certbot renew

# Проверить Nginx конфигурацию
sudo nginx -t
```

## 📋 Чеклист успешного развертывания

- [ ] VPS настроен (firewall, пакеты установлены)
- [ ] Пользователь botuser создан
- [ ] Репозиторий склонирован
- [ ] .env файл создан с правильными значениями
- [ ] credentials.json загружен
- [ ] Виртуальное окружение создано
- [ ] Зависимости установлены
- [ ] Systemd сервисы установлены и запущены
- [ ] Nginx настроен
- [ ] SSL сертификат получен
- [ ] WEBHOOK_SERVER_URL обновлен в .env
- [ ] Сервисы перезапущены
- [ ] Бот отвечает на /start
- [ ] WebApp загружается
- [ ] Фото загружаются и отправляются
- [ ] Фото автоматически удаляются через 5 минут
- [ ] Логи пишутся в Google Sheets

## 🎯 Критерии успеха

✅ Оба сервиса работают: `systemctl status timetracker-bot timetracker-webhook`
✅ HTTPS доступен: `curl https://YOUR_DOMAIN.com/health`
✅ Бот отвечает в Telegram
✅ WebApp загружается без ошибок
✅ Полный workflow check-in/out работает
✅ Фото автоматически удаляются через 5 минут
✅ Google Sheets логирование работает
✅ Нет ошибок в логах за последний час

## 📞 Поддержка

При возникновении проблем:
1. Проверьте логи: `sudo journalctl -u timetracker-bot -f`
2. Запустите health check: `./deploy/scripts/healthcheck.sh`
3. Проверьте Technical Deployment plan.md для детальных инструкций
