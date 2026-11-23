#!/usr/bin/env python3
"""Static callsite and ABI qualification for the opt-in S0 CSB snapshot.

Only the exact AppleIntelTGLGraphics donor is supported. This checks native
machine-code ordering; it cannot establish sleep power-state runtime safety.
"""
import hashlib
from pathlib import Path
import struct
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: tgl_s0_irq_boundary.py <exact AppleIntelTGLGraphics donor>")
source = Path(sys.argv[1]).read_bytes()
sha = hashlib.sha256(source).hexdigest()
EXPECTED = "6c8ab6cce50b9529679ee4fdf5b1c37d091677d945076f41cb4b7f8196c51449"
assert sha == EXPECTED, f"unqualified accelerator donor SHA256: {sha}"

def branch(offset: int, opcode: int) -> int:
    assert source[offset] == opcode, f"unexpected branch opcode @{offset:#x}"
    disp = struct.unpack_from("<i", source, offset + 1)[0]
    return offset + 5 + disp

entry = bytes.fromhex("55 48 89 e5 53 50 48 89 fb")
assert source[0x4AB14:0x4AB1D] == entry, "changed bridge sleep entry"
assert source[0x4A778:0x4A781] == entry, "changed bridge IRQ disable entry"
assert source[0x4A781:0x4A785] == bytes.fromhex("48 8b 7f 10"), "owner must remain bridge+0x10"

assert branch(0x28967, 0xE8) == 0x4AB14, "accelerator sleep must call bridge sleep"
assert branch(0x4AB2D, 0xE8) == 0x15DB0, "bridge sleep must first finish stamps"
assert branch(0x4AB3B, 0xE9) == 0x4A69A, "bridge sleep must delegate native bridge disable"
assert branch(0x4A6C0, 0xE8) == 0x15DB0, "bridge disable must finish remaining stamps"
for addr in (0x4A6D1, 0x4A70F):
    assert branch(addr, 0xE8) == 0x4A778, "both native branches must disable interrupts"
    assert addr > 0x4A6C0
assert branch(0x4A78F, 0xE8) == 0x28C2A, "native IRQ disable obtains its own ForceWake"

source_code = (Path(__file__).resolve().parents[1] / "WhateverXe" / "kern_xe.cpp").read_text()
for item in (
    '__ZN17IGInterruptBridge15systemWillSleepEv',
    '__ZN17IGInterruptBridge17disableInterruptsEv',
    'tglS0WrapBridgeSystemWillSleep',
    'tglS0WrapDisableInterrupts',
    'tglS0CaptureBeforeIRQDisable',
    '__atomic_compare_exchange_n(&tglS0CaptureAccelerator',
):
    assert item in source_code, f"missing opt-in S0 native boundary contract: {item}"

print("PASS exact donor:", sha)
print("PASS accelerator sleep -> bridge sleep -> first finishAllStamps")
print("PASS bridge disable -> second finishAllStamps -> both IRQ disable branches")
print("PASS native disableInterrupts owner+0x10 and own SafeForceWake")
print("NOTE: hardware ForceWake/IRQ safety and wake recovery still unverified")
