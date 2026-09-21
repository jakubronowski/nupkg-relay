import subprocess
from html import escape
from .logger import logger

def run_command(command: list[str], cwd=None, timeout: int = 1200):
    logger.info("Executing command: %s", " ".join(command))
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
            check=True
        )
        for line in result.stdout.splitlines():
            logger.info("  [dotnet] %s", line)
    except subprocess.CalledProcessError as e:
        logger.error("Command failed with exit code %d", e.returncode)
        for line in e.stdout.splitlines():
            logger.error("  [dotnet error] %s", line)
        raise RuntimeError(f"Command failed: {' '.join(command)}")
    except subprocess.TimeoutExpired:
        logger.error("Command timed out after %d seconds", timeout)
        raise RuntimeError(f"Command timed out: {' '.join(command)}")

def xml_escape(text: str) -> str:
    return escape(text, quote=True)