"""
Runtime fix for cgi module imports in Python 3.13+
Add this to your manage.py file at the top
"""
import sys
import os
import importlib.machinery
import importlib.util

# Add the project directory to sys.path to ensure our cgi.py is found first
project_dir = os.path.dirname(os.path.abspath(__file__))
if project_dir not in sys.path:
    sys.path.insert(0, project_dir)

# Define the hook
original_import = __import__

def patched_import(name, globals=None, locals=None, fromlist=(), level=0):
    if name == 'cgi' and fromlist:
        # Try to import our custom cgi module
        try:
            # First, check if our module is already loaded
            if 'cgi' in sys.modules:
                return sys.modules['cgi']

            # Load our custom cgi module
            spec = importlib.machinery.PathFinder.find_spec('cgi', [project_dir])
            if spec:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                sys.modules['cgi'] = module
                return module
        except Exception as e:
            print(f"Error loading custom cgi module: {e}")

    # Fall back to original import
    return original_import(name, globals, locals, fromlist, level)

# Apply the patch
__builtins__['__import__'] = patched_import

print("CGI import patch applied")
