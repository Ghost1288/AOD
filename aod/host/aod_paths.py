"""Where AOD keeps its data. A Windows service run uses C:\\ProgramData\\AOD and the real user's profile."""
import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("AOD_DATA_DIR") or (Path.home() / ".aod"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
USER_HOME = Path(os.environ.get("AOD_USER_HOME") or Path.home())
SERVICE = os.environ.get("AOD_SERVICE") == "1"
