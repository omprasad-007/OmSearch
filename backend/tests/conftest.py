import sys
from pathlib import Path

# Add project root and backend dir to sys.path
backend_dir = Path(__file__).resolve().parent.parent
project_root = backend_dir.parent

if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))
