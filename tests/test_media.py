import unittest
from unittest.mock import patch
from waterforce_linux import media
from waterforce_linux.device import CHUNK


class FakeCooler:
    def __init__(self):
        self.sent = []
        self.names = ['original.mkv']
        self.pending = None
        self.free = 40000
        self.position = 0
        self.mode = 1
        self.saved = False
        self.commit = True
    def send(self, p):
        self.sent.append(p)
        if p[:2] == b'\xf1\x01': self.pending = p[7:].decode()
        if p[:2] == b'\xf1\x02' and self.commit: self.names.append(self.pending)
        if p[:2] == b'\xf6\x07': self.position = p[3]
        if p[0] == 0xe7: self.mode = p[1]
    def query(self, p, match=1):
        if p[0] == 0xf4: return b'\x99\xf4\x02' + bytes([len(self.names)])
        if p[0] == 0xf5: return b'\x99' + p + bytes(2) + self.names[p[2]].encode() + bytes(1)
        if p[0] == 0xfd: return bytes([0x99, 0xfd, 7, 10, self.position, 0])
        raise AssertionError(p)
    def storage_free_kb(self): return self.free
    def screen_mode(self): return self.mode
    def save(self): self.saved = True


@patch('waterforce_linux.media.time.sleep')
class MediaTests(unittest.TestCase):
    def test_chunks_and_existing_media_preserved(self, sleep):
        for n in (1, CHUNK, CHUNK + 1, CHUNK * 2):
            c = FakeCooler()
            media.upload(c, b'x' * n, 'new.mkv')
            packets = [p for p in c.sent if p[0] == 0xf2]
            self.assertEqual(b''.join(p[2:] for p in packets), b'x' * n)
            self.assertEqual(len(packets), (n + CHUNK - 1)//CHUNK)
            self.assertEqual(packets[-1][1], 0xfd if n % CHUNK == 0 else (n % CHUNK) & 255)
            self.assertIn(b'\xf1\x02' + n.to_bytes(4, 'big'), c.sent)
            self.assertEqual(c.names, ['original.mkv', 'new.mkv'])
            self.assertEqual(c.mode, 1)
    def test_refuse_overwrite_and_low_space(self, sleep):
        for name, free in [('ORIGINAL.mkv', 40000), ('new.mkv', 0)]:
            c = FakeCooler(); c.free = free
            with self.assertRaises(ValueError): media.upload(c, b'x', name)
            self.assertFalse(any(p[0] in (0xf1, 0xf2) for p in c.sent))
    def test_invalid_names_never_access_device(self, sleep):
        for name in ('../x.mkv', 'x\n.mkv', 'B:x.mkv', 'x.gif', 'a'*65+'.mkv'):
            c = FakeCooler()
            with self.assertRaises(ValueError): media.upload(c, b'x', name)
            self.assertEqual(c.sent, [])
    def test_failed_transfer_never_commits(self, sleep):
        c = FakeCooler(); original = c.send
        def fail(p):
            if p[0] == 0xf2: raise IOError('write failed')
            original(p)
        c.send = fail
        with self.assertRaises(IOError): media.upload(c, b'x', 'new.mkv')
        self.assertFalse(any(p[:2] == b'\xf1\x02' for p in c.sent))
    def test_unconfirmed_upload_times_out(self, sleep):
        c = FakeCooler(); c.commit = False
        with self.assertRaises(TimeoutError): media.upload(c, b'x', 'new.mkv', timeout=0)
        self.assertEqual(c.mode, 1)
    def test_play_uses_position_without_reorder_or_delete(self, sleep):
        c = FakeCooler(); c.names.append('new.mkv')
        media.play(c, 'new.mkv')
        self.assertEqual(c.position, 2)
        self.assertTrue(c.saved)
        self.assertFalse(any(p[0] in (0xf0, 0xfe) for p in c.sent))
    def test_readback_failure_does_not_save(self, sleep):
        c = FakeCooler()
        with patch.object(c, 'screen_mode', return_value=1):
            with self.assertRaises(RuntimeError): media.play(c, 'original.mkv')
        self.assertFalse(c.saved)


class ServiceTests(unittest.TestCase):
    def test_service_restored_if_device_open_fails(self):
        with patch.object(media.os, 'geteuid', return_value=0), patch.object(media, 'require_idle'), \
             patch.object(media, 'Cooler', side_effect=IOError('USB')), \
             patch.object(media.subprocess, 'run') as run:
            run.return_value.returncode = 0
            with self.assertRaises(IOError):
                with media.idle_device(True): pass
            calls = [c.args[0] for c in run.call_args_list]
            for name in ('waterforce-monitor', 'waterforce-linux'):
                self.assertIn(['systemctl', 'start', name], calls)
