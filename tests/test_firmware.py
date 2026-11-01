import unittest
from unittest.mock import patch
from pathlib import Path
import tempfile
from waterforce_linux import firmware as w

class ProtocolTests(unittest.TestCase):
    def test_original_framing_and_remainder(self):
        data=bytes(range(256))*49
        packets=list(w.reports(data))
        self.assertTrue(all(len(p)==6144 for p,_ in packets))
        first=packets[0][0]
        self.assertEqual(first[:3],bytes.fromhex('99a201'))
        self.assertEqual(int.from_bytes(first[3:7],'big'),len(data))
        self.assertEqual(first[7],len(w.PKG_NAME)+1)
        self.assertEqual(first[8:8+len(w.PKG_NAME)],w.PKG_NAME)
        chunks=[p[2:] for p,_ in packets[1:-3]]
        self.assertEqual(b''.join(chunks)[:len(data)],data)
        rem=len(data)%6142
        self.assertEqual(chunks[-1][rem:],chunks[-2][rem:])
        self.assertEqual(packets[-3][0][:7],bytes.fromhex('99a200')+len(data).to_bytes(4,'big'))
        self.assertEqual(packets[-2][0][:4],bytes.fromhex('99e70100'))
        self.assertEqual(packets[-1][0][:2],bytes.fromhex('99a1'))
    def test_exact_multiple_no_extra_data(self):
        self.assertEqual(len(list(w.reports(b'x'*6142))),5)
        self.assertEqual(len(list(w.reports(b'x'*12284))),6)
    def test_small_packet_zero_tail(self):
        p=list(w.reports(b'abc'))[1][0]
        self.assertEqual(p[:5],b'\x99\xa0abc')
        self.assertEqual(set(p[5:]),{0})
    def test_modified_pkg_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'bad.pkg';p.write_bytes(b'bad')
            with self.assertRaises(ValueError):w.validate(p)
    def test_confirmation_before_access(self):
        with patch.object(w,'Device') as dev:
            with self.assertRaises(ValueError):w.flash(b'bad','')
            dev.assert_not_called()
    def test_partial_write_is_fatal(self):
        d=object.__new__(w.Device);d.fd=42
        with patch.object(w.os,'write',return_value=6143) as write:
            with self.assertRaises(IOError):d.write(bytes(6144))
            self.assertEqual(write.call_count,1)
    def test_write_failure_never_commits(self):
        with patch.object(w.os,'geteuid',return_value=0),patch.object(w,'require_idle'),patch.object(w,'Device') as cls,patch.object(w.time,'sleep'):
            dev=cls.return_value
            dev.info.return_value={'firmware':(1,2)}
            dev.write.side_effect=[None,OSError('USB disconnected')]
            with self.assertRaises(OSError):w.flash(b'x'*100,'FLASH-0414:7a5e-F1.2-TO-F2.0')
            self.assertEqual(dev.write.call_count,2)
            self.assertEqual([c.args[0][1] for c in dev.write.call_args_list],[0xa2,0xa0])
            dev.close.assert_called_once()
    def test_wrong_version_never_writes(self):
        with patch.object(w.os,'geteuid',return_value=0),patch.object(w,'require_idle'),patch.object(w,'Device') as cls:
            cls.return_value.info.return_value={'firmware':(2,0)}
            with self.assertRaises(RuntimeError):w.flash(b'x','FLASH-0414:7a5e-F1.2-TO-F2.0')
            cls.return_value.write.assert_not_called()

if __name__=='__main__':unittest.main()
