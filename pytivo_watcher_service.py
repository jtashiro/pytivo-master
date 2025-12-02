#!/usr/bin/env python3
"""
PyTivo Watcher Service - Monitors directory and auto-transfers to TiVo.

This service continuously monitors a directory for new video files and
automatically queues them for transfer to a TiVo device.
"""

import os
import sys
import time
import logging
from pathlib import Path
from pytivo_transfer import PyTivoAutomation

# Configuration
TIVO_IP = os.environ.get('TIVO_IP', '192.168.1.185')
WATCH_DIR = os.environ.get('WATCH_DIR', '/mnt/cloud/pytivo-watcher')
CHECK_INTERVAL = int(os.environ.get('CHECK_INTERVAL', '300'))  # seconds
MIN_FILE_AGE = int(os.environ.get('MIN_FILE_AGE', '60'))  # seconds to wait after file modification
SEQUENCE_NAME = os.environ.get('SEQUENCE_NAME', 'watcher')

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/log/pytivo-watcher.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def get_video_files(watch_dir):
    """Get list of video files in watch directory."""
    video_extensions = {'.mkv', '.mp4', '.avi', '.m4v', '.mov', '.mpg', '.mpeg', '.ts'}
    video_files = []
    
    try:
        for file in Path(watch_dir).iterdir():
            if file.is_file() and file.suffix.lower() in video_extensions:
                # Check if file is old enough (not currently being written)
                file_age = time.time() - file.stat().st_mtime
                if file_age >= MIN_FILE_AGE:
                    video_files.append(file)
    except Exception as e:
        logger.error(f"Error scanning directory: {e}")
    
    return sorted(video_files)


def run_transfer(tivo_ip, sequence_name):
    """Execute transfer sequence."""
    try:
        logger.info(f"Initiating transfer to {tivo_ip} using sequence '{sequence_name}'")
        
        automation = PyTivoAutomation(tivo_ip)
        
        if not automation.connect():
            logger.error("Failed to connect to TiVo")
            return False
        
        try:
            success = automation.execute_sequence(sequence_name)
            if success:
                logger.info("Transfer sequence completed successfully")
            else:
                logger.error(f"Transfer sequence '{sequence_name}' failed")
            return success
        finally:
            automation.disconnect()
            
    except Exception as e:
        logger.error(f"Error during transfer: {e}", exc_info=True)
        return False


def main():
    """Main service loop."""
    logger.info("=" * 60)
    logger.info("PyTivo Watcher Service Starting")
    logger.info("=" * 60)
    logger.info(f"TiVo IP: {TIVO_IP}")
    logger.info(f"Watch Directory: {WATCH_DIR}")
    logger.info(f"Check Interval: {CHECK_INTERVAL}s")
    logger.info(f"Min File Age: {MIN_FILE_AGE}s")
    logger.info(f"Sequence: {SEQUENCE_NAME}")
    logger.info("=" * 60)
    
    # Verify watch directory exists
    if not os.path.isdir(WATCH_DIR):
        logger.error(f"Watch directory does not exist: {WATCH_DIR}")
        sys.exit(1)
    
    last_file_count = 0
    
    while True:
        try:
            # Check for files
            video_files = get_video_files(WATCH_DIR)
            file_count = len(video_files)
            
            # Log status periodically
            if file_count != last_file_count:
                if file_count > 0:
                    logger.info(f"Found {file_count} file(s) in watch directory:")
                    for f in video_files:
                        logger.info(f"  - {f.name}")
                    
                    # Trigger transfer
                    logger.info("Starting transfer process...")
                    run_transfer(TIVO_IP, SEQUENCE_NAME)
                    
                else:
                    logger.info("Watch directory is empty")
                
                last_file_count = file_count
            
            # Wait before next check
            time.sleep(CHECK_INTERVAL)
            
        except KeyboardInterrupt:
            logger.info("Service stopped by user")
            break
        except Exception as e:
            logger.error(f"Unexpected error in main loop: {e}", exc_info=True)
            time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
