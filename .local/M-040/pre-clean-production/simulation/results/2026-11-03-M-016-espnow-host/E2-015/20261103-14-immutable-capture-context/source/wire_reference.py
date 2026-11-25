"""Independent reference for M-frozen ANN wire v1, not firmware execution."""
import struct
import zlib

HEADER, MAX_FRAME, MAX_PAYLOAD = 112, 250, 138


def encode(packet):
    payload=packet.get("payload",b"")
    path=packet.get("path",[])
    if not isinstance(payload,bytes) or len(payload)>MAX_PAYLOAD or len(path)>8:
        raise ValueError("wire payload/path bound")
    result=bytearray(HEADER+len(payload))
    result[:8]=bytes([0x41,0x4e,1,packet["type"],packet.get("flags",0),packet["ttl"],len(path),packet.get("index",0)])
    struct.pack_into("<QQIIIIHBB",result,8,packet["origin"],packet["dst"],packet["boot"],packet["seq"],packet["remaining_ms"],packet.get("key",0),len(payload),packet["kind"],0)
    struct.pack_into("<8Q",result,44,*(path+[0]*(8-len(path))))
    result[HEADER:]=payload
    struct.pack_into("<I",result,108,zlib.crc32(result)&0xffffffff)
    return bytes(result)


def decode(frame):
    if not HEADER<=len(frame)<=MAX_FRAME or frame[:3]!=b"AN\x01" or frame[43]!=0:
        raise ValueError("wire prefix/length/reserved")
    candidate=bytearray(frame)
    expected=struct.unpack_from("<I",candidate,108)[0]
    candidate[108:112]=b"\0"*4
    if zlib.crc32(candidate)&0xffffffff!=expected:
        raise ValueError("wire CRC")
    origin,dst,boot,seq,remaining,key,length,kind,reserved=struct.unpack_from("<QQIIIIHBB",frame,8)
    path_length=frame[6]
    if path_length>8 or length!=len(frame)-HEADER:
        raise ValueError("wire path/payload length")
    return dict(type=frame[3],flags=frame[4],ttl=frame[5],path=list(struct.unpack_from("<8Q",frame,44))[:path_length],index=frame[7],origin=origin,dst=dst,boot=boot,seq=seq,remaining_ms=remaining,key=key,kind=kind,payload=frame[HEADER:])
