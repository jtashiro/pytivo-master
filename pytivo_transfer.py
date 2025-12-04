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
import smtplib
import urllib.parse
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
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
        self.transfer_list = []  # Track files with status: [{filename, status}, ...]
        self.tivo_host = tivo_host
        self.transfer_start_time = None
        self.transfer_end_time = None
        
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
    
    def _find_pytivo_config(self):
        """Find pyTivo.conf in standard locations."""
        search_paths = [
            '/usr/local/etc/pytivo.conf',  # Primary system install (lowercase)
            '/usr/local/etc/pyTivo.conf',  # Primary system install (capitalized)
            '/etc/pytivo.conf',  # System config (lowercase)
            '/etc/pyTivo.conf',  # System config (capitalized)
            'pyTivo.conf',  # Current directory
            os.path.join(os.path.dirname(__file__), 'pyTivo.conf'),  # Same dir as script
            os.path.expanduser('~/.config/pytivo/pytivo.conf'),  # User config
            os.path.expanduser('~/.pytivo/pytivo.conf'),  # User config alt
        ]
        
        for path in search_paths:
            if os.path.exists(path):
                return path
        
        return None
    
    def get_pytivo_shares(self):
        """
        Read pyTivo.conf and extract share names.
        
        Returns:
            List of share names (section names that have type=video)
        """
        config_path = self._find_pytivo_config()
        if not config_path:
            return []
        
        shares = []
        try:
            import configparser
            config = configparser.ConfigParser()
            config.read(config_path)
            
            for section in config.sections():
                # Skip special sections
                if section.lower() in ['server', 'togo'] or section.startswith('_tivo'):
                    continue
                
                # Check if it's a video share
                if config.has_option(section, 'type'):
                    share_type = config.get(section, 'type').lower()
                    if share_type == 'video':
                        shares.append(section)
        except Exception as e:
            print(f"Warning: Could not read pyTivo config: {e}")
        
        return shares
    
    def get_share_by_path(self, path: str):
        """
        Find share name by matching its path in pyTivo.conf.
        
        Args:
            path: Directory path to match against share paths
        
        Returns:
            Share name if found, None otherwise
        """
        config_path = self._find_pytivo_config()
        if not config_path:
            return None
        
        # Normalize the search path
        search_path = os.path.abspath(os.path.expanduser(path)).rstrip('/')
        
        try:
            import configparser
            config = configparser.ConfigParser()
            config.read(config_path)
            
            for section in config.sections():
                # Skip special sections
                if section.lower() in ['server', 'togo'] or section.startswith('_tivo'):
                    continue
                
                # Check if it's a video share with matching path
                if config.has_option(section, 'type') and config.has_option(section, 'path'):
                    share_type = config.get(section, 'type').lower()
                    if share_type == 'video':
                        share_path = os.path.abspath(os.path.expanduser(config.get(section, 'path'))).rstrip('/')
                        if share_path == search_path:
                            return section
        except Exception as e:
            print(f"Warning: Could not read pyTivo config: {e}")
        
        return None
        
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
                        # Parse: LOCATE_SHARE "share name" (supports ${VAR} or $VAR expansion)
                        match = re.search(r'LOCATE_SHARE\s+"([^"]+)"', line, re.IGNORECASE)
                        if match:
                            share_text = match.group(1)
                            # Expand environment variables in share name
                            # Supports both ${VAR} and $VAR syntax
                            import string
                            share_text = os.path.expandvars(share_text)
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
            
            # Don't print during initialization - only in interactive/verbose mode
            # print(f"Loaded {len(sequences)} navigation sequences from {self.nav_config}")
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
    
    def wait_for_stable_files(self, share_path, timeout=60):
        """Wait for all files in directory to have stable sizes. Handles symlinks."""
        if not os.path.exists(share_path):
            return True
        
        print(f"Checking if files are stable (not being copied)...")
        start_time = time.time()
        
        while (time.time() - start_time) < timeout:
            try:
                # Get all video files (including symlinks)
                all_entries = os.listdir(share_path)
                files = []
                symlinks = []
                for f in all_entries:
                    full_path = os.path.join(share_path, f)
                    # Check if it's a video file extension
                    if f.lower().endswith(('.mkv', '.mp4', '.avi', '.mpg', '.mpeg', '.ts')):
                        # Check symlink first (before isfile, as isfile may return False for broken symlinks)
                        if os.path.islink(full_path):
                            symlinks.append(f)
                            files.append(f)
                        elif os.path.isfile(full_path):
                            files.append(f)
                
                if symlinks:
                    print(f"  Found {len(symlinks)} symlink(s): {', '.join(symlinks)}")
                
                if not files:
                    return True
                
                # For symlinks, check the target file size; for regular files, check directly
                sizes1 = {}
                for f in files:
                    try:
                        full_path = os.path.join(share_path, f)
                        # os.path.getsize follows symlinks automatically
                        sizes1[f] = os.path.getsize(full_path)
                    except:
                        pass
                
                time.sleep(2)
                
                sizes2 = {}
                for f in files:
                    try:
                        full_path = os.path.join(share_path, f)
                        sizes2[f] = os.path.getsize(full_path)
                    except:
                        pass
                
                all_stable = all(sizes1.get(f) == sizes2.get(f) for f in files if f in sizes1 and f in sizes2)
                if all_stable:
                    print(f"  ✓ All files stable")
                    return True
                
                for f in files:
                    if sizes1.get(f) != sizes2.get(f):
                        print(f"  Waiting for {f} to finish copying...")
                        break
            except Exception as e:
                print(f"  Note: {e}")
                return True
        
        print(f"  ⚠ Timeout waiting for stable files, proceeding anyway")
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
        # Wait for files to be stable before navigating
        config_path = self.get_pytivo_config_path()
        if config_path:
            try:
                with open(config_path, 'r') as f:
                    in_section = False
                    for line in f:
                        stripped = line.strip()
                        if stripped.startswith('['):
                            section = stripped[1:-1]
                            in_section = share_name.lower() in section.lower()
                        elif in_section and stripped.lower().startswith('path'):
                            match = re.search(r'path\s*=\s*(.+)', stripped, re.IGNORECASE)
                            if match:
                                self.wait_for_stable_files(match.group(1).strip())
                                break
            except:
                pass
        
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
                            # Debug: Extract and display the actual container name from the log
                            container_match = re.search(r'Container=([^&\s]+)', line)
                            if container_match:
                                container_encoded = container_match.group(1)
                                container_decoded = urllib.parse.unquote(container_encoded)
                                print(f"    Log shows container: '{container_decoded}'")
                            
                            # Extract container name from URL-encoded or regular format
                            if share_name in line or share_name.replace(' ', '%20') in line:
                                found = True
                                print(f"    ✓ Match! Looking for file count...")
                        
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
        Loops through items, pressing SELECT twice on each, queuing transfers.
        
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
        
        # Wait for all files in share to be stable before starting
        config_path = self.get_pytivo_config_path()
        if config_path:
            try:
                with open(config_path, 'r') as f:
                    lines = f.readlines()
                
                # Find all share sections and check their paths
                for i, line in enumerate(lines):
                    stripped = line.strip()
                    if stripped.startswith('[') and stripped.endswith(']'):
                        section = stripped[1:-1]
                        if section not in ['_tivo_SD', '_tivo_HD', 'Server']:
                            # Look for path in this section
                            for j in range(i+1, len(lines)):
                                check_line = lines[j].strip()
                                if check_line.startswith('['):
                                    break
                                if check_line.lower().startswith('path'):
                                    match = re.search(r'path\s*=\s*(.+)', check_line, re.IGNORECASE)
                                    if match:
                                        share_path = match.group(1).strip()
                                        self.wait_for_stable_files(share_path, timeout=120)
                                    break
            except Exception as e:
                print(f"Note: Could not check file stability: {e}")
        
        transferred = 0
        self.transfer_list = []  # Reset transfer list
        
        # Get initial log position BEFORE any SELECT presses
        with open(log_path, 'r') as f:
            f.seek(0, 2)
            initial_log_pos = f.tell()
        
        for item_num in range(items_to_transfer):
            print(f"  Item {item_num + 1}: ", end="")
            sys.stdout.flush()
            
            # Get current log position before this item
            with open(log_path, 'r') as f:
                f.seek(0, 2)
                item_log_pos = f.tell()
            
            # Press SELECT to enter item details
            self.remote.press(TiVoButton.SELECT, delay=2.5)
            
            # Get filename from log - look for GET request with File= parameter
            filename = None
            import urllib.parse
            try:
                time.sleep(0.5)  # Let log entry appear
                with open(log_path, 'r') as f:
                    f.seek(initial_log_pos)
                    new_lines = f.readlines()
                
                # Look backwards from most recent for File= parameter in GET request
                for line in reversed(new_lines):
                    if 'GET' in line and 'File=' in line:
                        match = re.search(r'File=([^&\s]+)', line)
                        if match:
                            encoded = match.group(1)
                            decoded = urllib.parse.unquote(encoded)
                            filename = decoded.lstrip('/').split('/')[-1]
                            break
            except Exception as e:
                pass
            
            if filename:
                # Check for duplicate
                is_duplicate = any(item['filename'] == filename for item in self.transfer_list)
                if is_duplicate:
                    print(f"{filename} (DUPLICATE - skipping)")
                    sys.stdout.flush()
                    # Skip this item - press LEFT twice to back out and move to next
                    self.remote.press(TiVoButton.LEFT, delay=0.5)
                    self.remote.press(TiVoButton.DOWN, delay=0.5)
                    continue
                else:
                    print(f"{filename}")
                    self.transfer_list.append({'filename': filename, 'status': 'queued'})
            else:
                print("(filename not detected)")
                self.transfer_list.append({'filename': f'Item {item_num + 1}', 'status': 'queued'})
            sys.stdout.flush()
            
            # Move DOWN to transfer option
            self.remote.press(TiVoButton.DOWN, delay=2.5)
            
            # Check for Start sending before SELECT
            try:
                with open(log_path, 'r') as f:
                    f.seek(item_log_pos)
                    check_lines = f.readlines()
                for line in check_lines:
                    if 'Start sending' in line:
                        match = re.search(r'Start sending "([^"]+)"', line)
                        if match:
                            print(f"    → Transfer started: {os.path.basename(match.group(1))}")
                            sys.stdout.flush()
            except:
                pass
            
            # Press SELECT to queue transfer
            self.remote.press(TiVoButton.SELECT, delay=2.5)
            
            print(f"    ✓ Queued")
            sys.stdout.flush()
            
            transferred += 1
            
            # Go back to list with LEFT
            self.remote.press(TiVoButton.LEFT, delay=2.5)
            
            # Check for Start sending after LEFT
            try:
                with open(log_path, 'r') as f:
                    f.seek(item_log_pos)
                    check_lines = f.readlines()
                for line in check_lines:
                    if 'Start sending' in line:
                        match = re.search(r'Start sending "([^"]+)"', line)
                        if match:
                            print(f"    → Transfer started: {os.path.basename(match.group(1))}")
                            sys.stdout.flush()
            except:
                pass
            
            # Move DOWN to next item
            self.remote.press(TiVoButton.DOWN, delay=2.5)
        
        # Check log for any transfers that started during queueing
        try:
            with open(log_path, 'r') as f:
                f.seek(initial_log_pos)
                all_lines = f.readlines()
            
            for line in all_lines:
                if 'Start sending' in line:
                    match = re.search(r'Start sending "([^"]+)"', line)
                    if match:
                        full_path = match.group(1)
                        started_filename = os.path.basename(full_path)
                        print(f"  → Transfer started: {started_filename}")
                        sys.stdout.flush()
                        # Update status in transfer_list
                        for item in self.transfer_list:
                            if started_filename in item['filename'] and item['status'] == 'queued':
                                item['status'] = 'in-progress'
                                break
        except:
            pass
        
        print(f"\n{'=' * 60}")
        print(f"TRANSFER SUMMARY")
        print(f"{'=' * 60}")
        print(f"Total items queued: {transferred}")
        print(f"\nFiles to transfer:")
        for idx, item in enumerate(self.transfer_list, 1):
            print(f"  {idx}. {item['filename']} [{item['status']}]")
        
        print(f"\nTiVo will pull items sequentially from the queue.")
        print(f"{'=' * 60}\n")
        sys.stdout.flush()
        
        # Return count and initial log position so monitoring can check for completions during queueing
        return (transferred, initial_log_pos)
    
    def monitor_all_transfers(self, expected_count: int, queueing_start_pos: int = None, timeout_minutes: int = 120):
        """
        Monitor log for all transfers to complete.
        Updates self.transfer_list status as files complete.
        
        Args:
            expected_count: Number of transfers to monitor
            queueing_start_pos: Log position from start of queueing (to catch early completions)
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
        
        # Check for completions that happened during queueing
        completed_count = 0
        if queueing_start_pos is not None:
            try:
                with open(log_path, 'r') as f:
                    f.seek(queueing_start_pos)
                    historical_lines = f.readlines()
                
                # Scan for Done sending messages that occurred during queueing
                for line in historical_lines:
                    if 'Done sending' in line:
                        match = re.search(r'Done sending "([^"]+)"', line)
                        if match:
                            full_path = match.group(1)
                            completed_filename = os.path.basename(full_path)
                            
                            # Find and update in transfer_list
                            for item in self.transfer_list:
                                if item['status'] != 'completed' and completed_filename in item['filename']:
                                    item['status'] = 'completed'
                                    completed_count += 1
                                    
                                    # Extract elapsed time if present
                                    elapsed_match = re.search(r'\((\d+)s\)', line)
                                    elapsed = elapsed_match.group(1) if elapsed_match else "?"
                                    print(f"  [{completed_count}/{expected_count}] ✓ Completed: {item['filename']} (elapsed: {elapsed}s)")
                                    sys.stdout.flush()
                                    break
            except Exception as e:
                print(f"Warning: Error checking for early completions: {e}")
        
        # Get current log position to continue monitoring from NOW
        with open(log_path, 'r') as f:
            f.seek(0, 2)
            start_pos = f.tell()
        
        start_time = time.time()
        
        # Monitor for Start sending and Done sending messages and update transfer_list
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
                            full_path = match.group(1)
                            started_filename = os.path.basename(full_path)
                            
                            # Find in transfer_list and update status
                            for item in self.transfer_list:
                                if item['status'] not in ['in-progress', 'completed'] and started_filename in item['filename']:
                                    item['status'] = 'in-progress'
                                    print(f"  → Transfer started: {item['filename']}")
                                    sys.stdout.flush()
                                    break
                    
                    # Track Done sending
                    if 'Done sending' in line:
                        match = re.search(r'Done sending "([^"]+)"', line)
                        if match:
                            full_path = match.group(1)
                            completed_filename = os.path.basename(full_path)
                            
                            # Find and update in transfer_list
                            for item in self.transfer_list:
                                if item['status'] != 'completed' and completed_filename in item['filename']:
                                    item['status'] = 'completed'
                                    completed_count += 1
                                    
                                    # Extract elapsed time if present
                                    elapsed_match = re.search(r'\((\d+)s\)', line)
                                    elapsed = elapsed_match.group(1) if elapsed_match else "?"
                                    print(f"  [{completed_count}/{expected_count}] ✓ Completed: {item['filename']} (elapsed: {elapsed}s)")
                                    sys.stdout.flush()
                                    break
                
                # Check if all expected transfers are complete
                if completed_count >= expected_count:
                    total_elapsed = int(time.time() - start_time)
                    print(f"\n✓ All {expected_count} transfers completed in {total_elapsed}s")
                    print(f"\nFinal status:")
                    for idx, item in enumerate(self.transfer_list, 1):
                        print(f"  {idx}. {item['filename']} [{item['status']}]")
                    sys.stdout.flush()
                    return [item['filename'] for item in self.transfer_list if item['status'] == 'completed']
                
                time.sleep(1)
                
            except Exception as e:
                print(f"Error reading log: {e}")
                time.sleep(1)
        
        print(f"\n✗ Timeout: {completed_count}/{expected_count} transfers completed")
        return [item['filename'] for item in self.transfer_list if item['status'] == 'completed']
    
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
        print(f"DEBUG: Sequence has {len(sequence)} commands")
        
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
                self.transfer_start_time = time.time()
                
                result = self.transfer_all_items(expected_count=file_count)
                
                # Unpack result
                if isinstance(result, tuple):
                    transferred_count, queueing_start_pos = result
                else:
                    transferred_count = result
                    queueing_start_pos = None
                
                # Check if next command is DELETE_SOURCE_FILE
                if idx + 1 < len(sequence) and sequence[idx + 1][0] == 'DELETE_SOURCE_FILE':
                    should_delete = True
                
                # Monitor all transfers if we have a count
                if transferred_count > 0:
                    print(f"\nDEBUG: About to monitor {transferred_count} transfers")
                    try:
                        completed_files = self.monitor_all_transfers(transferred_count, queueing_start_pos)
                        self.transfer_end_time = time.time()
                        
                        print(f"\nDEBUG: Monitoring complete, calling send_email_notification(success=True)")
                        print(f"DEBUG: Completed files: {completed_files}")
                        
                        # Send success email
                        self.send_email_notification(success=True)
                        
                        print(f"DEBUG: send_email_notification returned")
                    except Exception as e:
                        self.transfer_end_time = time.time()
                        print(f"\nDEBUG: Exception in monitoring: {e}")
                        print(f"DEBUG: Calling send_email_notification(success=False)")
                        
                        # Send failure email
                        self.send_email_notification(success=False, error_message=str(e))
                        raise
                else:
                    print(f"\nDEBUG: transferred_count is {transferred_count}, skipping monitoring")
                    
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
        If file is a symlink, only removes the symlink (not the target).
        Searches through all share sections in pyTivo config to find the file.
        
        Args:
            filename: Full path or basename of the file to remove
        """
        print(f"\nDeleting file from filesystem...")
        
        # If filename is already a full path and exists, delete it directly
        if os.path.isabs(filename) and os.path.exists(filename):
            try:
                if os.path.islink(filename):
                    os.unlink(filename)  # Remove symlink only
                    print(f"  ✓ Deleted symlink: {filename}")
                else:
                    os.remove(filename)  # Remove regular file
                    print(f"  ✓ Deleted: {filename}")
                return True
            except Exception as e:
                print(f"  ✗ Error deleting file: {e}")
                return False
        
        # Otherwise, search all share sections for the file
        config_path = self.get_pytivo_config_path()
        if not config_path:
            print(f"Cannot find file - config not found")
            return False
        
        try:
            with open(config_path, 'r') as f:
                lines = f.readlines()
            
            # Find all share sections and their paths
            current_section = None
            basename = os.path.basename(filename)
            
            for line in lines:
                stripped = line.strip()
                
                # Track section headers
                if stripped.startswith('[') and stripped.endswith(']'):
                    current_section = stripped[1:-1]
                    continue
                
                # Skip non-share sections
                if not current_section or current_section in ['_tivo_SD', '_tivo_HD', 'Server']:
                    continue
                
                # Look for path= in share sections
                if stripped.lower().startswith('path'):
                    match = re.search(r'path\s*=\s*(.+)', stripped, re.IGNORECASE)
                    if match:
                        share_path = match.group(1).strip()
                        # Try to find file in this share
                        potential_file = os.path.join(share_path, basename)
                        if os.path.exists(potential_file):
                            try:
                                if os.path.islink(potential_file):
                                    os.unlink(potential_file)  # Remove symlink only
                                    print(f"  ✓ Deleted symlink from [{current_section}]: {potential_file}")
                                else:
                                    os.remove(potential_file)  # Remove regular file
                                    print(f"  ✓ Deleted from [{current_section}]: {potential_file}")
                                return True
                            except Exception as e:
                                print(f"  ✗ Error deleting file: {e}")
                                return False
            
            print(f"  ✗ File '{basename}' not found in any share directories")
            return False
                
        except Exception as e:
            print(f"  ✗ Error deleting file: {e}")
            return False
    
    def send_email_notification(self, success: bool, error_message: str = None):
        """
        Send HTML email notification about transfer results.
        
        Args:
            success: True if transfers completed, False if failed
            error_message: Optional error message for failures
        """
        print("\n" + "=" * 60)
        print("EMAIL NOTIFICATION DEBUG")
        print("=" * 60)
        
        # Get email configuration from environment variables
        smtp_server = os.environ.get('SMTP_SERVER', 'localhost')
        smtp_port = int(os.environ.get('SMTP_PORT', '25'))
        smtp_user = os.environ.get('SMTP_USER')
        smtp_pass = os.environ.get('SMTP_PASS')
        from_email = os.environ.get('FROM_EMAIL', 'pytivo@localhost')
        to_email = os.environ.get('TO_EMAIL')
        
        print(f"SMTP Server: {smtp_server}:{smtp_port}")
        print(f"From: {from_email}")
        print(f"To: {to_email}")
        print(f"Auth: {'Yes' if smtp_user else 'No'}")
        print(f"Success: {success}")
        print(f"Error Message: {error_message}")
        print(f"Transfer Start Time: {self.transfer_start_time}")
        print(f"Transfer End Time: {self.transfer_end_time}")
        print(f"Transfer List Length: {len(self.transfer_list)}")
        
        if not to_email:
            print("✗ TO_EMAIL not set, skipping email notification")
            print("=" * 60)
            return
        
        print("✓ TO_EMAIL is set, proceeding with email...")
        
        # Calculate duration
        duration = ""
        if self.transfer_start_time and self.transfer_end_time:
            elapsed = int(self.transfer_end_time - self.transfer_start_time)
            minutes, seconds = divmod(elapsed, 60)
            hours, minutes = divmod(minutes, 60)
            if hours > 0:
                duration = f"{hours}h {minutes}m {seconds}s"
            elif minutes > 0:
                duration = f"{minutes}m {seconds}s"
            else:
                duration = f"{seconds}s"
        
        # Build email
        msg = MIMEMultipart('alternative')
        
        if success:
            completed_files = [f for f in self.transfer_list if f['status'] == 'completed']
            msg['Subject'] = f"✓ PyTivo Transfer Complete - {len(completed_files)} file(s)"
            
            # HTML body
            html = f"""
            <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 20px; }}
                    h2 {{ color: #28a745; }}
                    table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
                    th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
                    th {{ background-color: #28a745; color: white; }}
                    tr:hover {{ background-color: #f5f5f5; }}
                    .info {{ background-color: #f0f0f0; padding: 10px; border-radius: 5px; margin: 10px 0; }}
                    .success {{ color: #28a745; font-weight: bold; }}
                    .failed {{ color: #dc3545; font-weight: bold; }}
                </style>
            </head>
            <body>
                <h2>✓ PyTivo Transfer Completed Successfully</h2>
                
                <div class="info">
                    <strong>TiVo:</strong> {self.tivo_host}<br>
                    <strong>Date:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}<br>
                    <strong>Duration:</strong> {duration}<br>
                    <strong>Files Transferred:</strong> {len(completed_files)} of {len(self.transfer_list)}
                </div>
                
                <h3>Transfer Details:</h3>
                <table>
                    <tr>
                        <th>#</th>
                        <th>Filename</th>
                        <th>Status</th>
                    </tr>
            """
            
            for idx, item in enumerate(self.transfer_list, 1):
                status_class = "success" if item['status'] == 'completed' else "failed"
                status_text = "✓ Completed" if item['status'] == 'completed' else "✗ " + item['status']
                html += f"""
                    <tr>
                        <td>{idx}</td>
                        <td>{item['filename']}</td>
                        <td class="{status_class}">{status_text}</td>
                    </tr>
                """
            
            html += """
                </table>
            </body>
            </html>
            """
        else:
            msg['Subject'] = f"✗ PyTivo Transfer Failed"
            
            # HTML body for failure
            html = f"""
            <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 20px; }}
                    h2 {{ color: #dc3545; }}
                    .info {{ background-color: #f0f0f0; padding: 10px; border-radius: 5px; margin: 10px 0; }}
                    .error {{ background-color: #f8d7da; color: #721c24; padding: 15px; border-radius: 5px; margin: 10px 0; }}
                    table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
                    th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
                    th {{ background-color: #dc3545; color: white; }}
                </style>
            </head>
            <body>
                <h2>✗ PyTivo Transfer Failed</h2>
                
                <div class="info">
                    <strong>TiVo:</strong> {self.tivo_host}<br>
                    <strong>Date:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}<br>
                    <strong>Files Found:</strong> {len(self.transfer_list)}
                </div>
                
                <div class="error">
                    <strong>Error:</strong> {error_message or "Transfer process failed"}
                </div>
            """
            
            if self.transfer_list:
                html += """
                <h3>Files That Were Queued:</h3>
                <table>
                    <tr>
                        <th>#</th>
                        <th>Filename</th>
                        <th>Status</th>
                    </tr>
                """
                
                for idx, item in enumerate(self.transfer_list, 1):
                    html += f"""
                    <tr>
                        <td>{idx}</td>
                        <td>{item['filename']}</td>
                        <td>{item['status']}</td>
                    </tr>
                    """
                
                html += "</table>"
            
            html += """
            </body>
            </html>
            """
        
        msg['From'] = from_email
        msg['To'] = to_email
        msg.attach(MIMEText(html, 'html'))
        
        # Send email
        try:
            print(f"\nConnecting to {smtp_server}:{smtp_port}...")
            if smtp_user and smtp_pass:
                server = smtplib.SMTP(smtp_server, smtp_port)
                print("Starting TLS...")
                server.starttls()
                print("Authenticating...")
                server.login(smtp_user, smtp_pass)
            else:
                server = smtplib.SMTP(smtp_server, smtp_port)
            
            print("Sending email...")
            server.send_message(msg)
            server.quit()
            print(f"✓ Email notification sent to {to_email}")
            print("=" * 60)
        except Exception as e:
            print(f"✗ Failed to send email: {e}")
            print("=" * 60)
            import traceback
            traceback.print_exc()
    
    def send_test_email(self):
        """Send a test email with sample content to verify configuration."""
        # Get email configuration
        smtp_server = os.environ.get('SMTP_SERVER', 'localhost')
        smtp_port = int(os.environ.get('SMTP_PORT', '25'))
        smtp_user = os.environ.get('SMTP_USER')
        smtp_pass = os.environ.get('SMTP_PASS')
        from_email = os.environ.get('FROM_EMAIL', 'pytivo@localhost')
        to_email = os.environ.get('TO_EMAIL')
        
        if not to_email:
            print("\n✗ TO_EMAIL environment variable not set")
            print("Set TO_EMAIL to enable email notifications")
            return
        
        print(f"SMTP Server: {smtp_server}:{smtp_port}")
        print(f"From: {from_email}")
        print(f"To: {to_email}")
        print(f"Auth: {'Yes' if smtp_user else 'No'}")
        
        # Create test transfer list
        test_transfers = [
            {'filename': 'Test_Video_1.mkv', 'status': 'completed'},
            {'filename': 'Test_Video_2.mp4', 'status': 'completed'},
            {'filename': 'Test_Video_3.avi', 'status': 'failed'}
        ]
        
        # Build HTML email
        msg = MIMEMultipart('alternative')
        msg['Subject'] = '✓ PyTivo Test Email - 3 file(s)'
        msg['From'] = from_email
        msg['To'] = to_email
        
        # Calculate test duration
        duration_seconds = 245  # 4 minutes 5 seconds
        hours = duration_seconds // 3600
        minutes = (duration_seconds % 3600) // 60
        seconds = duration_seconds % 60
        duration_str = f"{hours}h {minutes}m {seconds}s" if hours > 0 else f"{minutes}m {seconds}s"
        
        html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .header {{ background-color: #4CAF50; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 20px; }}
                .info {{ margin: 10px 0; }}
                .info strong {{ display: inline-block; width: 120px; }}
                table {{ border-collapse: collapse; width: 100%; margin-top: 20px; }}
                th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
                th {{ background-color: #4CAF50; color: white; }}
                tr:nth-child(even) {{ background-color: #f2f2f2; }}
                .completed {{ color: green; }}
                .failed {{ color: red; }}
                .footer {{ margin-top: 20px; padding-top: 20px; border-top: 1px solid #ddd; color: #666; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>✓ PyTivo Test Email</h1>
            </div>
            <div class="content">
                <div class="info"><strong>TiVo IP:</strong> {self.tivo_host}</div>
                <div class="info"><strong>Date:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
                <div class="info"><strong>Duration:</strong> {duration_str}</div>
                <div class="info"><strong>Status:</strong> <span style="color: green;">3 of 3 files transferred</span></div>
                
                <h2>Transferred Files</h2>
                <table>
                    <tr>
                        <th>File</th>
                        <th>Status</th>
                    </tr>
        """
        
        for transfer in test_transfers:
            status_class = transfer['status']
            status_text = '✓ Completed' if transfer['status'] == 'completed' else '✗ Failed'
            html += f"""
                    <tr>
                        <td>{transfer['filename']}</td>
                        <td class="{status_class}">{status_text}</td>
                    </tr>
            """
        
        html += """
                </table>
                <div class="footer">
                    <p><strong>This is a test email from PyTivo Transfer Automation</strong></p>
                    <p>This email confirms your SMTP configuration is working correctly.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        msg.attach(MIMEText(html, 'html'))
        
        # Send email
        try:
            print(f"\nConnecting to {smtp_server}:{smtp_port}...")
            server = smtplib.SMTP(smtp_server, smtp_port)
            server.set_debuglevel(0)
            
            if smtp_user and smtp_pass:
                print("Starting TLS...")
                server.starttls()
                print("Authenticating...")
                server.login(smtp_user, smtp_pass)
            
            print(f"Sending test email to {to_email}...")
            server.send_message(msg)
            server.quit()
            
            print(f"\n✓ Test email sent successfully to {to_email}")
            print("\nCheck your inbox for the test email.")
        except Exception as e:
            print(f"\n✗ Failed to send test email: {e}")
            import traceback
            traceback.print_exc()
    
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
  # List video shares from pyTivo.conf
  python pytivo_transfer.py --list-shares
  
  # Find share name for a directory path
  python pytivo_transfer.py --share-for-path /mnt/cloud/pytivo-watcher-mediaroom
  
  # Interactive mode (manual control)
  python pytivo_transfer.py 192.168.1.185
  
  # Execute a sequence from config
  python pytivo_transfer.py 192.168.1.185 watcher
  python pytivo_transfer.py 192.168.1.185 import-wait-remove
  
  # Automated transfer (first video in share)
  python pytivo_transfer.py 192.168.1.185 --auto --position 0
  
  # Transfer video at position 3
  python pytivo_transfer.py 192.168.1.185 --auto --position 3
  
  # Send test email (verify SMTP configuration)
  python pytivo_transfer.py 192.168.1.185 --test-email

Note: Automated mode is fragile and may need customization for your menu layout.
      Interactive mode is recommended for initial testing.
      Set SHARE_NAME environment variable to specify which pyTivo share to use.
        """
    )
    
    parser.add_argument("tivo_ip", nargs="?", help="TiVo IP address")
    parser.add_argument("sequence", nargs="?", help="Optional: sequence name to execute from config")
    parser.add_argument("--auto", action="store_true", 
                       help="Attempt automated transfer (vs interactive mode)")
    parser.add_argument("--position", type=int, default=0,
                       help="Video position in list (0 = first)")
    parser.add_argument("--folders", nargs="*",
                       help="Folder path to navigate through")
    parser.add_argument("--test-email", action="store_true",
                       help="Send a test email with sample content and exit")
    parser.add_argument("--list-shares", action="store_true",
                       help="List video shares from pyTivo.conf and exit")
    parser.add_argument("--share-for-path", metavar="PATH",
                       help="Find share name for given directory path and exit")
    
    args = parser.parse_args()
    
    # Handle share-for-path mode (no banner or TiVo IP needed)
    if args.share_for_path:
        automation = PyTivoAutomation("dummy")
        share_name = automation.get_share_by_path(args.share_for_path)
        if share_name:
            print(share_name)
            return 0
        else:
            print(f"No share found for path: {args.share_for_path}", file=sys.stderr)
            return 1
    
    # Handle list-shares mode (no banner or TiVo IP needed)
    if args.list_shares:
        automation = PyTivoAutomation("dummy")
        shares = automation.get_pytivo_shares()
        if shares:
            print("Video shares from pyTivo.conf:")
            for share in shares:
                print(f"  - {share}")
        else:
            print("No video shares found in pyTivo.conf")
        return 0
    
    # Require tivo_ip for all other modes
    if not args.tivo_ip:
        parser.error("tivo_ip is required (unless using --list-shares)")
    
    # Print banner FIRST before any other output
    print("=" * 60)
    print("pyTivo Transfer Automation")
    print("=" * 60)
    print()
    sys.stdout.flush()
    
    automation = PyTivoAutomation(args.tivo_ip)
    
    # Handle test email mode (no TiVo connection needed)
    if args.test_email:
        print(f"TiVo: {args.tivo_ip}")
        print("\nSending test email...")
        automation.send_test_email()
        return 0
    
    print(f"TiVo: {args.tivo_ip}")
    
    if not automation.connect():
        print("\n✗ Failed to connect to TiVo!")
        print("Make sure Network Remote Control is enabled.")
        return 1
    
    print("✓ Connected to TiVo")
    sys.stdout.flush()
    
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
