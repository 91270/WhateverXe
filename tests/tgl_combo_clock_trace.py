#!/usr/bin/env python3
"""Structural contract for the opt-in, software-only TGL ComboClock trace.

This checks that the production wrappers bracket the target/begin guards and
native donor calls, that every guard rejection has a reason code, and that the
eDP diagnostic boot argument enables only the memory recorder (not broad
MMIO tracing). It does not prove runtime invocation or hardware causality.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "WhateverXe/kern_xe.cpp").read_text()
HEADER = (ROOT / "WhateverXe/kern_xe.hpp").read_text()
CAPTURE = (ROOT.parent.parent / "06-Research/WEX-TGL-AUX-UPSTREAM-20261118/capture_edp_refdiag.py").read_text()


def body(signature):
    start = SOURCE.index(signature)
    brace = SOURCE.index("{", start)
    depth = 0
    for i in range(brace, len(SOURCE)):
        if SOURCE[i] == "{":
            depth += 1
        elif SOURCE[i] == "}":
            depth -= 1
            if depth == 0:
                return SOURCE[brace + 1:i]
    raise AssertionError(f"unterminated function: {signature}")


target = body("bool XE::comboClockTarget(")
begin = body("bool XE::comboBeginClock(")
enable = body("void XE::wrapTGLComboEnableClocks(")
disable = body("void XE::wrapTGLDisableClocks(")

assert "uint32_t *reason=nullptr,uint32_t *detail=nullptr" in HEADER
assert "uint32_t *reason=nullptr,uint32_t *detail=nullptr" in HEADER
assert "return reject(" in target and target.count("return false;")==1
assert "return reject(" in begin and begin.count("return false;")==1
for code in range(1, 19):
    assert re.search(rf"reject\({code}(?:,|\))", target), f"target reason {code} missing"
for code in range(1, 13):
    assert re.search(rf"(?:reject|abort)\({code}(?:,|\))", begin), f"begin reason {code} missing"

def ordered(source, *needles):
    positions = [source.index(n) for n in needles]
    assert positions == sorted(positions), list(zip(needles, positions))

ordered(enable,
    "tglTransitionRecord(120,false",
    "comboClockTarget(",
    "tglTransitionRecord(121,true",
    "comboBeginClock(",
    "tglTransitionRecord(123,true",
    "tglTransitionRecord(124,false",
    "FunctionCast(wrapTGLComboEnableClocks",
    "tglTransitionRecord(125,true",
    "comboEndClock()",
    "tglTransitionRecord(126,true")
ordered(disable,
    "tglTransitionRecord(130,false",
    "comboClockTarget(",
    "tglTransitionRecord(131,true",
    "comboBeginClock(",
    "tglTransitionRecord(132,true",
    "tglTransitionRecord(133,false",
    "FunctionCast(wrapTGLDisableClocks",
    "tglTransitionRecord(134,true",
    "comboEndClock()",
    "tglTransitionRecord(135,true")
assert "tglTransitionRecord(127,false" in enable and "tglTransitionRecord(128,true" in enable
assert "tglTransitionRecord(136,false" in disable and "tglTransitionRecord(137,true" in disable
assert "WEXComboClockEnableRejected" in enable and "WEXComboClockDisableRejected" in disable
# No new MMIO helper is called by the wrapper-level tracing.
for name, source in (("enable", enable), ("disable", disable)):
    assert "comboClockRead(" not in source, name
    assert "comboClockWrite(" not in source, name

# Existing opt-in refdiag activates the record ring, but broad MMIO recording
# remains gated by the distinct -wex-display-trace argument.
assert "tglInitTransitionTrace(tglDisplayTraceEnabled || tglEDPRefDiagRequested)" in SOURCE
assert '"TGLComboClockTraceReady"' in SOURCE
assert 'if(!tglDisplayTraceEnabled)return false;' in SOURCE
assert '"WhateverXeTransitionLive"' in SOURCE and '"WhateverXeTransitionFirst"' in SOURCE
for stage in (120,121,122,123,124,125,126,127,128,130,131,132,133,134,135,136,137):
    assert f"{stage}:" in CAPTURE, f"capture parser missing stage {stage}"
assert 'property_name in ("WhateverXeTransitionFirst","WhateverXeTransitionLive")' in CAPTURE
assert "def json_property(value):" in CAPTURE
assert "key:json_property(root.get(key))" in CAPTURE
print("PASS: ComboClock target/begin reason codes, wrapper/native call brackets, opt-in memory-only trace and capture decoding")
print("LIMIT: structural source check only; no claim that a wake runtime path has been observed")
