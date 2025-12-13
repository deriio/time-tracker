# Telegram Attendance Bot (Check In/Out)

A robust Telegram bot for tracking employee attendance. It logs check-in/out times with photos directly to Google Sheets, automatically creates monthly timesheets, and manages user authorization via a Master Template.

## Features
- **Photo-based Check-in**: Employees send a photo to check in/out.
- **Google Sheets Integration**: Logs are saved to a specific monthly sheet (e.g., `Timesheet_December_2025`).
- **Automatic Sheet Management**: 
  - Automatically creates new monthly sheets from a template `MASTER_TEMPLATE`.
  - Intelligently updates date headers in the new sheet to match the current month.
- **Dynamic User Management**:
  - Authorized users are loaded from the `Config_Users` tab in the Master Template.
  - Admin command `/update` refreshes the user list without restarting the bot.
- **OAuth 2.0 Authentication**: Runs as the "User" to avoid Google Service Account storage quotas.

## Setup

### 1. Prerequisites
- Python 3.10+
- A Google Cloud Project with Drive and Sheets APIs enabled.
- **OAuth 2.0 Client ID** (Desktop App) credentials from Google Cloud.

### 2. Installation
1. Clone the repository.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Configure `.env` (see `.env.example`).
   ```ini
   BOT_TOKEN=your_telegram_bot_token
   GOOGLE_JSON_PATH=credentials.json  # Path to OAuth Client Secret
   DRIVE_FOLDER_ID=your_drive_folder_id
   TEMPLATE_FILE_ID=your_master_template_id
   ADMIN_IDS=12345678,87654321
   ```

### 3. Google Auth Setup (Important)
To allow the bot to create files on your behalf (solving Quota issues), perform this one-time setup:
1. Download `credentials.json` (OAuth Client ID) from Google Cloud and place it in the project root.
2. Run the setup script:
   ```bash
   python make_token.py
   ```
3. Follow the link printed in the console, log in with the Google Account that owns the Drive folder, and authorize the app.
4. This will generate a `token.json` file. The bot uses this to log in automatically.

### 4. Running the Bot
```bash
python main.py
```

## Admin Commands
- `/update`: Refreshes the authorized user list from the Master Template and syncs it to the current month's sheet. (Admins only).

## File Structure
- `main.py`: Bot entry point.
- `sheets_manager.py`: Google Sheets/Drive logic.
- `make_token.py`: Script to generate OAuth token.
- `credentials.json`: Your OAuth Client secret (DO NOT COMMIT).
- `token.json`: Generated access token (DO NOT COMMIT).
