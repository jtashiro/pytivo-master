# pyTivo Package Build Instructions

This directory contains the necessary files to build pyTivo as a Python package (egg/wheel format).

## Quick Start

### 1. Create Package Structure

Run the provided script to reorganize files into proper package layout:

```bash
./create_package_structure.sh
```

This creates a `src/pytivo/` directory with the proper structure.

### 2. Install Build Tools

```bash
pip3 install --upgrade build setuptools wheel
```

### 3. Build the Package

**Build wheel (recommended):**
```bash
python3 -m build
```

**Or build egg (legacy):**
```bash
python3 setup.py bdist_egg
```

### 4. Install

**Install in development mode (editable):**
```bash
pip3 install -e .
```

**Install from wheel:**
```bash
pip3 install dist/pyTivo-1.0.0-py3-none-any.whl
```

**Install from egg:**
```bash
easy_install dist/pyTivo-1.0.0-py3.13.egg
```

## Package Structure

After running `create_package_structure.sh`:

```
pytivo-master/
├── setup.py              # Setup script (legacy/egg support)
├── pyproject.toml        # Modern build configuration
├── MANIFEST.in           # Additional files to include
├── README                # Documentation
├── pyTivo.conf.dist      # Example configuration
├── src/
│   └── pytivo/
│       ├── __init__.py
│       ├── pyTivo.py
│       ├── beacon.py
│       ├── config.py
│       ├── httpserver.py
│       ├── lrucache.py
│       ├── metadata.py
│       ├── plugin.py
│       ├── turing.py
│       ├── zeroconf.py
│       ├── Cheetah/      # Bundled template engine
│       ├── mutagen/      # Bundled media library
│       ├── content/      # CSS files
│       ├── templates/    # Template files
│       └── plugins/
│           ├── music/
│           ├── photo/
│           ├── settings/
│           ├── togo/
│           └── video/
├── build/                # Generated during build
└── dist/                 # Built packages appear here
```

## Configuration After Installation

After installing the package, you'll need to create a configuration file:

1. Copy the example config:
   ```bash
   cp /usr/local/lib/python3.*/site-packages/pytivo/pyTivo.conf.dist ~/pyTivo.conf
   ```

2. Edit `~/pyTivo.conf` with your settings

3. Run pyTivo:
   ```bash
   pytivo
   ```

Or specify config location:
```bash
pytivo --config /path/to/pyTivo.conf
```

## Development

For development, install in editable mode:

```bash
pip3 install -e .
```

This allows you to edit source files in `src/pytivo/` and see changes immediately.

## Building for Distribution

To create packages for distribution:

```bash
# Clean previous builds
rm -rf build dist src/*.egg-info

# Build both wheel and source distribution
python3 -m build

# Results in dist/:
# - pyTivo-1.0.0-py3-none-any.whl (wheel)
# - pyTivo-1.0.0.tar.gz (source)
```

## Uninstalling

```bash
pip3 uninstall pyTivo
```

## Entry Points

After installation, these commands are available:

- `pytivo` - Start the pyTivo server
- `pytivo-service` - Service mode entry point

## Notes

- The original flat file structure remains in the root directory for direct execution
- The `src/pytivo/` structure is created by `create_package_structure.sh` for packaging
- Both structures can coexist - use root for development, src/ for distribution
