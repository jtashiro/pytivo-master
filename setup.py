#!/usr/bin/env python3
"""
pyTivo - TiVo HMO server for Python 3
"""

from setuptools import setup, find_packages
import os

def read_long_description():
    try:
        with open('README', 'r') as f:
            return f.read()
    except:
        return "pyTivo - TiVo HMO server"

def get_version():
    """Extract version from pyTivo.py"""
    # For now, set a default version
    return "1.0.0"

setup(
    name='pyTivo',
    version=get_version(),
    description='TiVo HMO and GoBack server',
    long_description=read_long_description(),
    author='pyTivo Contributors',
    url='https://github.com/wmcbrine/pytivo',
    license='GPL-2.0',
    
    packages=find_packages(where='src'),
    package_dir={'': 'src'},
    
    # Include package data
    package_data={
        'pytivo': [
            'content/*.css',
            'templates/*.tmpl',
        ],
        'pytivo.plugins.music': ['templates/*.tmpl'],
        'pytivo.plugins.photo': ['templates/*.tmpl'],
        'pytivo.plugins.settings': [
            'templates/*.tmpl',
            'content/*.css',
            'content/*.js',
            'help.txt',
        ],
        'pytivo.plugins.togo': ['templates/*.tmpl'],
        'pytivo.plugins.video': ['templates/*.tmpl'],
    },
    
    # Entry points for command-line scripts
    entry_points={
        'console_scripts': [
            'pytivo=pytivo.pyTivo:main',
            'pytivo-service=pytivo.pyTivoService:main',
        ],
    },
    
    # Dependencies
    install_requires=[
        # No external dependencies - includes bundled Cheetah and mutagen
    ],
    
    # Python version requirement
    python_requires='>=3.6',
    
    # Classifiers
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: End Users/Desktop',
        'License :: OSI Approved :: GNU General Public License v2 (GPLv2)',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Programming Language :: Python :: 3.13',
        'Topic :: Multimedia :: Video',
    ],
    
    # Include additional files
    include_package_data=True,
    zip_safe=False,
)
