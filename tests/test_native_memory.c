#include "d2e/native_runtime.h"

#include <stdio.h>
#include <stdlib.h>

extern const d2e_native_program d2e_generated_program;

int main(void) {
    const size_t conventional_size = UINT32_C(128) * 1024U;
    uint8_t *const memory = calloc(conventional_size, 1);
    d2e_x86_cpu cpu;
    int failed = 0;

    if (memory == NULL) {
        return 2;
    }
    d2e_x86_cpu_init(&cpu, memory, conventional_size, NULL);
    if (!d2e_native_load(&cpu, &d2e_generated_program)) {
        fprintf(stderr, "memory fixture load failed\n");
        failed = 1;
    } else {
        cpu.segments[D2E_X86_ES] = UINT16_C(0x1100);
        if (d2e_native_run(&cpu, &d2e_generated_program, 100U) !=
            D2E_X86_EXITED) {
            fprintf(stderr, "memory fixture stopped: %u at %04x:%04x\n",
                    (unsigned)cpu.stop_reason, cpu.fault_cs, cpu.fault_ip);
            failed = 1;
        } else if (cpu.regs[D2E_X86_DX] != UINT16_C(0x1234) ||
                   d2e_x86_read16_seg(&cpu, UINT16_C(0x1000),
                                      UINT16_C(0x0207)) != UINT16_C(0x1234) ||
                   d2e_x86_read8(&cpu, d2e_x86_linear(UINT16_C(0x1000),
                                                       UINT16_C(0x02ff))) !=
                       UINT8_C(0x7f) ||
                   d2e_x86_read8(&cpu, d2e_x86_linear(UINT16_C(0x1100),
                                                       UINT16_C(0x0200))) !=
                       UINT8_C(0x55) ||
                   cpu.instructions_retired != UINT64_C(9)) {
            fprintf(stderr,
                    "unexpected memory state: dx=%04x dsword=%04x "
                    "ssbyte=%02x esbyte=%02x instructions=%llu\n",
                    cpu.regs[D2E_X86_DX],
                    d2e_x86_read16_seg(&cpu, UINT16_C(0x1000),
                                       UINT16_C(0x0207)),
                    d2e_x86_read8(&cpu, d2e_x86_linear(UINT16_C(0x1000),
                                                        UINT16_C(0x02ff))),
                    d2e_x86_read8(&cpu, d2e_x86_linear(UINT16_C(0x1100),
                                                        UINT16_C(0x0200))),
                    (unsigned long long)cpu.instructions_retired);
            failed = 1;
        }
    }

    free(memory);
    if (failed) {
        return 1;
    }
    puts("native ModR/M memory test passed");
    return 0;
}
