import unittest
from wire_reference import encode,decode


class ReferenceWireTests(unittest.TestCase):
    def packet(self,payload=b"abc"):
        return dict(type=4,ttl=8,path=[0x001122334455,0x001122334466],index=0,origin=0x001122334455,dst=0x001122334466,boot=0x12345678,seq=7,remaining_ms=1000,key=0,kind=1,flags=0,payload=payload)

    def test_roundtrip_and_little_endian_offsets(self):
        packet=self.packet(); wire=encode(packet)
        self.assertEqual(wire[:3],b"AN\x01")
        self.assertEqual(wire[24:28],b"\x78\x56\x34\x12")
        self.assertEqual(len(wire),115)
        self.assertEqual(decode(wire),packet)

    def test_every_single_byte_mutation_fails_integrity(self):
        wire=encode(self.packet())
        for i in range(len(wire)):
            changed=bytearray(wire); changed[i]^=1
            with self.subTest(offset=i),self.assertRaises(ValueError): decode(changed)

    def test_max_payload_and_zero_payload(self):
        for payload in [b"",bytes(range(138))]:
            packet=self.packet(payload); self.assertEqual(decode(encode(packet)),packet)
        self.assertEqual(len(encode(self.packet(b"x"*138))),250)
        with self.assertRaises(ValueError): encode(self.packet(b"x"*139))

    def test_truncation_and_trailing_bytes_refused(self):
        wire=encode(self.packet())
        for candidate in [wire[:111],wire[:-1],wire+b"x"]:
            with self.assertRaises(ValueError): decode(candidate)
