import logging
import os
from logging.handlers import TimedRotatingFileHandler

class Logger:
    @staticmethod
    def load_logger():
        """Returns a logger instance that keeps logs only for the last 7 days (file.log(new)/file1.log(1 day old))."""
        
        #Set log file location here
        LOG_FILE = "../logs/vmsentry.log"

        logger = logging.getLogger("VMSentry")
        logger.setLevel(logging.INFO)

        # Ensure log directory exists
        log_dir = os.path.dirname(LOG_FILE)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)

        # Rotating file handler: rotates every day at midnight, keeps 7 days of logs
        handler = TimedRotatingFileHandler(LOG_FILE, when="midnight", interval=1, backupCount=7, encoding="utf-8", utc=True)
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))

        # Avoid duplicate handlers if this function is called multiple times
        if not logger.handlers:
            logger.addHandler(handler)

        return logger
