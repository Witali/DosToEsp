#include "d2e/native_runtime.h"

#include <stdio.h>
#include <stdlib.h>

static int test_mz_load(void) {
    static const uint8_t module[] = {
        UINT8_C(0x90), UINT8_C(0x90), UINT8_C(0x34), UINT8_C(0x12),
        UINT8_C(0xaa), UINT8_C(0xbb), UINT8_C(0xcc), UINT8_C(0xdd),
    };
    static const d2e_mz_relocation relocations[] = {
        {UINT16_C(0x0002), UINT16_C(0x0000)},
    };
    static const d2e_native_program program = {
        .name = "synthetic_mz",
        .format = D2E_NATIVE_IMAGE_MZ,
        .load_segment = UINT16_C(0x1000),
        .entry_cs = UINT16_C(0x0002),
        .entry_ip = UINT16_C(0x0040),
        .initial_ss = UINT16_C(0x0003),
        .initial_sp = UINT16_C(0x0100),
        .image = module,
        .image_size = sizeof(module),
        .relocations = relocations,
        .relocation_count = sizeof(relocations) / sizeof(relocations[0]),
        .blocks = NULL,
        .block_count = 0,
        .region = NULL,
    };
    const size_t memory_size = UINT32_C(128) * 1024U;
    uint8_t *const memory = calloc(memory_size, 1);
    d2e_x86_cpu cpu;
    const uint32_t psp = d2e_x86_linear(UINT16_C(0x0ff0), 0);
    const uint32_t image = d2e_x86_linear(UINT16_C(0x1000), 0);
    int failed = 0;

    if (memory == NULL) {
        return 1;
    }
    d2e_x86_cpu_init(&cpu, memory, memory_size, NULL);
    if (!d2e_native_load_mz(&cpu, &program)) {
        fprintf(stderr, "synthetic MZ load failed\n");
        failed = 1;
    } else if (cpu.segments[D2E_X86_CS] != UINT16_C(0x1002) ||
               cpu.ip != UINT16_C(0x0040) ||
               cpu.segments[D2E_X86_SS] != UINT16_C(0x1003) ||
               cpu.regs[D2E_X86_SP] != UINT16_C(0x0100) ||
               cpu.segments[D2E_X86_DS] != UINT16_C(0x0ff0) ||
               cpu.segments[D2E_X86_ES] != UINT16_C(0x0ff0)) {
        fprintf(stderr, "unexpected MZ initial register state\n");
        failed = 1;
    } else if (memory[psp] != UINT8_C(0xcd) ||
               memory[psp + 1U] != UINT8_C(0x20) ||
               memory[image] != UINT8_C(0x90) ||
               memory[image + 2U] != UINT8_C(0x34) ||
               memory[image + 3U] != UINT8_C(0x22)) {
        fprintf(stderr, "MZ image or relocation state is incorrect\n");
        failed = 1;
    }
    free(memory);
    return failed;
}

static int test_rejects_bad_mz(void) {
    static const uint8_t module[] = {UINT8_C(0x90)};
    static const d2e_mz_relocation relocation = {
        UINT16_C(0xffff), UINT16_C(0xffff),
    };
    static const d2e_native_program program = {
        .name = "bad_mz",
        .format = D2E_NATIVE_IMAGE_MZ,
        .load_segment = UINT16_C(0x1000),
        .image = module,
        .image_size = sizeof(module),
        .relocations = &relocation,
        .relocation_count = 1,
    };
    const size_t memory_size = UINT32_C(128) * 1024U;
    uint8_t *const memory = calloc(memory_size, 1);
    d2e_x86_cpu cpu;
    int accepted;
    if (memory == NULL) {
        return 1;
    }
    d2e_x86_cpu_init(&cpu, memory, memory_size, NULL);
    accepted = d2e_native_load_mz(&cpu, &program);
    free(memory);
    if (accepted) {
        fprintf(stderr, "out-of-range MZ relocation was accepted\n");
        return 1;
    }
    return 0;
}

int main(void) {
    if (test_mz_load() || test_rejects_bad_mz()) {
        return 1;
    }
    puts("MZ loader tests passed");
    return 0;
}
