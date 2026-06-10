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

from steamflow.feature_health import (
    classify_feature_error,
    record_feature_failure,
    record_feature_success,
)
from steamflow.wishlist_mutation_service import perform_wishlist_mutation


def configure_logger(secure_settings_dir):
    secure_settings_dir = Path(secure_settings_dir)
    secure_settings_dir.mkdir(parents=True, exist_ok=True)
    log_file = secure_settings_dir / "steam_wishlist_mutation_worker.log"

    log_handler = RotatingFileHandler(
        log_file,
        maxBytes=512 * 1024,
        backupCount=1,
        encoding="utf-8",
    )
    log_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))

    logger = logging.getLogger("steam_wishlist_mutation_worker")
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
        logger.info("Steam wishlist worker started for app %s action %s", app_id, action)
        perform_wishlist_mutation(secure_settings_dir, steamid64, app_id, action, logger=logger)
        record_feature_success(feature_health_cache_file, "steam_session_token")
        record_feature_success(feature_health_cache_file, "steam_wishlist")
        logger.info("Steam wishlist worker completed for app %s action %s", app_id, action)
        return 0
    except Exception as error:
        reason = classify_feature_error(error, "steam_wishlist")
        if reason in {"token_not_found", "htmlcache_missing", "token_rejected", "token_expired", "auth_rejected"}:
            record_feature_failure(feature_health_cache_file, "steam_session_token", error, reason=reason)
            record_feature_failure(feature_health_cache_file, "steam_wishlist", error, reason="dependency_failed")
        else:
            record_feature_failure(feature_health_cache_file, "steam_wishlist", error, reason=reason)
        logger.exception("Steam wishlist worker failed for app %s action %s", app_id, action)
        return 1
    finally:
        for handler in logger.handlers:
            handler.close()
        logger.handlers.clear()


if __name__ == "__main__":
    sys.exit(main())
