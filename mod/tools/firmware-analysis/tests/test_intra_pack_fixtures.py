import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('fixture_check', Path(__file__).resolve().parents[1]/'verify_intra_pack_fixtures.py')
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


def frame():
    # Synthetic fixture, no installation data: 32 zero payload bytes.
    raw = '2001465AC040'+'00'*32
    return '~'+raw+f'{-sum(raw.encode()) & 65535:04X}'+'\r'


class FixtureTests(unittest.TestCase):
    def test_decode_and_reject_corruption(self):
        wire = frame()
        self.assertEqual(check.decode(wire)['address'], 1)
        for broken in (wire[:-1], wire[:20]+'F'+wire[21:], wire[:9]+'D040'+wire[13:]):
            with self.subTest(frame=broken), self.assertRaises(ValueError):
                check.decode(broken)

    def test_readback_mismatch_is_not_success(self):
        data = check.decode(frame())
        with self.assertRaisesRegex(ValueError, 'soc_pct'):
            check.compare(data, {'soc_pct': 100}, complete=False)
        with self.assertRaisesRegex(ValueError, 'field set'):
            check.compare(data, {'soc_pct': 0}, complete=True)

    def test_separate_example_must_match_original_source_range(self):
        wire = frame()
        printed = wire[:-1]+'\\r'
        example = dict(wire_ascii=wire, raw_source_ascii=printed,
                       expected=check.decode(wire), source_lines=[1, 1],
                       log_bytes_dotted='.'.join(wire[1:-5][i:i+2] for i in range(0, len(wire[1:-5]), 2)))
        # Internally consistent data must not be accepted as another source's example.
        with self.assertRaisesRegex(ValueError, 'source'):
            check.verify_example(example, ['A different original source frame'])
        example['source_lines'] = [1, 2]
        check.verify_example(example, [printed, example['log_bytes_dotted']])
