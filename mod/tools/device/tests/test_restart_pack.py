"""No hardware; reset must be addressed, sent once and followed by an outage."""

# Resolve shared tool paths independently of the working directory and Python -I.
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(next(p for p in _Path(__file__).resolve().parents if (p / '_paths.py').is_file())))
from _paths import PROJECT_ROOT, TOOLS_ROOT, PATCHER_ROOT, LOCAL_ROOT
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock, patch


class RestartTests(unittest.TestCase):
    def module(self):
        path=Path(__file__).resolve().parents[1]/'restart_pack.py'
        self.assertTrue(path.is_file(), 'restart client not yet implemented')
        spec=importlib.util.spec_from_file_location('restart_under_test',path)
        m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

    def test_rejects_broadcast_before_io(self):
        m=self.module();port=Mock()
        with self.assertRaises(ValueError):m.restart(port,255)
        port.write.assert_not_called()

    def test_reset_once_and_verify_identity_after_outage(self):
        m=self.module();port=Mock();port.write.side_effect=len;clock=[0.0]
        def sleep(seconds):clock[0]+=seconds
        replies=[b'version', b'serial', TimeoutError(), b'version', b'serial']
        with patch.object(m,'query',side_effect=replies):
            result=m.restart(port,7,wait=2,now=lambda:clock[0],sleep=sleep)
        self.assertTrue(result['outage_observed'])
        port.write.assert_called_once_with(b'~20074645A006000600FC67\r')

    def test_continuous_replies_do_not_prove_a_restart(self):
        m=self.module();port=Mock();port.write.side_effect=len;clock=[0.0]
        def sleep(seconds):clock[0]+=seconds
        with patch.object(m,'query',return_value=b'unchanged'):
            with self.assertRaises(RuntimeError):m.restart(port,7,wait=1,now=lambda:clock[0],sleep=sleep)
        self.assertEqual(port.write.call_count,1)


if __name__=='__main__':unittest.main()
