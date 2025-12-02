#!/usr/bin/env python3
"""
Automate pyTivo video transfers to TiVo devices.

This script uses Network Remote Control to navigate to pyTivo shares
and start video transfers automatically.

NOTE: This is somewhat fragile and depends on your TiVo's menu structure.
You may need to customize the navigation logic for your specific setup.
"""

import sys
import time
import argparse
import subprocess
import re
import os
from tivo_remote import TiVoRemote, TiVoButton, TiVoNavigator


class PyTivoAutomation:
    """Automate pyTivo transfers."""
    
    def __init__(self, tivo_host: str, nav_config: str = None):
        """
        Initialize automation.
        
        Args:
            tivo_host: TiVo IP address
            nav_config: Path to navigation configuration file (optional)
                       If not provided, searches standard locations
        """
        self.remote = TiVoRemote(tivo_host)
        self.nav = TiVoNavigator(self.remote)
        
        # Find navigation config file
        if nav_config is None:
            nav_config = self._find_nav_config()
        
        self.nav_config = nav_config
        self.nav_sequences = self.load_navigation_config()
    
    def _find_nav_config(self):
        """Find tivo_navigation.txt in standard locations."""
        search_paths = [
            'tivo_navigation.txt',  # Current directory
            os.path.join(os.path.dirname(__file__), 'tivo_navigation.txt'),  # Same dir as script
            '/usr/local/bin/tivo_navigation.txt',  # System install
            '/usr/local/etc/tivo_navigation.txt',  # Alternative system location
            os.path.expanduser('~/.config/pytivo/tivo_navigation.txt'),  # User config
        ]
        
        for path in search_paths:
            if os.path.exists(path):
                return path
        
        # Default to current directory if not found
        return 'tivo_navigation.txt'
        
    def load_navigation_config(self):
        """
        Load navigation sequences from config file.
        
        Returns:
            Dict mapping command names to list of (button, delay) tuples
        """
        sequences = {}
        
        if not os.path.exists(self.nav_config):
            print(f"Warning: Navigation config not found: {self.nav_config}")
            return sequences
        
        try:
            with open(self.nav_config, 'r') as f:
                current_command = None
                current_sequence = []
                
                for line in f:
                    line = line.strip()
                    
                    # Skip comments and empty lines
                    if not line or line.startswith('#'):
                        continue
                    
                    # Check for command name [name]
                    if line.startswith('[') and line.endswith(']'):
                        # Save previous command if exists
                        if current_command and current_sequence:
                            sequences[current_command] = current_sequence
                        
                        # Start new command
                        current_command = line[1:-1].lower()
                        current_sequence = []
                        continue
                    
                    # Parse button and delay, or special commands
                    if line.upper().startswith('WAIT_FOR'):
                        # Parse: WAIT_FOR "text to match"
                        match = re.search(r'WAIT_FOR\s+"([^"]+)"', line, re.IGNORECASE)
                        if match:
                            wait_text = match.group(1)
                            current_sequence.append(('WAIT_FOR', wait_text))
                        else:
                            print(f"Warning: Invalid WAIT_FOR syntax in line: {line}")
                    elif line.upper().startswith('LOCATE_SHARE'):
                        # Parse: LOCATE_SHARE "share name"
                        match = re.search(r'LOCATE_SHARE\s+"([^"]+)"', line, re.IGNORECASE)
                        if match:
                            share_text = match.group(1)
                            current_sequence.append(('LOCATE_SHARE', share_text))
                        else:
                            print(f"Warning: Invalid LOCATE_SHARE syntax in line: {line}")
                    elif line.upper().strip() == 'TRANSFER_ALL':
                        current_sequence.append(('TRANSFER_ALL', None))
                    elif line.upper().strip() == 'DELETE_SOURCE_FILE':
                        current_sequence.append(('DELETE_SOURCE_FILE', None))
                    else:
                        parts = line.split()
                        if len(parts) >= 2:
                            button_name = parts[0].upper()
                            try:
                                delay = float(parts[1])
                                current_sequence.append((button_name, delay))
                            except ValueError:
                                print(f"Warning: Invalid delay in line: {line}")
                
                # Save last command
                if current_command and current_sequence:
                    sequences[current_command] = current_sequence
            
            print(f"Loaded {len(sequences)} navigation sequences from {self.nav_config}")
            return sequences
            
        except Exception as e:
            print(f"Error loading navigation config: {e}")
            return {}
    
    def wait_for_log_message(self, search_text: str, timeout_minutes: int = 5):
        """
        Wait for a specific message to appear in the log file.
        
        Args:
            search_text: Text to search for in log messages
            timeout_minutes: Maximum time to wait
        
        Returns:
            True if message found, False if timeout
        """
        log_path = self.get_log_file_path()
        if not log_path or not os.path.exists(log_path):
            print(f"Warning: Cannot monitor log file")
            return False
        
        print(f"Waiting for log message: '{search_text}'")
        
        # Get current position in log file
        with open(log_path, 'r') as f:
            f.seek(0, 2)  # Seek to end
            start_pos = f.tell()
        
        start_time = time.time()
        
        while (time.time() - start_time) < (timeout_minutes * 60):
            try:
                with open(log_path, 'r') as f:
                    f.seek(start_pos)
                    new_lines = f.readlines()
                    start_pos = f.tell()
                
                for line in new_lines:
                    if search_text in line:
                        print(f"✓ Found: {search_text}")
                        return True
                
                time.sleep(0.5)
                
            except Exception as e:
                print(f"Error reading log: {e}")
                time.sleep(1)
        
        print(f"✗ Timeout waiting for: {search_text}")
        return False
    
    def locate_share(self, share_name: str, max_attempts: int = 20):
        """
        Navigate through shares until the correct one is found by monitoring log.
        Performs DOWN+SELECT, checks log for Container query matching share name,
        backs out with LEFT if wrong, repeats until found.
        
        Also extracts the file count from "Found X files" log message.
        
        Args:
            share_name: Share name to search for (will match against Container= in log)
            max_attempts: Maximum number of shares to try
        
        Returns:
            Tuple of (found: bool, file_count: int or None)
        """
        log_path = self.get_log_file_path()
        if not log_path or not os.path.exists(log_path):
            print(f"Warning: Cannot monitor log file for share location")
            return (False, None)
        
        print(f"Locating share containing: '{share_name}'")
        
        for attempt in range(max_attempts):
            # Get current log position
            with open(log_path, 'r') as f:
                f.seek(0, 2)
                start_pos = f.tell()
            
            # Navigate: DOWN then SELECT
            print(f"  Attempt {attempt + 1}: DOWN")
            self.remote.press(TiVoButton.DOWN, delay=0.5)
            
            print(f"    SELECT (entering share)")
            self.remote.press(TiVoButton.SELECT, delay=1.5)
            
            # Check log for Container query with our share name and file count
            found = False
            file_count = None
            timeout = time.time() + 3  # 3 second timeout per attempt
            
            while time.time() < timeout:
                try:
                    with open(log_path, 'r') as f:
                        f.seek(start_pos)
                        new_lines = f.readlines()
                    
                    for line in new_lines:
                        # Look for: Container=Share%20Name or Container="Share Name"
                        if 'QueryContainer' in line and 'Container=' in line:
                            # Extract container name from URL-encoded or regular format
                            if share_name in line or share_name.replace(' ', '%20') in line:
                                found = True
                        
                        # Look for: Found X files, total=Y
                        if found and 'Found' in line and 'files' in line:
                            match = re.search(r'Found (\d+) files', line)
                            if match:
                                file_count = int(match.group(1))
                                print(f"✓ Found share: {share_name} ({file_count} files)")
                                return (True, file_count)
                    
                    if found and file_count is None:
                        # Found container but no file count yet, keep waiting
                        time.sleep(0.2)
                        continue
                    
                    time.sleep(0.2)
                except Exception as e:
                    print(f"Error reading log: {e}")
                    break
            
            # Wrong share, back out with LEFT and try next
            print(f"    Not the right share, pressing LEFT to back out...")
            self.remote.press(TiVoButton.LEFT, delay=1.0)
            # Continue to next iteration which will do DOWN + SELECT again
        
        print(f"✗ Share '{share_name}' not found after {max_attempts} attempts")
        return (False, None)
    
    def transfer_all_items(self, max_items: int = 50, expected_count: int = None):
        """
        Transfer all items in current share list.
        Loops through items, pressing SELECT twice on each, waiting for transfer to start.
        
        Args:
            max_items: Maximum number of items to transfer (fallback)
            expected_count: Expected number of files from log (if known)
        
        Returns:
            Number of items transferred
        """
        log_path = self.get_log_file_path()
        if not log_path or not os.path.exists(log_path):
            print(f"Warning: Cannot monitor log file for transfers")
            return 0
        
        # Use expected count if provided, otherwise use max_items
        items_to_transfer = expected_count if expected_count else max_items
        
        if expected_count:
            print(f"Transferring {expected_count} items from share...")
        else:
            print(f"Transferring all items in list (max {max_items})...")
        
        transferred = 0
        transfer_list = []
        started_transfers = []
        
        # Helper function to check for new transfers in log
        def check_for_transfers(start_pos):
            """Check log for 'Start sending' messages and report them."""
            try:
                with open(log_path, 'r') as f:
                    f.seek(start_pos)
                    new_lines = f.readlines()
                    new_pos = f.tell()
                
                for line in new_lines:
                    if 'Start sending' in line:
                        match = re.search(r'Start sending "([^"]+)"', line)
                        if match:
                            started_file = match.group(1)
                            if started_file not in started_transfers:
                                started_transfers.append(started_file)
                                print(f"\n    → Transfer started: {started_file}")
                
                return new_pos
            except Exception as e:
                return start_pos
        
        # Get initial log position
        with open(log_path, 'r') as f:
            f.seek(0, 2)
            log_pos = f.tell()
        
        for item_num in range(items_to_transfer):
            # Press SELECT to enter item details
            self.remote.press(TiVoButton.SELECT, delay=2.5)
            log_pos = check_for_transfers(log_pos)
            
            # Check log for AnchorItem to get filename
            filename = None
            timeout = time.time() + 3
            while time.time() < timeout and not filename:
                try:
                    with open(log_path, 'r') as f:
                        f.seek(log_pos)
                        new_lines = f.readlines()
                        log_pos = f.tell()
                    
                    for line in new_lines:
                        # Check for Start sending while looking for filename
                        if 'Start sending' in line:
                            match = re.search(r'Start sending "([^"]+)"', line)
                            if match:
                                started_file = match.group(1)
                                if started_file not in started_transfers:
                                    started_transfers.append(started_file)
                                    print(f"\n    → Transfer started: {started_file}")
                        
                        if 'AnchorItem=' in line:
                            # Extract: AnchorItem=%2FShare%2FFilename.mkv
                            match = re.search(r'AnchorItem=([^&\s]+)', line)
                            if match:
                                encoded = match.group(1)
                                # URL decode and extract just the filename
                                import urllib.parse
                                decoded = urllib.parse.unquote(encoded)
                                # Get just the filename (last part after /)
                                filename = decoded.split('/')[-1]
                                break
                    
                    if filename:
                        break
                    time.sleep(0.2)
                except Exception as e:
                    break
            
            # Display with filename if found
            if filename:
                print(f"  Item {item_num + 1}: {filename}")
                transfer_list.append(filename)
            else:
                print(f"  Item {item_num + 1}: ", end="")
            
            # Move DOWN to transfer option
            self.remote.press(TiVoButton.DOWN, delay=2.5)
            log_pos = check_for_transfers(log_pos)
            
            # Press SELECT to queue transfer
            self.remote.press(TiVoButton.SELECT, delay=2.5)
            log_pos = check_for_transfers(log_pos)
            
            if filename:
                print(f"    ✓ Queued: {filename}")
            else:
                print("✓ Queued")
            
            transferred += 1
            
            # Go back to list with LEFT
            self.remote.press(TiVoButton.LEFT, delay=2.5)
            log_pos = check_for_transfers(log_pos)
            
            # Move DOWN to next item
            self.remote.press(TiVoButton.DOWN, delay=2.5)
            log_pos = check_for_transfers(log_pos)
        
        print(f"\n{'=' * 60}")
        print(f"TRANSFER SUMMARY")
        print(f"{'=' * 60}")
        print(f"Total items queued: {transferred}")
        if transfer_list:
            print(f"\nQueued files:")
            for idx, item in enumerate(transfer_list, 1):
                print(f"  {idx}. {item}")
        print(f"\nTiVo will pull items sequentially from the queue.")
        print(f"{'=' * 60}\n")
        sys.stdout.flush()  # Ensure output is visible before monitoring starts
        
        # Return both count and the initial log position for monitoring
        return (transferred, log_pos)
    
    def monitor_all_transfers(self, expected_count: int, start_log_pos: int = None, timeout_minutes: int = 120):
        """
        Monitor log for all transfers to complete.
        Tracks 'Start sending' and 'Done sending' messages.
        
        Args:
            expected_count: Number of transfers to monitor
            timeout_minutes: Maximum time to wait
        
        Returns:
            List of transferred filenames in order of completion
        """
        log_path = self.get_log_file_path()
        if not log_path:
            print(f"ERROR: Cannot find pyTivo log file path")
            print(f"Make sure pyTivo is running and check config")
            return []
        
        if not os.path.exists(log_path):
            print(f"ERROR: Log file does not exist: {log_path}")
            print(f"Make sure pyTivo is running")
            return []
        
        print(f"Monitoring transfers (expecting {expected_count} files)...")
        print(f"Watching pyTivo log: {log_path}\n")
        sys.stdout.flush()
        
        # Use provided log position or get current position
        if start_log_pos is not None:
            start_pos = start_log_pos
        else:
            with open(log_path, 'r') as f:
                f.seek(0, 2)
                start_pos = f.tell()
        
        start_time = time.time()
        started_files = []
        completed_files = []
        
        while (time.time() - start_time) < (timeout_minutes * 60):
            try:
                with open(log_path, 'r') as f:
                    f.seek(start_pos)
                    new_lines = f.readlines()
                    start_pos = f.tell()
                
                for line in new_lines:
                    line = line.strip()
                    
                    # Track Start sending
                    if 'Start sending' in line:
                        match = re.search(r'Start sending "([^"]+)"', line)
                        if match:
                            filename = match.group(1)
                            if filename not in started_files:
                                started_files.append(filename)
                                # Show correct count for started files
                                print(f"  [{len(started_files)}/{expected_count}] Started: {filename}")
                                sys.stdout.flush()
                    
                    # Track Done sending (check separately, not elif)
                    if 'Done sending' in line:
                        match = re.search(r'Done sending "([^"]+)"', line)
                        if match:
                            filename = match.group(1)
                            if filename not in completed_files:
                                completed_files.append(filename)
                                elapsed = int(time.time() - start_time)
                                print(f"  [{len(completed_files)}/{expected_count}] ✓ Completed: {filename} (elapsed: {elapsed}s)")
                                sys.stdout.flush()
                
                # Check if all expected transfers are complete
                if len(completed_files) >= expected_count:
                    total_elapsed = int(time.time() - start_time)
                    print(f"\n✓ All {expected_count} transfers completed in {total_elapsed}s")
                    return completed_files
                
                time.sleep(1)
                
            except Exception as e:
                print(f"Error reading log: {e}")
                time.sleep(1)
        
        print(f"\n✗ Timeout: {len(completed_files)}/{expected_count} transfers completed")
        return completed_files
    
    def execute_sequence(self, command_name: str):
        """
        Execute a navigation sequence from config.
        
        Args:
            command_name: Name of the command to execute
        
        Returns:
            True if sequence executed, False if not found
        """
        command_name = command_name.lower()
        
        if command_name not in self.nav_sequences:
            print(f"Navigation sequence '{command_name}' not found in config")
            return False
        
        sequence = self.nav_sequences[command_name]
        print(f"Executing sequence: {command_name}")
        
        # Track file count from LOCATE_SHARE for use with TRANSFER_ALL
        file_count = None
        transferred_count = 0
        should_delete = False
        
        for idx, (button_name, param) in enumerate(sequence):
            # Handle special commands
            if button_name == 'WAIT_FOR':
                # param is the text to wait for
                if not self.wait_for_log_message(param):
                    print(f"Warning: Continuing despite timeout")
            elif button_name == 'LOCATE_SHARE':
                # param is the share name to find
                found, file_count = self.locate_share(param)
                if not found:
                    print(f"Warning: Could not locate share '{param}'")
            elif button_name == 'TRANSFER_ALL':
                # Transfer all items in current list, using file_count if available
                result = self.transfer_all_items(expected_count=file_count)
                
                # Unpack result (count, log_position)
                if isinstance(result, tuple):
                    transferred_count, log_start_pos = result
                else:
                    # Backward compatibility
                    transferred_count = result
                    log_start_pos = None
                
                # Check if next command is DELETE_SOURCE_FILE
                if idx + 1 < len(sequence) and sequence[idx + 1][0] == 'DELETE_SOURCE_FILE':
                    should_delete = True
                
                # Monitor all transfers if we have a count
                if transferred_count > 0:
                    completed_files = self.monitor_all_transfers(transferred_count, start_log_pos=log_start_pos)
                    
                    # Delete files if DELETE_SOURCE_FILE follows TRANSFER_ALL
                    if should_delete and completed_files:
                        print(f"\n{'=' * 60}")
                        print(f"DELETING TRANSFERRED FILES")
                        print(f"{'=' * 60}")
                        for filename in completed_files:
                            print(f"  Deleting: {filename}")
                            self.remove_file(filename)
                        print(f"{'=' * 60}\n")
            elif button_name == 'DELETE_SOURCE_FILE':
                # Skip if already handled after TRANSFER_ALL
                if not should_delete:
                    # Extract filename from last "Done sending" log message and delete it
                    log_path = self.get_log_file_path()
                    if log_path and os.path.exists(log_path):
                        try:
                            with open(log_path, 'r') as f:
                                lines = f.readlines()
                                for line in reversed(lines[-100:]):
                                    if 'Done sending' in line:
                                        match = re.search(r'Done sending "([^"]+)"', line)
                                        if match:
                                            filename = match.group(1)
                                            print(f"Deleting transferred file: {filename}")
                                            self.remove_file(filename)
                                            break
                        except Exception as e:
                            print(f"Error deleting source file: {e}")
                    else:
                        print("Warning: Cannot delete file - log not accessible")
                # Reset flag
                should_delete = False
            elif button_name == 'TOP':
                self.nav.jump_to_top()
            elif button_name == 'BOTTOM':
                self.nav.jump_to_bottom()
            elif button_name == 'TIVO':
                self.nav.go_home()
            else:
                # param is the delay
                # Get button from enum
                try:
                    button = TiVoButton[button_name]
                    self.remote.press(button, delay=param)
                except KeyError:
                    print(f"Warning: Unknown button '{button_name}'")
        
        return True
    
    def connect(self) -> bool:
        """Connect to TiVo."""
        return self.remote.connect()
    
    def disconnect(self):
        """Disconnect from TiVo."""
        self.remote.disconnect()
    
    def find_share_by_name(self, max_attempts: int = 30) -> bool:
        """
        Try to find pyTivo share by navigating through My Shows.
        
        This uses a simple strategy:
        1. Go to bottom of My Shows
        2. Navigate up looking for the share name (we can't see screen, so we guess)
        
        Args:
            max_attempts: Maximum navigation attempts
            
        Returns:
            True if we think we found it (really just completes navigation)
        """
        print("Looking for pyTivo share...")
        print("(Note: Can't verify visually - following navigation heuristics)")
        
        # In My Shows, external shares are typically at the bottom
        # Navigate down to bottom
        print("Navigating to bottom of My Shows...")
        for i in range(max_attempts):
            self.remote.press(TiVoButton.DOWN, delay=0.15)
        
        # Now navigate up a few to get to the shares
        # (bottom item might be settings or something)
        print("Moving up to shares...")
        for _ in range(5):
            self.remote.press(TiVoButton.UP, delay=0.3)
        
        print("Should be positioned near pyTivo shares")
        return True
    
    def manual_position_to_share(self):
        """
        Wait for user to manually position to the share.
        
        Returns when user presses Enter in the terminal.
        """
        print("\n" + "=" * 60)
        print("MANUAL POSITIONING REQUIRED")
        print("=" * 60)
        print("\nSteps:")
        print("1. Look at your TiVo screen")
        print("2. Verify you're in My Shows")
        print("3. Navigate to your pyTivo share")
        print("4. Highlight the share you want")
        print("5. Press Enter here when ready...")
        print("=" * 60)
        
        input("Press Enter when positioned on the share: ")
        print("Continuing automation...")
    
    def enter_share(self):
        """Enter the selected share."""
        print("Entering share...")
        self.remote.press(TiVoButton.SELECT, delay=1.5)
    
    def navigate_to_folder(self, folder_path: list):
        """
        Navigate through folder hierarchy.
        
        Args:
            folder_path: List of folder names to navigate through
        """
        for folder in folder_path:
            print(f"Entering folder: {folder}")
            # Assume we're at the right position and select
            self.remote.press(TiVoButton.SELECT, delay=1.0)
    
    def select_video_by_position(self, position: int = 0):
        """
        Select a video at a specific position in the current folder.
        
        Args:
            position: Position in list (0 = first video)
        """
        print(f"Navigating to video at position {position}...")
        
        # Navigate to the video
        for i in range(position):
            self.remote.press(TiVoButton.DOWN, delay=0.3)
        
        # Select to start transfer
        print("Starting transfer...")
        self.remote.press(TiVoButton.SELECT, delay=0.5)
        
        print("✓ Transfer initiated!")
        print("Check your TiVo to confirm transfer started.")
    
    def search_for_video(self, search_term: str):
        """
        Use keyboard search to find a video.
        
        Args:
            search_term: Text to search for
        """
        print(f"Searching for: {search_term}")
        
        # Go to search (varies by TiVo model)
        # This might not work on all models
        self.remote.press(TiVoButton.CLEAR, delay=0.5)
        self.remote.keyboard(search_term)
        self.remote.press(TiVoButton.ENTER, delay=1.0)
        
        print("Search submitted")
    
    def automated_transfer(self, video_position: int = 0, folder_path: list = None):
        """
        Attempt fully automated transfer.
        
        Args:
            video_position: Position of video in list
            folder_path: List of folders to navigate through (or None)
        """
        print("\nStarting automated transfer...")
        
        # Step 1: Go to My Shows
        print("\n1. Navigating to My Shows...")
        self.nav.go_to_my_shows()
        
        # Step 2: Find share (automatic attempt)
        print("\n2. Attempting to find share...")
        self.find_share_by_name()
        
        # Step 3: Manual verification (optional)
        if input("\nNeed manual positioning? (y/n): ").lower() == 'y':
            self.manual_position_to_share()
        
        # Step 4: Enter share
        print("\n3. Entering share...")
        self.enter_share()
        
        # Step 5: Navigate folders if specified
        if folder_path:
            print("\n4. Navigating folders...")
            self.navigate_to_folder(folder_path)
        
        # Step 6: Select video
        print("\n5. Selecting video...")
        self.select_video_by_position(video_position)
        
        print("\n✓ Automation complete!")
    
    def go_to_devices(self):
        """Navigate to TiVo Devices & Messages screen."""
        print("Navigating to Devices & Messages...")
        
        # Try to use config sequence first
        if self.execute_sequence('devices'):
            print("At Devices & Messages screen")
            return
        
        # Fall back to hardcoded sequence
        self.nav.go_home()
        self.remote.press(TiVoButton.SELECT, delay=0.5)
        self.remote.press(TiVoButton.LEFT, delay=0.5)
        self.nav.jump_to_bottom()
        self.remote.press(TiVoButton.RIGHT, delay=0.5)
        self.nav.jump_to_bottom()
        self.remote.press(TiVoButton.SELECT, delay=0.5)
        print("At Devices & Messages screen")
    
    def go_to_import(self):
        """Navigate to Import from pyTivo screen."""
        print("Navigating to Import from pyTivo...")
        
        # Try to use config sequence first
        if self.execute_sequence('import'):
            print("At Import from pyTivo screen")
            return
        
        # Fall back to hardcoded sequence
        self.go_to_devices()
        self.remote.press(TiVoButton.SELECT, delay=0.5)
        self.remote.press(TiVoButton.SELECT, delay=0.5)
        print("At Import from pyTivo screen")
    
    def get_pytivo_config_path(self):
        """Find pyTivo config file from running process."""
        try:
            # Get pytivo process with config file path
            result = subprocess.run(['ps', 'aux'], capture_output=True, text=True)
            for line in result.stdout.split('\n'):
                if 'pytivo' in line.lower() and '.conf' in line.lower():
                    # Look for -c flag followed by config path
                    match = re.search(r'-c\s+(\S+\.conf)', line)
                    if match:
                        return match.group(1)
        except Exception as e:
            print(f"Error finding config: {e}")
        return None
    
    def get_log_file_path(self):
        """Get log file path from pyTivo config."""
        config_path = self.get_pytivo_config_path()
        if not config_path:
            print("Could not find pyTivo config file from running process")
            return None
        
        print(f"Found config: {config_path}")
        
        try:
            with open(config_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('log_file'):
                        # Parse: log_file = /path/to/log
                        match = re.search(r'log_file\s*=\s*(.+)', line)
                        if match:
                            log_path = match.group(1).strip()
                            print(f"Found log file: {log_path}")
                            return log_path
        except Exception as e:
            print(f"Error reading config: {e}")
        
        return None
    
    def monitor_transfer(self, timeout_minutes=30, remove_after=False):
        """
        Monitor log file for transfer completion.
        
        Args:
            timeout_minutes: Maximum time to wait for transfer
            remove_after: If True, remove file from config after successful transfer
        
        Returns:
            Tuple of (success: bool, transferred_file: str or None)
        """
        log_path = self.get_log_file_path()
        if not log_path:
            print("Cannot monitor transfer - log file not found")
            return (False, None)
        
        if not os.path.exists(log_path):
            print(f"Log file does not exist: {log_path}")
            return (False, None)
        
        print(f"\nMonitoring log file: {log_path}")
        print("Waiting for 'Start sending' message...")
        
        # Get current position in log file
        with open(log_path, 'r') as f:
            f.seek(0, 2)  # Seek to end
            start_pos = f.tell()
        
        start_time = time.time()
        transfer_started = False
        last_progress_time = start_time
        transferred_file = None
        
        while (time.time() - start_time) < (timeout_minutes * 60):
            try:
                with open(log_path, 'r') as f:
                    f.seek(start_pos)
                    new_lines = f.readlines()
                    start_pos = f.tell()
                
                for line in new_lines:
                    line = line.strip()
                    
                    # Check for start of transfer
                    if 'Start sending' in line:
                        transfer_started = True
                        print(f"\n✓ Transfer started!")
                        print(f"  {line}")
                        # Extract filename: Start sending "filename" to ...
                        match = re.search(r'Start sending "([^"]+)"', line)
                        if match:
                            transferred_file = match.group(1)
                        last_progress_time = time.time()
                    
                    # Check for completion
                    elif 'Done sending' in line:
                        print(f"\n✓ Transfer completed!")
                        print(f"  {line}")
                        # Also try to extract filename from Done message if we don't have it
                        if not transferred_file:
                            match = re.search(r'Done sending "([^"]+)"', line)
                            if match:
                                transferred_file = match.group(1)
                        
                        # Remove file if requested
                        if remove_after and transferred_file:
                            self.remove_file(transferred_file)
                        
                        return (True, transferred_file)
                    
                    # Show other relevant messages
                    elif transfer_started and ('Mb/s' in line or 'bytes' in line):
                        # Progress indicator
                        elapsed = int(time.time() - last_progress_time)
                        if elapsed >= 10:  # Show update every 10 seconds
                            print(f"  Transfer in progress... ({elapsed}s)")
                            last_progress_time = time.time()
                
                time.sleep(1)
                
            except Exception as e:
                print(f"Error reading log: {e}")
                time.sleep(1)
        
        print(f"\n✗ Timeout after {timeout_minutes} minutes")
        return (False, None)
    
    def remove_file(self, filename):
        """
        Delete the transferred file from the filesystem.
        
        Args:
            filename: Full path or basename of the file to remove
        """
        print(f"\nDeleting file from filesystem...")
        
        # If filename is already a full path and exists, delete it directly
        if os.path.isabs(filename) and os.path.exists(filename):
            try:
                os.remove(filename)
                print(f"  ✓ Deleted: {filename}")
                return True
            except Exception as e:
                print(f"  ✗ Error deleting file: {e}")
                return False
        
        # Otherwise, need config to find the file
        config_path = self.get_pytivo_config_path()
        if not config_path:
            print(f"Cannot find file - config not found")
            return False
        
        try:
            with open(config_path, 'r') as f:
                lines = f.readlines()
            
            # Find [tivo-importer] section and locate matching file path
            in_importer_section = False
            file_to_delete = None
            basename = os.path.basename(filename)
            
            for line in lines:
                stripped = line.strip()
                
                # Track which section we're in
                if stripped.startswith('['):
                    in_importer_section = (stripped.lower() == '[tivo-importer]')
                    continue
                
                # If we're in tivo-importer and line contains path setting
                if in_importer_section and stripped.startswith('path'):
                    # Parse: path = /some/path
                    match = re.search(r'path\s*=\s*(.+)', stripped)
                    if match:
                        file_path = match.group(1).strip()
                        # Check if this path ends with our filename
                        if os.path.basename(file_path) == basename:
                            file_to_delete = file_path
                            break
            
            if file_to_delete:
                if os.path.exists(file_to_delete):
                    os.remove(file_to_delete)
                    print(f"✓ Successfully deleted: {file_to_delete}")
                    return True
                else:
                    print(f"File not found on filesystem: {file_to_delete}")
                    return False
            else:
                print(f"File '{basename}' not found in [tivo-importer] section")
                return False
                
        except Exception as e:
            print(f"Error deleting file: {e}")
            return False
    
    def interactive_mode(self):
        """Interactive mode - manual control with commands."""
        print("\n" + "=" * 60)
        print("INTERACTIVE MODE")
        print("=" * 60)
        print("\nCommands:")
        print("  u/d/l/r    - Up/Down/Left/Right")
        print("  s          - Select")
        print("  h          - Home (TiVo button)")
        print("  m          - My Shows")
        print("  devices    - Go to Devices & Messages")
        print("  import     - Go to Import from pyTivo (devices + select)")
        print("  import-wait - Go to Import and monitor for transfer completion")
        print("  import-wait-remove - Same as import-wait, then remove file")
        print("  b          - Back")
        print("  p          - Play")
        print("  i          - Info")
        print("  top        - Jump to top of list")
        print("  bottom     - Jump to bottom of list")
        print("  search <text> - Keyboard search")
        print("  pos <n>    - Select video at position n")
        print("  list       - List available sequences from config")
        print("  reload     - Reload navigation config file")
        print("  q          - Quit")
        
        # Show available sequences from config
        if self.nav_sequences:
            print("\nSequences from config:")
            for seq_name in sorted(self.nav_sequences.keys()):
                print(f"  {seq_name}")
        
        print("=" * 60)
        
        while True:
            cmd = input("\nCommand: ").strip().lower()
            
            if cmd == 'q':
                break
            elif cmd == 'u':
                self.remote.press(TiVoButton.UP)
            elif cmd == 'd':
                self.remote.press(TiVoButton.DOWN)
            elif cmd == 'l':
                self.remote.press(TiVoButton.LEFT)
            elif cmd == 'r':
                self.remote.press(TiVoButton.RIGHT)
            elif cmd == 's':
                self.remote.press(TiVoButton.SELECT)
            elif cmd == 'h':
                self.nav.go_home()
            elif cmd == 'm':
                self.nav.go_to_my_shows()
            elif cmd in self.nav_sequences:
                # Execute sequence from config file
                if not self.execute_sequence(cmd):
                    print(f"✗ Failed to execute sequence: {cmd}")
            elif cmd == 'b':
                self.remote.press(TiVoButton.LEFT)  # Back is often LEFT
            elif cmd == 'p':
                self.remote.press(TiVoButton.PLAY)
            elif cmd == 'i':
                self.remote.press(TiVoButton.INFO)
            elif cmd == 'top':
                self.nav.jump_to_top()
                print("Jumped to top of list")
            elif cmd == 'bottom':
                self.nav.jump_to_bottom()
                print("Jumped to bottom of list")
            elif cmd.startswith('search '):
                search_term = cmd[7:]
                self.search_for_video(search_term)
            elif cmd.startswith('pos '):
                try:
                    pos = int(cmd[4:])
                    self.select_video_by_position(pos)
                except ValueError:
                    print("Invalid position number")
            elif cmd == 'list':
                # List available sequences
                if self.nav_sequences:
                    print("\nAvailable sequences:")
                    for seq_name in sorted(self.nav_sequences.keys()):
                        print(f"  {seq_name}")
                else:
                    print("No sequences loaded from config")
            elif cmd == 'reload':
                # Reload navigation config
                self.nav_sequences = self.load_navigation_config()
                print("Navigation config reloaded")
            else:
                print(f"Unknown command: {cmd}")


def main():
    parser = argparse.ArgumentParser(
        description="Automate pyTivo video transfers to TiVo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive mode (manual control)
  python pytivo_transfer.py 192.168.1.185
  
  # Execute a sequence from config
  python pytivo_transfer.py 192.168.1.185 watcher
  python pytivo_transfer.py 192.168.1.185 import-wait-remove
  
  # Automated transfer (first video in share)
  python pytivo_transfer.py 192.168.1.185 --auto --position 0
  
  # Transfer video at position 3
  python pytivo_transfer.py 192.168.1.185 --auto --position 3

Note: Automated mode is fragile and may need customization for your menu layout.
      Interactive mode is recommended for initial testing.
        """
    )
    
    parser.add_argument("tivo_ip", help="TiVo IP address")
    parser.add_argument("sequence", nargs="?", help="Optional: sequence name to execute from config")
    parser.add_argument("--auto", action="store_true", 
                       help="Attempt automated transfer (vs interactive mode)")
    parser.add_argument("--position", type=int, default=0,
                       help="Video position in list (0 = first)")
    parser.add_argument("--folders", nargs="*",
                       help="Folder path to navigate through")
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("pyTivo Transfer Automation")
    print("=" * 60)
    print(f"\nTiVo: {args.tivo_ip}")
    
    automation = PyTivoAutomation(args.tivo_ip)
    
    if not automation.connect():
        print("\n✗ Failed to connect to TiVo!")
        print("Make sure Network Remote Control is enabled.")
        return 1
    
    print("✓ Connected to TiVo")
    
    try:
        if args.sequence:
            # Execute specified sequence and exit
            if not automation.execute_sequence(args.sequence):
                print(f"\n✗ Failed to execute sequence: {args.sequence}")
                return 1
            print(f"\n✓ Sequence '{args.sequence}' completed")
        elif args.auto:
            automation.automated_transfer(args.position, args.folders)
        else:
            automation.interactive_mode()
    finally:
        automation.disconnect()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
