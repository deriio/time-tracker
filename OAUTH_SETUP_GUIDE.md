# 🔐 Настройка OAuth 2.0 (Чтобы бот работал от имени владельца)

Этот метод авторизации позволяет боту использовать квоту и права вашего личного Google Аккаунта. Это решает ошибку `storageQuotaExceeded`.

---

## ШАГ 1: Настройка экрана согласия (Consent Screen)

1.  Зайдите в [Google Cloud Console](https://console.cloud.google.com/) (в проект `TimeTrackingBot`).
2.  В меню слева выберите **APIs & Services** -> **OAuth consent screen**.
3.  Выберите **External** (Внешний) и нажмите **CREATE**.
4.  Заполните обязательные поля:
    *   **App name**: `TimeBot`
    *   **User support email**: Ваш email.
    *   **Developer contact information**: Ваш email.
    *   Нажмите **SAVE AND CONTINUE**.
5.  **Scopes** (Области доступа):
    *   Нажмите **ADD OR REMOVE SCOPES**.
    *   В поиске найдите и отметьте галочками:
        *   `.../auth/drive` (Google Drive API)
        *   `.../auth/spreadsheets` (Google Sheets API)
    *   Нажмите **UPDATE**, затем **SAVE AND CONTINUE**.
6.  **Test Users** (Тестовые пользователи):
    *   Нажмите **ADD USERS**.
    *   Введите **Email заказчика** (на котором висит проект и папка).
    *   Нажмите **ADD**, затем **SAVE AND CONTINUE**.
7.  В конце нажмите **BACK TO DASHBOARD**.

---

## ШАГ 2: Создание ключей (Client ID)

1.  В меню слева выберите **Credentials**.
2.  Нажмите **+ CREATE CREDENTIALS** -> **OAuth client ID**.
3.  **Application type**: Выберите **Desktop app** (Приложение для ПК).
4.  **Name**: `Desktop Client 1` (можно оставить как есть).
5.  Нажмите **CREATE**.
6.  Появится окно "OAuth client created".
    *   Нажмите кнопку **DOWNLOAD JSON** (иконка скачивания).
    *   Сохраните файл как **`credentials.json`** в папку с ботом.

---

## ШАГ 3: Получение Токена (Один раз)

1.  В папке с ботом запустите скрипт генерации токена (я его создам для вас):
    ```bash
    python make_token.py
    ```
2.  В консоли появится ссылка. Скопируйте её и вставьте в браузер.
3.  Выберите аккаунт Заказчика.
4.  Google скажет "Google hasn’t verified this app" (Приложение не проверено).
    *   Нажмите **Advanced** (Дополнительно) -> **Go to TimeBot (unsafe)**.
5.  Нажмите **Continue** / **Allow** (Разрешить), чтобы дать права на Диск и Таблицы.
6.  Появится код (или сообщение "Authentication successful").
7.  В папке бота появится файл **`token.json`**.

Всё! Теперь у вас есть `token.json`, который дает боту полные права вашего аккаунта. Бот будет использовать его автоматически.
