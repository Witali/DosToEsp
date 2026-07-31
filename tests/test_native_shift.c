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
    if (!d2e_native_load(&cpu, &d2e_generated_program) ||
        d2e_native_run(&cpu, &d2e_generated_program, 100U) !=
            D2E_X86_EXITED) {
        fprintf(stderr, "shift fixture failed to run\n");
        failed = 1;
    } else if (cpu.regs[D2E_X86_AX] != 0U ||
               d2e_x86_get_reg8(&cpu, 3U) != UINT8_C(0x80) ||
               d2e_x86_get_reg8(&cpu, 1U) != UINT8_C(4) ||
               (cpu.flags & (D2E_X86_FLAG_ZF | D2E_X86_FLAG_PF)) !=
                   (D2E_X86_FLAG_ZF | D2E_X86_FLAG_PF) ||
               (cpu.flags & D2E_X86_FLAG_CF) != 0U ||
               cpu.instructions_retired != UINT64_C(7)) {
        fprintf(stderr,
                "unexpected shift state: ax=%04x bl=%02x cl=%02x "
                "flags=%04x instructions=%llu\n",
                cpu.regs[D2E_X86_AX], d2e_x86_get_reg8(&cpu, 3U),
                d2e_x86_get_reg8(&cpu, 1U), cpu.flags,
                (unsigned long long)cpu.instructions_retired);
        failed = 1;
    }

    free(memory);
    if (failed) {
        return 1;
    }
    puts("native shift and rotate test passed");
    return 0;
}
