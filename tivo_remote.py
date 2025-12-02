#!/usr/bin/env python3
"""
TiVo Network Remote Control Library

Provides programmatic control of TiVo devices via the Network Remote Control feature.
Enable on TiVo: Settings → Network Settings → Network Remote Control

Based on TiVo TCP Remote Protocol:
https://www.tivo.com/assets/images/abouttivo/resources/downloads/brochures/TiVo_TCP_Network_Remote_Control_Protocol.pdf
"""

import socket
import time
from typing import Optional, List
from enum import Enum

class TiVoButton(Enum):
    """TiVo remote control buttons."""
    # Navigation
    UP = "UP"
    DOWN = "DOWN"
    LEFT = "LEFT"
    RIGHT = "RIGHT"
    SELECT = "SELECT"
    
    # Playback
    PLAY = "PLAY"
    PAUSE = "PAUSE"
    REVERSE = "REVERSE"
    FORWARD = "FORWARD"
    SLOW = "SLOW"
    REPLAY = "REPLAY"
    ADVANCE = "ADVANCE"
    
    # Channel/Guide
    CHANNELUP = "CHANNELUP"
    CHANNELDOWN = "CHANNELDOWN"
    GUIDE = "GUIDE"
    LIVETV = "LIVETV"
    
    # Special
    TIVO = "TIVO"  # TiVo button (home)
    NOWSHOWING = "NOWSHOWING"  # My Shows
    INFO = "INFO"
    
    # Numbers
    NUM0 = "NUM0"
    NUM1 = "NUM1"
    NUM2 = "NUM2"
    NUM3 = "NUM3"
    NUM4 = "NUM4"
    NUM5 = "NUM5"
    NUM6 = "NUM6"
    NUM7 = "NUM7"
    NUM8 = "NUM8"
    NUM9 = "NUM9"
    
    # Actions
    ENTER = "ENTER"
    CLEAR = "CLEAR"
    THUMBSUP = "THUMBSUP"
    THUMBSDOWN = "THUMBSDOWN"
    RECORD = "RECORD"
    
    # Color buttons
    ACTION_A = "ACTION_A"  # Yellow (A)
    ACTION_B = "ACTION_B"  # Blue (B)
    ACTION_C = "ACTION_C"  # Red (C)
    ACTION_D = "ACTION_D"  # Green (D)

class TiVoRemote:
    """Control a TiVo via Network Remote Control."""
    
    def __init__(self, host: str, port: int = 31339, timeout: float = 5.0):
        """
        Initialize TiVo remote control.
        
        Args:
            host: TiVo IP address
            port: Network Remote Control port (default 31339)
            timeout: Socket timeout in seconds
        """
        self.host = host
        self.port = port
        self.timeout = timeout
        self.socket: Optional[socket.socket] = None
        
    def connect(self) -> bool:
        """Connect to the TiVo."""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(self.timeout)
            self.socket.connect((self.host, self.port))
            return True
        except socket.error as e:
            print(f"Failed to connect to TiVo at {self.host}:{self.port} - {e}")
            return False
    
    def disconnect(self):
        """Disconnect from the TiVo."""
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None
    
    def send_command(self, command: str) -> bool:
        """
        Send a raw command to the TiVo.
        
        Args:
            command: Command string (e.g., "IRCODE TIVO")
            
        Returns:
            True if command sent successfully
        """
        if not self.socket:
            if not self.connect():
                return False
        
        try:
            self.socket.sendall(f"{command}\r\n".encode('utf-8'))
            return True
        except socket.error as e:
            print(f"Failed to send command '{command}': {e}")
            self.disconnect()
            return False
    
    def press(self, button: TiVoButton, delay: float = 0.3) -> bool:
        """
        Press a button on the remote.
        
        Args:
            button: Button to press
            delay: Delay after pressing (seconds)
            
        Returns:
            True if successful
        """
        result = self.send_command(f"IRCODE {button.value}")
        if result and delay > 0:
            time.sleep(delay)
        return result
    
    def press_multiple(self, buttons: List[TiVoButton], delay: float = 0.3) -> bool:
        """
        Press multiple buttons in sequence.
        
        Args:
            buttons: List of buttons to press
            delay: Delay between presses (seconds)
            
        Returns:
            True if all successful
        """
        for button in buttons:
            if not self.press(button, delay):
                return False
        return True
    
    def teleport(self, code: str) -> bool:
        """
        Use TELEPORT command to jump directly to a screen.
        
        Args:
            code: Teleport code (e.g., "TIVO", "LIVETV", "GUIDE", "NOWSHOWING")
            
        Returns:
            True if successful
        """
        return self.send_command(f"TELEPORT {code}")
    
    def keyboard(self, text: str) -> bool:
        """
        Send keyboard text to TiVo (for search, etc.).
        
        Args:
            text: Text to send
            
        Returns:
            True if successful
        """
        return self.send_command(f"KEYBOARD {text}")
    
    def forced_channel(self, channel: int, subchannel: int = 0) -> bool:
        """
        Force tune to a specific channel.
        
        Args:
            channel: Channel number
            subchannel: Subchannel (0 if none)
            
        Returns:
            True if successful
        """
        if subchannel > 0:
            return self.send_command(f"FORCEDCH {channel} {subchannel}")
        else:
            return self.send_command(f"FORCECH {channel}")
    
    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()


class TiVoNavigator:
    """High-level navigation helpers for TiVo."""
    
    def __init__(self, remote: TiVoRemote):
        """Initialize with a TiVoRemote instance."""
        self.remote = remote
    
    def go_home(self):
        """Go to TiVo home screen."""
        self.remote.teleport("TIVO")
        time.sleep(1.5)
    
    def go_to_my_shows(self):
        """Go to My Shows (Now Playing)."""
        self.remote.teleport("NOWSHOWING")
        time.sleep(1.5)
    
    def go_to_live_tv(self):
        """Go to Live TV."""
        self.remote.teleport("LIVETV")
        time.sleep(1.5)
    
    def jump_to_top(self, max_presses: int = 50):
        """
        Jump to the first item in the current menu/list.
        
        Args:
            max_presses: Maximum number of UP presses to send
        """
        # Press UP repeatedly to get to top
        # Most TiVo lists aren't deeper than 50 items
        for _ in range(max_presses):
            self.remote.press(TiVoButton.UP, delay=0.1)
        time.sleep(0.3)
    
    def jump_to_bottom(self, max_presses: int = 50):
        """
        Jump to the last item in the current menu/list.
        
        Args:
            max_presses: Maximum number of DOWN presses to send
        """
        # Press DOWN repeatedly to get to bottom
        for _ in range(max_presses):
            self.remote.press(TiVoButton.DOWN, delay=0.1)
        time.sleep(0.3)
    
    def navigate_to_pytivo_share(self, share_name: str, from_my_shows: bool = True) -> bool:
        """
        Navigate to a pyTivo share from My Shows.
        
        This is fragile and depends on your TiVo's menu layout!
        
        Args:
            share_name: Name of pyTivo share to find
            from_my_shows: Start from My Shows screen (default True)
            
        Returns:
            True if navigation attempted
        """
        if from_my_shows:
            self.go_to_my_shows()
        
        # In My Shows, pyTivo shares often appear at the bottom
        # Press DOWN several times to get to them
        print(f"Navigating to find pyTivo share '{share_name}'...")
        
        # Go to bottom of My Shows list
        for _ in range(20):  # Arbitrary - adjust based on your setup
            self.remote.press(TiVoButton.DOWN, delay=0.2)
        
        # Now we should be near pyTivo shares
        # This is the fragile part - you'd need to customize this
        print("Near pyTivo shares. Manual navigation may be needed.")
        print("Press SELECT when on the correct share.")
        
        return True
    
    def start_video_transfer(self, video_index: int = 0) -> bool:
        """
        Select a video to start transfer (assumes you're in a video list).
        
        Args:
            video_index: Index of video in list (0 = first, 1 = second, etc.)
            
        Returns:
            True if selection attempted
        """
        print(f"Selecting video at index {video_index}...")
        
        # Navigate to the video
        for _ in range(video_index):
            self.remote.press(TiVoButton.DOWN, delay=0.3)
        
        # Select it to start transfer
        self.remote.press(TiVoButton.SELECT, delay=0.5)
        
        print("Transfer should start if video was selected.")
        return True


def demo_remote_control(tivo_host: str):
    """Demonstrate remote control functionality."""
    print(f"Connecting to TiVo at {tivo_host}...")
    
    with TiVoRemote(tivo_host) as remote:
        if not remote.socket:
            print("Failed to connect!")
            return
        
        print("Connected! Running demo...")
        
        # Create navigator
        nav = TiVoNavigator(remote)
        
        # Demo 1: Go to TiVo home
        print("\n1. Going to TiVo home screen...")
        nav.go_home()
        
        # Demo 2: Go to My Shows
        print("\n2. Going to My Shows...")
        nav.go_to_my_shows()
        
        # Demo 3: Navigate down a few times
        print("\n3. Navigating down 3 times...")
        for i in range(3):
            print(f"   Press DOWN ({i+1}/3)")
            remote.press(TiVoButton.DOWN, delay=0.5)
        
        print("\nDemo complete!")
        print("\nTo automate pyTivo transfers:")
        print("1. Customize navigate_to_pytivo_share() for your menu layout")
        print("2. Use keyboard() to search for specific videos")
        print("3. Use start_video_transfer() when in a video list")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("TiVo Network Remote Control")
        print("=" * 60)
        print("\nUsage:")
        print("  python tivo_remote.py <tivo_ip> [demo]")
        print("\nExamples:")
        print("  python tivo_remote.py 192.168.1.185 demo")
        print("  python tivo_remote.py 192.168.1.79")
        print("\nTo use in your own scripts:")
        print("  from tivo_remote import TiVoRemote, TiVoButton, TiVoNavigator")
        sys.exit(1)
    
    tivo_host = sys.argv[1]
    
    if len(sys.argv) > 2 and sys.argv[2] == "demo":
        demo_remote_control(tivo_host)
    else:
        print(f"Testing connection to {tivo_host}...")
        with TiVoRemote(tivo_host) as remote:
            if remote.socket:
                print("✓ Connected successfully!")
                print("\nAvailable features:")
                print("  - Press buttons: remote.press(TiVoButton.SELECT)")
                print("  - Teleport: remote.teleport('NOWSHOWING')")
                print("  - Keyboard: remote.keyboard('search text')")
                print("  - Navigator: nav = TiVoNavigator(remote)")
                print("\nRun with 'demo' argument to see examples:")
                print(f"  python tivo_remote.py {tivo_host} demo")
            else:
                print("✗ Connection failed!")
                print("Make sure Network Remote Control is enabled on the TiVo")
