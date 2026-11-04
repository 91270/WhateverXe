#!/usr/bin/env python3
"""Read-only Gen12 MEDIA pipeline transition audit with actual captured RCS batch.
No hardware access, driver modifications, or GPU execution.
"""
import argparse
import json
import struct
from pathlib import Path

PC_HEADER = 0x7A000004
MEDIA_SELECT = 0x69041301
SBA = 0x6101000E
SECOND_LEVEL = 0x18C00001
CS_STALL = 1 << 20
RT_FLUSH = 1 << 12
DEPTH_FLUSH = 1 << 0
DEPTH_STALL = 1 << 13
HDC_FLUSH_HEADER = 1 << 9


def inspect(batch: bytes):
    if len(batch) != 216:
        raise ValueError('exact 216-byte native RCS packet required')
    w = struct.unpack('<54I', batch)
    if not (w[3] & 0xFFFFFDFF) == PC_HEADER or w[9] != MEDIA_SELECT or w[10] != SBA:
        raise ValueError('not the captured Sequoia VideoToolbox MEDIA packet')
    if w[39] != SECOND_LEVEL or w[41] != 0:
        raise ValueError('unexpected second-level MEDIA batch')
    header, flags = w[3], w[4]
    return {
        'pre_media_header': f'0x{header:08x}',
        'pre_media_flags': f'0x{flags:08x}',
        'cs_stall': bool(flags & CS_STALL),
        'render_target_flush': bool(flags & RT_FLUSH),
        'depth_cache_flush': bool(flags & DEPTH_FLUSH),
        'depth_stall': bool(flags & DEPTH_STALL),
        'hdc_pipeline_flush': bool(header & HDC_FLUSH_HEADER),
        'switch_to_media': f'0x{w[9]:08x}',
        'secondary_batch': f'0x{w[40]:08x}',
        'secondary_opcode': f'0x{w[39]:08x}',
        'previous_3d_to_media_requirement_met': bool(
            flags & CS_STALL and flags & RT_FLUSH and
            flags & DEPTH_FLUSH and header & HDC_FLUSH_HEADER),
    }


def sample():
    w = [0] * 54
    w[3], w[4] = PC_HEADER, 0x001010A0
    w[9], w[10] = MEDIA_SELECT, SBA
    w[39], w[40], w[41] = SECOND_LEVEL, 0x4032E000, 0
    return struct.pack('<54I', *w)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--batch', type=Path)
    p.add_argument('--va', type=Path)
    args = p.parse_args()
    r = inspect(sample())
    assert r['cs_stall'] and r['render_target_flush']
    assert not r['depth_cache_flush'] and not r['hdc_pipeline_flush']
    assert not r['previous_3d_to_media_requirement_met']
    fixed = bytearray(sample())
    struct.pack_into('<I', fixed, 0x0C, PC_HEADER | HDC_FLUSH_HEADER)
    struct.pack_into('<I', fixed, 0x10, 0x001010A0 | DEPTH_FLUSH | DEPTH_STALL)
    f = inspect(fixed)
    assert f['previous_3d_to_media_requirement_met']
    assert f['depth_stall']
    if args.batch:
        r = inspect(args.batch.read_bytes())
        assert not r['previous_3d_to_media_requirement_met']
    if args.va:
        b = args.va.read_bytes()
        assert b[0x24bb54:0x24bb5c] == bytes.fromhex('0400007a00100000')
        assert b[0x31e9dc:0x31e9e0] == bytes.fromhex('01130469')
        r['driver_pre_flush_template'] = '0x24bb54: 0x7a000004 0x00001000'
        r['driver_media_select_template'] = '0x31e9dc: 0x69041301'
    print(json.dumps(r, indent=2))
    print('CAVEAT: The transition rule is conditional on previous pipeline=3D; this capture does not prove prior state. No live GPU validation.')


if __name__ == '__main__':
    main()
