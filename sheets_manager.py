import gspread
import os
import datetime
import pytz
import logging
from google.oauth2.credentials import Credentials as UserCredentials
from google.oauth2.service_account import Credentials as ServiceCredentials
from googleapiclient.discovery import build

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("sheets_manager")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

class GoogleSheetManager:
    def __init__(self, json_path, drive_folder_id, template_file_id=None):
        self.json_path = json_path
        self.drive_folder_id = drive_folder_id
        self.template_file_id = template_file_id
        
        # Authenticate Strategy:
        # 1. Try OAuth "token.json" (User Account - No Quota issues)
        # 2. Try Service Account "json_path" (Fall back)
        
        self.creds = None
        
        if os.path.exists("token.json"):
            try:
                self.creds = UserCredentials.from_authorized_user_file("token.json", SCOPES)
                logger.info("Authenticated using OAuth (token.json).")
            except Exception as e:
                logger.error(f"Failed to use token.json: {e}")

        if not self.creds:
            # Fallback to Service Account
            logger.info("Using Service Account for authentication.")
            self.creds = ServiceCredentials.from_service_account_file(json_path, scopes=SCOPES)

        self.gc = gspread.authorize(self.creds)
        self.drive_service = build('drive', 'v3', credentials=self.creds)

        # Cache for current month's sheet ID to reduce API calls
        self._current_sheet_key = None
        self._current_sheet_month = None

    def _get_moscow_time(self):
        tz = pytz.timezone('Europe/Moscow')
        return datetime.datetime.now(tz)

    def _get_sheet_name(self, date_obj):
        # Format: "Timesheet_December_2025"
        return f"Timesheet_{date_obj.strftime('%B_%Y')}"

    @staticmethod
    def normalize_username(username: str) -> str:
        """Standardizes username for consistent comparison."""
        if not username: return ""
        return str(username).replace("@", "").strip().lower()

    def get_users_v2(self):
        """
        Reads users from Config_Users with columns:
        A: Name, B: Username, C: Telegram ID, D: Role, E: Team, F: Department, G: Status
        Actually headers say: 
        1: Name, 2: Username, 3: ID, 4: Role, 5: Team, 6: Department
        Let's assume G is status or we use Role/Department to deduce. 
        User said status is after. Let's read A:G.
        """
        import time
        for attempt in range(3):
            try:
                sheet = self.gc.open_by_key(self.template_file_id)
                wks = sheet.worksheet("Config_Users")
                # Reading A2:H to be safe and get all columns
                raw_values = wks.get("A2:H")
                if not raw_values: return []
                
                users = []
                for row in raw_values:
                    if len(row) >= 1 and row[0].strip():
                        name = row[0].strip()
                        users.append({
                            "name": name,
                            "username": self.normalize_username(row[1]) if len(row) > 1 else "",
                            "tg_id": str(row[2]).strip() if len(row) > 2 else "",
                            "role": row[3].strip().lower() if len(row) > 3 else "employee",
                            "team": row[4].strip() if len(row) > 4 else "Цех", # Default to CEH
                            "department": row[5].strip() if len(row) > 5 else "",
                            "status": row[6].strip().lower() if len(row) > 6 else "active"
                        })
                return users
            except Exception as e:
                logger.warning(f"Attempt {attempt+1} failed to load users: {e}")
                if attempt == 2: return []
                time.sleep(1)
        return []

    def find_user(self, tg_id: str = None, username: str = None):
        """Finds active user by ID or Normalized Username."""
        users = self.get_users_v2()
        norm_username = self.normalize_username(username) if username else None
        target_id = str(tg_id).strip() if tg_id else None
        
        # 1. Primary check by ID
        if target_id:
            for u in users:
                if u["tg_id"] == target_id and u["status"] == "active":
                    return u
        
        # 2. Secondary check by Username
        if norm_username:
            for u in users:
                if u["username"] == norm_username and u["status"] == "active":
                    return u
        return None

    def auto_bind_user(self, username: str, tg_id: str):
        """Binds Telegram ID automatically if username matches and ID slot is empty."""
        norm_search = self.normalize_username(username)
        if not norm_search: return None
        
        try:
            sheet = self.gc.open_by_key(self.template_file_id)
            wks = sheet.worksheet("Config_Users")
            raw_values = wks.get_all_values()
            
            for idx, row in enumerate(raw_values):
                if idx == 0: continue
                # Column B (index 1)
                row_username = self.normalize_username(row[1]) if len(row) > 1 else ""
                
                if row_username == norm_search:
                    # Update Column C (index 2)
                    wks.update_cell(idx + 1, 3, str(tg_id))
                    logger.info(f"SUCCESS: Auto-bound ID {tg_id} to @{norm_search}")
                    
                    return {
                        "name": row[0].strip(),
                        "username": row_username,
                        "tg_id": str(tg_id),
                        "role": row[3].strip().lower() if len(row) > 3 else "employee",
                        "team": row[4].strip() if len(row) > 4 else "Цех",
                        "department": row[5].strip() if len(row) > 5 else "",
                        "status": "active"
                    }
            return None
        except Exception as e:
            logger.error(f"CRITICAL: Auto-bind logic failed: {e}")
            return None

    def get_orphan_users(self):
        """Returns list of names that have no Telegram ID linked."""
        users = self.get_users_v2()
        return [u["name"] for u in users if not u["tg_id"] and u["status"] == "active"]

    def bind_telegram_id(self, tg_id: int, name: str):
        """Binds a Telegram ID to a specific name in Config_Users."""
        try:
            sheet = self.gc.open_by_key(self.template_file_id)
            wks = sheet.worksheet("Config_Users")
            
            # Find the row by Name in Column A
            cell = wks.find(name, in_column=1)
            if cell:
                wks.update_cell(cell.row, 3, str(tg_id))
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to bind ID: {e}")
            return False

    def get_users_from_template(self):
        """
        LEGACY: Reads users from the 'Config_Users' tab.
        Updated to handle new schema but return old formats for compatibility.
        """
        try:
            sheet = self.gc.open_by_key(self.template_file_id)
            wks = sheet.worksheet("Config_Users")
            
            # Read from A2 to E (New Schema)
            raw_values = wks.get("A2:E") 
            
            users_cache = {} # normalized_username -> real_name
            valid_rows = []
            all_names_set = set()
            
            if not raw_values:
                logger.warning("Config_Users is empty in Master Template.")
                return {}, [], set()

            for row in raw_values:
                if len(row) >= 1:
                    name = row[0].strip()
                    if name:
                        all_names_set.add(name)
                        
                    if len(row) >= 2:
                        username = row[1].strip()
                        if name and username:
                            norm_username = username.replace("@", "").lower()
                            users_cache[norm_username] = name
                            valid_rows.append(row[:2]) # Still return only A:B for generic sync
            
            logger.info(f"Loaded {len(users_cache)} users from Master Template.")
            return users_cache, valid_rows, all_names_set
            
        except Exception as e:
            logger.error(f"Failed to load users from template: {e}")
            raise e

    def sync_users_to_current_month(self, users_list=None):
        """
        Updates the 'Config_Users' tab in the CURRENT month's sheets for both teams.
        """
        try:
            now = self._get_moscow_time()
            target_name = self._get_sheet_name(now)
            
            # Map of team (normalized) -> folder_id
            teams_mapping = {
                "цех": os.getenv("WORKSHOP_FOLDER_ID"),
                "офис": os.getenv("OFFICE_FOLDER_ID"),
                "цех(офис)": os.getenv("CEH_OFFICE_FOLDER_ID"),
                "ташкент(офис)": os.getenv("TASHKENT_FOLDER_ID")
            }
            
            summary = []
            for team_key, folder_id in teams_mapping.items():
                if not folder_id: continue
                
                # Search sheet in specific folder
                query = f"name = '{target_name}' and '{folder_id}' in parents and mimeType = 'application/vnd.google-apps.spreadsheet' and trashed = false"
                results = self.drive_service.files().list(q=query, fields="files(id, name)").execute()
                items = results.get('files', [])
                
                if items:
                    file_id = items[0]['id']
                    if self._filter_sheet_users(file_id, team_key):
                        summary.append(f"{team_key}: Synced successfully.")
                    else:
                        summary.append(f"{team_key}: Sync failed.")
                else:
                    summary.append(f"{team_key}: Sheet not found.")
            
            return " | ".join(summary)

        except Exception as e:
            logger.error(f"Failed to sync users: {e}")
            return f"Error syncing users: {e}"

    def soft_delete_user(self, telegram_id: int):
        """Marks a user as deleted in Config_Users."""
        try:
            sheet = self.gc.open_by_key(self.template_file_id)
            wks = sheet.worksheet("Config_Users")
            # Find in Column C (ID)
            cell = wks.find(str(telegram_id), in_column=3)
            if cell:
                wks.update_cell(cell.row, 5, "deleted")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to soft delete: {e}")
            return False

    def admin_add_user(self, full_name, username="", tg_id="", role="employee"):
        """Adds a new user to Config_Users and optionally to the current month."""
        try:
            sheet = self.gc.open_by_key(self.template_file_id)
            wks = sheet.worksheet("Config_Users")
            wks.append_row([full_name, username, str(tg_id), role, "active"])
            
            # Immediately add to current month report if it exists
            self.add_user_to_current_month(full_name)
            return True
        except Exception as e:
            logger.error(f"Failed to add user: {e}")
            return False

    def add_user_to_current_month(self, full_name, team):
        """Adds a row for a new user in the specific team's report sheet."""
        now = self._get_moscow_time()
        target_name = self._get_sheet_name(now)
        
        team_norm = str(team).lower().strip()
        teams_mapping = {
            "цех": os.getenv("WORKSHOP_FOLDER_ID"),
            "офис": os.getenv("OFFICE_FOLDER_ID"),
            "цех(офис)": os.getenv("CEH_OFFICE_FOLDER_ID"),
            "ташкент(офис)": os.getenv("TASHKENT_FOLDER_ID")
        }
        folder_id = teams_mapping.get(team_norm)
        
        if not folder_id: return False
        
        try:
            query = f"name = '{target_name}' and '{folder_id}' in parents and trashed = false"
            results = self.drive_service.files().list(q=query, fields="files(id)").execute()
            items = results.get('files', [])
            if not items: return False
            
            sheet_id = items[0]['id']
            sheet = self.gc.open_by_key(sheet_id)
            wks = sheet.worksheet("Отчет_Месяц")
            
            names = wks.col_values(1)
            last_row = len(names)
            if last_row < 3: return False
            
            next_row = last_row + 1
            wks.copy_range(f"A{last_row}:DM{last_row}", f"A{next_row}:DM{next_row}")
            wks.update_acell(f"A{next_row}", full_name)
            return True
        except Exception as e:
            logger.error(f"Failed to add user to {team} month: {e}")
            return False


    def update_sheet_headers(self, sheet_file_id, date_obj):
        """
        Updates the header dates in 'Отчет_Месяц' (Row 1) to match the actual month/year.
        Assumes layout: Day 1 at Col C, Day 2 at Col F (every 3rd column).
        """
        try:
            logger.info("Updating sheet headers with correct dates...")
            
            import calendar
            year = date_obj.year
            month = date_obj.month
            num_days = calendar.monthrange(year, month)[1]
            
            sheet = self.gc.open_by_key(sheet_file_id)
            wks = sheet.worksheet("Отчет_Месяц")
            
            # Target Row 1, starting from Col C
            # We need to construct a list of values for the header row
            # Max possible width: 31 days * 3 cols = 93 cols
            
            # Fetch current row 1 to preserve formatting/structure if we were doing granular updates,
            # but simpler to just overwrite the date cells.
            
            # We will construct a list of size 93 (max days * 3)
            # But the sheet might have merged cells or specific structure.
            # Writing cell by cell is slow. Writing row is fast.
            # Let's get the whole Row 1 values first to not break "merged" cells logic if possible?
            # Actually, gspread update usually handles merged cells okay if we write to top-left.
            
            # Strategy: Construct a long list where only every 3rd element is the Date.
            # Others are empty strings (which gspread might overwrite existing data with empty).
            # BETTER: Read Row 1, update specific indices, write back.
            
            header_range = "C1:DM1" 
            current_values = wks.get(header_range)[0] 
            
            # Extend if short
            expected_len = 31 * 3
            if len(current_values) < expected_len:
                current_values.extend([""] * (expected_len - len(current_values)))
            
            new_values = list(current_values)
            
            for day in range(1, 32):
                col_offset = (day - 1) * 3 # 0, 3, 6... for C, F, I...
                
                if day <= num_days:
                    # Send as ISO date string "YYYY-MM-DD"
                    # Google Sheets 'USER_ENTERED' will parse this as a Date Object
                    d_obj = datetime.date(year, month, day)
                    val = d_obj.strftime("%Y-%m-%d")
                    
                    if col_offset < len(new_values):
                        new_values[col_offset] = val
                else:
                    # Clear invalid days
                    if col_offset < len(new_values):
                        new_values[col_offset] = ""
            
            # Write back to Row 1
            wks.update("C1", [new_values], value_input_option="USER_ENTERED")
            logger.info(f"Headers updated for {month}/{year} (Row 1)")
            
        except Exception as e:
            logger.error(f"Failed to update headers: {e}")

    def _filter_sheet_users(self, file_id, team_name):
        """Processes a specific sheet to only contain active users of a certain team."""
        try:
            users_list = self.get_users_v2()
            
            # 1. Filter active users for this specific team
            team_key = str(team_name).lower().strip()
            team_users = [u for u in users_list if str(u.get("team", "")).lower().strip() == team_key and u.get("status") == "active"]
            
            # Format: [Name, @Username]
            raw_rows = []
            for u in team_users:
                username = u.get("username", "")
                if username and not username.startswith("@"):
                    username = "@" + username
                raw_rows.append([u["name"], username])

            # 2. Update the Config_Users worksheet in the TARGET spreadsheet
            sheet = self.gc.open_by_key(file_id)
            wks = sheet.worksheet("Config_Users")
            
            # Clear existing data (A2:B contains name and username)
            wks.batch_clear(["A2:B100"]) # Clearing up to 100 rows to be safe
            
            if raw_rows:
                wks.update("A2", raw_rows, value_input_option="USER_ENTERED")
            
            logger.info(f"Team Filter Applied: {team_name} now has {len(raw_rows)} users in {file_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to filter users for team {team_name} in sheet {file_id}: {e}")
            return False

    def check_or_create_monthly_sheet(self, team="Цех"):
        """
        Checks if the sheet for the current month exists in the specific department folder.
        If not, copies the template and renames it.
        """
        now = self._get_moscow_time()
        target_name = self._get_sheet_name(now)
        
        team_norm = str(team).lower().strip()
        teams_mapping = {
            "цех": os.getenv("WORKSHOP_FOLDER_ID"),
            "офис": os.getenv("OFFICE_FOLDER_ID"),
            "цех(офис)": os.getenv("CEH_OFFICE_FOLDER_ID"),
            "ташкент(офис)": os.getenv("TASHKENT_FOLDER_ID")
        }
        folder_id = teams_mapping.get(team_norm)
        
        if not folder_id:
            logger.error(f"Missing folder ID for team: {team}")
            return None

        try:
            # Search for existing sheet in the SPECIFIC folder
            query = f"name = '{target_name}' and '{folder_id}' in parents and mimeType = 'application/vnd.google-apps.spreadsheet' and trashed = false"
            results = self.drive_service.files().list(q=query, fields="files(id, name)").execute()
            items = results.get('files', [])

            if items:
                file_id = items[0]['id']
                logger.info(f"Found existing sheet for {team}: {target_name}")
                self.update_sheet_headers(file_id, now)
                self._filter_sheet_users(file_id, team)
                return file_id

            logger.info(f"Sheet {target_name} not found for {team}. Creating from template...")
            new_file_id = None
            
            # Method A: Standard Copy
            try:
                file_metadata = {'name': target_name, 'parents': [folder_id]}
                file = self.drive_service.files().copy(
                    fileId=self.template_file_id,
                    body=file_metadata,
                    fields='id'
                ).execute()
                new_file_id = file.get('id')
                
            except Exception as e:
                if "storageQuotaExceeded" in str(e):
                    logger.warning(f"Quota limit hit on file copy for {team}. Applying Fallback.")
                    new_file_id = self._create_sheet_fallback(target_name, folder_id)
                else:
                    raise e
            
            if new_file_id:
                self.update_sheet_headers(new_file_id, now)
                self._filter_sheet_users(new_file_id, team)
                return new_file_id

        except Exception as e:
            logger.error(f"Error checking/creating sheet for {team}: {e}")
            return None

    def _create_sheet_fallback(self, target_name, folder_id):
        """
        Fallback: Create empty sheet -> Copy tabs from Template -> Delete default tab.
        """
        try:
            # 1. Create native sheet in specific folder
            sh = self.gc.create(target_name, folder_id=folder_id)
            template = self.gc.open_by_key(self.template_file_id)
            
            # 2. Copy Worksheets
            for ws in template.worksheets():
                ws.copy_to(sh.id)
            
            # 3. Reload to rename sheets
            sh = self.gc.open_by_key(sh.id)
            for ws in sh.worksheets():
                if ws.title.startswith("Copy of "):
                    original_name = ws.title.replace("Copy of ", "")
                    try:
                        ws.update_title(original_name)
                    except:
                        pass 
            
            # 4. Delete default Sheet1
            try:
                sheet1 = sh.worksheet("Sheet1")
                if len(sh.worksheets()) > 1:
                    sh.del_worksheet(sheet1)
            except:
                pass
                
            return sh.id
        except Exception as e:
            logger.error(f"Fallback creation failed: {e}")
            return None

    def append_log(self, user_name: str, telegram_id: int, log_type: str = "Log", 
                   photo_url: str = "", submitted_by: str = "", team="Цех"):
        """
        Appends a log entry to the current month's sheet of the SPECIFIC team.
        """
        now = self._get_moscow_time()
        
        # Ensure sheet exists for this team
        file_id = self.check_or_create_monthly_sheet(team)
        if not file_id:
            raise Exception(f"Could not find or create sheet for team {team}")
        
        try:
            sheet = self.gc.open_by_key(file_id)
            wks = sheet.worksheet("DB_Logs")
            
            # MANUAL ROW CALCULATION TO PREVENT SHIFTS
            # Find the next available row based on Column A
            col_a = wks.col_values(1)
            next_row = len(col_a) + 1
            
            date_str = now.strftime("%d.%m.%Y")
            time_str = now.strftime("%H:%M")
            
            # Row Format: Date, Time, Employee Name, Type, Submitted By
            row = [date_str, time_str, user_name, log_type, submitted_by]
            
            # Update specific range A{next_row}
            range_name = f"A{next_row}"
            wks.update(range_name, [row], value_input_option="USER_ENTERED")
            
            logger.info(f"Logged {log_type} for {user_name} at {time_str} (Row {next_row})")
            
        except Exception as e:
            logger.error(f"Failed to append log: {e}")
            raise e

