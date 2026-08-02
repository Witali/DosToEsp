#include "d2e/native_runtime.h"

#include <stdio.h>
#include <stdlib.h>

typedef struct interrupt_state {
    uint8_t numbers[2];
    uint16_t return_ips[2];
    unsigned count;
} interrupt_state;

extern const d2e_native_program d2e_generated_program;

static int interrupt(void *context, d2e_x86_cpu *cpu, uint8_t number) {
    interrupt_state *const state = context;
    if (state->count >= 2U || (number != 3U && number != 4U)) {
        return 0;
    }
    state->numbers[state->count] = number;
    state->return_ips[state->count] = cpu->ip;
    ++state->count;
    return 1;
}

int main(void) {
    const size_t conventional_size = UINT32_C(128) * 1024U;
    uint8_t *const memory = calloc(conventional_size, 1);
    interrupt_state state = {{0}, {0}, 0};
    d2e_x86_cpu cpu;
    int failed = 0;

    if (memory == NULL) {
        return 2;
    }
    d2e_x86_cpu_init(&cpu, memory, conventional_size, NULL);
    d2e_x86_configure_interrupts(&cpu, &state, interrupt);
    if (!d2e_native_load(&cpu, &d2e_generated_program) ||
        d2e_native_run(&cpu, &d2e_generated_program, 100U) !=
            D2E_X86_EXITED) {
        fprintf(stderr, "control fixture failed: reason=%u target=%04x:%04x\n",
                (unsigned)cpu.stop_reason, cpu.fault_cs, cpu.fault_ip);
        failed = 1;
    } else if (state.count != 2U || state.numbers[0] != 3U ||
               state.return_ips[0] != UINT16_C(0x0117) ||
               state.numbers[1] != 4U ||
               state.return_ips[1] != UINT16_C(0x011f) ||
               cpu.regs[D2E_X86_AX] != UINT16_C(0x8000) ||
               cpu.regs[D2E_X86_BX] != UINT16_C(0x0116) ||
               cpu.regs[D2E_X86_CX] != UINT16_C(1) ||
               cpu.regs[D2E_X86_DX] != 0U ||
               cpu.regs[D2E_X86_SI] != UINT16_C(2) ||
               cpu.regs[D2E_X86_SP] != UINT16_C(0xfffe) ||
               cpu.segments[D2E_X86_CS] != UINT16_C(0x1000) ||
               cpu.ip != UINT16_C(0x012f) ||
               d2e_x86_read16_seg(&cpu, UINT16_C(0x1000),
                                  UINT16_C(0xfffa)) != UINT16_C(0x0128) ||
               d2e_x86_read16_seg(&cpu, UINT16_C(0x1000),
                                  UINT16_C(0xfffc)) != UINT16_C(0x1000) ||
               cpu.instructions_retired != UINT64_C(24)) {
        fprintf(stderr,
                "unexpected control state: interrupts=%u ax=%04x bx=%04x "
                "cx=%04x dx=%04x si=%04x sp=%04x cs:ip=%04x:%04x "
                "stack=%04x/%04x instructions=%llu\n",
                state.count, cpu.regs[D2E_X86_AX], cpu.regs[D2E_X86_BX],
                cpu.regs[D2E_X86_CX], cpu.regs[D2E_X86_DX],
                cpu.regs[D2E_X86_SI], cpu.regs[D2E_X86_SP],
                cpu.segments[D2E_X86_CS], cpu.ip,
                d2e_x86_read16_seg(&cpu, UINT16_C(0x1000),
                                   UINT16_C(0xfffa)),
                d2e_x86_read16_seg(&cpu, UINT16_C(0x1000),
                                   UINT16_C(0xfffc)),
                (unsigned long long)cpu.instructions_retired);
        failed = 1;
    }

    free(memory);
    if (failed) {
        return 1;
    }
    puts("native complete control-flow test passed");
    return 0;
}
