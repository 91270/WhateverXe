// Gen12 RCS PIPE_CONTROL pre-invalidate scoreboard workaround candidate.
//
// The only accepted packet is the precisely witnessed 216-byte render batch.
// Change DW1 of the PRECEDING CS stall, never the invalidating PIPE_CONTROL.
// This header has no kernel dependencies and can be fixture tested offline.
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

inline bool matches(const uint32_t *words, unsigned count) {
    if (!words || count != BatchDwords) return false;
    if (words[0] != 0x11000001U ||
        words[3] != 0x7A000004U ||
        words[4] != NativeStallFlags ||
        words[9] != 0x69041301U ||
        words[10] != 0x6101000EU ||
        words[StallCommand] != 0x7A000004U ||
        words[StallFlags] != NativeStallFlags ||
        words[InvalidateCommand] != 0x7A000004U ||
        words[InvalidateFlags] != 0x0000089CU) return false;
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
    return true;
}
}
#endif
