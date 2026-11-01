import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock
from waterforce_linux import presets


class FakeCooler:
    def __init__(self):
        self.mode = 1
        self.flags = bytes(52)
        self.saved = False
        self.sent = []
    def firmware(self): return '2.0'
    def modes(self): return (2, 0)
    def send(self, p):
        self.sent.append(p)
        if p[0] == 0xe7: self.mode = p[1]
        if p[0] == 0xe2: self.flags = p[1:]
    def screen_mode(self): return self.mode
    def query(self, p): return b'\x99\xdf' + self.flags
    def save(self): self.saved = True
    def send_cpu_name(self, name): self.label = name


class PresetTests(unittest.TestCase):
    @patch('waterforce_linux.presets.time.sleep')
    def test_every_preset_only_changes_display_commands(self, sleep):
        allowed = {0xfb, 0xe7, 0xe2, 0xe4, 0xaa, 0xac, 0xae}
        for name, spec in presets.PRESETS.items():
            c = FakeCooler()
            result = presets.apply(c, name, 'IP 192.0.2.10')
            self.assertEqual(c.mode, spec['mode'])
            self.assertTrue(c.saved)
            self.assertTrue(result['cooling_modes_unchanged'])
            self.assertTrue(all(p[0] in allowed for p in c.sent))
            if name == 'network': self.assertEqual(c.label, 'IP 192.0.2.10')
    @patch('waterforce_linux.presets.time.sleep')
    def test_bad_readback_does_not_save(self, sleep):
        c = FakeCooler()
        with patch.object(c, 'query', return_value=bytes(256)):
            with self.assertRaises(RuntimeError): presets.apply(c, 'dashboard')
        self.assertFalse(c.saved)
    @patch('waterforce_linux.presets.time.sleep')
    def test_cooling_mode_change_does_not_save(self, sleep):
        c = FakeCooler()
        with patch.object(c, 'modes', side_effect=[(2,0),(4,4)]):
            with self.assertRaises(RuntimeError): presets.apply(c, 'temperature')
        self.assertFalse(c.saved)
    def test_config_atomic_write_and_invalid_input(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'preset.json'
            presets.write_config({'preset':'network','interface':'eth0'},path)
            self.assertEqual(presets.read_config(path)['interface'],'eth0')
            path.write_text('{broken')
            self.assertEqual(presets.read_config(path),{})
            path.write_text(json.dumps({'preset':'network','interface':'bad;name'}))
            self.assertEqual(presets.read_config(path),{})
    @patch('waterforce_linux.presets.subprocess.run')
    def test_route_choice_and_offline(self, run):
        run.return_value=Mock(returncode=0, stdout='[{"prefsrc":"192.0.2.10"}]')
        self.assertEqual(presets.local_ip(),'192.0.2.10')
        self.assertEqual(presets.live_label({'preset':'network'}),'IP 192.0.2.10')
        run.return_value=Mock(returncode=1, stdout='')
        self.assertEqual(presets.live_label({'preset':'network'}),'IP OFFLINE')
    @patch('waterforce_linux.presets.subprocess.run')
    def test_interface_choice_and_invalid_name(self, run):
        run.return_value=Mock(returncode=0, stdout='[{"addr_info":[{"local":"192.0.2.20","scope":"global"}]}]')
        self.assertEqual(presets.local_ip('eth0'),'192.0.2.20')
        with self.assertRaises(ValueError): presets.local_ip('x;rm')

class MonitorPresetTests(unittest.TestCase):
    def test_network_label_keeps_real_telemetry_and_no_cooling_writes(self):
        from waterforce_linux import monitor
        c = Mock()
        c.firmware.return_value = '2.0'
        c.modes.return_value = (2, 0)
        c.rpm.return_value = (1400, 2700)
        sensors = Mock(temp_path='/fake/temp')
        sensors.load.return_value = 25
        sensors.freq_mhz.return_value = 4200
        context = Mock()
        context.__enter__ = Mock(return_value=c)
        context.__exit__ = Mock(return_value=False)
        with patch.object(monitor, 'Cooler', return_value=context), \
             patch.object(monitor, 'CpuSensors', return_value=sensors), \
             patch.object(monitor, 'read_temperature', return_value=45), \
             patch.object(monitor, 'read_config', return_value={'preset':'network'}), \
             patch.object(monitor, 'live_label', return_value='IP 192.0.2.10'):
            monitor.run(once=True)
        c.send_cpu_name.assert_called_once_with('IP 192.0.2.10')
        c.send.assert_called_once_with(monitor.f2_sensor_payload(45,25,4200))
