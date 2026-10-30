// Offscreen Metal compute + render validation. No external assets, GUI or root.
#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#import <dispatch/dispatch.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

static const NSUInteger kComputeCount = 4096;
static const NSUInteger kRenderWidth = 64;
static const NSUInteger kRenderHeight = 64;
static const NSUInteger kRounds = 3;

static BOOL complete(id<MTLCommandBuffer> commandBuffer, const char *stage) {
    dispatch_semaphore_t sem = dispatch_semaphore_create(0);
    [commandBuffer addCompletedHandler:^(id<MTLCommandBuffer> completed) {
        (void)completed;
        dispatch_semaphore_signal(sem);
    }];
    [commandBuffer commit];
    if (dispatch_semaphore_wait(sem, dispatch_time(DISPATCH_TIME_NOW, 20LL * NSEC_PER_SEC)) != 0) {
        printf("FAIL %s: GPU command timed out after 20 seconds\n", stage);
        return NO;
    }
    if (commandBuffer.status != MTLCommandBufferStatusCompleted || commandBuffer.error) {
        printf("FAIL %s: command status=%ld, error=%s\n", stage,
               (long)commandBuffer.status,
               commandBuffer.error ? commandBuffer.error.localizedDescription.UTF8String : "none");
        return NO;
    }
    return YES;
}

static BOOL computeTest(id<MTLDevice> device, id<MTLLibrary> library, id<MTLCommandQueue> queue) {
    id<MTLFunction> function = [library newFunctionWithName:@"testCompute"];
    if (!function) {
        puts("FAIL COMPUTE: shader function unavailable");
        return NO;
    }
    NSError *error = nil;
    id<MTLComputePipelineState> pipeline = [device newComputePipelineStateWithFunction:function error:&error];
    if (!pipeline) {
        printf("FAIL COMPUTE: pipeline: %s\n", error.localizedDescription.UTF8String);
        return NO;
    }
    id<MTLBuffer> result = [device newBufferWithLength:kComputeCount * sizeof(uint32_t)
                                              options:MTLResourceStorageModeShared];
    if (!result) {
        puts("FAIL COMPUTE: shared output buffer allocation");
        return NO;
    }
    const NSUInteger groupSize = MIN((NSUInteger)128, pipeline.maxTotalThreadsPerThreadgroup);
    if (!groupSize) {
        puts("FAIL COMPUTE: no executable threadgroup size");
        return NO;
    }
    for (NSUInteger round = 0; round < kRounds; round++) {
        memset(result.contents, 0, result.length);
        id<MTLCommandBuffer> cb = [queue commandBuffer];
        if (!cb) {
            puts("FAIL COMPUTE: command buffer unavailable");
            return NO;
        }
        id<MTLComputeCommandEncoder> encoder = [cb computeCommandEncoder];
        if (!encoder) {
            puts("FAIL COMPUTE: command encoder unavailable");
            return NO;
        }
        [encoder setComputePipelineState:pipeline];
        [encoder setBuffer:result offset:0 atIndex:0];
        [encoder dispatchThreads:MTLSizeMake(kComputeCount, 1, 1)
         threadsPerThreadgroup:MTLSizeMake(groupSize, 1, 1)];
        [encoder endEncoding];
        if (!complete(cb, "COMPUTE")) return NO;
        const uint32_t *values = (const uint32_t *)result.contents;
        for (NSUInteger i = 0; i < kComputeCount; i++) {
            const uint32_t expected = (((uint32_t)i) * 3u) ^ 0xA5A55A5Au;
            if (values[i] != expected) {
                printf("FAIL COMPUTE: round=%lu index=%lu expected=0x%08x got=0x%08x\n",
                       (unsigned long)round, (unsigned long)i, expected, values[i]);
                return NO;
            }
        }
        printf("PASS COMPUTE round=%lu values=%lu\n",
               (unsigned long)(round + 1), (unsigned long)kComputeCount);
    }
    return YES;
}

static BOOL renderTest(id<MTLDevice> device, id<MTLLibrary> library, id<MTLCommandQueue> queue) {
    id<MTLFunction> vertex = [library newFunctionWithName:@"testVertex"];
    id<MTLFunction> fragment = [library newFunctionWithName:@"testFragment"];
    if (!vertex || !fragment) {
        puts("FAIL RENDER: shaders unavailable");
        return NO;
    }
    MTLRenderPipelineDescriptor *descriptor = [MTLRenderPipelineDescriptor new];
    descriptor.vertexFunction = vertex;
    descriptor.fragmentFunction = fragment;
    descriptor.colorAttachments[0].pixelFormat = MTLPixelFormatRGBA8Unorm;
    NSError *error = nil;
    id<MTLRenderPipelineState> pipeline = [device newRenderPipelineStateWithDescriptor:descriptor error:&error];
    if (!pipeline) {
        printf("FAIL RENDER: pipeline: %s\n", error.localizedDescription.UTF8String);
        return NO;
    }
    MTLTextureDescriptor *textureDescriptor =
        [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:MTLPixelFormatRGBA8Unorm
                                                            width:kRenderWidth
                                                           height:kRenderHeight
                                                        mipmapped:NO];
    textureDescriptor.storageMode = MTLStorageModePrivate;
    textureDescriptor.usage = MTLTextureUsageRenderTarget;
    id<MTLTexture> target = [device newTextureWithDescriptor:textureDescriptor];
    const NSUInteger byteLength = kRenderWidth * kRenderHeight * 4;
    id<MTLBuffer> readback = [device newBufferWithLength:byteLength
                                                options:MTLResourceStorageModeShared];
    if (!target || !readback) {
        puts("FAIL RENDER: target or readback buffer allocation");
        return NO;
    }
    for (NSUInteger round = 0; round < kRounds; round++) {
        memset(readback.contents, 0, readback.length);
        MTLRenderPassDescriptor *pass = [MTLRenderPassDescriptor renderPassDescriptor];
        pass.colorAttachments[0].texture = target;
        pass.colorAttachments[0].loadAction = MTLLoadActionClear;
        pass.colorAttachments[0].storeAction = MTLStoreActionStore;
        pass.colorAttachments[0].clearColor = MTLClearColorMake(0, 0, 0, 1);
        id<MTLCommandBuffer> cb = [queue commandBuffer];
        if (!cb) {
            puts("FAIL RENDER: command buffer unavailable");
            return NO;
        }
        id<MTLRenderCommandEncoder> renderer = [cb renderCommandEncoderWithDescriptor:pass];
        if (!renderer) {
            puts("FAIL RENDER: render encoder unavailable");
            return NO;
        }
        [renderer setRenderPipelineState:pipeline];
        [renderer drawPrimitives:MTLPrimitiveTypeTriangle vertexStart:0 vertexCount:3];
        [renderer endEncoding];
        id<MTLBlitCommandEncoder> blit = [cb blitCommandEncoder];
        if (!blit) {
            puts("FAIL RENDER: blit encoder unavailable");
            return NO;
        }
        [blit copyFromTexture:target
                 sourceSlice:0 sourceLevel:0
                sourceOrigin:MTLOriginMake(0, 0, 0)
                  sourceSize:MTLSizeMake(kRenderWidth, kRenderHeight, 1)
                    toBuffer:readback
           destinationOffset:0
      destinationBytesPerRow:kRenderWidth * 4
    destinationBytesPerImage:byteLength];
        [blit endEncoding];
        if (!complete(cb, "RENDER")) return NO;
        const uint8_t *bytes = (const uint8_t *)readback.contents;
        for (NSUInteger px = 0; px < kRenderWidth * kRenderHeight; px++) {
            NSUInteger offset = px * 4;
            // Unsigned normalized RGBA8, full-screen bright green fragment.
            if (bytes[offset] != 0 || bytes[offset + 1] != 255 ||
                bytes[offset + 2] != 0 || bytes[offset + 3] != 255) {
                printf("FAIL RENDER: round=%lu pixel=%lu RGBA=%u,%u,%u,%u\n",
                       (unsigned long)round, (unsigned long)px,
                       bytes[offset], bytes[offset + 1], bytes[offset + 2], bytes[offset + 3]);
                return NO;
            }
        }
        printf("PASS RENDER round=%lu pixels=%lu\n",
               (unsigned long)(round + 1), (unsigned long)(kRenderWidth * kRenderHeight));
    }
    return YES;
}

int main(void) {
    @autoreleasepool {
        setvbuf(stdout, NULL, _IONBF, 0);
        puts("WhateverXe independent Metal GPU runtime validation v1");
        printf("System=%s\n", NSProcessInfo.processInfo.operatingSystemVersionString.UTF8String);
        NSArray<id<MTLDevice>> *devices = MTLCopyAllDevices();
        printf("MetalDeviceCount=%lu\n", (unsigned long)devices.count);
        for (id<MTLDevice> candidate in devices) {
            printf("DEVICE name=%s registryID=%llu lowPower=%s\n",
                   candidate.name.UTF8String,
                   (unsigned long long)candidate.registryID,
                   candidate.isLowPower ? "yes" : "no");
        }
        id<MTLDevice> device = MTLCreateSystemDefaultDevice();
        if (!device) {
            puts("FAIL: No default Metal device");
            return 10;
        }
        if ([device.name rangeOfString:@"Intel" options:NSCaseInsensitiveSearch].location == NSNotFound) {
            printf("FAIL: Default Metal device is not Intel: %s\n", device.name.UTF8String);
            return 11;
        }
        printf("SelectedGPU=%s\n", device.name.UTF8String);
        id<MTLCommandQueue> queue = [device newCommandQueue];
        if (!queue) {
            puts("FAIL: Metal command queue creation");
            return 12;
        }
        NSString *source =
            @"#include <metal_stdlib>\n"
            @"using namespace metal;\n"
            @"kernel void testCompute(device uint* output [[buffer(0)]], uint i [[thread_position_in_grid]]) {\n"
            @"    output[i] = (i * 3u) ^ 0xA5A55A5Au;\n"
            @"}\n"
            @"struct VSOutput { float4 position [[position]]; };\n"
            @"vertex VSOutput testVertex(uint vertexID [[vertex_id]]) {\n"
            @"    const float2 positions[3] = {float2(-1.0,-1.0), float2(3.0,-1.0), float2(-1.0,3.0)};\n"
            @"    VSOutput result;\n"
            @"    result.position = float4(positions[vertexID], 0.0, 1.0);\n"
            @"    return result;\n"
            @"}\n"
            @"fragment float4 testFragment() { return float4(0.0,1.0,0.0,1.0); }\n";
        NSError *error = nil;
        id<MTLLibrary> library = [device newLibraryWithSource:source options:nil error:&error];
        if (!library) {
            printf("FAIL: Metal shader compilation: %s\n", error.localizedDescription.UTF8String);
            return 13;
        }
        puts("PASS METAL_LIBRARY");
        if (!computeTest(device, library, queue)) return 20;
        if (!renderTest(device, library, queue)) return 30;
        puts("PASS ALL: GPU compute and offscreen rendering readback verified");
        return 0;
    }
}
