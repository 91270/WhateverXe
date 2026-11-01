# Archived upstream PR proposal

> This document preserves the complete body of GitHub Issue #1 before the repository's planned transition from a Fork to an independent project.

- Original repository: `91270/WhateverXe`
- Original issue: [#1 — Full PR proposal: Fix Sequoia MMIO UC initialization by validating the CALL rel32 target](https://github.com/91270/WhateverXe/issues/1)
- Author: `91270`
- State at archival: `open`
- Created: `2026-10-31T08:37:24Z`
- Last updated: `2026-10-31T08:44:07Z`
- Comments at archival: `0`
- Archive purpose: preserve the original technical proposal, validation claims, and evidence references; this archive does not imply upstream acceptance or merge.

---

## Original issue body

@b00t0x — I am posting the complete PR proposal here because the upstream repository only permits collaborators to open pull requests. Could you review this patch or enable an upstream PR?

---

# Fix Sequoia MMIO UC initialization by validating the CALL rel32 target

## 1. Observed issue with the original driver

When testing the original WhateverXe 0.6.1 together with its matching graphics package on a Tiger Lake laptop running macOS Sequoia 15.8.2 (24H232), the system could boot and display the desktop, but GPU hardware acceleration did not initialize correctly.

Specifically:

- OpenCore successfully booted macOS to the desktop.
- The internal display worked at 1920 × 1080.
- The original WhateverXe kernel extension was loaded successfully.
- macOS enumerated the Intel integrated GPU, but a usable GPU accelerator was not initialized.
- The system_profiler display report did not include a Metal Support field.
- A reported GPU name or shared VRAM size alone did not demonstrate working acceleration.

The pre-fix IORegistry diagnostics captured the following state:

| Check | Original WhateverXe 0.6.1 |
| --- | --- |
| WhateverXe extension | Loaded |
| Intel GPU PCI detection | Successful |
| Internal display output | Working |
| TGLSequoiaMMIOGuard[16] | 0 |
| TGLSequoiaMMIOGuard[19] | 0 |
| TGLMMIOStrongUCRouted | No |
| TGLAcceleratorAdmissionReady | No |
| Active registered IntelAccelerator | Not observed in the captured IORegistry |
| Metal Support in system_profiler | Not reported |

This is not a case where the entire driver failed to load. Rather, specific GPU initialization requirements failed after the extension had loaded, while framebuffer display output remained operational.

**Evidence:** See the sanitized pre-fix diagnostic excerpt in before-fix.txt. An independent Metal compute/render benchmark was **not** executed on the original driver; the pre-fix assessment is based on system_profiler and IORegistry evidence.

## 2. Root cause analysis

Inspection of the Sequoia-specific tglPrepareSequoiaMMIOUC implementation revealed a build-dependent, exact-byte comparison for an x86-64 CALL rel32 instruction.

Inspection location:

~~~text
_IOProtectCacheMode + 0xCA
~~~

The original expected five-byte instruction was:

~~~text
E8 71 CB 02 00
~~~

On macOS Sequoia 15.8.2 (24H232), the actual bytes were:

~~~text
E8 A1 CB 02 00
~~~

These instructions have different relative displacements. However, after resolving their respective addresses in the corresponding kernel images, both instructions target:

~~~text
_pmap_enter_options
~~~

Kernel analysis established that:

1. The CALL opcode remained 0xE8.
2. Its relative displacement changed between the examined builds.
3. The resolved call destination remained the expected _pmap_enter_options function.
4. The eight other instruction checks in the same guard matched the inspected 24H232 kernel.

The issue was therefore the comparison of the **entire encoded CALL instruction** rather than verification of its intended destination. Changes in kernel layout can alter the displacement bytes without changing the call's semantic target.

As a result, the existing guard rejected the valid instruction on 24H232, preventing the guarded MMIO UC initialization path from completing and leaving accelerator admission unavailable.

## 3. Proposed fix

This change avoids adding a macOS Build whitelist, a device-specific workaround, or another hardcoded displacement.

Instead, it validates the actual target of the CALL instruction:

1. Check that the instruction opcode is the expected x86-64 CALL rel32 opcode (0xE8).
2. Decode the following four bytes as a **signed 32-bit relative displacement**.
3. Compute the destination from the call-site address, the instruction length, and that displacement.
4. Compare the destination against the dynamically resolved _pmap_enter_options symbol address.
5. Accept that guard only when the destination matches.
6. Preserve the other eight existing instruction checks.
7. Preserve the MMIO prerequisites and diagnostic fields, including TGLSequoiaMMIOGuard.
8. Preserve the behavior of rejecting the guarded operation when validation fails.

This changes the verification criterion from a kernel-build-specific byte sequence to the expected instruction semantics; it does **not** remove validation.

### Change scope

The patch is deliberately limited to the relevant Sequoia MMIO UC guard.

It does **not**:

- Add or remove GPU PCI IDs.
- Modify framebuffer configuration or display property injection.
- Change connector routing or the supported GPU family selection.
- Introduce a Lenovo/model-specific condition.
- Change the separate MMIO implementations used for other macOS versions.
- Bypass the existing eight unrelated instruction guards.

The helper that decodes CALL rel32 is covered by regression tests, including invalid inputs.

## 4. Automated testing

To reduce the chance of breaking previously accepted instruction patterns, the fix includes targeted regression cases and build verification.

### 4.1 CALL instruction regression tests

The test suite verifies:

- The original macOS 24H32 CALL pattern is accepted when it resolves to the expected target.
- The observed macOS 24H232 CALL pattern is also accepted.
- Valid positive relative displacements.
- Valid negative signed relative displacements.
- Incorrect target addresses are rejected.
- Invalid CALL opcodes are rejected.
- Invalid/zero address inputs are rejected.

### 4.2 Kernel-based validation

The actual 24H232 kernel image was inspected to verify:

- The CALL bytes at the expected location.
- The decoded target points to _pmap_enter_options.
- All eight other unchanged instruction guards match the corresponding kernel bytes.

### 4.3 GitHub Actions CI results

| Check | Result |
| --- | --- |
| CPU/C++ automated tests | 160/160 passed / 0 failed |
| DEBUG build | Passed |
| RELEASE build | Passed |
| Artifact packaging | Passed |
| Build artifact SHA-256 verification | Passed |

Successful GitHub Actions run:

https://github.com/91270/WhateverXe/actions/runs/41173906479

These checks validate this source change and the examined kernel patterns; they do not constitute full hardware regression coverage for every macOS release or every GPU model.

## 5. Real hardware verification

The patched driver was deployed and tested on actual Tiger Lake hardware.

### 5.1 Test environment

| Component | Configuration |
| --- | --- |
| Laptop | Lenovo Xiaoxin Air 15 2021 (82GM) |
| CPU | Intel Core i5-1135G7 |
| Integrated GPU | Intel Iris Xe Graphics, 80 EU |
| GPU PCI ID | 8086:9A49 |
| macOS | Sequoia 15.8.2 |
| macOS build | 24H232 |
| Bootloader | OpenCore 1.0.8 |
| Driver | WhateverXe 0.6.1 with this patch |

### 5.2 GPU initialization after applying the fix

The resulting diagnostic state was:

| Check | Patched driver |
| --- | --- |
| WhateverXe extension | Loaded |
| TGLSequoiaMMIOGuard[16] | 1 |
| TGLSequoiaMMIOGuard[19] | 1 |
| TGLMMIOStrongUCRouted | Yes |
| TGLAcceleratorAdmissionReady | Yes |
| IntelAccelerator | Registered, matched, active |
| MetalPluginName | AppleIntelTGLGraphicsMTLDriver |
| Metal Support | Metal 2 |

The loaded WhateverXe Mach-O UUID was:

~~~text
95403F61-2F4D-30B1-9209-6A8FCCB71BFF
~~~

This matched the RELEASE binary produced by the successful GitHub Actions build, providing evidence that the patched build—not the pre-fix binary—was loaded during the successful diagnostic session.

### 5.3 Actual Metal compute and rendering tests

Device enumeration or the presence of "Metal 2" in system_profiler would not, on its own, establish that GPU workloads actually execute correctly.

An independent Metal runtime test executable was therefore used to:

1. Enumerate and select the Intel Metal device.
2. Compile Metal shader functions.
3. Create a Metal command queue and dispatch GPU compute work.
4. Perform offscreen GPU rendering.
5. Read GPU-produced data back to memory and compare it against expected values.

The executable was run **twice** on the patched system.

| Test | Verified result |
| --- | --- |
| Intel Metal device creation | Passed |
| Metal shader compilation | Passed |
| Compute rounds per execution | 3 / 3 |
| Compute results checked per round | 4096, all correct |
| Offscreen render rounds per execution | 3 / 3 |
| Pixels checked per render round | 4096, all correct |
| Full executions | 2 / 2 passed |
| Process exit codes | 0 on both runs |

Representative output (the same checks passed in both runs):

~~~text
MetalDeviceCount=1
SelectedGPU=Intel(R) TGL Unknown
PASS METAL_LIBRARY
PASS COMPUTE round=1 values=4096
PASS COMPUTE round=2 values=4096
PASS COMPUTE round=3 values=4096
PASS RENDER round=1 pixels=4096
PASS RENDER round=2 pixels=4096
PASS RENDER round=3 pixels=4096
PASS ALL: GPU compute and offscreen rendering readback verified
~~~

These results confirm that basic Metal GPU compute, offscreen rendering, and readback work on the tested configuration. They do not, by themselves, establish long-term GPU stability or support for every Metal feature.

The sanitized records are available as after-fix.txt and metal-test.txt in the local evidence bundle.

## 6. Compatibility across macOS versions

A goal of this change is to reduce dependence on the exact binary layout produced by a particular macOS kernel Build.

The previous strict comparison could fail when a compiler/linker layout change altered a relative CALL displacement even though the called function remained the same.

By checking the resolved destination, the guard can tolerate **some** kernel layout changes as long as the surrounding expectations and all other guards remain valid.

### Compatibility principles

- Keep the existing OS-version detection and dispatch.
- Keep the MMIO implementations for the different macOS families separate.
- Change only the confirmed Sequoia CALL displacement check.
- Reject unexpected opcodes, destinations and other failed guard conditions.
- Avoid adding a special case that only works for one macOS Build.

### Verified coverage

| Target | Verification status |
| --- | --- |
| Original 24H32 instruction pattern | Offline regression test passed |
| Sequoia 15.8.2 / 24H232 | Kernel inspection and real hardware tests passed |
| Other Sequoia Builds | Not comprehensively verified |
| Other macOS families | Paths unchanged; no comprehensive real-hardware regression in this PR |

**This does not guarantee future macOS updates.** Other kernel instructions, APIs, ABIs or graphics-driver behavior may change and require further adaptation.

## 7. Compatibility across hardware configurations

The fix uses a general x86-64 CALL target check rather than a laptop-specific identifier or fixed per-device address.

The modified guard does not depend on:

- Lenovo 82GM as a model identifier.
- A particular internal display or EDID.
- A specific GPU Execution Unit count.
- A particular BIOS implementation.
- A fixed framebuffer configuration.
- A motherboard vendor.

Therefore, this patch does not intentionally narrow support to the test laptop.

Nevertheless, different systems can have important differences in GPU initialization, MMIO mapping, framebuffer arrangements, connector wiring, firmware, and power management. Those differences are outside the scope of this guard-level fix.

**The only real-hardware configuration validated for this patch is Intel Iris Xe 80 EU (8086:9A49).** No additional hardware compatibility is claimed for other Tiger Lake configurations or other GPU families supported by WhateverXe.

No existing hardware support list is changed by this PR.

## 8. Safety and regression considerations

The patch is intentionally narrow to reduce regression risk for configurations already working with the upstream driver.

It follows these rules:

- Do not bypass guard checks to make one kernel Build pass.
- Continue requiring the correct CALL opcode and target.
- Preserve all eight unrelated instruction checks.
- Preserve existing MMIO prerequisite checks.
- Avoid modifying unrelated kernel patching logic.
- Do not change other macOS adaptation paths.
- Do not introduce a device-specific exception.

The new check accepts a differently encoded relative displacement **only when it resolves to the intended target**. It does not accept an arbitrary unknown CALL.

If the required symbol cannot be resolved, the opcode or destination does not match, or other prerequisites fail, the relevant guard remains unsatisfied.

The original 24H32 pattern was tested for regression, but complete coverage of all previously supported macOS Builds and hardware combinations is not available. Residual regression risk cannot be ruled out without broader testing.

## 9. Known limitations

The following items have **not** been fully verified by this patch and its current test evidence:

- Extended GPU stress testing and thermal/power behavior.
- GPU state recovery after sleep and wake.
- H.264 / HEVC hardware video encoding and decoding.
- HDMI, USB-C/DisplayPort, multi-monitor operation and hot-plug.
- Full OpenGL and Metal feature coverage.
- Every GPU family supported by WhateverXe.
- Compatibility after future macOS updates.

These items should not be inferred from the successful basic Metal tests.

## 10. Possible follow-up work

This PR addresses a confirmed fixed-displacement compatibility issue while keeping the reviewable change small.

Possible follow-up improvements, preferably in separate changes, include:

1. Auditing the other OS-version-specific paths for similarly brittle machine-code comparisons.
2. Reusing semantic instruction validation utilities where their assumptions can be proved safe.
3. Building regression fixtures for additional macOS kernel Builds.
4. Improving cross-version resilience without removing the existing safety checks.
5. Collecting real hardware reports across different Tiger Lake and other supported GPU configurations.

A broad cross-version rewrite is intentionally **not** included in this PR, to avoid mixing an independently validated fix with larger, harder-to-review changes.

## 11. Conclusion

This patch fixes a confirmed Sequoia 24H232 MMIO UC initialization failure caused by an exact comparison of a build-dependent CALL rel32 displacement.

Validating the dynamically resolved call destination instead of the complete displacement bytes allows the guard to accept the expected instruction semantics while retaining the other checks.

The change:

- Fixes the tested Sequoia 24H232 incompatibility.
- Preserves existing guard conditions.
- Introduces no laptop-specific or GPU-ID-specific workaround.
- Leaves other macOS-version paths unchanged.
- Passes automated tests, kernel inspection and actual Metal compute/render tests on hardware.

The intended outcome is a minimal, reviewable improvement to macOS kernel Build compatibility with lower risk to existing hardware support—not an unverified claim of universal macOS or GPU compatibility.

### Evidence references

The accompanying **sanitized** local review bundle contains:

- evidence/before-fix.txt — pre-fix Kext, guard, MMIO and accelerator state.
- evidence/after-fix.txt — post-fix Kext identity and restored accelerator initialization.
- evidence/metal-test.txt — both Metal compute/render test results.

The essential values and outputs are reproduced above, so the PR description remains useful even if the full original diagnostic archives are not publicly uploaded.

CI: https://github.com/91270/WhateverXe/actions/runs/41173906479

Patch commit: https://github.com/91270/WhateverXe/commit/edc358c

