"""Centralized logging configuration for the application."""

import logging
import sys

DEBUG_MODE = True

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)


def get_logger(name: str | None = None):
    base_level = logging.DEBUG if DEBUG_MODE else logging.INFO
    root_logger = logging.getLogger()
    root_logger.setLevel(base_level)
    if name is None:
        return root_logger
    logger = logging.getLogger(name)
    logger.setLevel(base_level)
    return logger
