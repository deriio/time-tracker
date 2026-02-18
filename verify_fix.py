import unittest
from unittest.mock import MagicMock, patch
import sys
import os
import logging

# Add project root to sys.path
sys.path.append(os.getcwd())

# Suppress logging for clean output
logging.disable(logging.CRITICAL)

from sheets_manager import GoogleSheetManager

class TestCacheFix(unittest.TestCase):
    @patch('sheets_manager.gspread')
    @patch('sheets_manager.build') # mock googleapiclient.discovery.build
    def test_auto_bind_updates_cache(self, mock_build, mock_gspread):
        # Setup mocks
        mock_gc = MagicMock()
        mock_gspread.authorize.return_value = mock_gc
        
        # Mock sheet behavior
        mock_sheet = MagicMock()
        mock_gc.open_by_key.return_value = mock_sheet
        mock_wks = MagicMock()
        mock_sheet.worksheet.return_value = mock_wks
        
        # Setup data for auto_bind_user to find a match
        # It reads all values, row 0 is header.
        # It expects [Name, Username, TG_ID, Role, Team, Dept, Status] in Config_Users
        # Index 1 is Username.
        mock_wks.get_all_values.return_value = [
            ["Name", "Username", "TG_ID", "Role", "Team", "Dept", "Status"],
            ["Test User", "testuser", "", "employee", "Office", "IT", "active"]
        ]
        
        # Initialize Manager
        # We need to mock credentials too or init will fail/try to read files
        with patch('sheets_manager.ServiceCredentials'), patch('sheets_manager.UserCredentials'):
            sm = GoogleSheetManager("dummy.json", "folder_id", "template_id")
            
            # Spy on get_users_v2
            # We must assign it back to the instance carefully so it's still callable if needed,
            # but wrapping it with MagicMock is easier to verify calls.
            # However, auto_bind_user calls self.get_users_v2(). 
            # If we replace it with a Mock, the original code won't run, which is fine for this test 
            # as long as we verify the CALL.
            sm.get_users_v2 = MagicMock(return_value=[{
                "name": "Test User", "username": "testuser", "tg_id": "123456", "role": "employee", "team": "Office", "department": "IT", "status": "active"
            }])
            
            print("\nExecuting auto_bind_user...")
            # Run auto_bind_user
            result = sm.auto_bind_user("testuser", "123456")
            
            # Verify result
            self.assertIsNotNone(result)
            self.assertEqual(result['tg_id'], "123456")
            
            # CRITICAL: Verify cache update was called with use_cache=False
            sm.get_users_v2.assert_called_with(use_cache=False)
            print("SUCCESS: auto_bind_user triggered cache refresh!")

if __name__ == '__main__':
    unittest.main()
