import unittest
from unittest.mock import patch
from waterforce_linux.__main__ import display_temperature

class FakeCooler:
    def __init__(self, version):
        self.version = version
        self.flags = bytearray(52 if version == '2.0' else 24)
        self.flags[-1] = 1
        self.mode = 7
        self.saved = False
        self.sent = []
    def firmware(self): return self.version
    def query(self, command): return b'\x99\xdf' + self.flags + bytes(256 - 2 - len(self.flags))
    def screen_mode(self): return self.mode
    def send(self, p):
        self.sent.append(p)
        if p[0] == 0xe2:
            if self.mode != 1: raise AssertionError('Select mode before writing its fields')
            self.flags = bytearray(p[1:])
        if p[0] == 0xe7: self.mode = p[1]
    def save(self): self.saved = True

class DisplayTests(unittest.TestCase):
    @patch('waterforce_linux.__main__.time.sleep')
    def test_version_width_and_preserved_other_zones(self, sleep):
        for version, width in [('1.2', 6), ('2.0', 13)]:
            c = FakeCooler(version)
            display_temperature(c)
            self.assertEqual(len(c.flags), width * 4)
            self.assertEqual(c.flags[:width], bytes([0,0,0,1]) + bytes(width-4))
            self.assertEqual(c.flags[-1], 1)
            self.assertFalse(c.saved)
    @patch('waterforce_linux.__main__.time.sleep')
    def test_save_only_after_readback(self, sleep):
        c = FakeCooler('2.0')
        display_temperature(c, True)
        self.assertTrue(c.saved)
        c = FakeCooler('2.0')
        with patch.object(c, 'screen_mode', return_value=7):
            with self.assertRaises(RuntimeError): display_temperature(c, True)
        self.assertFalse(c.saved)
