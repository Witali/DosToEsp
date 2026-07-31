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
        fprintf(stderr, "call fixture load failed\n");
        failed = 1;
    } else {
        cpu.segments[D2E_X86_ES] = UINT16_C(0x1100);
        if (d2e_native_run(&cpu, &d2e_generated_program, 100U) !=
            D2E_X86_EXITED) {
            fprintf(stderr, "call fixture stopped: %u at %04x:%04x\n",
                    (unsigned)cpu.stop_reason, cpu.fault_cs, cpu.fault_ip);
            failed = 1;
        } else if (cpu.regs[D2E_X86_AX] != UINT16_C(7) ||
                   cpu.regs[D2E_X86_BX] != UINT16_C(1) ||
                   cpu.regs[D2E_X86_DX] != UINT16_C(0x1000) ||
                   cpu.regs[D2E_X86_SP] != UINT16_C(0xfffe) ||
                   cpu.segments[D2E_X86_ES] != UINT16_C(0x1000) ||
                   d2e_x86_read16_seg(&cpu, UINT16_C(0x1000),
                                      UINT16_C(0xfffa)) != UINT16_C(0x0115) ||
                   d2e_x86_read16_seg(&cpu, UINT16_C(0x1000),
                                      UINT16_C(0xfffc)) != UINT16_C(0x010f) ||
                   cpu.instructions_retired != UINT64_C(14)) {
            fprintf(stderr,
                    "unexpected call state: ax=%04x bx=%04x dx=%04x "
                    "sp=%04x es=%04x inner=%04x outer=%04x instructions=%llu\n",
                    cpu.regs[D2E_X86_AX], cpu.regs[D2E_X86_BX],
                    cpu.regs[D2E_X86_DX], cpu.regs[D2E_X86_SP],
                    cpu.segments[D2E_X86_ES],
                    d2e_x86_read16_seg(&cpu, UINT16_C(0x1000),
                                       UINT16_C(0xfffa)),
                    d2e_x86_read16_seg(&cpu, UINT16_C(0x1000),
                                       UINT16_C(0xfffc)),
                    (unsigned long long)cpu.instructions_retired);
            failed = 1;
        }
    }

    free(memory);
    if (failed) {
        return 1;
    }
    puts("native stack and call test passed");
    return 0;
}
