#include "d2e/native_runtime.h"

#include <stdio.h>
#include <stdlib.h>

extern const d2e_native_program d2e_generated_program;

int main(void) {
    const size_t conventional_size = UINT32_C(128) * 1024U;
    uint8_t *const memory = calloc(conventional_size, 1);
    uint32_t *const generations = calloc(D2E_X86_PAGE_COUNT, sizeof(uint32_t));
    d2e_x86_cpu cpu;
    int failed = 0;

    if (memory == NULL || generations == NULL) {
        fprintf(stderr, "allocation failed\n");
        free(generations);
        free(memory);
        return 2;
    }
    d2e_x86_cpu_init(&cpu, memory, conventional_size, generations);
    if (!d2e_native_load_com(&cpu, &d2e_generated_program)) {
        fprintf(stderr, "COM load failed\n");
        failed = 1;
    } else if (d2e_native_run(&cpu, &d2e_generated_program, 100U) !=
               D2E_X86_EXITED) {
        fprintf(stderr, "native program stopped: %u at %04x:%04x\n",
                (unsigned)cpu.stop_reason, cpu.fault_cs, cpu.fault_ip);
        failed = 1;
    } else if (cpu.exit_code != 42U || cpu.regs[D2E_X86_CX] != 0U ||
               cpu.instructions_retired != UINT64_C(15)) {
        fprintf(stderr,
                "unexpected state: exit=%u ax=%04x cx=%04x instructions=%llu\n",
                cpu.exit_code, cpu.regs[D2E_X86_AX], cpu.regs[D2E_X86_CX],
                (unsigned long long)cpu.instructions_retired);
        failed = 1;
    }

    free(generations);
    free(memory);
    if (failed) {
        return 1;
    }
    puts("native translated COM test passed");
    return 0;
}
