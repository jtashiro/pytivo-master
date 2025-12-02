#!/bin/bash

# pyTivo Installation Script
# Copies all necessary files to a specified installation directory

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Function to print status messages
print_status() {
    echo -e "${BLUE}==>${NC} $1"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

# Check if destination directory is provided
if [ -z "$1" ]; then
    echo "Usage: $0 <installation_directory>"
    echo "Example: $0 /opt/pytivo"
    exit 1
fi

INSTALL_DIR="$1"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

print_status "Installing pyTivo to: $INSTALL_DIR"
print_status "Source directory: $SOURCE_DIR"

# Create installation directory if it doesn't exist
if [ ! -d "$INSTALL_DIR" ]; then
    print_status "Creating installation directory..."
    mkdir -p "$INSTALL_DIR"
    print_success "Directory created"
else
    print_status "Installation directory exists"
fi

# Copy main Python files
print_status "Copying main application files..."
cp "$SOURCE_DIR/pyTivo.py" "$INSTALL_DIR/"
cp "$SOURCE_DIR/beacon.py" "$INSTALL_DIR/"
cp "$SOURCE_DIR/config.py" "$INSTALL_DIR/"
cp "$SOURCE_DIR/httpserver.py" "$INSTALL_DIR/"
cp "$SOURCE_DIR/lrucache.py" "$INSTALL_DIR/"
cp "$SOURCE_DIR/metadata.py" "$INSTALL_DIR/"
cp "$SOURCE_DIR/plugin.py" "$INSTALL_DIR/"
cp "$SOURCE_DIR/turing.py" "$INSTALL_DIR/"
cp "$SOURCE_DIR/zeroconf.py" "$INSTALL_DIR/"
print_success "Main files copied"

# Copy service files
print_status "Copying service files..."
cp "$SOURCE_DIR/pyTivoService.py" "$INSTALL_DIR/"
cp "$SOURCE_DIR/pyTivoConfigurator.pyw" "$INSTALL_DIR/"
print_success "Service files copied"

# Copy configuration files
print_status "Copying configuration files..."
cp "$SOURCE_DIR/pyTivo.conf.dist" "$INSTALL_DIR/"
if [ -f "$SOURCE_DIR/pyTivo.conf" ] && [ ! -f "$INSTALL_DIR/pyTivo.conf" ]; then
    print_status "Copying existing pyTivo.conf..."
    cp "$SOURCE_DIR/pyTivo.conf" "$INSTALL_DIR/"
    print_success "Configuration preserved"
else
    print_status "Skipping pyTivo.conf (already exists or not present)"
fi

# Copy README
print_status "Copying documentation..."
cp "$SOURCE_DIR/README" "$INSTALL_DIR/"
print_success "Documentation copied"

# Copy directories with Python code
print_status "Copying Cheetah template engine..."
cp -r "$SOURCE_DIR/Cheetah" "$INSTALL_DIR/"
print_success "Cheetah copied"

print_status "Copying mutagen library..."
cp -r "$SOURCE_DIR/mutagen" "$INSTALL_DIR/"
print_success "mutagen copied"

print_status "Copying plugins..."
cp -r "$SOURCE_DIR/plugins" "$INSTALL_DIR/"
print_success "Plugins copied"

print_status "Copying templates..."
cp -r "$SOURCE_DIR/templates" "$INSTALL_DIR/"
print_success "Templates copied"

print_status "Copying content (CSS/JS)..."
cp -r "$SOURCE_DIR/content" "$INSTALL_DIR/"
print_success "Content copied"

# Clean up bytecode files in installation
print_status "Cleaning up bytecode files..."
find "$INSTALL_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "$INSTALL_DIR" -type f -name "*.pyc" -delete 2>/dev/null || true
find "$INSTALL_DIR" -type f -name "*.pyo" -delete 2>/dev/null || true
print_success "Cleanup complete"

# Set executable permissions
print_status "Setting executable permissions..."
chmod +x "$INSTALL_DIR/pyTivo.py"
chmod +x "$INSTALL_DIR/pyTivoService.py"
print_success "Permissions set"

# Display completion message
echo ""
print_success "Installation complete!"
echo ""
echo "Installation directory: $INSTALL_DIR"
echo ""
echo "Next steps:"
echo "  1. Edit $INSTALL_DIR/pyTivo.conf (or copy from pyTivo.conf.dist)"
echo "  2. Configure your shares and settings"
echo "  3. Run: cd $INSTALL_DIR && python3 pyTivo.py"
echo ""
