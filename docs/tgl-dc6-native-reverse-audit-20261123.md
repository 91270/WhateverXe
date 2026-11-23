# Tiger Lake display DC6/AUX: new native Mach-O reverse audit (2026-11-23)

**Research status: physical root cause not confirmed. No repair deployed.**

## Provenance: no REA or current Ghidra installation

The reinstalled MeiamBook (macOS 15.8.3, 24H241) has neither REA nor Ghidra installed. Older Ghidra transcripts in the 06-Research directory were produced before reinstall; reading those was not a fresh reverse-engineering run. For this audit, LLVM llvm-objdump directly disassembled the actual x86_64 Apple donor binary in /Library/Extensions on 2026-11-23.

- AppleIntelTGLGraphicsFramebuffer SHA-256: 1b9f425f46c2a833e3c819b1efc6b7be2f52eac80390f699f37b339d1134129f.
- Its Mach-O UUID: B6078743-F795-3202-A55E-EA690FA40949.
- AppleIntelTGLGraphics SHA-256: 6c8ab6cce50b9529679ee4fdf5b1c37d091677d945076f41cb4b7f8196c51449.
- Its UUID: BA3AA1C0-FE6B-33B3-9D85-73F848394E3D.
- These match the earlier 24H232 historical donor fingerprints. Host macOS 24H241 does not change these /Library/Extensions donor bytes on this device. Other donor dependencies still require independent validation.

The original per-function disassembly files were saved locally in 06-Research/WEX-TGL-DisplayWake-20261117/20261123-*-actual-disassembly.txt, outside the Git repository.

## Verified control flow from actual disassembly

1. AppleIntelFramebufferController::setDCState(bool) at 0x472B4. On the hardware DC6 exit, after testing controller+0xB4C and controller+0xB48, the calls are disableHWDC6 (0x474FC), hwEnableInterrupts (0x4751A), then hwConfigureCustomAUX(true) (0x47527). On DC6 entry the native order is hwConfigureCustomAUX(false) at 0x4749B, followed by enableHWDC6 at 0x474A3.
2. disableHWDC6 at 0x48054 decrements controller+0xC24. Its MMIO clear runs only when the old refcount was 1: native ReadRegister32(0x45504) at 0x480A4, then WriteRegister32 of the value with the DC5/DC6 bits cleared. This routine does not independently read back completion.
3. hwConfigureCustomAUX at 0x47A08 requires controller+0xB48==1; controller+0xCE4 selects either the 0x86338..0x86364 bank or the 0x80040..0x8006C bank. It performs ordered native WriteRegister32 requests and no explicit native readback of those Custom AUX registers in the function. These are not DDI A AUX_CTL (0x64010).
4. AppleIntelRegisterAccessManager::WriteRegister32 at 0x5EB5C uses the mapped MMIO region (with bounds/conflict-register handling), not a generic hardware readiness acknowledgment.
5. AppleIntelPortHAL::runAUXCommand at 0x61748 has a 42-iteration software polling loop at 0x619CB..0x61A67. The failure exit 0x61ACC returns 0xE00002D6. Later hardware TIME_OUT_ERROR samples after native retry are not the direct first-return cause.

## Cross-check of original real-hardware captures (not new tests)

Raw files:
- AUX0-refdiag-v2-20261119-093823.json
- AUX0-refdiag-v2-20261119-110739.json
- AUX0-refdiag-v2-20261119-120556.json

All three failing display-wake episodes recorded native read 0x45504=2 and a write request 0, 231.707, 235.468 and 234.634 milliseconds respectively before first native AUX SEND. The register READ caller RVA was 0x480A9, proving that the native disableHWDC6 reference gate entered its hardware-clear branch; an always-skipped clear is therefore not the explanation in these episodes. DDI and AUX power-well ACK registers read 3 before SEND. First AUX SEND 0x8C60023F later yielded a stuck BUSY/DONE=0 state and a native 0xE00002D6 software return.

Prior configuration with display DC6 disabled succeeded in two sets of five short wake tests. This is a valid workaround observation, not proof of the particular PHY, PSR, clock or Custom AUX failure.

## Physical root still unproven

Those three old captures did not record the original 0x86338..0x86364 or 0x80040..0x8006C native accesses. There are no corresponding direct pre-SEND PHY/PSR/GTC ready readbacks. An earlier DC_STATE_EN clear and a later Power Well ACK do not prove that Custom AUX writes were issued while the right hardware resource was ready, nor that the sink responded.

The disassembly proves a possible readiness/order verification gap; it does NOT prove that Custom AUX writes were lost. This evidence is insufficient to justify replaying registers, draining PG refs, increasing AUX timeout, or disabling DC6 as a universal repair. The previously added opt-in native-access witness is diagnostic only and is not a completed fix.

References: project 08-Reports/WEX-TGL-20261119-AUX-PRM-COMPLIANCE-POSTMORTEM.md; 08-Reports/WEX-TGL-DC6-EXIT-RETRY-20261119.md; saved original Ghidra call graph; Intel TGL Display PRM; upstream WhateverXe issue #63.
