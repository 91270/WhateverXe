// Gen12 RCS PIPE_CONTROL cache-invalidate workaround experiment.
//
// Only the exact 216-byte RCS batch captured in the VideoToolbox hangs is
// accepted. In addition to the pre-invalidate CS+scoreboard stall, replace
// the constant-cache invalidate with HDC pipeline flush + state invalidation
// per Tiger Lake PRM Volume 14 (the documented erratum targets A0/GT1; this
// GT2 B0 application is experimental and unverified on hardware).
// CPU-only fixture tests are not proof that the GPU fault is fixed.
#ifndef KERN_TGL_PIPE_CONTROL_WA_HPP
#define KERN_TGL_PIPE_CONTROL_WA_HPP

#include <stdint.h>

namespace TGLPipeControlWA {
constexpr unsigned BatchDwords = 54;
constexpr unsigned StallCommand = 0xA8 / 4;
constexpr unsigned StallFlags = 0xAC / 4;
constexpr unsigned InvalidateCommand = 0xC0 / 4;
constexpr unsigned InvalidateFlags = 0xC4 / 4;
constexpr uint32_t NativeStallFlags = 0x001010A0U;
constexpr uint32_t RevisedStallFlags = NativeStallFlags | (1U << 1); // scoreboard
constexpr uint32_t NativeInvalidateCommand = 0x7A000004U;
constexpr uint32_t NativeInvalidateFlags = 0x0000089CU;
// DW0[9] = HDC pipeline flush; DW1[3] = constant cache invalidate.
// DW1[2] (state cache invalidate) is already set in the captured packet.
constexpr uint32_t RevisedInvalidateCommand = NativeInvalidateCommand | (1U << 9);
constexpr uint32_t RevisedInvalidateFlags = NativeInvalidateFlags & ~(1U << 3);
constexpr uint64_t NativeInvalidatePair =
    (uint64_t(NativeInvalidateFlags) << 32) | NativeInvalidateCommand;
constexpr uint64_t RevisedInvalidatePair =
    (uint64_t(RevisedInvalidateFlags) << 32) | RevisedInvalidateCommand;
static_assert((RevisedInvalidateFlags & (1U << 2)) != 0, "State invalidate must remain enabled");
static_assert((RevisedInvalidateFlags & (1U << 3)) == 0, "Constant invalidate must be disabled");
static_assert((RevisedInvalidateCommand & (1U << 9)) != 0, "HDC flush must be enabled");

inline bool matches(const uint32_t *words, unsigned count) {
    if (!words || count != BatchDwords) return false;
    if (words[0] != 0x11000001U ||
        words[3] != 0x7A000004U ||
        words[4] != NativeStallFlags ||
        words[9] != 0x69041301U ||
        words[10] != 0x6101000EU ||
        words[StallCommand] != 0x7A000004U ||
        words[StallFlags] != NativeStallFlags ||
        words[InvalidateCommand] != NativeInvalidateCommand ||
        words[InvalidateFlags] != NativeInvalidateFlags) return false;
    for (unsigned i = StallFlags + 1; i < InvalidateCommand; ++i)
        if (words[i] != 0) return false;
    for (unsigned i = InvalidateFlags + 1; i < BatchDwords; ++i)
        if (words[i] != 0) return false;
    // Invalidate the instruction cache, then test that it has a preceding
    // CS stall. Do not attempt to rewrite arbitrary user commands.
    const bool instructionInvalidate = (words[InvalidateFlags] & (1U << 11)) != 0;
    const bool csStall = (words[StallFlags] & (1U << 20)) != 0;
    return instructionInvalidate && csStall;
}
inline bool patch(uint32_t *words, unsigned count) {
    if (!matches(words, count)) return false;
    words[StallFlags] = RevisedStallFlags;
    words[InvalidateCommand] = RevisedInvalidateCommand;
    words[InvalidateFlags] = RevisedInvalidateFlags;
    return true;
}
}
#endif
