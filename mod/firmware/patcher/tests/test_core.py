"""Container and structural discovery contracts. Run from /tmp with Python -I."""
from pathlib import Path
import importlib.util
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from corpus import ORIGINALS, LEGACY, legacy_files, historical_input, fixture

class Core(unittest.TestCase):
    def test_distribution_exists(self):
        self.assertTrue((ROOT / 'seplos' / 'image.py').exists(), 'strict container reader missing')

    def test_all_oem_roundtrip(self):
        from seplos.image import Image, ImageError
        for path in sorted((ORIGINALS).glob('*.ehex')):
            with self.subTest(path=path.name):
                image = Image.read(path)
                self.assertEqual(Image.parse(image.render()), image)
                self.assertTrue(0x20001000 <= image.sp < 0x20004000)
                self.assertEqual(image.app[4] & 1, 1)
                lines = image.render().splitlines()
                lines[16] = lines[16][:-2] + ('00' if lines[16][-2:] != '00' else '01')
                with self.assertRaises(ImageError):
                    Image.parse('\n'.join(lines))

    def test_discovery_not_version_addresses(self):
        from seplos.image import Image
        from seplos.analysis import discover
        for path in sorted((ORIGINALS).glob('*.ehex')):
            with self.subTest(path=path.name):
                image = Image.read(path)
                facts = discover(image)
                for key in ('loader', 'serializer', 'validator', 'crc', 'lcd_read', 'lcd_write', 'uart1_send', 'dip', 'iap_read', 'iap_write', 'iap_erase', 'iap_program'):
                    self.assertTrue(0xC0 <= facts['functions'][key] < len(image.app), key)
                self.assertEqual(len(facts['hooks']), 4)
                self.assertEqual(facts['sp'], image.sp)
                self.assertEqual(facts['functions']['irq'], int.from_bytes(image.app[0x50:0x54], 'little') & ~1)
                self.assertTrue(facts['evidence'])

if __name__ == '__main__':
    unittest.main()
