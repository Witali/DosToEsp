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
        fprintf(stderr, "IRQ fixture setup failed: reason=%u\n",
                (unsigned)cpu.stop_reason);
        failed = 1;
    } else if (d2e_x86_read16(&cpu, UINT32_C(0x24)) != UINT16_C(0x0120) ||
               d2e_x86_read16(&cpu, UINT32_C(0x26)) != UINT16_C(0x1000)) {
        fprintf(stderr, "IRQ vector was not installed\n");
        failed = 1;
    }

    cpu.regs[D2E_X86_AX] = 0U;
    cpu.regs[D2E_X86_SP] = UINT16_C(0x0200);
    cpu.segments[D2E_X86_CS] = UINT16_C(0x1000);
    cpu.ip = UINT16_C(0x0120);
    d2e_x86_write16_seg(&cpu, cpu.segments[D2E_X86_SS], UINT16_C(0x0200),
                        UINT16_C(0x0100));
    d2e_x86_write16_seg(&cpu, cpu.segments[D2E_X86_SS], UINT16_C(0x0202),
                        UINT16_C(0x1000));
    d2e_x86_write16_seg(
        &cpu, cpu.segments[D2E_X86_SS], UINT16_C(0x0204),
        D2E_X86_FLAG_CF | D2E_X86_FLAG_FIXED);
    if (!failed &&
        d2e_native_run(&cpu, &d2e_generated_program, 100U) !=
            D2E_X86_EXITED) {
        fprintf(stderr, "IRET path failed: reason=%u target=%04x:%04x\n",
                (unsigned)cpu.stop_reason, cpu.fault_cs, cpu.fault_ip);
        failed = 1;
    } else if (!failed &&
               (cpu.regs[D2E_X86_SP] != UINT16_C(0x0206) ||
                cpu.flags != (D2E_X86_FLAG_CF | D2E_X86_FLAG_FIXED) ||
                cpu.instructions_retired != UINT64_C(17))) {
        fprintf(stderr, "unexpected IRET state: sp=%04x flags=%04x ins=%llu\n",
                cpu.regs[D2E_X86_SP], cpu.flags,
                (unsigned long long)cpu.instructions_retired);
        failed = 1;
    }

    cpu.regs[D2E_X86_AX] = UINT16_C(1);
    cpu.segments[D2E_X86_CS] = UINT16_C(0x1000);
    cpu.ip = UINT16_C(0x0120);
    if (!failed &&
        d2e_native_run(&cpu, &d2e_generated_program, 100U) !=
            D2E_X86_UNTRANSLATED_TARGET) {
        fprintf(stderr, "external far JMP did not stop strictly\n");
        failed = 1;
    } else if (!failed &&
               (cpu.fault_cs != UINT16_C(0xf000) ||
                cpu.fault_ip != UINT16_C(0xe05b))) {
        fprintf(stderr, "wrong external target: %04x:%04x\n", cpu.fault_cs,
                cpu.fault_ip);
        failed = 1;
    }

    free(memory);
    if (failed) {
        return 1;
    }
    puts("native IRQ root, IRET and far-JMP test passed");
    return 0;
}
