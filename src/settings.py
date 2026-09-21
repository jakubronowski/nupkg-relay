import os
from pathlib import Path

# Root directory of the project (/srv/nupkg-relay)
ROOT = Path(__file__).resolve().parent.parent

# Variable / runtime data directory
VAR_DIR = ROOT / "var"

# Working directories for dotnet, output .nupkg artifacts, and individual history state files
BUILD_DIR = VAR_DIR / "build"
OUTPUT_DIR = VAR_DIR / "output"
HISTORY_DIR = VAR_DIR / "history"

# Packages directory on the SMB share (or configurable via environment variable)
DEFAULT_PACKAGES_DIR = Path(os.getenv("CHOCO_PACKAGES_DIR", "/mnt/choco-packages"))

# Nexus repository configuration
NEXUS_SOURCE = os.getenv("NEXUS_SOURCE", "http://127.0.0.1:8080/repository/nexus/")
NEXUS_API_KEY = os.getenv("NEXUS_API_KEY", "")