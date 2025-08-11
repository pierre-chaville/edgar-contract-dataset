import os
import sys
from pathlib import Path


def _add_project_root_to_sys_path() -> None:
    project_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project_root))


_add_project_root_to_sys_path()


