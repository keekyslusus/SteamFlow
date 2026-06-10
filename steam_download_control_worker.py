import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.resolve()
LIB_PATH = PROJECT_ROOT / "lib"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(LIB_PATH) not in sys.path:
    sys.path.insert(0, str(LIB_PATH))

from steamflow.download_control import perform_download_control
from steamflow.download_status_cache import set_download_control_status_hint
from steamflow.feature_health import (
    classify_feature_error,
    record_feature_failure,
    record_feature_success,
)


def configure_logger(secure_settings_dir):
    secure_settings_dir = Path(secure_settings_dir)
    secure_settings_dir.mkdir(parents=True, exist_ok=True)
    log_file = secure_settings_dir / "steam_download_control_worker.log"

    log_handler = RotatingFileHandler(
        log_file,
        maxBytes=512 * 1024,
        backupCount=1,
        encoding="utf-8",
    )
    log_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))

    logger = logging.getLogger("steam_download_control_worker")
    for handler in logger.handlers:
        handler.close()
    logger.handlers.clear()
    logger.addHandler(log_handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger


def main():
    if len(sys.argv) != 5:
        return 1

    secure_settings_dir, steamid64, app_id, action = sys.argv[1:]
    logger = configure_logger(secure_settings_dir)
    feature_health_cache_file = PROJECT_ROOT / "cache_feature_health.json"
    try:
        logger.info("Download control worker started for app %s action=%s", app_id, action)
        perform_download_control(secure_settings_dir, steamid64, app_id, action, logger=logger)
        set_download_control_status_hint(PROJECT_ROOT / "cache_download_progress.json", app_id, action)
        record_feature_success(feature_health_cache_file, "steam_session_token")
        record_feature_success(feature_health_cache_file, "download_control")
        logger.info("Download control worker finished for app %s action=%s", app_id, action)
        return 0
    except Exception as error:
        reason = classify_feature_error(error, "download_control")
        if reason in {"token_not_found", "htmlcache_missing", "token_rejected", "token_expired", "auth_rejected"}:
            record_feature_failure(feature_health_cache_file, "steam_session_token", error, reason=reason)
            record_feature_failure(feature_health_cache_file, "download_control", error, reason="dependency_failed")
        else:
            record_feature_failure(feature_health_cache_file, "download_control", error, reason=reason)
        logger.exception("Download control worker failed for app %s action=%s", app_id, action)
        return 1
    finally:
        for handler in logger.handlers:
            handler.close()
        logger.handlers.clear()


if __name__ == "__main__":
    sys.exit(main())
