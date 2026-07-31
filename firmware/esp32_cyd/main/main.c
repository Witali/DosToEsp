#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>

#include "esp_heap_caps.h"
#include "esp_rom_sys.h"
#include "esp_system.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "d2e/cga.h"
#include "d2e/native_runtime.h"

#define D2E_CONVENTIONAL_BYTES (UINT32_C(128) * 1024U)

extern const d2e_native_program d2e_generated_program;

static uint8_t conventional_memory[D2E_CONVENTIONAL_BYTES];
static uint8_t cga_vram[D2E_CGA_VRAM_SIZE];

static __attribute__((noreturn)) void finish(int code) {
    fflush(stdout);
#if D2E_QEMU_SMOKE
    esp_rom_printf("D2E_QEMU_DONE,%d\n", code);
    fflush(stdout);
    vTaskDelay(pdMS_TO_TICKS(10));
    esp_restart();
#else
    esp_rom_printf("D2E_BOARD_DONE,%d\n", code);
    fflush(stdout);
    for (;;) {
        vTaskDelay(portMAX_DELAY);
    }
#endif
    __builtin_unreachable();
}

void app_main(void) {
    d2e_x86_cpu cpu;
    d2e_x86_stop_reason reason;

    d2e_x86_cpu_init(&cpu, conventional_memory,
                     sizeof(conventional_memory), NULL);
    d2e_x86_map_cga_vram(&cpu, cga_vram);
    if (!d2e_native_load_com(&cpu, &d2e_generated_program)) {
        esp_rom_printf("D2E_NATIVE_FAIL,load,reason=%u,address=%08x\n",
                       (unsigned)cpu.stop_reason,
                       (unsigned)cpu.fault_address);
        finish(1);
    }

    reason = d2e_native_run(&cpu, &d2e_generated_program, 100U);
    if (reason != D2E_X86_EXITED || cpu.exit_code != 42U ||
        cpu.regs[D2E_X86_AX] != UINT16_C(0x4c2a) ||
        cpu.regs[D2E_X86_CX] != 0U ||
        cpu.instructions_retired != UINT64_C(15)) {
        esp_rom_printf(
            "D2E_NATIVE_FAIL,run,reason=%u,exit=%u,ax=%04x,cx=%04x,"
            "instructions=%" PRIu64 ",target=%04x:%04x,address=%08x\n",
            (unsigned)reason, (unsigned)cpu.exit_code,
            (unsigned)cpu.regs[D2E_X86_AX],
            (unsigned)cpu.regs[D2E_X86_CX], cpu.instructions_retired,
            (unsigned)cpu.fault_cs, (unsigned)cpu.fault_ip,
            (unsigned)cpu.fault_address);
        finish(2);
    }

    esp_rom_printf(
        "D2E_NATIVE_OK,exit=%u,ax=%04x,cx=%04x,instructions=%" PRIu64
        ",heap=%u,largest=%u\n",
        (unsigned)cpu.exit_code, (unsigned)cpu.regs[D2E_X86_AX],
        (unsigned)cpu.regs[D2E_X86_CX], cpu.instructions_retired,
        (unsigned)heap_caps_get_free_size(MALLOC_CAP_8BIT),
        (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_8BIT));
    finish(0);
}
