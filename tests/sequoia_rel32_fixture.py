#!/usr/bin/env python3
"""Validate Sequoia CALL rel32 semantics; --kernel checks the exact 24H232 donor."""
from pathlib import Path
import argparse
import hashlib
import re
import struct

ROOT=Path(__file__).resolve().parents[1]
SOURCE=(ROOT/'WhateverXe/kern_xe.cpp').read_text(encoding='utf-8')
HEADER=(ROOT/'WhateverXe/kern_tgl_pmap_call.hpp').read_text(encoding='utf-8')
BLOCK=SOURCE.split('static void tglPrepareSequoiaMMIOUC',1)[1].split('static void tglPrepareSonomaMMIOUC',1)[0]


def calls_target(callsite, data, expected):
    if len(data)!=5 or data[0]!=0xE8 or not callsite or not expected:
        return False
    offset=struct.unpack_from('<i',data,1)[0]
    return (callsite+5+offset)&((1<<64)-1)==expected


def regression_tests():
    assert 'tglSequoiaPmapCallMatches(protect+0xCA,fn)' in BLOCK
    assert 'guard[16]=tglSequoiaPmapCallMatches(protect+0xCA,fn)' in BLOCK
    assert 'memcmp(reinterpret_cast<void *>(protect+0xCA)' not in BLOCK
    assert 'code[0]!=0xE8' in HEADER
    assert 'memcpy(&displacement,code+1,sizeof(displacement))' in HEADER
    assert 'static_cast<intptr_t>(displacement)' in HEADER

    old_site=0xffffff80003ffc50+0xCA
    old_fn=0xffffff800042c890
    new_site=0xffffff80004e7240+0xCA
    new_fn=0xffffff8000513eb0
    for callsite,raw,target in [
        (old_site,bytes.fromhex('e871cb0200'),old_fn),
        (new_site,bytes.fromhex('e8a1cb0200'),new_fn),
    ]:
        assert calls_target(callsite,raw,target)
        assert not calls_target(callsite,raw,target+1)
        assert not calls_target(callsite,b'\xE9'+raw[1:],target)
        assert not calls_target(callsite,raw[:1]+b'\x00'*4,target)

    # The x86 displacement is a signed 32-bit integer, not an unsigned offset.
    negative_site=0xffffff8000500000
    assert calls_target(negative_site,b'\xE8'+struct.pack('<i',-0x1234),negative_site+5-0x1234)
    assert not calls_target(0,bytes.fromhex('e8a1cb0200'),new_fn)
    assert not calls_target(new_site,bytes.fromhex('e8a1cb0200'),0)


def check_kernel(path):
    data=path.read_bytes()
    sha=hashlib.sha256(data).hexdigest()
    assert sha=='ddd9016e225a61ebfd4f04b02a00937262f26690c57a928613e08506978c81be',sha
    fn=0xffffff8000513eb0
    protect=0xffffff80004e7240
    kernel_vm_base=0xffffff8000200000

    def read(va,size):
        off=va-kernel_vm_base
        assert 0<=off<=len(data)-size,(hex(va),off)
        return data[off:off+size]

    guard_specs=re.findall(
        r'!memcmp\(reinterpret_cast<void \*>\((fn|protect)(\+0x[0-9A-Fa-f]+)?\),([A-Za-z]+),sizeof',
        BLOCK,
    )
    assert len(guard_specs)==8,guard_specs
    for base,offset,name in guard_specs:
        addr=(fn if base=='fn' else protect)+(int(offset[1:],16) if offset else 0)
        expected_values=re.search(r'const uint8_t '+name+r'\[\] \{([^}]+)\}',BLOCK)[1]
        expected=bytes(int(i.strip(),0) for i in expected_values.split(','))
        actual=read(addr,len(expected))
        assert actual==expected,(name,actual.hex(),expected.hex())

    callsite=protect+0xCA
    actual_call=read(callsite,5)
    assert actual_call==bytes.fromhex('e8a1cb0200'),actual_call.hex()
    assert calls_target(callsite,actual_call,fn)
    print('PASS: 24H232 kernel SHA256, 8 byte guards, decoded CALL target')


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--kernel',type=Path,help='24H232 BootKernelExtensions.kc file')
    args=p.parse_args()
    regression_tests()
    print('PASS: original 24H32 and current 24H232 CALL rel32 semantics + negative cases')
    if args.kernel:check_kernel(args.kernel)


if __name__=='__main__':
    main()
