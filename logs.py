import logging
import os
import time

log_filename = f"logs/avatar_updater_{time.strftime('%Y%m%d_%H%M%S')}.log"

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_filename, mode='w'),
        logging.StreamHandler()
    ]
)

# Optional: Clean up old log files (older than 7 days)
def clean_old_logs(days_to_keep=7):
    cutoff = time.time() - days_to_keep * 86400
    for filename in os.listdir("logs"):
        if filename.startswith('avatar_updater_') and filename.endswith('.log'):
            file_time = os.path.getmtime("logs/" + filename)
            if file_time < cutoff:
                try:
                    os.remove("logs/" + filename)
                except OSError:
                    pass

clean_old_logs()
def setup_logging():
    for logger_name in ['telethon', 'aiohttp', 'asyncio']:
        logging.getLogger(logger_name).setLevel(logging.WARNING)