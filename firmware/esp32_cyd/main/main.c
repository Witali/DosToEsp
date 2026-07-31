#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "esp_err.h"
#include "esp_heap_caps.h"
#include "esp_rom_sys.h"
#include "esp_system.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "d2e/cga.h"
#include "d2e/native_runtime.h"
#include "d2e/pc_at.h"
#include "d2e/text_video.h"
#include "cyd_display.h"

#define D2E_CONVENTIONAL_BYTES (UINT32_C(128) * 1024U)

extern const d2e_native_program d2e_generated_program;

static uint8_t conventional_memory[D2E_CONVENTIONAL_BYTES];
static uint8_t cga_vram[D2E_CGA_VRAM_SIZE];
static d2e_pc_at pc_at;
#if !D2E_QEMU_SMOKE
static cyd_display_t display;

#if D2E_ALLEY_CAT
static esp_err_t render_pc_frame(void) {
    const int rows_per_transfer = cyd_display_rows_per_transfer(&display);
    d2e_text_render_config text_config = {0};
    int panel_y;

    text_config.columns = pc_at.columns;
    text_config.rows = pc_at.rows;
    text_config.character_height = pc_at.character_height;
    text_config.page_offset = (uint16_t)(
        pc_at.active_page * (pc_at.columns == 40U ? 0x0800U : 0x1000U));
    text_config.cursor_row = pc_at.cursor_row[pc_at.active_page];
    text_config.cursor_column = pc_at.cursor_column[pc_at.active_page];
    text_config.cursor_start = pc_at.cursor_start;
    text_config.cursor_end = pc_at.cursor_end;
    text_config.cursor_visible = 1U;
    text_config.blink_on = 1U;
    text_config.output_height = D2E_CGA_HEIGHT;

    for (panel_y = 0; panel_y < CYD_DISPLAY_HEIGHT;
         panel_y += rows_per_transfer) {
        int rows = rows_per_transfer;
        int local_y;
        uint16_t *const pixels = cyd_display_acquire_buffer(&display);
        if (pixels == NULL) {
            return ESP_ERR_NO_MEM;
        }
        if (rows > CYD_DISPLAY_HEIGHT - panel_y) {
            rows = CYD_DISPLAY_HEIGHT - panel_y;
        }
        for (local_y = 0; local_y < rows; ++local_y) {
            const int y = panel_y + local_y;
            uint16_t *const row =
                pixels + (size_t)local_y * CYD_DISPLAY_WIDTH;
            if (y < 20 || y >= 20 + (int)D2E_CGA_HEIGHT) {
                memset(row, 0, CYD_DISPLAY_WIDTH * sizeof(*row));
            } else if (pc_at.video_mode <= 3U || pc_at.video_mode == 7U) {
                d2e_text_render_320_row(
                    &pc_at.cga, cga_vram, sizeof(cga_vram), &text_config,
                    (unsigned)(y - 20), row);
            } else {
                d2e_cga_render_320x200_row(
                    &pc_at.cga, cga_vram, (unsigned)(y - 20), row);
            }
        }
        {
            const esp_err_t result = cyd_display_draw_bitmap(
                &display, 0, panel_y, CYD_DISPLAY_WIDTH, rows, pixels);
            if (result != ESP_OK) {
                return result;
            }
        }
    }
    return cyd_display_flush(&display);
}
#endif
#endif

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
    d2e_pc_at_init(&pc_at, cga_vram, sizeof(cga_vram));
    d2e_pc_at_attach(&pc_at, &cpu);
#if !D2E_QEMU_SMOKE
    ESP_ERROR_CHECK(cyd_display_init(&display));
#endif
    if (!d2e_native_load(&cpu, &d2e_generated_program)) {
        esp_rom_printf("D2E_NATIVE_FAIL,load,reason=%u,address=%08x\n",
                       (unsigned)cpu.stop_reason,
                       (unsigned)cpu.fault_address);
        finish(1);
    }

#if D2E_ALLEY_CAT
    esp_rom_printf(
        "D2E_ALLEY_START,csip=%04x:%04x,sssp=%04x:%04x,heap=%u\n",
        (unsigned)cpu.segments[D2E_X86_CS], (unsigned)cpu.ip,
        (unsigned)cpu.segments[D2E_X86_SS],
        (unsigned)cpu.regs[D2E_X86_SP],
        (unsigned)heap_caps_get_free_size(MALLOC_CAP_8BIT));
    reason = d2e_native_run(&cpu, &d2e_generated_program, UINT32_C(100000));
    esp_rom_printf(
        "D2E_ALLEY_STOP,reason=%u,csip=%04x:%04x,ax=%04x,bx=%04x,"
        "cx=%04x,dx=%04x,instructions=%" PRIu64 ",address=%08x,"
        "heap=%u\n",
        (unsigned)reason, (unsigned)cpu.segments[D2E_X86_CS],
        (unsigned)cpu.ip, (unsigned)cpu.regs[D2E_X86_AX],
        (unsigned)cpu.regs[D2E_X86_BX],
        (unsigned)cpu.regs[D2E_X86_CX],
        (unsigned)cpu.regs[D2E_X86_DX], cpu.instructions_retired,
        (unsigned)cpu.fault_address,
        (unsigned)heap_caps_get_free_size(MALLOC_CAP_8BIT));
#if !D2E_QEMU_SMOKE
    ESP_ERROR_CHECK(render_pc_frame());
#endif
    finish(0);
#else
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
#endif
}
