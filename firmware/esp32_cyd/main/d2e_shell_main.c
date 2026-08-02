#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "driver/gpio.h"
#include "driver/uart.h"
#include "esp_err.h"
#if D2E_TRANSLATION_PROFILE
#include "esp_cpu.h"
#endif
#include "esp_heap_caps.h"
#include "esp_rom_sys.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "board_config.h"
#include "cyd_flash.h"
#include "cyd_display.h"
#include "d2e/cga.h"
#include "d2e/native_runtime.h"
#include "d2e/package.h"
#include "d2e/pc_at.h"
#include "d2e/pc_input.h"
#include "d2e/shell.h"
#include "d2e/supervisor.h"
#include "d2e/text_video.h"
#include "cyd_sd.h"
#include "pc_speaker_audio.h"
#include "qemu_frame_dump.h"

#define D2E_PRIMARY_CONVENTIONAL_BYTES (UINT32_C(124) * 1024U)
#define D2E_EXTENDED_CONVENTIONAL_BYTES (UINT32_C(100) * 1024U)
#define D2E_EXTENDED_PAGE_BYTES UINT32_C(4096)
#define D2E_EXTENDED_PAGE_COUNT                                               \
    (D2E_EXTENDED_CONVENTIONAL_BYTES / D2E_EXTENDED_PAGE_BYTES)
#define D2E_RUN_BUDGET UINT32_C(100000)

#if D2E_ALLEY_CAT
extern const d2e_native_program d2e_generated_program;
#endif

enum { D2E_PACKAGE_CAPACITY = 1 + CYD_FLASH_MODULE_CAPACITY };
static d2e_package packages[D2E_PACKAGE_CAPACITY];
static d2e_native_program module_stubs[CYD_FLASH_MODULE_CAPACITY];
static uint8_t package_module_indices[D2E_PACKAGE_CAPACITY];
static size_t package_count;

static uint8_t conventional_memory[D2E_PRIMARY_CONVENTIONAL_BYTES];
static uint32_t *extended_conventional_pages[D2E_EXTENDED_PAGE_COUNT];
static uint8_t cga_vram[D2E_CGA_VRAM_SIZE];
static d2e_x86_cpu cpu;
static d2e_pc_at pc_at;
static d2e_pc_input pc_input;
static d2e_supervisor supervisor;
static d2e_shell shell;
static uint64_t last_clock_day;
static uint16_t active_load_segment;
static uint8_t drive_a_ready;
static uint8_t drive_c_ready;
#if !D2E_QEMU_SMOKE || D2E_QEMU_BOARD_DEVICES
static uint8_t boot_button_down;
#endif

#if !D2E_QEMU_SMOKE || D2E_QEMU_BOARD_DEVICES
static cyd_display_t display;
#endif

static uint8_t read_extended_conventional(void *context, uint32_t offset) {
    uint32_t **const pages = (uint32_t **)context;
    const uint32_t page_index = offset / D2E_EXTENDED_PAGE_BYTES;
    const uint32_t page_offset = offset % D2E_EXTENDED_PAGE_BYTES;
    const uint32_t *page;
    if (page_index >= D2E_EXTENDED_PAGE_COUNT) {
        return UINT8_C(0xff);
    }
    page = pages[page_index];
    if (page == NULL) {
        return 0U;
    }
    return (uint8_t)(page[page_offset >> 2U] >>
                     ((page_offset & 3U) * 8U));
}

static int write_extended_conventional(void *context, uint32_t offset,
                                       uint8_t value) {
    uint32_t **const pages = (uint32_t **)context;
    const uint32_t page_index = offset / D2E_EXTENDED_PAGE_BYTES;
    const uint32_t page_offset = offset % D2E_EXTENDED_PAGE_BYTES;
    uint32_t *page;
    unsigned shift;
    uint32_t mask;
    if (page_index >= D2E_EXTENDED_PAGE_COUNT) {
        return 0;
    }
    page = pages[page_index];
    if (page == NULL) {
        page = heap_caps_calloc(1U, D2E_EXTENDED_PAGE_BYTES,
                                MALLOC_CAP_INTERNAL | MALLOC_CAP_32BIT);
        if (page == NULL) {
            return 0;
        }
        pages[page_index] = page;
    }
    shift = (unsigned)((page_offset & 3U) * 8U);
    mask = UINT32_C(0xff) << shift;
    page[page_offset >> 2U] =
        (page[page_offset >> 2U] & ~mask) | ((uint32_t)value << shift);
    return 1;
}

static void clear_extended_conventional(void *context) {
    uint32_t **const pages = (uint32_t **)context;
    size_t index;
    for (index = 0U; index < D2E_EXTENDED_PAGE_COUNT; ++index) {
        if (pages[index] != NULL) {
            heap_caps_free(pages[index]);
            pages[index] = NULL;
        }
    }
}

#if D2E_QEMU_EXIT_AFTER_RETURN
static __attribute__((noreturn)) void finish(int code) {
    fflush(stdout);
    esp_rom_printf("D2E_QEMU_DONE,%d\n", code);
    fflush(stdout);
    vTaskDelay(pdMS_TO_TICKS(10));
    esp_restart();
    __builtin_unreachable();
}
#endif

static esp_err_t init_input(void) {
    gpio_config_t button = {0};
    d2e_pc_input_init(&pc_input);
    if (!uart_is_driver_installed(UART_NUM_0)) {
        const esp_err_t result =
            uart_driver_install(UART_NUM_0, 256, 0, 0, NULL, 0);
        if (result != ESP_OK) {
            return result;
        }
    }
#if !D2E_QEMU_SMOKE || D2E_QEMU_BOARD_DEVICES
    button.pin_bit_mask = 1ULL << BOARD_BOOT_BUTTON;
    button.mode = GPIO_MODE_INPUT;
    button.pull_up_en = GPIO_PULLUP_ENABLE;
    button.pull_down_en = GPIO_PULLDOWN_DISABLE;
    button.intr_type = GPIO_INTR_DISABLE;
    return gpio_config(&button);
#else
    (void)button;
    return ESP_OK;
#endif
}

static int read_uart(uint8_t *bytes, size_t capacity) {
    size_t buffered = 0U;
    if (uart_get_buffered_data_len(UART_NUM_0, &buffered) != ESP_OK ||
        buffered == 0U) {
        return 0;
    }
    if (buffered > capacity) {
        buffered = capacity;
    }
    return uart_read_bytes(UART_NUM_0, bytes, buffered, 0U);
}

static void update_clock(void) {
    const uint64_t micros = (uint64_t)esp_timer_get_time();
    const uint64_t day = micros / UINT64_C(86400000000);
    const uint64_t day_micros = micros % UINT64_C(86400000000);
    const uint32_t ticks = (uint32_t)(
        day_micros * UINT64_C(182065) / UINT64_C(10000000000));
    d2e_pc_at_set_timer_ticks(
        &pc_at, ticks, (uint8_t)(day > last_clock_day ? day - last_clock_day
                                                       : 0U));
    last_clock_day = day;
}

#if !D2E_QEMU_SMOKE || D2E_QEMU_BOARD_DEVICES
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
        ESP_ERROR_CHECK(cyd_display_draw_bitmap(
            &display, 0, panel_y, CYD_DISPLAY_WIDTH, rows, pixels));
    }
    return cyd_display_flush(&display);
}
#endif

static void render_shell(void) {
    d2e_shell_render(&shell, cga_vram, sizeof(cga_vram));
    pc_at.cursor_row[0] = 22U;
    pc_at.cursor_column[0] =
        (uint8_t)(4U + shell.input_length < D2E_SHELL_COLUMNS
                      ? 4U + shell.input_length
                      : D2E_SHELL_COLUMNS - 1U);
#if !D2E_QEMU_SMOKE || D2E_QEMU_BOARD_DEVICES
    ESP_ERROR_CHECK(render_pc_frame());
#endif
}

static void enter_shell(const char *message);

static void refresh_package_catalog(void) {
    size_t module_index;
    package_count = 0U;
    memset(packages, 0, sizeof(packages));
    memset(module_stubs, 0, sizeof(module_stubs));
#if D2E_ALLEY_CAT
    packages[package_count] = (d2e_package){
        D2E_PACKAGE_ABI_VERSION, "ALLEY", "Alley Cat",
        D2E_PACKAGE_BUILTIN_FLASH, &d2e_generated_program};
    package_module_indices[package_count++] = UINT8_MAX;
#endif
    for (module_index = 0U;
         module_index < cyd_flash_module_count() &&
         package_count < D2E_PACKAGE_CAPACITY;
         ++module_index) {
        const cyd_flash_module *const module =
            cyd_flash_module_at(module_index);
        if (module == NULL) {
            continue;
        }
        module_stubs[module_index].name = module->manifest.name;
        packages[package_count] = (d2e_package){
            D2E_PACKAGE_ABI_VERSION, module->manifest.command,
            module->manifest.title, D2E_PACKAGE_EXTERNAL_MODULE,
            &module_stubs[module_index]};
        package_module_indices[package_count++] = (uint8_t)module_index;
    }
}

static void reset_shell_catalog(const char *message) {
    refresh_package_catalog();
    d2e_shell_init(&shell, packages, package_count);
    d2e_shell_set_drive_available(&shell, 'A', drive_a_ready);
    d2e_shell_set_drive_available(&shell, 'C', drive_c_ready);
    enter_shell(message);
}

static void enter_shell(const char *message) {
    d2e_supervisor_return_to_shell(&supervisor);
    d2e_pc_at_reset(&pc_at);
    cpu.regs[D2E_X86_AX] = UINT16_C(0x0001);
    cpu.stop_reason = D2E_X86_RUNNING;
    d2e_native_interrupt(&cpu, UINT8_C(0x10));
    d2e_shell_set_message(&shell, message);
    render_shell();
    esp_rom_printf("D2E_SHELL_READY,packages=%u,message=%s\n",
                   (unsigned)package_count,
                   message);
}

static void handle_shell_request(void) {
    char argument[D2E_SHELL_INPUT_CAPACITY + 1U];
    const d2e_shell_request request =
        d2e_shell_take_request(&shell, argument, sizeof(argument));
    if (request == D2E_SHELL_REQUEST_INSTALL) {
        char message[D2E_SHELL_COLUMNS + 1U];
        const esp_err_t result = cyd_flash_install_file(argument);
        if (result == ESP_OK) {
            (void)snprintf(message, sizeof(message), "Installed %.29s",
                           argument);
        } else {
            (void)snprintf(message, sizeof(message),
                           "Install failed: %.22s",
                           esp_err_to_name(result));
        }
        reset_shell_catalog(message);
    }
}

static const d2e_package *wait_for_shell_command(void) {
#if D2E_SHELL_AUTORUN
    return &packages[0];
#else
    for (;;) {
        uint8_t bytes[32];
        const int received = read_uart(bytes, sizeof(bytes));
        int index;
        for (index = 0; index < received; ++index) {
            const d2e_package *const selected =
                d2e_shell_feed(&shell, bytes[index]);
            if (selected != NULL) {
                return selected;
            }
        }
        if (shell.request != D2E_SHELL_REQUEST_NONE) {
            handle_shell_request();
        }
#if !D2E_QEMU_SMOKE || D2E_QEMU_BOARD_DEVICES
        {
            const uint8_t button_down =
                gpio_get_level(BOARD_BOOT_BUTTON) == 0 ? 1U : 0U;
            if (button_down != 0U && boot_button_down == 0U) {
                boot_button_down = button_down;
                if (package_count != 0U) {
                    return &packages[0];
                }
            }
            boot_button_down = button_down;
        }
#endif
        if (shell.dirty != 0U) {
            render_shell();
        }
        vTaskDelay(pdMS_TO_TICKS(16));
    }
#endif
}

#if D2E_QEMU_SCRIPTED_INPUT
static void feed_scripted_input(uint64_t frame) {
    static const struct {
        uint32_t target;
        uint8_t ascii;
        uint8_t scan;
    } setup[] = {
        {UINT32_C(0x0d127), (uint8_t)'n', UINT8_C(0x31)},
        {UINT32_C(0x0d159), (uint8_t)'k', UINT8_C(0x25)},
        {UINT32_C(0x0d1da), (uint8_t)' ', UINT8_C(0x39)},
    };
    static const struct {
        uint64_t delay;
        uint8_t ascii;
        uint8_t scan;
    } gameplay[] = {
        {UINT64_C(150), 0U, UINT8_C(0x4d)},
        {UINT64_C(220), 0U, UINT8_C(0x4b)},
        {UINT64_C(280), (uint8_t)' ', UINT8_C(0x39)},
    };
    static size_t setup_index;
    static size_t gameplay_index;
    static uint64_t gameplay_start;

    if (setup_index < sizeof(setup) / sizeof(setup[0])) {
        uint32_t target;
        if (cpu.segments[D2E_X86_CS] < active_load_segment) {
            return;
        }
        target = ((uint32_t)(uint16_t)(cpu.segments[D2E_X86_CS] -
                                       active_load_segment)
                  << 4U) +
                 cpu.ip;
        if (target == setup[setup_index].target &&
            d2e_pc_at_enqueue_key(&pc_at, setup[setup_index].ascii,
                                  setup[setup_index].scan)) {
            ++setup_index;
            if (setup_index == sizeof(setup) / sizeof(setup[0])) {
                gameplay_start = frame;
            }
        }
        return;
    }
    if (gameplay_index < sizeof(gameplay) / sizeof(gameplay[0]) &&
        frame >= gameplay_start + gameplay[gameplay_index].delay &&
        d2e_pc_at_enqueue_key(&pc_at, gameplay[gameplay_index].ascii,
                              gameplay[gameplay_index].scan)) {
        ++gameplay_index;
    }
}
#endif

static int poll_program_input(void) {
    uint8_t bytes[32];
    const int received = read_uart(bytes, sizeof(bytes));
    int index;
    int return_requested = 0;
#if !D2E_QEMU_SMOKE || D2E_QEMU_BOARD_DEVICES
    const uint8_t button_down =
        gpio_get_level(BOARD_BOOT_BUTTON) == 0 ? 1U : 0U;
    if (button_down != 0U && boot_button_down == 0U) {
        (void)d2e_pc_at_enqueue_key(&pc_at, (uint8_t)' ', UINT8_C(0x39));
    }
    boot_button_down = button_down;
#endif
    for (index = 0; index < received; ++index) {
        if (bytes[index] == UINT8_C(0x1d)) {
            return_requested = 1;
        } else {
            const int accepted =
                d2e_pc_input_feed_byte(&pc_input, &pc_at, bytes[index]);
#if D2E_QEMU_BOARD_DEVICES
            if (accepted) {
                esp_rom_printf("D2E_UART_KEY,byte=%02x\n",
                               (unsigned)bytes[index]);
            }
#endif
        }
    }
    update_clock();
    return return_requested;
}

static void run_package(const d2e_package *package) {
    uint64_t frame = 0U;
    uint32_t previous_hash = 0U;
    const char *return_source = "program";
    char message[D2E_SHELL_COLUMNS + 1U];
    d2e_package external_package;
    int external_active = 0;
#if D2E_TRANSLATION_PROFILE
    uint64_t translation_cycles = 0U;
    uint32_t translation_calls = 0U;
    uint32_t translation_min_cycles = UINT32_MAX;
    uint32_t translation_max_cycles = 0U;
#endif

    if (package->storage == D2E_PACKAGE_EXTERNAL_MODULE) {
        const size_t package_index = (size_t)(package - packages);
        esp_err_t result;
        if (package_index >= package_count ||
            package_module_indices[package_index] == UINT8_MAX) {
            enter_shell("Invalid external package");
            return;
        }
        result = cyd_flash_activate_module(
            package_module_indices[package_index], &external_package);
        if (result != ESP_OK) {
            (void)snprintf(message, sizeof(message), "XIP load failed: %.20s",
                           esp_err_to_name(result));
            enter_shell(message);
            return;
        }
        package = &external_package;
        external_active = 1;
    }
    active_load_segment = package->program->load_segment;

    d2e_pc_at_reset(&pc_at);
    d2e_pc_input_init(&pc_input);
    if (!d2e_supervisor_launch(&supervisor, package)) {
        (void)snprintf(message, sizeof(message), "%s load failed",
                       package->command);
        enter_shell(message);
        if (external_active) {
            cyd_flash_deactivate_module();
        }
        return;
    }
    d2e_pc_at_prepare_dos(
        &pc_at,
        package->program->format == D2E_NATIVE_IMAGE_COM
            ? package->program->load_segment
            : (uint16_t)(package->program->load_segment - UINT16_C(0x0010)));
    esp_rom_printf("D2E_SHELL_RUN,command=%s,csip=%04x:%04x,heap=%u\n",
                   package->command, (unsigned)cpu.segments[D2E_X86_CS],
                   (unsigned)cpu.ip,
                   (unsigned)heap_caps_get_free_size(MALLOC_CAP_8BIT));

    while (supervisor.state == D2E_SUPERVISOR_ACTIVE) {
        uint32_t hash = UINT32_C(2166136261);
        size_t index;
        int report_frame;
#if D2E_TRANSLATION_PROFILE
        const uint32_t cycles_before = (uint32_t)esp_cpu_get_cycle_count();
#endif
        (void)d2e_supervisor_step(&supervisor, D2E_RUN_BUDGET);
#if D2E_TRANSLATION_PROFILE
        {
            const uint32_t call_cycles =
                (uint32_t)esp_cpu_get_cycle_count() - cycles_before;
            translation_cycles += call_cycles;
            ++translation_calls;
            if (call_cycles < translation_min_cycles) {
                translation_min_cycles = call_cycles;
            }
            if (call_cycles > translation_max_cycles) {
                translation_max_cycles = call_cycles;
            }
        }
#endif
#if !D2E_QEMU_SMOKE || D2E_QEMU_BOARD_DEVICES
        ESP_ERROR_CHECK(render_pc_frame());
#endif
#if D2E_QEMU_SCRIPTED_INPUT
        feed_scripted_input(frame + UINT64_C(1));
#endif
        if (poll_program_input()) {
            return_source = "user";
            break;
        }
        (void)d2e_pc_at_dispatch_keyboard_irq(&pc_at);
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
            return_source = "harness";
            break;
        }
#elif D2E_QEMU_SMOKE
        if (frame >= UINT64_C(64)) {
            return_source = "harness";
            break;
        }
#endif
        if (supervisor.state == D2E_SUPERVISOR_ACTIVE) {
#if D2E_QEMU_INTERACTIVE || !D2E_QEMU_SMOKE
            vTaskDelay(pdMS_TO_TICKS(16));
#endif
        }
    }

    esp_rom_printf(
        "D2E_SHELL_RETURN,command=%s,source=%s,state=%u,reason=%u,exit=%u,"
        "instructions=%" PRIu64 ",fault=%04x:%04x,address=%08" PRIx32 "\n",
        package->command, return_source, (unsigned)supervisor.state,
        (unsigned)supervisor.last_stop_reason, (unsigned)supervisor.exit_code,
        cpu.instructions_retired, (unsigned)cpu.fault_cs,
        (unsigned)cpu.fault_ip, cpu.fault_address);
#if D2E_TRANSLATION_PROFILE
    esp_rom_printf(
        "D2E_TRANSLATION_PROFILE,calls=%" PRIu32 ",cycles=%" PRIu64
        ",min=%" PRIu32 ",max=%" PRIu32 ",instructions=%" PRIu64
        ",cycles_per_kinstruction=%" PRIu64 "\n",
        translation_calls, translation_cycles,
        translation_calls != 0U ? translation_min_cycles : 0U,
        translation_max_cycles, cpu.instructions_retired,
        cpu.instructions_retired != 0U
            ? translation_cycles * UINT64_C(1000) /
                  cpu.instructions_retired
            : 0U);
#endif
    if (supervisor.state == D2E_SUPERVISOR_EXITED) {
        (void)snprintf(message, sizeof(message), "%s exited, code %u",
                       package->command, (unsigned)supervisor.exit_code);
    } else if (supervisor.state == D2E_SUPERVISOR_FAULTED) {
        (void)snprintf(message, sizeof(message), "%s fault, reason %u",
                       package->command,
                       (unsigned)supervisor.last_stop_reason);
    } else {
        (void)snprintf(message, sizeof(message), "%s returned (%s)",
                       package->command, return_source);
    }
    enter_shell(message);
    if (external_active) {
        cyd_flash_deactivate_module();
    }
}

static size_t run_autoexec(void) {
    char script[CYD_FLASH_AUTOEXEC_CAPACITY + 1U];
    char *cursor;
    size_t length = 0U;
    size_t line_number = 0U;
    size_t launched = 0U;
    esp_err_t result;
    if (drive_a_ready == 0U) {
        return 0U;
    }
    result = cyd_flash_read_autoexec(script, sizeof(script), &length);
    if (result == ESP_ERR_NOT_FOUND) {
        esp_rom_printf("D2E_AUTOEXEC_MISSING,file=A:/AUTOEXEC.BAT\n");
        return 0U;
    }
    if (result != ESP_OK) {
        esp_rom_printf("D2E_AUTOEXEC_FAILED,file=A:/AUTOEXEC.BAT,result=%s\n",
                       esp_err_to_name(result));
        return 0U;
    }
    esp_rom_printf("D2E_AUTOEXEC_RUN,file=A:/AUTOEXEC.BAT,bytes=%u\n",
                   (unsigned)length);
    cursor = script;
    while (*cursor != '\0') {
        char *const line = cursor;
        const d2e_package *package;
        while (*cursor != '\0' && *cursor != '\r' && *cursor != '\n') {
            ++cursor;
        }
        if (*cursor != '\0') {
            const char terminator = *cursor;
            *cursor++ = '\0';
            if (terminator == '\r' && *cursor == '\n') {
                ++cursor;
            }
        }
        ++line_number;
        if (*line == '\0') {
            continue;
        }
        esp_rom_printf("D2E_AUTOEXEC_LINE,line=%u,text=%s\n",
                       (unsigned)line_number, line);
        package = d2e_shell_execute_line(&shell, line);
        if (shell.request != D2E_SHELL_REQUEST_NONE) {
            handle_shell_request();
        }
        if (package != NULL) {
            run_package(package);
            ++launched;
        }
    }
    if (launched == 0U && shell.dirty != 0U) {
        render_shell();
    }
    return launched;
}

void app_main(void) {
    size_t autoexec_runs;
    d2e_x86_cpu_init(&cpu, conventional_memory, sizeof(conventional_memory),
                     NULL);
    d2e_x86_configure_extended_memory(
        &cpu, D2E_EXTENDED_CONVENTIONAL_BYTES,
        extended_conventional_pages, read_extended_conventional,
        write_extended_conventional, clear_extended_conventional);
    d2e_pc_at_init(&pc_at, cga_vram, sizeof(cga_vram));
    d2e_pc_at_attach(&pc_at, &cpu);
    d2e_supervisor_init(&supervisor, &cpu);
#if !D2E_QEMU_SMOKE || D2E_QEMU_BOARD_DEVICES
    ESP_ERROR_CHECK(cyd_display_init(&display));
    ESP_ERROR_CHECK(cyd_flash_mount());
    drive_a_ready = 1U;
    if (cyd_sd_mount_and_probe() == ESP_OK) {
        drive_c_ready = 1U;
        d2e_pc_at_set_dos_drive_root(&pc_at, 'C', "/C");
    }
#if defined(D2E_QEMU_XIP_INSTALL_FILE)
    if (drive_c_ready != 0U && cyd_flash_module_count() == 0U) {
        const esp_err_t install_result =
            cyd_flash_install_file(D2E_QEMU_XIP_INSTALL_FILE);
        esp_rom_printf("D2E_QEMU_XIP_INSTALL,file=%s,result=%s\n",
                       D2E_QEMU_XIP_INSTALL_FILE,
                       esp_err_to_name(install_result));
    }
#endif
#endif
    refresh_package_catalog();
    d2e_shell_init(&shell, packages, package_count);
    d2e_shell_set_drive_available(&shell, 'A', drive_a_ready);
    d2e_shell_set_drive_available(&shell, 'C', drive_c_ready);
    ESP_ERROR_CHECK(init_input());
#if !D2E_QEMU_SMOKE || D2E_QEMU_BOARD_DEVICES
    ESP_ERROR_CHECK(pc_speaker_audio_init(&pc_at));
#endif

    enter_shell("Type HELP for commands");
    autoexec_runs = run_autoexec();
#if D2E_QEMU_EXIT_AFTER_RETURN
    if (autoexec_runs != 0U) {
        finish(0);
    }
#else
    (void)autoexec_runs;
#endif
    for (;;) {
        const d2e_package *const package = wait_for_shell_command();
        run_package(package);
#if D2E_QEMU_EXIT_AFTER_RETURN
        finish(0);
#endif
    }
}
