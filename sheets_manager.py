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
        A: Name, B: Username, C: Telegram ID, D: Role, E: Status
        """
        import time
        for attempt in range(3):
            try:
                sheet = self.gc.open_by_key(self.template_file_id)
                wks = sheet.worksheet("Config_Users")
                raw_values = wks.get("A2:E")
                if not raw_values: return []
                
                users = []
                for row in raw_values:
                    if len(row) >= 1 and row[0].strip():
                        users.append({
                            "name": row[0].strip(),
                            "username": self.normalize_username(row[1]) if len(row) > 1 else "",
                            "tg_id": str(row[2]).strip() if len(row) > 2 else "",
                            "role": row[3].strip().lower() if len(row) > 3 else "employee",
                            "status": row[4].strip().lower() if len(row) > 4 else "active"
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

    def sync_users_to_current_month(self, raw_values):
        """
        Updates the 'Config_Users' tab in the CURRENT month's sheet.
        """
        try:
            now = self._get_moscow_time()
            target_name = self._get_sheet_name(now)
            
            # Use cached sheet key if valid
            sheet = None
            if self._current_sheet_key and self._current_sheet_month == target_name:
                try:
                    sheet = self.gc.open_by_key(self._current_sheet_key)
                except:
                    pass
            
            if not sheet:
                # Search
                query = f"name = '{target_name}' and '{self.drive_folder_id}' in parents and mimeType = 'application/vnd.google-apps.spreadsheet' and trashed = false"
                results = self.drive_service.files().list(q=query, fields="files(id, name)").execute()
                items = results.get('files', [])
                if items:
                    file_id = items[0]['id']
                    sheet = self.gc.open_by_key(file_id)
                    # update cache
                    self._current_sheet_key = file_id
                    self._current_sheet_month = target_name
                else:
                    return "Current month sheet does not exist. No sync needed."

            # Perform Sync
            wks = sheet.worksheet("Config_Users")
            # Clear old data A2:B
            wks.batch_clear(["A2:B"])
            # Update with new data
            if raw_values:
                wks.update("A2", raw_values, value_input_option="USER_ENTERED")
            
            return f"Synced {len(raw_values)} users to {target_name}."

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

    def add_user_to_current_month(self, full_name):
        """Adds a row for a new user in the current month's report sheet if it exists."""
        now = self._get_moscow_time()
        target_name = self._get_sheet_name(now)
        try:
            query = f"name = '{target_name}' and '{self.drive_folder_id}' in parents and trashed = false"
            results = self.drive_service.files().list(q=query, fields="files(id)").execute()
            items = results.get('files', [])
            if not items: return False
            
            sheet_id = items[0]['id']
            sheet = self.gc.open_by_key(sheet_id)
            wks = sheet.worksheet("Отчет_Месяц")
            
            # Find the last row with a name in Column A
            names = wks.col_values(1)
            last_row = len(names)
            
            if last_row < 3: return False # Header is 1-2
            
            # Copy formatting and formulas from the last existing employee row
            # Range structure from structure.js: A:DM
            next_row = last_row + 1
            wks.copy_range(f"A{last_row}:DM{last_row}", f"A{next_row}:DM{next_row}")
            wks.update_acell(f"A{next_row}", full_name)
            return True
        except Exception as e:
            logger.error(f"Failed to add user to month: {e}")
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

    def check_or_create_monthly_sheet(self):
        """
        Checks if the sheet for the current month exists in the target folder.
        If not, copies the template and renames it.
        Handles storageQuotaExceeded by falling back to manual sheet creation.
        """
        now = self._get_moscow_time()
        target_name = self._get_sheet_name(now)
        
        # Check cache
        if self._current_sheet_key and self._current_sheet_month == target_name:
            try:
                self.gc.open_by_key(self._current_sheet_key)
                return 
            except:
                self._current_sheet_key = None

        try:
            # Search for existing sheet
            query = f"name = '{target_name}' and '{self.drive_folder_id}' in parents and mimeType = 'application/vnd.google-apps.spreadsheet' and trashed = false"
            results = self.drive_service.files().list(q=query, fields="files(id, name)").execute()
            items = results.get('files', [])

            if items:
                self._current_sheet_key = items[0]['id']
                self._current_sheet_month = target_name
                logger.info(f"Found existing sheet: {target_name} ({items[0]['id']})")
                
                # OPTIONAL: Force update headers even for existing sheets? 
                # For now, let's do it to fix the User's current problem automatically!
                self.update_sheet_headers(self._current_sheet_key, now)
                return

            logger.info(f"Sheet {target_name} not found. Creating from template...")
            new_file_id = None
            
            # Method A: Standard Copy
            try:
                file_metadata = {
                    'name': target_name,
                    'parents': [self.drive_folder_id]
                }
                file = self.drive_service.files().copy(
                    fileId=self.template_file_id,
                    body=file_metadata,
                    fields='id'
                ).execute()
                new_file_id = file.get('id')
                
            except Exception as e:
                if "storageQuotaExceeded" in str(e):
                    logger.warning("Quota limit hit on file copy. Applying Fallback: Manual Create & Copy.")
                    new_file_id = self._create_sheet_fallback(target_name)
                    if not new_file_id:
                        raise e 
                else:
                    raise e
            
            if new_file_id:
                self._current_sheet_key = new_file_id
                self._current_sheet_month = target_name
                logger.info(f"Successfully created monthly sheet: {target_name}")

                try:
                    # 1. Update Headers
                    self.update_sheet_headers(new_file_id, now)
                    
                    # 2. Sync Users
                    users, raw, _ = self.get_users_from_template()
                    self.sync_users_to_current_month(raw)
                    
                except Exception as sync_err:
                     logger.error(f"Post-creation updates failed: {sync_err}")

        except Exception as e:
            logger.error(f"An error occurred with Google Drive API: {e}")
            raise e

    def _create_sheet_fallback(self, target_name):
        """
        Fallback: Create empty sheet -> Copy tabs from Template -> Delete default tab.
        This uses Sheets API quota (Docs) instead of Drive Storage quota.
        """
        try:
            # 1. Create native sheet
            sh = self.gc.create(target_name, folder_id=self.drive_folder_id)
            template = self.gc.open_by_key(self.template_file_id)
            
            # 2. Copy Worksheets
            for ws in template.worksheets():
                ws.copy_to(sh.id)
            
            # 3. Reload to rename sheets (copied sheets are named "Copy of X")
            sh = self.gc.open_by_key(sh.id)
            for ws in sh.worksheets():
                if ws.title.startswith("Copy of "):
                    original_name = ws.title.replace("Copy of ", "")
                    try:
                        ws.update_title(original_name)
                    except:
                        pass # Ignore if name exists
            
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
                   photo_url: str = "", submitted_by: str = ""):
        """
        Appends a log entry to the current month's sheet.
        """
        now = self._get_moscow_time()
        
        # Ensure sheet exists
        self.check_or_create_monthly_sheet()
        
        try:
            sheet = self.gc.open_by_key(self._current_sheet_key)
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

