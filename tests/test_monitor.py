import tempfile
import unittest
from pathlib import Path
from waterforce_linux.monitor import read_temperature


class SensorTests(unittest.TestCase):
    def test_real_and_invalid_readings(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "temp1_input"
            path.write_text("42875\n")
            self.assertEqual(read_temperature(path), 43)
            for value in ("0", "-1", "120000", "not available"):
                path.write_text(value)
                with self.assertRaises(ValueError):
                    read_temperature(path)
            path.unlink()
            with self.assertRaises(OSError):
                read_temperature(path)
        with self.assertRaises(ValueError):
            read_temperature(None)


if __name__ == "__main__":
    unittest.main()

class F2PacketTests(unittest.TestCase):
    def test_windows_f2_layout(self):
        from waterforce_linux.monitor import f2_sensor_payload
        wire = b'\x99' + f2_sensor_payload(47, 12, 5321)
        self.assertEqual(len(wire), 24)
        self.assertEqual(wire[:2], bytes.fromhex('99e0'))
        self.assertEqual(wire[4], 47)
        self.assertEqual(wire[6:8], bytes([5, 3]))
        self.assertEqual(wire[11], 12)
        self.assertEqual(wire[2:4], bytes(2))
        self.assertEqual(wire[12:], bytes(12))
        for t in (0, -1, 111):
            with self.assertRaises(ValueError): f2_sensor_payload(t, 12, 5321)
