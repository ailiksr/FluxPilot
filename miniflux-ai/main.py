"""
Main entry point for the Miniflux-AI application.
"""

import datetime
import os
import signal
import sys
import threading
import traceback
from typing import NoReturn

import schedule
from common import config, shutdown_event
from common.logger import get_logger
from core import generate_daily_digest, get_miniflux_client, handle_unread_entries, init_digest_feed
from core.entry_handler import initialize_executor, shutdown_executor
from app import create_app

logger = get_logger(__name__)


def run_flask_server() -> None:
    """Start the WSGI server, with a dependency-free fallback for offline builds."""
    try:
        app = create_app()
        try:
            from waitress import serve
        except ImportError:
            logger.warning("Waitress is unavailable; using the existing Flask server fallback")
            app.run(host="0.0.0.0", port=80, threaded=True)
        else:
            logger.info("Starting Waitress server on 0.0.0.0:80")
            serve(app, host="0.0.0.0", port=80, threads=max(4, int(config.llm_max_workers) + 2), _quiet=True)
    except Exception as e:
        logger.error(f"WSGI server failed: {e}")
        logger.error(traceback.format_exc())
        shutdown_event.set()


def run_scheduler() -> None:
    try:
        if config.digest_schedule:
            init_digest_feed()
            for digest_time in config.digest_schedule:
                schedule.every().day.at(digest_time).do(generate_daily_digest)
                logger.info(f"Scheduled daily digest at {digest_time}")
        interval = 15 if config.miniflux_webhook_secret else 1
        unread_entries_job = schedule.every(interval).minutes.do(handle_unread_entries)
        logger.info(f"Scheduled entry processing every {interval} minute(s)")
        unread_entries_job.next_run = datetime.datetime.now()

        try:
            from core.feed_healer import heal_all_feeds
            schedule.every(30).minutes.do(heal_all_feeds)
            logger.info("Scheduled feed self-healing patrol every 30 minutes")
        except Exception as heal_init_err:
            logger.warning(f"Could not register self-healing patrol: {heal_init_err}")

        try:
            from core.storage_patrol import run_storage_sync
            schedule.every(10).minutes.do(run_storage_sync)
            logger.info("Scheduled in-container storage sync patrol every 10 minutes")
            # Run initial sync on startup
            run_storage_sync()
        except Exception as patrol_err:
            logger.warning(f"Could not register storage patrol: {patrol_err}")
        while not shutdown_event.is_set():
            schedule.run_pending()
            shutdown_event.wait(1)
        logger.info("Scheduler stopped")
    except Exception as e:
        logger.error(f"Scheduler failed: {e}")
        logger.error(traceback.format_exc())
        shutdown_event.set()


def handle_shutdown(signum: int, frame) -> None:
    logger.info(f"Received {signal.Signals(signum).name}, initiating graceful shutdown...")
    shutdown_event.set()


def initialize_application() -> None:
    try:
        os.makedirs("data", exist_ok=True)
        get_miniflux_client()
        initialize_executor()
        logger.info("Application initialized")
    except Exception as e:
        logger.error(f"Failed to initialize application: {e}")
        logger.error(traceback.format_exc())
        sys.exit(1)


def setup_signal_handlers() -> None:
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)
    logger.info("Signal handlers registered")


def cleanup_application() -> None:
    try:
        shutdown_executor()
        logger.info("Application resources cleaned up")
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")
        logger.error(traceback.format_exc())


def main() -> NoReturn:
    logger.info("=" * 60)
    logger.info("Miniflux-AI Application Starting")
    logger.info("=" * 60)
    initialize_application()
    setup_signal_handlers()
    flask_thread = threading.Thread(target=run_flask_server, name="FlaskServer", daemon=True)
    schedule_thread = threading.Thread(target=run_scheduler, name="Scheduler", daemon=False)
    flask_thread.start()
    logger.info("Flask server thread started")
    schedule_thread.start()
    logger.info("Scheduler thread started")
    try:
        schedule_thread.join()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
        shutdown_event.set()
    cleanup_application()
    logger.info("=" * 60)
    logger.info("Miniflux-AI Application Stopped")
    logger.info("=" * 60)
    sys.exit(0)


if __name__ == "__main__":
    main()
