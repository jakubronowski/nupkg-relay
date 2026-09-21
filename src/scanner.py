import time
import os
import json
import datetime
from pathlib import Path
from watchdog.observers.polling import PollingObserver as Observer
from watchdog.events import FileSystemEventHandler

from src.settings import DEFAULT_PACKAGES_DIR, HISTORY_DIR, NEXUS_API_KEY
from src.builder import PackageBuilder
from src.package_config import PackageConfig
from src.logger import logger

def is_already_processed(package_id: str, version: str) -> bool:
    """Checks if a discrete history state file exists for the given package and version."""
    history_file = HISTORY_DIR / f"{package_id}_{version}.json"
    return history_file.is_file()

def save_to_history(package_id: str, version: str):
    """Creates a dedicated JSON state file in the history directory confirming processing."""
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    history_file = HISTORY_DIR / f"{package_id}_{version}.json"
    
    data = {
        "package_id": package_id,
        "version": version,
        "processed_at": datetime.datetime.now().isoformat()
    }
    
    try:
        history_file.write_text(json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8")
        logger.info("Created state file: %s", history_file.name)
    except Exception as e:
        logger.error("Failed to save history file for '%s' v%s: %s", package_id, version, e)


class CombinedEventHandler(FileSystemEventHandler):
    """Unified handler supporting both package creation/modification and history deletions."""

    def __init__(self, watch_packages_dir: Path):
        self.watch_packages_dir = watch_packages_dir.resolve()

    def on_created(self, event):
        if event.is_directory:
            return
        safe_path = os.fsdecode(event.src_path)
        self._handle_package_event(Path(safe_path))

    def on_modified(self, event):
        if event.is_directory:
            return
        safe_path = os.fsdecode(event.src_path)
        self._handle_package_event(Path(safe_path))

    def on_deleted(self, event):
        if event.is_directory:
            return
        safe_path = os.fsdecode(event.src_path)
        deleted_path = Path(safe_path)

        if HISTORY_DIR.resolve() in deleted_path.parents or deleted_path.parent == HISTORY_DIR.resolve():
            filename = deleted_path.stem
            logger.info("History state file removed: %s.json", filename)
            self._trigger_rebuild_by_history_name(filename)

    def _handle_package_event(self, ready_path: Path):
        if ready_path.name != "READY":
            return

        try:
            version_dir = ready_path.parent
            version = version_dir.name
            package_dir = version_dir.parent.parent
            
            config_path = package_dir / "package.yaml"
            config = PackageConfig.from_yaml(config_path)
            package_id = config.id
            
        except Exception as e:
            logger.error("Failed to parse package configuration for %s: %s", ready_path, e)
            return

        if is_already_processed(package_id, version):
            return

        logger.info("Detected new ready package: ID '%s' v%s", package_id, version)
        self._build_and_publish(package_dir, package_id, version)

    def _trigger_rebuild_by_history_name(self, history_stem: str):
        parts = history_stem.rsplit("_", 1)
        if len(parts) != 2:
            logger.warning("Could not parse package ID and version from history name: %s", history_stem)
            return

        target_package_id, target_version = parts

        for ready_file in self.watch_packages_dir.glob("**/versions/*/READY"):
            try:
                version_dir = ready_file.parent
                version = version_dir.name
                if version != target_version:
                    continue
                
                package_dir = version_dir.parent.parent
                config_path = package_dir / "package.yaml"
                if not config_path.is_file():
                    continue
                    
                config = PackageConfig.from_yaml(config_path)
                if config.id == target_package_id:
                    logger.info("Rebuild triggered by history deletion for: ID '%s' v%s", target_package_id, target_version)
                    self._build_and_publish(package_dir, target_package_id, target_version)
                    return
            except Exception as e:
                logger.error("Error while resolving package for history stem %s: %s", history_stem, e)

    def _build_and_publish(self, package_dir: Path, package_id: str, version: str):
        try:
            builder = PackageBuilder(package_dir=package_dir, version=version)
            package_file = builder.build()
            builder.publish(package_file)
            
            save_to_history(package_id, version)
            logger.info("Success! Processed and saved state for: ID '%s' v%s", package_id, version)

        except Exception as e:
            logger.error("Error building package ID '%s' v%s: %s", package_id, version, e)


def initial_scan(watch_dir: Path):
    """Catches up on unprocessed packages during startup."""
    logger.info("Running initial catch-up scan for existing 'READY' packages...")
    
    if not watch_dir.exists():
        return

    for ready_file in watch_dir.glob("**/versions/*/READY"):
        try:
            version_dir = ready_file.parent
            version = version_dir.name
            package_dir = version_dir.parent.parent
            
            config_path = package_dir / "package.yaml"
            if not config_path.is_file():
                continue
                
            config = PackageConfig.from_yaml(config_path)
            package_id = config.id
            
            if not is_already_processed(package_id, version):
                logger.info("Found unprocessed historical package during startup: ID '%s' v%s", package_id, version)
                
                builder = PackageBuilder(package_dir=package_dir, version=version)
                package_file = builder.build()
                builder.publish(package_file)
                
                save_to_history(package_id, version)
                logger.info("Success! Processed historical package: ID '%s' v%s", package_id, version)
                
        except Exception as e:
            logger.error("Error processing historical package at %s: %s", ready_file, e)


def run_daemon():
    if not NEXUS_API_KEY:
        logger.error("CRITICAL: NEXUS_API_KEY environment variable is not set! Exiting.")
        return

    watch_dir = DEFAULT_PACKAGES_DIR
    if not watch_dir.exists():
        logger.error("Watch directory does not exist or is unreachable: %s", watch_dir)
        return

    HISTORY_DIR.mkdir(parents=True, exist_ok=True)

    logger.info("Starting nupkg-relay scanner daemon")
    logger.info("Watch directory (packages): %s", watch_dir)
    logger.info("History state directory: %s", HISTORY_DIR)

    initial_scan(watch_dir)

    logger.info("Listening for real-time 'READY' events and history deletions (Press Ctrl+C to stop)...")

    event_handler = CombinedEventHandler(watch_packages_dir=watch_dir)
    observer = Observer()
    
    try:
        observer.schedule(event_handler, str(watch_dir), recursive=True)
        observer.schedule(event_handler, str(HISTORY_DIR), recursive=False)
        observer.start()
    except Exception as e:
        logger.error("Failed to start filesystem observer: %s", e)
        return

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Stopping scanner daemon on user request...")
        observer.stop()
    
    observer.join()
    logger.info("Scanner daemon stopped cleanly.")