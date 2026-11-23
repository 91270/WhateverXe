#!/usr/bin/env python3
"""Execute production S0 wrappers under bounded native lifecycle stubs.

This checks the one-shot owner handshake and the sampling window. It cannot
establish the physical ForceWake, hardware stamp, or interrupt ordering.
"""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
text = (ROOT / "WhateverXe" / "kern_xe.cpp").read_text()


def function(marker):
    a = text.index(marker)
    b = text.index("{", a + len(marker))
    depth = 0
    for i in range(b, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if not depth:
                return text[a:i + 1]
    raise AssertionError(marker)


bridge = function("static void tglS0WrapDisableInterrupts(void *bridge)")
sleep = function("static void tglS0WrapBridgeSystemWillSleep(void *bridge)")
assert "tglS0CaptureBeforeIRQDisable(accelerator,epoch)" in bridge
assert "tglS0CaptureBeforeIRQDisable" not in sleep
assert bridge.index("tglS0CaptureBeforeIRQDisable") < bridge.index("tglS0OrgDisableInterrupts)(bridge)")
assert sleep.index("tglS0CaptureAccelerator,accelerator") < sleep.rindex("original(bridge);")

harness = r"""
#include <cassert>
#include <cstdint>
#include <cstring>
#include <vector>
#include <string>
#include <iostream>
using mach_vm_address_t=uintptr_t;
struct TGLWakeBefore {bool valid=false;};
struct TGLS0SleepRecord {TGLWakeBefore before;void *streamer=nullptr;uint32_t epoch=0;};
static TGLS0SleepRecord tglS0Sleep[6];
static uint32_t tglS0Epoch=0;
static mach_vm_address_t tglS0OrgBridgeSystemWillSleep=0;
static mach_vm_address_t tglS0OrgDisableInterrupts=0;
static bool tglS0SleepHookRouted=false;
static void *tglS0CaptureAccelerator=nullptr;
static uint32_t tglS0CaptureEpoch=0;
static int snapshots=0,originalIRQ=0,originalSleep=0;
static std::vector<std::string> events;
struct Bridge {void *vtable;void *pad;void *accelerator;};
static Bridge matching {}, foreign {};
static bool nativeCallsIRQ=true,invokeForeign=true,invokeTwice=true;

static void tglS0CaptureBeforeIRQDisable(void *accelerator,uint32_t epoch) {
 assert(accelerator==matching.accelerator);
 assert(epoch && tglS0Sleep[0].epoch==0);
 ++snapshots;
 events.emplace_back("snapshot");
 tglS0Sleep[0].before.valid=true;
 __atomic_store_n(&tglS0Sleep[0].epoch,epoch,__ATOMIC_RELEASE);
}
@BRIDGE_FUNCTION@
static void nativeDisable(void *bridge) {
 (void)bridge;
 events.emplace_back("native-disable");
 ++originalIRQ;
}
static void nativeSleep(void *bridge) {
 events.emplace_back("native-sleep-start");
 ++originalSleep;
 if(invokeForeign)tglS0WrapDisableInterrupts(&foreign);
 if(nativeCallsIRQ) {
  tglS0WrapDisableInterrupts(&matching);
  if(invokeTwice)tglS0WrapDisableInterrupts(&matching);
 }
 events.emplace_back("native-sleep-end");
 assert(bridge==&matching);
}
@SLEEP_FUNCTION@
void init() {
 snapshots=originalIRQ=originalSleep=0;events.clear();
 tglS0SleepHookRouted=true;nativeCallsIRQ=true;invokeForeign=true;invokeTwice=true;
 tglS0CaptureAccelerator=nullptr;tglS0CaptureEpoch=0;
 tglS0Sleep[0].epoch=0; tglS0Sleep[0].before.valid=false;
 matching.accelerator=reinterpret_cast<void *>(0x100000);
 foreign.accelerator=reinterpret_cast<void *>(0x200000);
 tglS0OrgBridgeSystemWillSleep=reinterpret_cast<mach_vm_address_t>(&nativeSleep);
 tglS0OrgDisableInterrupts=reinterpret_cast<mach_vm_address_t>(&nativeDisable);
}
int main() {
 init();
 // A matching native bridge request captures once, after a foreign callback
 // and before the native IRQ mask write; later disables cannot mutate epoch.
 tglS0WrapBridgeSystemWillSleep(&matching);
 assert(snapshots==1 && originalIRQ==3 && originalSleep==1);
 assert(tglS0Sleep[0].before.valid);
 assert(tglS0Sleep[0].epoch==tglS0Epoch);
 assert(tglS0CaptureAccelerator==nullptr && tglS0CaptureEpoch==0);
 assert(events==std::vector<std::string>({"native-sleep-start",
             "native-disable","snapshot","native-disable","native-disable","native-sleep-end"}));
 tglS0WrapDisableInterrupts(&matching);
 assert(snapshots==1 && originalIRQ==4);
 std::cout<<"PASS native owner gate and exactly-once pre-IRQ snapshot\n";

 // If original sleep skips bridge disable, there must be NO new snapshot;
 // the wake side will take its no-snapshot/initialize path.
 init();nativeCallsIRQ=false;
 tglS0WrapBridgeSystemWillSleep(&matching);
 assert(snapshots==0 && tglS0Sleep[0].epoch==0 && !tglS0Sleep[0].before.valid);
 assert(originalSleep==1 && originalIRQ==1);
 std::cout<<"PASS skipped IRQ disable leaves no stale sleep baseline\n";

 // All off-scope bridge disables must be forwarded unmodified.
 init();
 tglS0WrapDisableInterrupts(&foreign);
 assert(snapshots==0 && originalIRQ==1);
 std::cout<<"PASS foreign bridge is native-only\n";

 // If the optional pair did not fully route, do NOT arm for snapshots.
 init();tglS0SleepHookRouted=false;
 tglS0WrapBridgeSystemWillSleep(&matching);
 assert(snapshots==0 && originalSleep==1 && originalIRQ==3);
 assert(tglS0CaptureAccelerator==nullptr && tglS0CaptureEpoch==0);
 std::cout<<"PASS inactive partial route does not sample GPU\n";

 // Retry after valid capture requires an explicit new sleep epoch.
 init();invokeForeign=false;invokeTwice=false;
 tglS0WrapBridgeSystemWillSleep(&matching);
 const uint32_t epoch=tglS0Sleep[0].epoch;
 assert(snapshots==1 && epoch==tglS0Epoch);
 tglS0WrapBridgeSystemWillSleep(&matching);
 assert(snapshots==2 && tglS0Sleep[0].epoch==epoch+1);
 std::cout<<"PASS new sleep epoch explicitly invalidates previous record\n";
}
"""
harness = harness.replace("@BRIDGE_FUNCTION@", bridge).replace("@SLEEP_FUNCTION@", sleep)
with tempfile.TemporaryDirectory(prefix="wex-s0-window-") as td:
    path = Path(td)
    (path / "window.cpp").write_text(harness)
    subprocess.run([
        "clang++", "-std=c++17", "-O1", "-g", "-fno-omit-frame-pointer",
        "-fsanitize=address,undefined", str(path / "window.cpp"),
        "-o", str(path / "window")], check=True)
    subprocess.run([str(path / "window")], check=True)
