"""Create a tiny synthetic OSM PBF (four residential nodes), no downloads.

Only the minimal OSM protobuf fields needed by libosmium are encoded here.
This is infrastructure smoke data, not a geographic or optimizer benchmark.
"""
from pathlib import Path
import struct
import sys
import zlib


def varint(n):
    out = bytearray()
    while n > 127:
        out.append((n & 127) | 128)
        n >>= 7
    out.append(n)
    return bytes(out)


def integer(field, value):
    return varint(field << 3) + varint(value)


def message(field, value):
    return varint((field << 3) | 2) + varint(len(value)) + value


def signed(n):
    return varint(n * 2 if n >= 0 else -n * 2 - 1)


def block(kind, payload):
    blob = integer(2, len(payload)) + message(3, zlib.compress(payload))
    header = message(1, kind.encode()) + integer(3, len(blob))
    return struct.pack('!I', len(header)) + header + blob


def create(path):
    strings = b''.join(message(1, s) for s in (b'', b'highway', b'residential', b'name', b'Synthetic square'))
    group = b''
    for ident, lat, lon in [(1, 408500000, 142500000), (2, 408501000, 142500000),
                             (3, 408501000, 142501000), (4, 408500000, 142501000)]:
        node = varint(8) + signed(ident) + varint(64) + signed(lat) + varint(72) + signed(lon)
        group += message(1, node)
    way = integer(1, 1) + message(2, varint(1)+varint(3)) + message(3, varint(2)+varint(4))
    way += message(8, b''.join(signed(n) for n in (1, 1, 1, 1, -3)))
    group += message(3, way)
    primitive = message(1, strings) + message(2, group)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(block('OSMHeader', message(4, b'OsmSchema-V0.6')) + block('OSMData', primitive))


if __name__ == '__main__':
    create(sys.argv[1])
