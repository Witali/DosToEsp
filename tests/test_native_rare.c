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
        fprintf(stderr, "rare fixture failed: reason=%u target=%04x:%04x\n",
                (unsigned)cpu.stop_reason, cpu.fault_cs, cpu.fault_ip);
        failed = 1;
    } else if (cpu.regs[D2E_X86_AX] != UINT16_C(0x0a00) ||
               cpu.regs[D2E_X86_BX] != UINT16_C(2) ||
               cpu.regs[D2E_X86_CX] != UINT16_C(1) ||
               cpu.regs[D2E_X86_DX] != UINT16_C(0x0139) ||
               cpu.regs[D2E_X86_BP] != UINT16_C(0x0a00) ||
               cpu.regs[D2E_X86_SI] != UINT16_C(6) ||
               cpu.regs[D2E_X86_DI] != UINT16_C(0x3412) ||
               cpu.regs[D2E_X86_SP] != UINT16_C(0xfffe) ||
               cpu.ip != UINT16_C(0x013a) ||
               cpu.instructions_retired != UINT64_C(26)) {
        fprintf(stderr,
                "unexpected rare state: ax=%04x bx=%04x cx=%04x dx=%04x "
                "bp=%04x si=%04x di=%04x sp=%04x ip=%04x instructions=%llu\n",
                cpu.regs[D2E_X86_AX], cpu.regs[D2E_X86_BX],
                cpu.regs[D2E_X86_CX], cpu.regs[D2E_X86_DX],
                cpu.regs[D2E_X86_BP], cpu.regs[D2E_X86_SI],
                cpu.regs[D2E_X86_DI], cpu.regs[D2E_X86_SP], cpu.ip,
                (unsigned long long)cpu.instructions_retired);
        failed = 1;
    }

    free(memory);
    if (failed) {
        return 1;
    }
    puts("native rare instruction test passed");
    return 0;
}
