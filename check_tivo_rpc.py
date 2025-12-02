#!/usr/bin/env python3
"""
Check if a TiVo device has RPC interface available.

This script tests for various TiVo interfaces:
1. Network Remote Control (port 31339) - documented
2. RPC interface (port 1413) - undocumented Mind RPC
3. Web interface (ports 80, 443)
"""

import socket
import sys
import struct
import json
from typing import Tuple, Optional

# Common TiVo ports
REMOTE_CONTROL_PORT = 31339  # Network Remote Control
MIND_RPC_PORT = 1413         # Mind RPC (undocumented)
HTTP_PORT = 80
HTTPS_PORT = 443

def check_port(host: str, port: int, timeout: float = 3.0) -> bool:
    """Check if a port is open on the host."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except socket.error:
        return False

def test_network_remote(host: str, timeout: float = 3.0) -> Tuple[bool, Optional[str]]:
    """
    Test if Network Remote Control is available.
    Sends a harmless command (IRCODE TIVO) and checks for response.
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((host, REMOTE_CONTROL_PORT))
        
        # Wait a moment for any banner/greeting
        try:
            greeting = sock.recv(1024, socket.MSG_DONTWAIT)
            if greeting:
                sock.close()
                return True, f"Greeting: {greeting.decode('utf-8', errors='ignore').strip()}"
        except socket.error:
            pass  # No greeting, that's okay
        
        # Send IRCODE TIVO command (brings up TiVo menu, harmless)
        sock.sendall(b'IRCODE TIVO\r\n')
        
        # Try to receive response
        try:
            response = sock.recv(1024)
            sock.close()
            if response:
                return True, f"Response: {response.decode('utf-8', errors='ignore').strip()}"
        except socket.timeout:
            sock.close()
            return True, "Connected (no response expected)"
            
        return True, "Connected successfully"
    except ConnectionResetError:
        return False, "Connection reset - feature may be disabled on TiVo"
    except socket.timeout:
        return False, "Connection timeout"
    except socket.error as e:
        return False, str(e)

def test_mind_rpc(host: str, timeout: float = 3.0) -> Tuple[bool, Optional[str]]:
    """
    Test if Mind RPC interface is available.
    This is TiVo's undocumented RPC protocol.
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((host, MIND_RPC_PORT))
        
        # Try to send a basic Mind RPC handshake
        # Mind protocol uses length-prefixed JSON messages
        test_request = {
            "type": "bodyConfigSearch",
            "bodyId": "-"
        }
        
        json_data = json.dumps(test_request).encode('utf-8')
        # Mind protocol: 4-byte length prefix (big-endian) + JSON
        length_prefix = struct.pack('>I', len(json_data) + 10)
        header = b'\x00\x00\x00\x00\x00\x00'  # 6 bytes of header
        
        message = length_prefix + header + json_data
        sock.sendall(message)
        
        # Try to receive response
        response_header = sock.recv(10)
        if len(response_header) >= 4:
            response_length = struct.unpack('>I', response_header[:4])[0]
            if response_length > 0 and response_length < 10000:
                response_data = sock.recv(response_length)
                sock.close()
                return True, f"Mind RPC active (received {len(response_data)} bytes)"
        
        sock.close()
        return True, "Connected but unexpected response"
    except ConnectionResetError:
        return False, "Connection reset - authentication required or disabled"
    except socket.timeout:
        return False, "Connection timeout"
    except socket.error as e:
        return False, str(e)

def check_tivo_interfaces(host: str):
    """Check all known TiVo interfaces."""
    print(f"Checking TiVo interfaces for: {host}")
    print("=" * 60)
    
    # Check Network Remote Control
    print(f"\n[Network Remote Control - Port {REMOTE_CONTROL_PORT}]")
    if check_port(host, REMOTE_CONTROL_PORT):
        available, info = test_network_remote(host)
        if available:
            print(f"✓ AVAILABLE")
            print(f"  Info: {info}")
            print(f"  Usage: Can send IR remote codes (IRCODE <button>)")
        else:
            print(f"✗ DISABLED")
            print(f"  Info: {info}")
            print(f"  Enable: TiVo Settings → Network Settings → Network Remote Control")
    else:
        print(f"✗ NOT AVAILABLE (port closed)")
        print(f"  Enable: TiVo Settings → Network Settings → Network Remote Control")
    
    # Check Mind RPC
    print(f"\n[Mind RPC Interface - Port {MIND_RPC_PORT}]")
    if check_port(host, MIND_RPC_PORT):
        available, info = test_mind_rpc(host)
        if available:
            print(f"✓ AVAILABLE (undocumented)")
            print(f"  Info: {info}")
            print(f"  Usage: Advanced RPC commands (requires MAK/auth)")
            print(f"  Note: Used by TiVo mobile apps and kmttg")
        else:
            print(f"✗ PROTECTED")
            print(f"  Info: {info}")
            print(f"  Note: Port accessible but requires authentication")
    else:
        print(f"✗ NOT AVAILABLE (port closed)")
    
    # Check HTTP
    print(f"\n[Web Interface - Port {HTTP_PORT}]")
    if check_port(host, HTTP_PORT):
        print(f"✓ AVAILABLE")
        print(f"  URL: http://{host}")
    else:
        print(f"✗ NOT AVAILABLE")
    
    # Check HTTPS
    print(f"\n[Web Interface (HTTPS) - Port {HTTPS_PORT}]")
    if check_port(host, HTTPS_PORT):
        print(f"✓ AVAILABLE")
        print(f"  URL: https://{host}")
    else:
        print(f"✗ NOT AVAILABLE")
    
    print("\n" + "=" * 60)
    print("\nSummary:")
    print("- Network Remote Control: Basic remote control simulation")
    print("- Mind RPC: Advanced control (undocumented, reverse-engineered)")
    print("- Web Interface: Status and some configuration")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python check_tivo_rpc.py <tivo_ip_address>")
        print("\nExample: python check_tivo_rpc.py 192.168.1.79")
        sys.exit(1)
    
    tivo_host = sys.argv[1]
    
    try:
        # Validate IP or hostname
        socket.gethostbyname(tivo_host)
        check_tivo_interfaces(tivo_host)
    except socket.gaierror:
        print(f"Error: Cannot resolve hostname '{tivo_host}'")
        sys.exit(1)
