#!/usr/bin/env python3

import py_compile
import sys
import os

def check_file(filepath):
    print(f"Checking {filepath}")
    try:
        py_compile.compile(filepath, doraise=True)
        print(f"✓ {filepath} is syntactically correct")
        return True
    except py_compile.PyCompileError as e:
        print(f"✗ {filepath} has syntax errors:")
        print(e)
        return False

if __name__ == "__main__":
    files_to_check = [
        "smart-restroom-cli.py",
        "central-hub-mod/cen_mod_main.py"
    ]
    
    success = True
    for file in files_to_check:
        if not check_file(file):
            success = False
    
    sys.exit(0 if success else 1) 