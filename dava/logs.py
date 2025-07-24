import logging
import logging.handlers
from collections import deque
from typing import List

log_filename = f"logs/dava.log"
# Add in-memory log storage with max 1000 entries
in_memory_logs = deque(maxlen=1000)

class MemoryHandler(logging.Handler):
    def emit(self, record):
        log_entry = self.format(record)
        in_memory_logs.append(log_entry)

def setup_logging():
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(filename)s - %(lineno)d - %(message)s')
    
    # File handler
    file_handler = logging.handlers.RotatingFileHandler(
        log_filename, 
        backupCount=3, 
        maxBytes=5_000_000
    )
    file_handler.setFormatter(formatter)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    
    # Memory handler
    memory_handler = MemoryHandler()
    memory_handler.setFormatter(formatter)
    
    root_logger.handlers = []
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(memory_handler)
    
    # Set lower level for third-party loggers
    for logger_name in ['aiohttp', 'asyncio']:
        logging.getLogger(logger_name).setLevel(logging.WARNING)
    logging.getLogger('telethon').setLevel(logging.ERROR)

def get_recent_logs(count: int = 50) -> List[str]:
    """Get recent log entries from memory buffer.
    
    Args:
        count: Number of log entries to return (default: 50)
    
    Returns:
        List of formatted log strings, most recent last
    """
    return list(in_memory_logs)[-count:] if count > 0 else []
