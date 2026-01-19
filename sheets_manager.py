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

    def get_users_from_template(self):
        """
        Reads users from the 'Config_Users' tab in the MASTER TEMPLATE.
        Returns: 
           - dict: {normalized_username: real_name} (for auth)
           - list: raw rows for syncing
           - set: all_names_set (set of all valid names found in column A)
        """
        try:
            # Open the TEMPLATE file directly
            sheet = self.gc.open_by_key(self.template_file_id)
            wks = sheet.worksheet("Config_Users")
            
            # Read from A2 to B (assuming headers in row 1)
            raw_values = wks.get("A2:B") 
            
            users_cache = {}
            valid_rows = []
            all_names_set = set()
            
            if not raw_values:
                logger.warning("Config_Users is empty in Master Template.")
                return {}, [], set()

            for row in raw_values:
                if len(row) >= 1: # At least name must exist
                    name = row[0].strip()
                    if name:
                        all_names_set.add(name)
                        
                    if len(row) >= 2:
                        username = row[1].strip()
                        if name and username:
                            # Normalize: lower case, remove @
                            norm_username = username.replace("@", "").lower()
                            users_cache[norm_username] = name
                            valid_rows.append(row)
            
            logger.info(f"Loaded {len(users_cache)} users (auth) and {len(all_names_set)} total names from Master Template.")
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

    def append_log(self, user_name: str, telegram_id: int, telegram_username: str, log_type: str = "Log"):
        """
        Appends a log entry to the current month's sheet.
        """
        now = self._get_moscow_time()
        
        # Ensure sheet exists
        self.check_or_create_monthly_sheet()
        
        try:
            sheet = self.gc.open_by_key(self._current_sheet_key)
            wks = sheet.worksheet("DB_Logs")
            
            date_str = now.strftime("%d.%m.%Y")
            time_str = now.strftime("%H:%M")
            
            # Row Format: Date, Time, Employee Name, Type, Telegram Username
            row = [date_str, time_str, user_name, log_type, telegram_username]
            
            # Append using USER_ENTERED to ensure dates are parsed correctly by Sheets
            wks.append_row(row, value_input_option="USER_ENTERED")
            
            logger.info(f"Logged entry for {user_name} at {time_str}")
            
        except Exception as e:
            logger.error(f"Failed to append log: {e}")
            raise e
