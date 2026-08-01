#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "esp_err.h"
#include "esp_heap_caps.h"
#include "esp_rom_sys.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "driver/gpio.h"
#include "driver/uart.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "d2e/cga.h"
#include "d2e/native_runtime.h"
#include "d2e/pc_at.h"
#include "d2e/pc_input.h"
#include "d2e/text_video.h"
#include "board_config.h"
#include "cyd_display.h"
#include "qemu_frame_dump.h"

#define D2E_CONVENTIONAL_BYTES (UINT32_C(128) * 1024U)

extern const d2e_native_program d2e_generated_program;

static uint8_t conventional_memory[D2E_CONVENTIONAL_BYTES];
static uint8_t cga_vram[D2E_CGA_VRAM_SIZE];
static d2e_pc_at pc_at;

#if D2E_ALLEY_CAT
static d2e_pc_input pc_input;
#if !D2E_QEMU_SMOKE
static uint8_t boot_button_down;
#endif
static uint64_t last_clock_day;

static esp_err_t init_pc_input(void) {
#if !D2E_QEMU_SMOKE
    gpio_config_t button = {0};
    button.pin_bit_mask = 1ULL << BOARD_BOOT_BUTTON;
    button.mode = GPIO_MODE_INPUT;
    button.pull_up_en = GPIO_PULLUP_ENABLE;
    button.pull_down_en = GPIO_PULLDOWN_DISABLE;
    button.intr_type = GPIO_INTR_DISABLE;
#endif
    d2e_pc_input_init(&pc_input);
    if (!uart_is_driver_installed(UART_NUM_0)) {
        const esp_err_t uart_result =
            uart_driver_install(UART_NUM_0, 256, 0, 0, NULL, 0);
        if (uart_result != ESP_OK) {
            return uart_result;
        }
    }
#if !D2E_QEMU_SMOKE
    return gpio_config(&button);
#else
    return ESP_OK;
#endif
}

static void poll_pc_input_and_clock(void) {
    uint8_t bytes[32];
    size_t buffered = 0U;
#if !D2E_QEMU_SMOKE
    const uint8_t button_down =
        gpio_get_level(BOARD_BOOT_BUTTON) == 0 ? 1U : 0U;
#endif
    const uint64_t micros = (uint64_t)esp_timer_get_time();
    const uint64_t day = micros / UINT64_C(86400000000);
    const uint64_t day_micros = micros % UINT64_C(86400000000);
    const uint32_t ticks = (uint32_t)(
        day_micros * UINT64_C(182065) / UINT64_C(10000000000));

#if !D2E_QEMU_SMOKE
    if (button_down != 0U && boot_button_down == 0U) {
        (void)d2e_pc_at_enqueue_key(&pc_at, UINT8_C(' '), UINT8_C(0x39));
    }
    boot_button_down = button_down;
#endif
    d2e_pc_at_set_timer_ticks(
        &pc_at, ticks, (uint8_t)(day > last_clock_day ? day - last_clock_day
                                                       : 0U));
    last_clock_day = day;

    if (uart_get_buffered_data_len(UART_NUM_0, &buffered) == ESP_OK &&
        buffered != 0U) {
        int received;
        if (buffered > sizeof(bytes)) {
            buffered = sizeof(bytes);
        }
        received = uart_read_bytes(UART_NUM_0, bytes, buffered, 0U);
        if (received > 0) {
            int index;
            for (index = 0; index < received; ++index) {
                (void)d2e_pc_input_feed_byte(&pc_input, &pc_at, bytes[index]);
            }
        }
    }
}
#endif

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
#if D2E_ALLEY_CAT
    ESP_ERROR_CHECK(init_pc_input());
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
#if D2E_QEMU_SMOKE && !D2E_QEMU_INTERACTIVE
    {
        unsigned slice;
        unsigned slices = 0U;
        for (slice = 0U; slice < 64U; ++slice) {
            d2e_pc_at_set_timer_ticks(&pc_at, (uint32_t)slice, 0U);
            reason = d2e_native_run(&cpu, &d2e_generated_program,
                                    UINT32_C(100000));
            ++slices;
            if (reason != D2E_X86_BUDGET_EXHAUSTED) {
                break;
            }
        }
        esp_rom_printf("D2E_ALLEY_SLICES,%u\n", slices);
        {
            uint32_t hash = UINT32_C(2166136261);
            size_t nonzero = 0U;
            size_t index;
            for (index = 0U; index < sizeof(cga_vram); ++index) {
                hash = (hash ^ cga_vram[index]) * UINT32_C(16777619);
                if (cga_vram[index] != 0U) {
                    ++nonzero;
                }
            }
            esp_rom_printf(
                "D2E_ALLEY_VIDEO,mode=%u,nonzero=%u,fnv1a=%08x\n",
                (unsigned)pc_at.video_mode, (unsigned)nonzero,
                (unsigned)hash);
        }
    }
#else
    {
        uint64_t frame = 0U;
        uint32_t previous_hash = 0U;
    for (;;) {
        uint32_t hash = UINT32_C(2166136261);
        size_t index;
        int report_frame;
        reason =
            d2e_native_run(&cpu, &d2e_generated_program, UINT32_C(100000));
#if !D2E_QEMU_SMOKE
        ESP_ERROR_CHECK(render_pc_frame());
#endif
        poll_pc_input_and_clock();
        for (index = 0U; index < sizeof(cga_vram); ++index) {
            hash = (hash ^ cga_vram[index]) * UINT32_C(16777619);
        }
        ++frame;
        report_frame =
            hash != previous_hash || (frame % UINT64_C(60)) == 0U;
#if D2E_QEMU_INTERACTIVE && D2E_QEMU_INTERACTIVE_FRAME_LIMIT > 0
        if (frame >= D2E_QEMU_INTERACTIVE_FRAME_LIMIT) {
            report_frame = 1;
        }
#endif
        if (report_frame) {
            esp_rom_printf(
                "D2E_FRAME,seq=%" PRIu64 ",mode=%u,dirty=%u,fnv1a=%08x\n",
                frame, (unsigned)pc_at.video_mode,
                hash != previous_hash ? 1U : 0U, (unsigned)hash);
            previous_hash = hash;
        }
#if D2E_QEMU_INTERACTIVE && D2E_QEMU_INTERACTIVE_FRAME_LIMIT > 0
        if (frame >= D2E_QEMU_INTERACTIVE_FRAME_LIMIT) {
#if D2E_QEMU_DUMP_FRAME
            d2e_qemu_dump_cga(&pc_at, cga_vram, sizeof(cga_vram));
#endif
            break;
        }
#endif
        if (reason == D2E_X86_BUDGET_EXHAUSTED ||
            reason == D2E_X86_WAITING_INPUT) {
            vTaskDelay(pdMS_TO_TICKS(16));
            continue;
        }
        break;
    }
    }
#endif
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
