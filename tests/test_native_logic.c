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
        fprintf(stderr, "logic fixture failed to run\n");
        failed = 1;
    } else if (cpu.regs[D2E_X86_AX] != UINT16_C(0x07f3) ||
               cpu.regs[D2E_X86_BX] != UINT16_C(0xf00f) ||
               (cpu.flags & (D2E_X86_FLAG_CF | D2E_X86_FLAG_PF |
                             D2E_X86_FLAG_FIXED)) !=
                   (D2E_X86_FLAG_CF | D2E_X86_FLAG_PF |
                    D2E_X86_FLAG_FIXED) ||
               (cpu.flags & (D2E_X86_FLAG_OF | D2E_X86_FLAG_SF |
                             D2E_X86_FLAG_ZF | D2E_X86_FLAG_AF |
                             D2E_X86_FLAG_DF | D2E_X86_FLAG_IF)) != 0U ||
               cpu.instructions_retired != UINT64_C(15)) {
        fprintf(stderr,
                "unexpected logic state: ax=%04x bx=%04x flags=%04x "
                "instructions=%llu\n",
                cpu.regs[D2E_X86_AX], cpu.regs[D2E_X86_BX], cpu.flags,
                (unsigned long long)cpu.instructions_retired);
        failed = 1;
    }

    free(memory);
    if (failed) {
        return 1;
    }
    puts("native boolean and flag test passed");
    return 0;
}
