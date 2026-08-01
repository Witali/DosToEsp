#include "d2e/native_runtime.h"

#include <stdio.h>
#include <stdlib.h>

extern const d2e_native_program d2e_generated_program;

int main(void) {
    const size_t conventional_size = UINT32_C(128) * 1024U;
    uint8_t *const memory = calloc(conventional_size, 1);
    d2e_x86_cpu cpu;
    uint32_t source;
    uint32_t destination;
    int failed = 0;

    if (memory == NULL) {
        return 2;
    }
    d2e_x86_cpu_init(&cpu, memory, conventional_size, NULL);
    if (!d2e_native_load(&cpu, &d2e_generated_program)) {
        free(memory);
        return 2;
    }
    cpu.segments[D2E_X86_ES] = UINT16_C(0x1100);
    source = d2e_x86_linear(UINT16_C(0x1000), UINT16_C(0x0200));
    destination = d2e_x86_linear(UINT16_C(0x1100), UINT16_C(0x0300));
    memory[source] = UINT8_C(0x11);
    memory[source + 1U] = UINT8_C(0x12);
    memory[source + 2U] = UINT8_C(0x13);
    memory[source + 3U] = UINT8_C(0x44);
    memory[d2e_x86_linear(UINT16_C(0x1100), UINT16_C(0x0400))] =
        UINT8_C(0x10);
    memory[d2e_x86_linear(UINT16_C(0x1100), UINT16_C(0x0401))] =
        UINT8_C(0x20);
    memory[d2e_x86_linear(UINT16_C(0x1100), UINT16_C(0x0402))] =
        UINT8_C(0x33);
    memory[d2e_x86_linear(UINT16_C(0x1100), UINT16_C(0x0403))] =
        UINT8_C(0x40);

    if (d2e_native_run(&cpu, &d2e_generated_program, 100U) !=
        D2E_X86_EXITED) {
        fprintf(stderr, "string fixture failed to run\n");
        failed = 1;
    } else if (cpu.regs[D2E_X86_SI] != UINT16_C(0x0204) ||
               cpu.regs[D2E_X86_DI] != UINT16_C(0x0403) ||
               cpu.regs[D2E_X86_CX] != UINT16_C(1) ||
               cpu.regs[D2E_X86_AX] != UINT16_C(0xbe33) ||
               (cpu.flags & D2E_X86_FLAG_DF) != 0U ||
               (cpu.flags & D2E_X86_FLAG_ZF) == 0U ||
               memory[destination] != UINT8_C(0x11) ||
               memory[destination + 1U] != UINT8_C(0xef) ||
               memory[destination + 2U] != UINT8_C(0xbe) ||
               memory[destination + 3U] != UINT8_C(0xef) ||
               memory[destination + 4U] != UINT8_C(0xbe) ||
               cpu.instructions_retired != UINT64_C(16)) {
        fprintf(stderr,
                "unexpected string state: ax=%04x cx=%04x si=%04x di=%04x "
                "flags=%04x bytes=%02x,%02x,%02x,%02x,%02x instructions=%llu\n",
                cpu.regs[D2E_X86_AX], cpu.regs[D2E_X86_CX],
                cpu.regs[D2E_X86_SI], cpu.regs[D2E_X86_DI], cpu.flags,
                memory[destination], memory[destination + 1U],
                memory[destination + 2U], memory[destination + 3U],
                memory[destination + 4U],
                (unsigned long long)cpu.instructions_retired);
        failed = 1;
    }

    free(memory);
    if (failed) {
        return 1;
    }
    puts("native string and REP test passed");
    return 0;
}
