import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from realtime_system_monitor import RealTimeSystemMonitor


class RealTimeSystemMonitorTests(unittest.TestCase):
    def test_set_target_pid_populates_process_metrics(self):
        monitor = RealTimeSystemMonitor(sample_interval=0.1, max_samples=16)
        monitor.set_target_pid(os.getpid())

        snapshot = monitor._capture_snapshot()

        self.assertGreater(snapshot.process_memory_mb, 0.0)
        self.assertGreaterEqual(snapshot.process_num_threads, 1)

    def test_capture_snapshot_retries_process_discovery_when_target_missing(self):
        monitor = RealTimeSystemMonitor(sample_interval=0.1, max_samples=16)
        monitor.target_process = None
        monitor.target_process_name = "mini-agent"

        with patch.object(monitor, "_find_target_process", return_value=None) as find_spy:
            monitor._capture_snapshot()
            find_spy.assert_called_with("mini-agent")

    def test_capture_snapshot_handles_cpu_freq_system_error(self):
        monitor = RealTimeSystemMonitor(sample_interval=0.1, max_samples=16)

        with patch("realtime_system_monitor.psutil.cpu_freq", side_effect=SystemError), \
             patch.object(monitor, "_find_target_process", return_value=None):
            snapshot = monitor._capture_snapshot()

        self.assertEqual(snapshot.cpu_freq_current, 0.0)

    def test_find_target_process_uses_exact_matching_for_short_name_hints(self):
        monitor = RealTimeSystemMonitor(sample_interval=0.1, max_samples=16)

        unrelated = MagicMock()
        unrelated.info = {"pid": 100, "name": "sync", "cmdline": ["/usr/bin/sync"]}
        target = MagicMock()
        target.info = {"pid": 200, "name": "cn", "cmdline": ["/usr/local/bin/cn", "-p", "hi"]}

        fake_process = MagicMock()
        fake_process.cpu_percent.return_value = 0.0

        with patch("realtime_system_monitor.psutil.process_iter", return_value=[unrelated, target]), \
             patch("realtime_system_monitor.psutil.Process", return_value=fake_process) as process_cls:
            monitor._find_target_process("cn")

        process_cls.assert_called_once_with(200)
        self.assertIsNotNone(monitor.target_process)


if __name__ == "__main__":
    unittest.main()
