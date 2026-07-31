#include "d2e/native_runtime.h"

#include <stdio.h>
#include <stdlib.h>

extern const d2e_native_program d2e_generated_program;

int main(void) {
    const size_t conventional_size = UINT32_C(128) * 1024U;
    uint8_t *const memory = calloc(conventional_size, 1);
    d2e_x86_cpu cpu;
    const uint16_t expected_flags =
        D2E_X86_FLAG_FIXED | D2E_X86_FLAG_CF | D2E_X86_FLAG_PF |
        D2E_X86_FLAG_AF | D2E_X86_FLAG_ZF;
    int failed = 0;

    if (memory == NULL) {
        return 2;
    }
    d2e_x86_cpu_init(&cpu, memory, conventional_size, NULL);
    if (!d2e_native_load(&cpu, &d2e_generated_program) ||
        d2e_native_run(&cpu, &d2e_generated_program, 100U) !=
            D2E_X86_EXITED) {
        fprintf(stderr, "ADC/flags fixture failed: reason=%u target=%04x:%04x\n",
                (unsigned)cpu.stop_reason, cpu.fault_cs, cpu.fault_ip);
        failed = 1;
    } else if (cpu.regs[D2E_X86_AX] != 0U ||
               cpu.regs[D2E_X86_BX] != UINT16_C(0x0114) ||
               cpu.regs[D2E_X86_SP] != UINT16_C(0xfffe) ||
               cpu.flags != expected_flags ||
               cpu.ip != UINT16_C(0x0114) ||
               cpu.instructions_retired != UINT64_C(14)) {
        fprintf(stderr,
                "unexpected ADC/flags state: ax=%04x bx=%04x sp=%04x "
                "flags=%04x ip=%04x instructions=%llu\n",
                cpu.regs[D2E_X86_AX], cpu.regs[D2E_X86_BX],
                cpu.regs[D2E_X86_SP], cpu.flags, cpu.ip,
                (unsigned long long)cpu.instructions_retired);
        failed = 1;
    }

    free(memory);
    if (failed) {
        return 1;
    }
    puts("native ADC and flags-stack test passed");
    return 0;
}
