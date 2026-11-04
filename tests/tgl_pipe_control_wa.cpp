#include "../WhateverXe/kern_tgl_pipe_control_wa.hpp"
#include <array>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <iterator>
#include <vector>

using namespace TGLPipeControlWA;
using Batch = std::array<uint32_t, BatchDwords>;

static Batch sample() {
    Batch a {};
    a[0] = 0x11000001U;
    a[3] = 0x7A000004U;
    a[4] = NativeStallFlags;
    a[9] = 0x69041301U;
    a[10] = 0x6101000EU;
    a[0x9C/4] = 0x18C00001U;
    a[0xA0/4] = 0x4032E000U;
    a[StallCommand] = 0x7A000004U;
    a[StallFlags] = NativeStallFlags;
    a[InvalidateCommand] = 0x7A000004U;
    a[InvalidateFlags] = 0x0000089CU;
    return a;
}
static void checkOnlyOneWordChanged(Batch a) {
    const auto original = a;
    assert(matches(a.data(), a.size()));
    assert(patch(a.data(), a.size()));
    for (unsigned i = 0; i < a.size(); ++i)
        assert(a[i] == (i == StallFlags ? RevisedStallFlags : original[i]));
    assert(a[0x10/4] == NativeStallFlags); // First unrelated stall is unchanged.
    assert(a[InvalidateFlags] == 0x89CU);
    assert(!patch(a.data(), a.size())); // Idempotent; do not double-write.
}
int main(int argc, char **argv) {
    unsigned cases = 0;
    Batch a = sample();
    checkOnlyOneWordChanged(a); ++cases;
    assert(!matches(nullptr, BatchDwords)); ++cases;
    for (unsigned n : {0U, 1U, BatchDwords - 1U, BatchDwords + 1U}) {
        assert(!matches(a.data(), n)); ++cases;
    }
    const unsigned anchors[] = {
        0U, 3U, 4U, 9U, 10U,
        StallCommand, StallFlags, InvalidateCommand, InvalidateFlags
    };
    for (unsigned i : anchors) {
        auto bad = sample(); bad[i] ^= 1U;
        assert(!matches(bad.data(), bad.size()));
        assert(!patch(bad.data(), bad.size()));
        ++cases;
    }
    for (unsigned i = StallFlags + 1; i < InvalidateCommand; ++i) {
        auto bad = sample(); bad[i] = 1;
        assert(!matches(bad.data(), bad.size())); ++cases;
    }
    for (unsigned i = InvalidateFlags + 1; i < BatchDwords; ++i) {
        auto bad = sample(); bad[i] = 1;
        assert(!matches(bad.data(), bad.size())); ++cases;
    }
    // Fails closed on a related instruction-invalidation packet with a
    // different DW1, even when a neighbouring flush is recognizable.
    a = sample(); a[InvalidateFlags] = 0x0000088CU;
    assert(!matches(a.data(), a.size())); ++cases;
    // An optional local 216-byte post-mortem capture is checked without
    // checking it into Git or leaking local machine diagnostics.
    if (argc > 1) {
        std::ifstream f(argv[1], std::ios::binary);
        assert(f.good());
        std::vector<unsigned char> b((std::istreambuf_iterator<char>(f)),
                                     std::istreambuf_iterator<char>());
        assert(b.size() == sizeof(Batch));
        Batch actual {};
        std::memcpy(actual.data(), b.data(), b.size());
        checkOnlyOneWordChanged(actual); ++cases;
    }
    std::printf("Gen12 PIPE_CONTROL repair: %u cases passed\n", cases);
}
