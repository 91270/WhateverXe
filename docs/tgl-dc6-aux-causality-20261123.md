# Tiger Lake eDP: DC6 exit, Custom AUX configuration and first AUX transaction

Research status: **passive diagnostic only; hardware repair not established**.
Historical measurements: Lenovo 82GM, Sequoia 15.8.2 build 24H232.
Current macOS 15.8.3 build 24H241 is NOT tested by these historical results.

## Evidence and status

- Real display-only wake failures show first native DPCD 0x100 AUX submission
  (AUX_CTL 0x8C60023F), BUSY=1 and DONE=0 (0x8D40023F),
  followed by Apple software polling exhaustion, 0xE00002D6,
  link training failure and native display disable. PWM being zero is
  a consequence; restoring PWM cannot repair the stalled AUX transaction.
- Before the failed SEND, original DDI/AUX power-well ACK was 3.
  An earlier DC_STATE_EN (0x45504) write requested clearing DC6.
  This is NOT evidence that all PHY/clock/PSR conditions had recovered.
- Disabling *display* DC6 worked in ten short wake tests and selected
  system wake tests. It is a board-level workaround, not a general fix.
- Ghidra 24H232 donor: Controller::setDCState @0x472B4 calls
  disableHWDC6 or disableSWDC6, enables native interrupts, then
  hwConfigureCustomAUX(true) on the applicable DC6-exit path.
  hwConfigureCustomAUX @0x47A08 selects one of the banks
  0x86338..0x86364 or 0x80040..0x8006C based on native controller
  configuration. The reverse transition disables portions of that bank.
- These *Custom AUX* banks are different from DDI A AUX_CTL=0x64010.
  Original failed-wake traces did not include the Custom AUX bank writes;
  consequently their presence and effectiveness are unknown.
- TGL PRM says Port A IO/PHY programming is preserved during DC6;
  other Combo PHY ports may need reinitialization. Thus a blanket
  Port A PHY reset is not justified by current evidence.

## Passive capture added in research branch

The existing experimental -wex-tgl-edp-refdiag records only original
native ReadRegister32/WriteRegister32 accesses. Its bounded
WhateverXeAUXNativeMMIO trace now accepts both aligned Custom AUX banks
without generating any MMIO reads or writes. No power-well reference
management, DC mode state, timeout or port programming is changed.
No fixed PCI ID is required; the existing TGL native donor gate remains.

Each 48-byte receipt retains sequence, wake epoch, read/write direction,
register address, native accessor value and caller. The existing
WhateverXeAUXFirstCommand freeze identifies the first native SEND.
Use same-epoch sequence and timing to compare whether Custom AUX
configuration was requested before first SEND, including successes
and failures. A native WRITE is only a request, NOT a hardware ACK;
lack of a receipt is not proof that the callback never ran if the
hook was absent or the bounded capture overflowed. Original readbacks,
when available, must be separated from write requests.

## General repair admission requirements

- Establish the *first* reproducible success-versus-failure divergence
  before the native AUX SEND, not the downstream PWM or AGDC failure.
- Confirm native ownership and the relevant register/PHY/PSR/DC6
  prerequisites for the discovered display/port capability.
- Only if a missing or incorrect precondition is verified, implement
  an owned and bounded recovery with explicit failure handling.
  No unconditional DC6 ban, arbitrary AUX timeouts, forced PG drain,
  hard-coded 8086:9A49 exception or speculative shared PHY reset.
- Preserve other TGL/ADL paths and keep experimental recovery opt-in
  until tested across matching hardware and system versions.

## References and tests

Local original source:
  08-Reports/WEX-TGL-20261119-AUX-PRM-COMPLIANCE-POSTMORTEM.md
  08-Reports/WEX-TGL-DC6-EXIT-RETRY-20261119.md
  06-Research/WEX-TGL-DisplayWake-20261117/native-aux-state-machine-branches.log

Intel TGL Display PRM:
  https://cdrdv2-public.intel.com/705833/intel-gfx-prm-osrc-tgl-vol-12-display-engine.pdf
Linux i915 C-state guidance:
  https://www.kernel.org/doc/html/v6.12/gpu/i915.html
Cross-device case:
  https://github.com/b00t0x/WhateverXe/issues/63

Validation: CPU fixture of actual recording code and bounded behavior;
kernel build, physical display wake, 24H241 donor compatibility and a
real cause-level repair remain unverified. No Apple binary distributed.
