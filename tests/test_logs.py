import logging

from dava.logs import setup_logging, get_recent_logs, in_memory_logs, MemoryHandler


class TestSetupLogging:
    def test_sets_root_logger_level(self):
        setup_logging()
        root = logging.getLogger()
        assert root.level == logging.DEBUG

    def test_adds_handlers(self):
        setup_logging()
        root = logging.getLogger()
        handler_types = [type(h).__name__ for h in root.handlers]
        assert "MemoryHandler" in handler_types
        assert "RotatingFileHandler" in handler_types
        assert "StreamHandler" in handler_types

    def test_memory_handler_added(self):
        setup_logging()
        memory_handlers = [h for h in logging.getLogger().handlers if isinstance(h, MemoryHandler)]
        assert len(memory_handlers) >= 1


class TestGetRecentLogs:
    def test_returns_recent_entries(self):
        in_memory_logs.clear()
        setup_logging()
        logger = logging.getLogger("test_module")
        logger.info("test message 1")
        logger.info("test message 2")
        logs = get_recent_logs(2)
        assert len(logs) == 2
        assert "test message 1" in logs[0]
        assert "test message 2" in logs[1]

    def test_returns_all_if_count_exceeds_buffer(self):
        in_memory_logs.clear()
        setup_logging()
        logger = logging.getLogger("test_module2")
        logger.info("only one")
        logs = get_recent_logs(100)
        assert len(logs) >= 1

    def test_zero_count(self):
        in_memory_logs.clear()
        setup_logging()
        logger = logging.getLogger("test_module3")
        logger.info("message")
        logs = get_recent_logs(0)
        assert logs == []