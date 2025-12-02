#!/bin/bash

# Script to reorganize pyTivo into proper Python package structure
# Creates src/pytivo/ directory structure suitable for egg/wheel distribution

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${BLUE}==>${NC} $1"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}!${NC} $1"
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

print_status "Creating Python package structure..."

# Create src directory structure
mkdir -p src/pytivo/plugins/music/templates
mkdir -p src/pytivo/plugins/photo/templates
mkdir -p src/pytivo/plugins/settings/templates
mkdir -p src/pytivo/plugins/settings/content
mkdir -p src/pytivo/plugins/togo/templates
mkdir -p src/pytivo/plugins/video/templates
mkdir -p src/pytivo/templates
mkdir -p src/pytivo/content

print_success "Directory structure created"

# Copy main package files
print_status "Copying main package files..."
cp beacon.py src/pytivo/
cp config.py src/pytivo/
cp httpserver.py src/pytivo/
cp lrucache.py src/pytivo/
cp metadata.py src/pytivo/
cp plugin.py src/pytivo/
cp pyTivo.py src/pytivo/
cp pyTivoService.py src/pytivo/
cp turing.py src/pytivo/
cp zeroconf.py src/pytivo/
print_success "Main files copied"

# Copy bundled libraries
print_status "Copying bundled libraries..."
cp -r Cheetah src/pytivo/
cp -r mutagen src/pytivo/
print_success "Libraries copied"

# Copy plugins
print_status "Copying plugins..."
cp plugins/__init__.py src/pytivo/plugins/

cp plugins/music/__init__.py src/pytivo/plugins/music/
cp plugins/music/music.py src/pytivo/plugins/music/
cp plugins/music/templates/*.tmpl src/pytivo/plugins/music/templates/

cp plugins/photo/__init__.py src/pytivo/plugins/photo/
cp plugins/photo/photo.py src/pytivo/plugins/photo/
cp plugins/photo/templates/*.tmpl src/pytivo/plugins/photo/templates/

cp plugins/settings/__init__.py src/pytivo/plugins/settings/
cp plugins/settings/buildhelp.py src/pytivo/plugins/settings/
cp plugins/settings/help.txt src/pytivo/plugins/settings/
cp plugins/settings/settings.py src/pytivo/plugins/settings/
cp plugins/settings/templates/*.tmpl src/pytivo/plugins/settings/templates/
cp plugins/settings/content/*.css src/pytivo/plugins/settings/content/ 2>/dev/null || true
cp plugins/settings/content/*.js src/pytivo/plugins/settings/content/ 2>/dev/null || true

cp plugins/togo/__init__.py src/pytivo/plugins/togo/
cp plugins/togo/togo.py src/pytivo/plugins/togo/
cp plugins/togo/templates/*.tmpl src/pytivo/plugins/togo/templates/

cp plugins/video/__init__.py src/pytivo/plugins/video/
cp plugins/video/transcode.py src/pytivo/plugins/video/
cp plugins/video/video.py src/pytivo/plugins/video/
cp plugins/video/templates/*.tmpl src/pytivo/plugins/video/templates/

print_success "Plugins copied"

# Copy templates and content
print_status "Copying templates and content..."
cp templates/*.tmpl src/pytivo/templates/
cp content/*.css src/pytivo/content/
print_success "Templates and content copied"

# Create __init__.py files
print_status "Creating __init__.py files..."
cat > src/pytivo/__init__.py << 'EOF'
"""
pyTivo - TiVo HMO and GoBack server

A TiVo Home Media Option (HMO) and GoBack server for Python 3.
Streams video, music, and photos to TiVo devices on your network.
"""

__version__ = "1.0.0"
__author__ = "pyTivo Contributors"

EOF

touch src/pytivo/plugins/__init__.py
touch src/pytivo/plugins/music/__init__.py
touch src/pytivo/plugins/photo/__init__.py
touch src/pytivo/plugins/settings/__init__.py
touch src/pytivo/plugins/togo/__init__.py
touch src/pytivo/plugins/video/__init__.py

print_success "__init__.py files created"

# Fix imports in package files to use relative imports
print_status "Fixing imports for package structure..."

# List of pytivo module names to convert to relative imports
PYTIVO_MODULES="beacon config httpserver plugin metadata lrucache turing zeroconf"

# Fix all Python files in src/pytivo/ (main package)
for pyfile in src/pytivo/*.py; do
    if [ -f "$pyfile" ]; then
        for module in $PYTIVO_MODULES; do
            # Fix "import module" -> "from . import module"
            sed -i.bak "s/^import ${module}$/from . import ${module}/" "$pyfile"
            # Fix "from module import" -> "from .module import"
            sed -i.bak "s/^from ${module} import /from .${module} import /" "$pyfile"
        done
        # Fix "import plugins.video.transcode" -> "from .plugins.video import transcode"
        sed -i.bak "s|^import plugins\.video\.transcode$|from .plugins.video import transcode|" "$pyfile"
    fi
done

# Special fix for metadata.py to explicitly import mutagen.mp4
if [ -f "src/pytivo/metadata.py" ]; then
    # Add "from . import mutagen" after finding it and add mp4 import
    sed -i.bak '/^from \. import mutagen$/a\
from .mutagen import mp4 as mutagen_mp4
' "src/pytivo/metadata.py"
    # Replace mutagen.mp4.MediaKind with mutagen_mp4.MediaKind
    sed -i.bak 's/mutagen\.mp4\.MediaKind/mutagen_mp4.MediaKind/g' "src/pytivo/metadata.py"
fi

# Fix plugin files - they need to import from parent package
for pyfile in src/pytivo/plugins/*/*.py; do
    if [ -f "$pyfile" ]; then
        # Fix "import config" -> "from ... import config" (go up 2 levels to pytivo package)
        sed -i.bak "s/^import config$/from ... import config/" "$pyfile"
        sed -i.bak "s/^import metadata$/from ... import metadata/" "$pyfile"
        sed -i.bak "s/^import lrucache$/from ... import lrucache/" "$pyfile"
        # Fix "from plugin import" -> "from ...plugin import"
        sed -i.bak "s/^from plugin import /from ...plugin import /" "$pyfile"
        sed -i.bak "s/^from lrucache import /from ...lrucache import /" "$pyfile"
        sed -i.bak "s/^from metadata import /from ...metadata import /" "$pyfile"
        # Fix "from plugins.video.transcode import" -> relative import
        sed -i.bak "s/^from plugins\.video\.transcode import /from ..video.transcode import /" "$pyfile"
    fi
done

# Fix bundled library imports (Cheetah, mutagen) to be relative
print_status "Fixing bundled library imports..."

# In plugin.py and other files that import Cheetah
for pyfile in src/pytivo/*.py; do
    if [ -f "$pyfile" ]; then
        # Fix "from Cheetah." -> "from .Cheetah."
        sed -i.bak "s/^from Cheetah\./from .Cheetah./" "$pyfile"
        sed -i.bak "s/^import Cheetah$/from . import Cheetah/" "$pyfile"
        # Fix "from mutagen" -> "from .mutagen"
        sed -i.bak "s/^from mutagen\./from .mutagen./" "$pyfile"
        sed -i.bak "s/^import mutagen$/from . import mutagen/" "$pyfile"
    fi
done

# Fix plugin.py GetPlugin() to use importlib for proper package imports
print_status "Fixing plugin loading for package structure..."
if [ -f "src/pytivo/plugin.py" ]; then
    # Replace the GetPlugin function to use importlib and relative imports
    cat > /tmp/plugin_fix.py << 'PLUGINFIX'
import importlib

class Error:
    CONTENT_TYPE = 'text/html'

def GetPlugin(name):
    try:
        # Use relative import within the package
        module_name = f'.plugins.{name}.{name}'
        module = importlib.import_module(module_name, package='pytivo')
        plugin = getattr(module, module.CLASS_NAME)()
        return plugin
    except ImportError as e:
        print('Error no', name, 'plugin exists. Check the type '
              'setting for your share.')
        print(f'Import error: {e}')
        return Error
PLUGINFIX

    # Find the GetPlugin function and replace it
    python3 << 'PYEOF'
import re

with open('src/pytivo/plugin.py', 'r') as f:
    content = f.read()

# Find and replace the GetPlugin function
pattern = r'class Error:.*?def GetPlugin\(name\):.*?return Error'
replacement = open('/tmp/plugin_fix.py').read()

content = re.sub(pattern, replacement, content, flags=re.DOTALL)

with open('src/pytivo/plugin.py', 'w') as f:
    f.write(content)
PYEOF

    rm /tmp/plugin_fix.py
    print_success "Plugin loading fixed to use importlib"
fi

# Fix internal Cheetah imports - Cheetah files import each other
print_status "Fixing internal Cheetah imports..."
for pyfile in src/pytivo/Cheetah/*.py src/pytivo/Cheetah/*/*.py; do
    if [ -f "$pyfile" ]; then
        # Fix absolute imports within Cheetah to relative imports
        # "from Cheetah.Module import" -> "from .Module import" (or from ..Module for subdirs)
        
        # Determine relative path based on file depth
        if [[ "$pyfile" == src/pytivo/Cheetah/Utils/* ]] || [[ "$pyfile" == src/pytivo/Cheetah/Macros/* ]]; then
            # In subdirectory - use .. to go up to Cheetah level
            sed -i.bak "s|^from Cheetah\.|from ..|" "$pyfile"
            sed -i.bak "s|^import Cheetah\.|from .. import |" "$pyfile"
        else
            # In Cheetah root - use . for same level
            sed -i.bak "s|^from Cheetah\.|from .|" "$pyfile"
            sed -i.bak "s|^import Cheetah$|from . import Cheetah|" "$pyfile"
        fi
    fi
done

# Fix Cheetah Compiler to generate code with correct imports for package structure
print_status "Fixing Cheetah template compilation imports..."
if [ -f "src/pytivo/Cheetah/Compiler.py" ]; then
    # The compiler generates "from Cheetah.Template import" and "import Cheetah.Filters" in compiled templates
    # Change them to generate "from pytivo.Cheetah.Template import" and "import pytivo.Cheetah.Filters"
    sed -i.bak "s|'from Cheetah\.|'from pytivo.Cheetah.|g" "src/pytivo/Cheetah/Compiler.py"
    sed -i.bak 's|"from Cheetah\.|"from pytivo.Cheetah.|g' "src/pytivo/Cheetah/Compiler.py"
    sed -i.bak "s|'import Cheetah\.|'import pytivo.Cheetah.|g" "src/pytivo/Cheetah/Compiler.py"
    sed -i.bak 's|"import Cheetah\.|"import pytivo.Cheetah.|g' "src/pytivo/Cheetah/Compiler.py"
    print_success "Cheetah compiler fixed to generate package-aware imports"
fi

# Fix internal mutagen imports if any
for pyfile in src/pytivo/mutagen/*.py; do
    if [ -f "$pyfile" ]; then
        sed -i.bak "s|^from mutagen\.|from .|" "$pyfile"
        sed -i.bak "s|^import mutagen\.|from . import |" "$pyfile"
        # Fix references like mutagen._util in class definitions
        sed -i.bak "s|mutagen\._util|_util|g" "$pyfile"
        sed -i.bak "s|mutagen\.version_string|version_string|g" "$pyfile"
    fi
done

# In plugin files that import mutagen and Cheetah
for pyfile in src/pytivo/plugins/*/*.py; do
    if [ -f "$pyfile" ]; then
        # Fix "from mutagen" -> "from ...mutagen"
        sed -i.bak "s/^from mutagen\./from ...mutagen./" "$pyfile"
        sed -i.bak "s/^import mutagen$/from ... import mutagen/" "$pyfile"
        # Fix "from Cheetah" -> "from ...Cheetah" (plugins are 2 levels deep)
        sed -i.bak "s/^from Cheetah\./from ...Cheetah./" "$pyfile"
        sed -i.bak "s/^import Cheetah$/from ... import Cheetah/" "$pyfile"
    fi
done

# Clean up backup files
find src -name "*.bak" -delete

print_success "Imports fixed for package structure"

# Update pyTivo.py to add main() function
print_status "Adding main() entry point to pyTivo.py..."
if ! grep -q "^def main():" src/pytivo/pyTivo.py; then
    cat >> src/pytivo/pyTivo.py << 'EOF'

def main():
    """Entry point for console script"""
    httpd = setup()
    serve(httpd)

if __name__ == '__main__':
    main()
EOF
    print_success "main() entry point added"
else
    print_warning "main() entry point already exists"
fi

# Update pyTivoService.py to add main() function if needed
print_status "Checking pyTivoService.py..."
if [ -f src/pytivo/pyTivoService.py ]; then
    if ! grep -q "^def main():" src/pytivo/pyTivoService.py; then
        echo "" >> src/pytivo/pyTivoService.py
        echo "def main():" >> src/pytivo/pyTivoService.py
        echo '    """Entry point for service script"""' >> src/pytivo/pyTivoService.py
        echo "    pass  # Service entry point" >> src/pytivo/pyTivoService.py
        print_success "Service main() entry point added"
    fi
fi

# Clean up bytecode
print_status "Cleaning up bytecode files..."
find src -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find src -type f -name "*.pyc" -delete 2>/dev/null || true
find src -type f -name "*.pyo" -delete 2>/dev/null || true
print_success "Cleanup complete"

echo ""
print_success "Package structure created successfully!"
echo ""
echo "Next steps to build the package:"
echo ""
echo "  1. Build wheel and source distribution:"
echo "     python3 -m build"
echo ""
echo "  2. Or build egg (deprecated but still works):"
echo "     python3 setup.py bdist_egg"
echo ""
echo "  3. Install locally for testing:"
echo "     pip3 install -e ."
echo ""
echo "  4. Install from wheel:"
echo "     pip3 install dist/pyTivo-1.0.0-py3-none-any.whl"
echo ""
echo "Package structure:"
echo "  src/pytivo/          - Main package"
echo "  src/pytivo/plugins/  - Plugin modules"
echo "  setup.py             - Setup script"
echo "  pyproject.toml       - Modern build config"
echo ""
