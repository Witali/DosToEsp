#if defined(_MSC_VER)
#define _CRT_SECURE_NO_WARNINGS
#endif

#include "d2e/pc_at.h"
#include "d2e/text_video.h"

#include <ctype.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#if defined(_WIN32)
#include <io.h>
#else
#include <dirent.h>
#include <sys/stat.h>
#endif

enum {
    k_bda_video_mode = 0x449,
    k_bda_columns = 0x44a,
    k_bda_page_size = 0x44c,
    k_bda_page_offset = 0x44e,
    k_bda_cursor_positions = 0x450,
    k_bda_cursor_shape = 0x460,
    k_bda_active_page = 0x462,
    k_bda_crt_port = 0x463,
    k_bda_rows_minus_one = 0x484,
    k_bda_character_height = 0x485
};

static uint8_t get_ah(const d2e_x86_cpu *cpu) {
    return d2e_x86_get_reg8(cpu, 4U);
}

static uint8_t get_al(const d2e_x86_cpu *cpu) {
    return d2e_x86_get_reg8(cpu, 0U);
}

static void set_ah(d2e_x86_cpu *cpu, uint8_t value) {
    d2e_x86_set_reg8(cpu, 4U, value);
}

static void set_al(d2e_x86_cpu *cpu, uint8_t value) {
    d2e_x86_set_reg8(cpu, 0U, value);
}

static void set_flag(d2e_x86_cpu *cpu, uint16_t flag, int enabled) {
    if (enabled) {
        cpu->flags = (uint16_t)(cpu->flags | flag);
    } else {
        cpu->flags = (uint16_t)(cpu->flags & (uint16_t)~flag);
    }
    cpu->flags = (uint16_t)(cpu->flags | D2E_X86_FLAG_FIXED);
}

static void notify_speaker(d2e_pc_at *machine) {
    d2e_pc_speaker_control control;
    if (machine->speaker_callback == NULL) {
        return;
    }
    control.generation = ++machine->speaker_generation;
    control.reload = machine->pit_reload[2];
    control.mode = machine->pit_mode[2];
    control.gate = machine->system_port_b & UINT8_C(0x01);
    control.speaker_data =
        (uint8_t)((machine->system_port_b >> 1U) & UINT8_C(0x01));
    machine->speaker_callback(machine->speaker_context, &control);
}

static uint16_t text_page_size(const d2e_pc_at *machine) {
    return machine->columns == 40U ? UINT16_C(0x0800) : UINT16_C(0x1000);
}

static size_t text_cell_offset(const d2e_pc_at *machine, uint8_t page,
                               uint8_t row, uint8_t column) {
    return (size_t)page * text_page_size(machine) +
           ((size_t)row * machine->columns + column) * 2U;
}

static void bda_write8(d2e_x86_cpu *cpu, uint16_t address, uint8_t value) {
    if (address < cpu->memory_size) {
        cpu->memory[address] = value;
    }
}

static void bda_write16(d2e_x86_cpu *cpu, uint16_t address, uint16_t value) {
    bda_write8(cpu, address, (uint8_t)value);
    bda_write8(cpu, (uint16_t)(address + 1U), (uint8_t)(value >> 8U));
}

static void update_video_bda(d2e_pc_at *machine, d2e_x86_cpu *cpu) {
    unsigned page;
    bda_write8(cpu, k_bda_video_mode, machine->video_mode);
    bda_write16(cpu, k_bda_columns, machine->columns);
    bda_write16(cpu, k_bda_page_size, text_page_size(machine));
    bda_write16(cpu, k_bda_page_offset,
                (uint16_t)(machine->active_page * text_page_size(machine)));
    for (page = 0; page < D2E_PC_AT_TEXT_PAGES; ++page) {
        const uint16_t cursor =
            (uint16_t)(((uint16_t)machine->cursor_row[page] << 8U) |
                       machine->cursor_column[page]);
        bda_write16(cpu, (uint16_t)(k_bda_cursor_positions + page * 2U),
                    cursor);
    }
    bda_write16(cpu, k_bda_cursor_shape,
                (uint16_t)(((uint16_t)machine->cursor_start << 8U) |
                           machine->cursor_end));
    bda_write8(cpu, k_bda_active_page, machine->active_page);
    bda_write16(cpu, k_bda_crt_port, UINT16_C(0x03d4));
    bda_write8(cpu, k_bda_rows_minus_one,
               (uint8_t)(machine->rows - 1U));
    bda_write16(cpu, k_bda_character_height, machine->character_height);
}

static void clear_text_page(d2e_pc_at *machine, uint8_t page,
                            uint8_t attribute) {
    uint8_t row;
    uint8_t column;
    if (machine->cga_vram == NULL) {
        return;
    }
    for (row = 0; row < machine->rows; ++row) {
        for (column = 0; column < machine->columns; ++column) {
            const size_t offset =
                text_cell_offset(machine, page, row, column);
            if (offset + 1U < machine->cga_vram_size) {
                machine->cga_vram[offset] = UINT8_C(0x20);
                machine->cga_vram[offset + 1U] = attribute;
            }
        }
    }
}

static void set_video_mode(d2e_pc_at *machine, d2e_x86_cpu *cpu,
                           uint8_t requested_mode) {
    const int preserve = (requested_mode & UINT8_C(0x80)) != 0U;
    const uint8_t mode = requested_mode & UINT8_C(0x7f);
    unsigned page;

    machine->video_mode = mode;
    machine->columns =
        mode <= 1U || mode == 4U || mode == 5U ? 40U : 80U;
    machine->rows = 25U;
    machine->character_height = mode >= UINT8_C(0x0d) ? 14U : 8U;
    machine->active_page = 0U;
    machine->cursor_start = 6U;
    machine->cursor_end = 7U;
    for (page = 0; page < D2E_PC_AT_TEXT_PAGES; ++page) {
        machine->cursor_row[page] = 0U;
        machine->cursor_column[page] = 0U;
    }
    d2e_cga_set_mode(&machine->cga, mode);
    if (!preserve && machine->cga_vram != NULL) {
        memset(machine->cga_vram, 0, machine->cga_vram_size);
        if (mode <= 3U || mode == 7U) {
            clear_text_page(machine, 0U, UINT8_C(0x07));
        }
    }
    update_video_bda(machine, cpu);
}

static void set_cursor(d2e_pc_at *machine, d2e_x86_cpu *cpu,
                       uint8_t page, uint8_t row, uint8_t column) {
    if (page >= D2E_PC_AT_TEXT_PAGES) {
        return;
    }
    machine->cursor_row[page] = row < machine->rows
                                    ? row
                                    : (uint8_t)(machine->rows - 1U);
    machine->cursor_column[page] = column < machine->columns
                                       ? column
                                       : (uint8_t)(machine->columns - 1U);
    update_video_bda(machine, cpu);
}

static uint16_t read_text_cell(const d2e_pc_at *machine, uint8_t page,
                               uint8_t row, uint8_t column) {
    const size_t offset = text_cell_offset(machine, page, row, column);
    if (machine->cga_vram == NULL ||
        offset + 1U >= machine->cga_vram_size) {
        return UINT16_C(0x0720);
    }
    return (uint16_t)(machine->cga_vram[offset] |
                      ((uint16_t)machine->cga_vram[offset + 1U] << 8U));
}

static void write_text_cell(d2e_pc_at *machine, uint8_t page, uint8_t row,
                            uint8_t column, uint8_t character,
                            uint8_t attribute, int write_attribute) {
    const size_t offset = text_cell_offset(machine, page, row, column);
    if (machine->cga_vram == NULL ||
        offset + 1U >= machine->cga_vram_size) {
        return;
    }
    machine->cga_vram[offset] = character;
    if (write_attribute) {
        machine->cga_vram[offset + 1U] = attribute;
    }
}

static void scroll_window(d2e_pc_at *machine, uint8_t lines,
                          uint8_t attribute, uint8_t top, uint8_t left,
                          uint8_t bottom, uint8_t right, int down) {
    unsigned row;
    unsigned column;
    unsigned height;

    if (top >= machine->rows || left >= machine->columns) {
        return;
    }
    if (bottom >= machine->rows) {
        bottom = (uint8_t)(machine->rows - 1U);
    }
    if (right >= machine->columns) {
        right = (uint8_t)(machine->columns - 1U);
    }
    if (top > bottom || left > right) {
        return;
    }
    height = (unsigned)bottom - top + 1U;
    if (lines == 0U || lines >= height) {
        lines = (uint8_t)height;
    }

    if (down) {
        for (row = height; row-- > lines;) {
            for (column = left; column <= right; ++column) {
                const uint16_t cell = read_text_cell(
                    machine, machine->active_page,
                    (uint8_t)(top + row - lines), (uint8_t)column);
                write_text_cell(machine, machine->active_page,
                                (uint8_t)(top + row), (uint8_t)column,
                                (uint8_t)cell, (uint8_t)(cell >> 8U), 1);
            }
        }
        for (row = 0; row < lines; ++row) {
            for (column = left; column <= right; ++column) {
                write_text_cell(machine, machine->active_page,
                                (uint8_t)(top + row), (uint8_t)column,
                                UINT8_C(0x20), attribute, 1);
            }
        }
    } else {
        for (row = 0; row + lines < height; ++row) {
            for (column = left; column <= right; ++column) {
                const uint16_t cell = read_text_cell(
                    machine, machine->active_page,
                    (uint8_t)(top + row + lines), (uint8_t)column);
                write_text_cell(machine, machine->active_page,
                                (uint8_t)(top + row), (uint8_t)column,
                                (uint8_t)cell, (uint8_t)(cell >> 8U), 1);
            }
        }
        for (; row < height; ++row) {
            for (column = left; column <= right; ++column) {
                write_text_cell(machine, machine->active_page,
                                (uint8_t)(top + row), (uint8_t)column,
                                UINT8_C(0x20), attribute, 1);
            }
        }
    }
}

static void cga_write_pixel(d2e_pc_at *machine, uint16_t x, uint16_t y,
                            uint8_t color);
static uint8_t cga_read_pixel(const d2e_pc_at *machine, uint16_t x,
                              uint16_t y);

static int is_cga_graphics_mode(const d2e_pc_at *machine) {
    return machine->video_mode >= 4U && machine->video_mode <= 6U;
}

static void write_graphics_character(d2e_pc_at *machine, uint8_t row,
                                     uint8_t column, uint8_t character,
                                     uint8_t color) {
    const uint16_t left = (uint16_t)column * D2E_CP437_HEIGHT;
    const uint16_t top = (uint16_t)row * D2E_CP437_HEIGHT;
    const uint8_t foreground = machine->video_mode == 6U
                                   ? (uint8_t)(color & 1U)
                                   : (uint8_t)(color & 3U);
    const int xor_character = (color & UINT8_C(0x80)) != 0U;
    unsigned glyph_y;

    for (glyph_y = 0; glyph_y < D2E_CP437_HEIGHT; ++glyph_y) {
        const uint8_t bits =
            d2e_cp437_font[(size_t)character * D2E_CP437_HEIGHT + glyph_y];
        unsigned glyph_x;
        for (glyph_x = 0; glyph_x < D2E_CP437_HEIGHT; ++glyph_x) {
            const uint16_t x = (uint16_t)(left + glyph_x);
            const uint16_t y = (uint16_t)(top + glyph_y);
            const int set = (bits & (UINT8_C(1) << glyph_x)) != 0U;
            uint8_t pixel = set ? foreground : 0U;
            if (xor_character) {
                if (!set) {
                    continue;
                }
                pixel = (uint8_t)(cga_read_pixel(machine, x, y) ^ foreground);
            }
            cga_write_pixel(machine, x, y, pixel);
        }
    }
}

static void write_character(d2e_pc_at *machine, uint8_t page, uint8_t row,
                            uint8_t column, uint8_t character,
                            uint8_t attribute, int write_attribute) {
    if (is_cga_graphics_mode(machine)) {
        write_graphics_character(machine, row, column, character, attribute);
    } else {
        write_text_cell(machine, page, row, column, character, attribute,
                        write_attribute);
    }
}

static void teletype(d2e_pc_at *machine, d2e_x86_cpu *cpu,
                     uint8_t character, uint8_t attribute) {
    const uint8_t page = machine->active_page;
    uint8_t row = machine->cursor_row[page];
    uint8_t column = machine->cursor_column[page];

    if (character == UINT8_C(0x08)) {
        if (column != 0U) {
            --column;
        }
    } else if (character == UINT8_C(0x0d)) {
        column = 0U;
    } else if (character == UINT8_C(0x0a)) {
        ++row;
    } else if (character != UINT8_C(0x07)) {
        write_character(machine, page, row, column, character, attribute, 1);
        ++column;
        if (column >= machine->columns) {
            column = 0U;
            ++row;
        }
    }
    if (row >= machine->rows) {
        scroll_window(machine, 1U, UINT8_C(0x07), 0U, 0U,
                      (uint8_t)(machine->rows - 1U),
                      (uint8_t)(machine->columns - 1U), 0);
        row = (uint8_t)(machine->rows - 1U);
    }
    set_cursor(machine, cpu, page, row, column);
}

static void cga_write_pixel(d2e_pc_at *machine, uint16_t x, uint16_t y,
                            uint8_t color) {
    size_t offset;
    uint8_t mask;
    uint8_t value;
    const uint16_t width = machine->video_mode == 6U ? 640U : 320U;
    if (machine->cga_vram == NULL || x >= width || y >= 200U) {
        return;
    }
    offset = d2e_cga_row_offset(y);
    if (machine->video_mode == 6U) {
        offset += x >> 3U;
        if (offset >= machine->cga_vram_size) {
            return;
        }
        mask = (uint8_t)(UINT8_C(0x80) >> (x & 7U));
        if ((color & 1U) != 0U) {
            machine->cga_vram[offset] |= mask;
        } else {
            machine->cga_vram[offset] &= (uint8_t)~mask;
        }
        return;
    }
    offset += x >> 2U;
    if (offset >= machine->cga_vram_size) {
        return;
    }
    mask = (uint8_t)(UINT8_C(0x03) << (6U - (x & 3U) * 2U));
    value = (uint8_t)((color & 3U) << (6U - (x & 3U) * 2U));
    machine->cga_vram[offset] =
        (uint8_t)((machine->cga_vram[offset] & (uint8_t)~mask) | value);
}

static uint8_t cga_read_pixel(const d2e_pc_at *machine, uint16_t x,
                              uint16_t y) {
    size_t offset;
    const uint16_t width = machine->video_mode == 6U ? 640U : 320U;
    if (machine->cga_vram == NULL || x >= width || y >= 200U) {
        return 0U;
    }
    offset = d2e_cga_row_offset(y);
    if (machine->video_mode == 6U) {
        offset += x >> 3U;
        return (uint8_t)((machine->cga_vram[offset] >> (7U - (x & 7U))) & 1U);
    }
    offset += x >> 2U;
    return (uint8_t)((machine->cga_vram[offset] >>
                      (6U - (x & 3U) * 2U)) & 3U);
}

static int video_interrupt(d2e_pc_at *machine, d2e_x86_cpu *cpu) {
    const uint8_t function = get_ah(cpu);
    const uint8_t al = get_al(cpu);
    const uint8_t bh = d2e_x86_get_reg8(cpu, 7U);
    const uint8_t bl = d2e_x86_get_reg8(cpu, 3U);
    const uint8_t ch = d2e_x86_get_reg8(cpu, 5U);
    const uint8_t cl = d2e_x86_get_reg8(cpu, 1U);
    const uint8_t dh = d2e_x86_get_reg8(cpu, 6U);
    const uint8_t dl = d2e_x86_get_reg8(cpu, 2U);

    switch (function) {
        case 0x00:
            set_video_mode(machine, cpu, al);
            return 1;
        case 0x01:
            machine->cursor_start = ch;
            machine->cursor_end = cl;
            update_video_bda(machine, cpu);
            return 1;
        case 0x02:
            set_cursor(machine, cpu, bh, dh, dl);
            return 1;
        case 0x03:
            if (bh < D2E_PC_AT_TEXT_PAGES) {
                d2e_x86_set_reg8(cpu, 5U, machine->cursor_start);
                d2e_x86_set_reg8(cpu, 1U, machine->cursor_end);
                d2e_x86_set_reg8(cpu, 6U, machine->cursor_row[bh]);
                d2e_x86_set_reg8(cpu, 2U, machine->cursor_column[bh]);
            }
            return 1;
        case 0x05:
            machine->active_page =
                al < D2E_PC_AT_TEXT_PAGES ? al : 0U;
            update_video_bda(machine, cpu);
            return 1;
        case 0x06:
        case 0x07:
            scroll_window(machine, al, bh, ch, cl, dh, dl,
                          function == 0x07);
            return 1;
        case 0x08:
            if (bh < D2E_PC_AT_TEXT_PAGES) {
                cpu->regs[D2E_X86_AX] = read_text_cell(
                    machine, bh, machine->cursor_row[bh],
                    machine->cursor_column[bh]);
            }
            return 1;
        case 0x09:
        case 0x0a: {
            uint16_t count;
            uint8_t row;
            uint8_t column;
            if (bh >= D2E_PC_AT_TEXT_PAGES) {
                return 1;
            }
            row = machine->cursor_row[bh];
            column = machine->cursor_column[bh];
            for (count = 0; count < cpu->regs[D2E_X86_CX]; ++count) {
                write_character(machine, bh, row, column, al, bl,
                                function == 0x09);
                ++column;
                if (column >= machine->columns) {
                    column = 0U;
                    ++row;
                    if (row >= machine->rows) {
                        row = 0U;
                    }
                }
            }
            return 1;
        }
        case 0x0b:
            if (bh == 0U) {
                machine->cga.color_control =
                    (uint8_t)((machine->cga.color_control & UINT8_C(0x30)) |
                              (bl & UINT8_C(0x0f)));
            } else if (bh == 1U) {
                machine->cga.color_control =
                    (uint8_t)((machine->cga.color_control & UINT8_C(0x0f)) |
                              ((bl & 1U) << 5U));
            }
            return 1;
        case 0x0c:
            if (machine->video_mode >= 4U && machine->video_mode <= 6U) {
                cga_write_pixel(machine, cpu->regs[D2E_X86_CX],
                                cpu->regs[D2E_X86_DX], al);
                return 1;
            }
            return 0;
        case 0x0d:
            if (machine->video_mode >= 4U && machine->video_mode <= 6U) {
                set_al(cpu, cga_read_pixel(machine, cpu->regs[D2E_X86_CX],
                                           cpu->regs[D2E_X86_DX]));
                return 1;
            }
            return 0;
        case 0x0e:
            teletype(machine, cpu, al, bl != 0U ? bl : UINT8_C(0x07));
            return 1;
        case 0x0f:
            set_al(cpu, machine->video_mode);
            set_ah(cpu, machine->columns);
            d2e_x86_set_reg8(cpu, 7U, machine->active_page);
            return 1;
        case 0x10:
            if (al == 0U || al == 1U) {
                machine->cga.color_control = bl;
                return 1;
            }
            if (al == 3U) {
                return 1;
            }
            return 0;
        case 0x11:
            if (al == UINT8_C(0x30)) {
                cpu->segments[D2E_X86_ES] = 0U;
                cpu->regs[D2E_X86_BP] = 0U;
                cpu->regs[D2E_X86_CX] = machine->character_height;
                d2e_x86_set_reg8(cpu, 2U,
                                 (uint8_t)(machine->rows - 1U));
                return 1;
            }
            return 0;
        case 0x12:
            if (bl == UINT8_C(0x10)) {
                d2e_x86_set_reg8(cpu, 7U, 0U);
                d2e_x86_set_reg8(cpu, 3U, 3U);
                d2e_x86_set_reg8(cpu, 5U, 0U);
                d2e_x86_set_reg8(cpu, 1U, 0U);
                return 1;
            }
            return 0;
        case 0x1a:
            if (al == 0U) {
                set_al(cpu, UINT8_C(0x1a));
                cpu->regs[D2E_X86_BX] = UINT16_C(0x0004);
                return 1;
            }
            return 0;
        case 0xfe:
            return 1;
        default:
            return 0;
    }
}

static int keyboard_interrupt(d2e_pc_at *machine, d2e_x86_cpu *cpu) {
    const uint8_t function = get_ah(cpu);
    d2e_pc_at_key key;
    if (function == 0U || function == UINT8_C(0x10)) {
        if (machine->key_count == 0U) {
            machine->waiting_keyboard_cpu = cpu;
            cpu->stop_reason = D2E_X86_WAITING_INPUT;
            return 1;
        }
        machine->waiting_keyboard_cpu = NULL;
        key = machine->key_queue[machine->key_head];
        machine->key_head =
            (uint8_t)((machine->key_head + 1U) % D2E_PC_AT_KEY_QUEUE_CAPACITY);
        --machine->key_count;
        cpu->regs[D2E_X86_AX] =
            (uint16_t)(((uint16_t)key.scan << 8U) | key.ascii);
        return 1;
    }
    if (function == 1U || function == UINT8_C(0x11)) {
        if (machine->key_count == 0U) {
            set_flag(cpu, D2E_X86_FLAG_ZF, 1);
        } else {
            key = machine->key_queue[machine->key_head];
            cpu->regs[D2E_X86_AX] =
                (uint16_t)(((uint16_t)key.scan << 8U) | key.ascii);
            set_flag(cpu, D2E_X86_FLAG_ZF, 0);
        }
        return 1;
    }
    if (function == 2U) {
        set_al(cpu, machine->keyboard_shift_flags);
        return 1;
    }
    if (function == UINT8_C(0x12)) {
        cpu->regs[D2E_X86_AX] = machine->keyboard_shift_flags;
        return 1;
    }
    return 0;
}

static int clock_interrupt(d2e_pc_at *machine, d2e_x86_cpu *cpu) {
    const uint8_t function = get_ah(cpu);
    if (function == 0U) {
        cpu->regs[D2E_X86_CX] = (uint16_t)(machine->timer_ticks >> 16U);
        cpu->regs[D2E_X86_DX] = (uint16_t)machine->timer_ticks;
        set_al(cpu, machine->midnight_rollover);
        machine->midnight_rollover = 0U;
        set_flag(cpu, D2E_X86_FLAG_CF, 0);
        return 1;
    }
    if (function == 1U) {
        machine->timer_ticks =
            ((uint32_t)cpu->regs[D2E_X86_CX] << 16U) |
            cpu->regs[D2E_X86_DX];
        machine->midnight_rollover = 0U;
        set_flag(cpu, D2E_X86_FLAG_CF, 0);
        return 1;
    }
    if (function == 2U) {
        cpu->regs[D2E_X86_CX] = 0U;
        cpu->regs[D2E_X86_DX] = 0U;
        set_flag(cpu, D2E_X86_FLAG_CF, 0);
        return 1;
    }
    if (function == 4U) {
        cpu->regs[D2E_X86_CX] = UINT16_C(0x1980);
        cpu->regs[D2E_X86_DX] = UINT16_C(0x0101);
        set_flag(cpu, D2E_X86_FLAG_CF, 0);
        return 1;
    }
    return 0;
}

static int services_interrupt(d2e_x86_cpu *cpu) {
    const uint8_t function = get_ah(cpu);
    if (function == UINT8_C(0x86)) {
        set_flag(cpu, D2E_X86_FLAG_CF, 0);
        set_ah(cpu, 0U);
        return 1;
    }
    if (function == UINT8_C(0x88)) {
        cpu->regs[D2E_X86_AX] = 0U;
        set_flag(cpu, D2E_X86_FLAG_CF, 0);
        return 1;
    }
    if (function == UINT8_C(0x90) || function == UINT8_C(0x91)) {
        set_flag(cpu, D2E_X86_FLAG_CF, 0);
        return 1;
    }
    if (function == UINT8_C(0xc0)) {
        cpu->segments[D2E_X86_ES] = 0U;
        cpu->regs[D2E_X86_BX] = 0U;
        set_ah(cpu, 0U);
        set_flag(cpu, D2E_X86_FLAG_CF, 0);
        return 1;
    }
    return 0;
}

static int mouse_interrupt(d2e_x86_cpu *cpu) {
    const uint16_t function = cpu->regs[D2E_X86_AX];
    if (function == 0U || function == UINT16_C(0x0021)) {
        cpu->regs[D2E_X86_AX] = 0U;
        cpu->regs[D2E_X86_BX] = 0U;
    } else if (function == UINT16_C(0x0003)) {
        cpu->regs[D2E_X86_BX] = 0U;
        cpu->regs[D2E_X86_CX] = 0U;
        cpu->regs[D2E_X86_DX] = 0U;
    }
    return 1;
}

static uint16_t dos_memory_end(const d2e_x86_cpu *cpu) {
    const size_t paragraphs = cpu->memory_size >> 4U;
    return paragraphs > UINT16_MAX ? UINT16_MAX : (uint16_t)paragraphs;
}

static void dos_success(d2e_x86_cpu *cpu) {
    set_flag(cpu, D2E_X86_FLAG_CF, 0);
}

static void dos_error(d2e_x86_cpu *cpu, uint16_t error) {
    cpu->regs[D2E_X86_AX] = error;
    set_flag(cpu, D2E_X86_FLAG_CF, 1);
}

static uint16_t dos_errno(void) {
    switch (errno) {
        case ENOENT:
            return UINT16_C(2);
        case EMFILE:
            return UINT16_C(4);
        case EACCES:
            return UINT16_C(5);
        default:
            return UINT16_C(5);
    }
}

static int dos_read_guest_string(const d2e_x86_cpu *cpu, uint16_t segment,
                                 uint16_t offset, char *destination,
                                 size_t capacity) {
    size_t index;
    if (capacity == 0U) {
        return 0;
    }
    for (index = 0U; index + 1U < capacity; ++index) {
        const uint32_t address = d2e_x86_linear(segment, offset);
        const uint8_t value = d2e_x86_read8(cpu, address);
        destination[index] = (char)value;
        offset = (uint16_t)(offset + UINT16_C(1));
        if (value == 0U) {
            return 1;
        }
    }
    destination[capacity - 1U] = '\0';
    return 0;
}

static int dos_append_component(char *path, size_t capacity,
                                const char *component, size_t length) {
    size_t used = strlen(path);
    const int separator = used != 0U && path[used - 1U] != '/' &&
                          path[used - 1U] != '\\';
    if (used + (separator ? 1U : 0U) + length + 1U > capacity) {
        return 0;
    }
    if (separator) {
        path[used++] = '/';
    }
    memcpy(path + used, component, length);
    path[used + length] = '\0';
    return 1;
}

static void dos_remove_component(char *path, size_t root_length) {
    size_t length = strlen(path);
    while (length > root_length &&
           (path[length - 1U] == '/' || path[length - 1U] == '\\')) {
        path[--length] = '\0';
    }
    while (length > root_length && path[length - 1U] != '/' &&
           path[length - 1U] != '\\') {
        path[--length] = '\0';
    }
    while (length > root_length &&
           (path[length - 1U] == '/' || path[length - 1U] == '\\')) {
        path[--length] = '\0';
    }
}

static int dos_resolve_path(const d2e_pc_at *machine, const char *guest,
                            char *host, size_t capacity) {
    const char *cursor = guest;
    const char *component;
    size_t root_length;
    if (machine->dos_drive_root[0] == '\0' || guest == NULL ||
        capacity == 0U) {
        return 0;
    }
    if (cursor[0] != '\0' && cursor[1] == ':') {
        const unsigned char requested =
            (unsigned char)toupper((unsigned char)cursor[0]);
        if (requested != (unsigned char)('A' + machine->dos_current_drive)) {
            return 0;
        }
        cursor += 2;
    }
    (void)snprintf(host, capacity, "%s", machine->dos_drive_root);
    root_length = strlen(host);
    if (*cursor != '/' && *cursor != '\\' &&
        machine->dos_current_directory[0] != '\0' &&
        !dos_append_component(host, capacity,
                              machine->dos_current_directory,
                              strlen(machine->dos_current_directory))) {
        return 0;
    }
    while (*cursor == '/' || *cursor == '\\') {
        ++cursor;
    }
    while (*cursor != '\0') {
        size_t length;
        component = cursor;
        while (*cursor != '\0' && *cursor != '/' && *cursor != '\\') {
            ++cursor;
        }
        length = (size_t)(cursor - component);
        if (length == 1U && component[0] == '.') {
            /* Keep the current directory. */
        } else if (length == 2U && component[0] == '.' &&
                   component[1] == '.') {
            dos_remove_component(host, root_length);
        } else if (length != 0U &&
                   !dos_append_component(host, capacity, component, length)) {
            return 0;
        }
        while (*cursor == '/' || *cursor == '\\') {
            ++cursor;
        }
    }
    return 1;
}

static FILE *dos_file(d2e_pc_at *machine, uint16_t handle) {
    const size_t index = handle >= 5U ? (size_t)(handle - 5U) : SIZE_MAX;
    return index < D2E_PC_AT_DOS_FILE_CAPACITY
               ? (FILE *)machine->dos_files[index]
               : NULL;
}

typedef struct dos_find_entry {
    char name[D2E_PC_AT_DOS_PATH_CAPACITY];
    uint32_t size;
    time_t modified;
    uint8_t attributes;
} dos_find_entry;

static int dos_wildcard_match(const char *pattern, const char *name) {
    if (strcmp(pattern, "*.*") == 0) {
        pattern = "*";
    }
    while (*pattern != '\0') {
        if (*pattern == '*') {
            while (*pattern == '*') {
                ++pattern;
            }
            if (*pattern == '\0') {
                return 1;
            }
            while (*name != '\0') {
                if (dos_wildcard_match(pattern, name)) {
                    return 1;
                }
                ++name;
            }
            return dos_wildcard_match(pattern, name);
        }
        if (*name == '\0' ||
            (*pattern != '?' &&
             toupper((unsigned char)*pattern) !=
                 toupper((unsigned char)*name))) {
            return 0;
        }
        ++pattern;
        ++name;
    }
    return *name == '\0';
}

static void dos_close_find(d2e_pc_at *machine) {
#if defined(_WIN32)
    if (machine->dos_find_handle != (intptr_t)-1) {
        (void)_findclose(machine->dos_find_handle);
        machine->dos_find_handle = (intptr_t)-1;
    }
#else
    if (machine->dos_find_directory != NULL) {
        (void)closedir((DIR *)machine->dos_find_directory);
        machine->dos_find_directory = NULL;
    }
#endif
}

#if defined(_WIN32)
static int dos_make_enumeration_path(const d2e_pc_at *machine, char *path,
                                     size_t capacity) {
    const size_t directory_length = strlen(machine->dos_find_directory_path);
    if (directory_length + 3U > capacity) {
        return 0;
    }
    memcpy(path, machine->dos_find_directory_path, directory_length);
    memcpy(path + directory_length, "/*", 3U);
    return 1;
}
#endif

static int dos_open_find(d2e_pc_at *machine) {
#if defined(_WIN32)
    char enumeration_path[D2E_PC_AT_DOS_PATH_CAPACITY];
    struct _finddata_t ignored;
    if (!dos_make_enumeration_path(machine, enumeration_path,
                                   sizeof(enumeration_path))) {
        return 0;
    }
    machine->dos_find_handle = _findfirst(enumeration_path, &ignored);
    if (machine->dos_find_handle == (intptr_t)-1) {
        return 0;
    }
    (void)_findclose(machine->dos_find_handle);
    machine->dos_find_handle = (intptr_t)-1;
    return 1;
#else
    machine->dos_find_directory =
        opendir(machine->dos_find_directory_path);
    return machine->dos_find_directory != NULL;
#endif
}

#if defined(_WIN32)
static int dos_next_find_entry(d2e_pc_at *machine, dos_find_entry *entry) {
    struct _finddata_t data;
    int result;
    if (machine->dos_find_handle == (intptr_t)-1) {
        char enumeration_path[D2E_PC_AT_DOS_PATH_CAPACITY];
        if (!dos_make_enumeration_path(machine, enumeration_path,
                                       sizeof(enumeration_path))) {
            return 0;
        }
        machine->dos_find_handle = _findfirst(enumeration_path, &data);
        result = machine->dos_find_handle != (intptr_t)-1 ? 0 : -1;
    } else {
        result = _findnext(machine->dos_find_handle, &data);
    }
    while (result == 0) {
        if (strcmp(data.name, ".") != 0 && strcmp(data.name, "..") != 0 &&
            dos_wildcard_match(machine->dos_find_pattern, data.name)) {
            (void)snprintf(entry->name, sizeof(entry->name), "%s", data.name);
            entry->size = data.size > UINT32_MAX ? UINT32_MAX
                                                 : (uint32_t)data.size;
            entry->modified = data.time_write;
            entry->attributes =
                (data.attrib & _A_SUBDIR) != 0U ? UINT8_C(0x10)
                                                : UINT8_C(0x20);
            if ((data.attrib & _A_HIDDEN) != 0U) {
                entry->attributes |= UINT8_C(0x02);
            }
            if ((data.attrib & _A_SYSTEM) != 0U) {
                entry->attributes |= UINT8_C(0x04);
            }
            return 1;
        }
        result = _findnext(machine->dos_find_handle, &data);
    }
    return 0;
}
#else
static int dos_next_find_entry(d2e_pc_at *machine, dos_find_entry *entry) {
    struct dirent *item;
    while (machine->dos_find_directory != NULL &&
           (item = readdir((DIR *)machine->dos_find_directory)) != NULL) {
        char path[D2E_PC_AT_DOS_PATH_CAPACITY];
        struct stat status;
        const size_t directory_length =
            strlen(machine->dos_find_directory_path);
        const size_t name_length = strlen(item->d_name);
        if (strcmp(item->d_name, ".") == 0 || strcmp(item->d_name, "..") == 0 ||
            !dos_wildcard_match(machine->dos_find_pattern, item->d_name)) {
            continue;
        }
        if (directory_length + name_length + 2U > sizeof(path)) {
            continue;
        }
        memcpy(path, machine->dos_find_directory_path, directory_length);
        path[directory_length] = '/';
        memcpy(path + directory_length + 1U, item->d_name, name_length + 1U);
        if (stat(path, &status) != 0) {
            continue;
        }
        (void)snprintf(entry->name, sizeof(entry->name), "%s", item->d_name);
        entry->size = status.st_size < 0
                          ? 0U
                          : (uint64_t)status.st_size > UINT32_MAX
                                ? UINT32_MAX
                                : (uint32_t)status.st_size;
        entry->modified = status.st_mtime;
        entry->attributes = S_ISDIR(status.st_mode) ? UINT8_C(0x10)
                                                    : UINT8_C(0x20);
        if (item->d_name[0] == '.') {
            entry->attributes |= UINT8_C(0x02);
        }
        return 1;
    }
    return 0;
}
#endif

static void dos_write_dta_byte(d2e_x86_cpu *cpu, const d2e_pc_at *machine,
                               uint16_t offset, uint8_t value) {
    d2e_x86_write8(
        cpu,
        d2e_x86_linear(machine->dos_dta_segment,
                       (uint16_t)(machine->dos_dta_offset + offset)),
        value);
}

static void dos_write_dta_word(d2e_x86_cpu *cpu, const d2e_pc_at *machine,
                               uint16_t offset, uint16_t value) {
    dos_write_dta_byte(cpu, machine, offset, (uint8_t)value);
    dos_write_dta_byte(cpu, machine, (uint16_t)(offset + UINT16_C(1)),
                       (uint8_t)(value >> 8U));
}

static void dos_write_dta_entry(d2e_x86_cpu *cpu, const d2e_pc_at *machine,
                                const dos_find_entry *entry) {
    struct tm *local = localtime(&entry->modified);
    uint16_t time_value = 0U;
    uint16_t date_value = UINT16_C(0x0021);
    size_t index;
    if (local != NULL) {
        unsigned year = local->tm_year >= 80 ? (unsigned)local->tm_year - 80U
                                             : 0U;
        if (year > 127U) {
            year = 127U;
        }
        time_value = (uint16_t)(((uint16_t)local->tm_hour << 11U) |
                                ((uint16_t)local->tm_min << 5U) |
                                (uint16_t)(local->tm_sec / 2));
        date_value = (uint16_t)(((uint16_t)year << 9U) |
                                ((uint16_t)(local->tm_mon + 1) << 5U) |
                                (uint16_t)local->tm_mday);
    }
    for (index = 0U; index < 43U; ++index) {
        dos_write_dta_byte(cpu, machine, (uint16_t)index, 0U);
    }
    dos_write_dta_byte(cpu, machine, UINT16_C(21), entry->attributes);
    dos_write_dta_word(cpu, machine, UINT16_C(22), time_value);
    dos_write_dta_word(cpu, machine, UINT16_C(24), date_value);
    dos_write_dta_word(cpu, machine, UINT16_C(26), (uint16_t)entry->size);
    dos_write_dta_word(cpu, machine, UINT16_C(28),
                       (uint16_t)(entry->size >> 16U));
    for (index = 0U; index < 12U && entry->name[index] != '\0'; ++index) {
        dos_write_dta_byte(cpu, machine, (uint16_t)(30U + index),
                           (uint8_t)toupper((unsigned char)entry->name[index]));
    }
}

static int dos_find_next(d2e_pc_at *machine, d2e_x86_cpu *cpu) {
    dos_find_entry entry;
    while (dos_next_find_entry(machine, &entry)) {
        const uint8_t special = entry.attributes & UINT8_C(0x16);
        if (special != 0U &&
            (special & (uint8_t)~machine->dos_find_attributes) != 0U) {
            continue;
        }
        dos_write_dta_entry(cpu, machine, &entry);
        if (cpu->stop_reason == D2E_X86_RUNNING) {
            dos_success(cpu);
        }
        return 1;
    }
    dos_close_find(machine);
    dos_error(cpu, UINT16_C(18));
    return 1;
}

static int dos_interrupt(d2e_pc_at *machine, d2e_x86_cpu *cpu) {
    const uint8_t function = get_ah(cpu);
    if (function == UINT8_C(0x2a) || function == UINT8_C(0x2c)) {
        const time_t now = time(NULL);
        const struct tm *const local = localtime(&now);
        if (function == UINT8_C(0x2a)) {
            const unsigned year = local != NULL && local->tm_year >= 80
                                      ? (unsigned)local->tm_year + 1900U
                                      : 1980U;
            cpu->regs[D2E_X86_CX] = (uint16_t)year;
            cpu->regs[D2E_X86_DX] =
                (uint16_t)(((uint16_t)(local != NULL ? local->tm_mon + 1 : 1)
                            << 8U) |
                           (uint16_t)(local != NULL ? local->tm_mday : 1));
            set_al(cpu, (uint8_t)(local != NULL ? local->tm_wday : 2));
        } else {
            cpu->regs[D2E_X86_CX] =
                (uint16_t)(((uint16_t)(local != NULL ? local->tm_hour : 0)
                            << 8U) |
                           (uint16_t)(local != NULL ? local->tm_min : 0));
            cpu->regs[D2E_X86_DX] =
                (uint16_t)((uint16_t)(local != NULL ? local->tm_sec : 0)
                           << 8U);
        }
        return 1;
    }
    if (function == UINT8_C(0x2b) || function == UINT8_C(0x2d)) {
        set_al(cpu, UINT8_C(0xff));
        return 1;
    }
    if (function == UINT8_C(0x02)) {
        const uint8_t character = (uint8_t)cpu->regs[D2E_X86_DX];
        teletype(machine, cpu, character, UINT8_C(0x07));
        set_al(cpu, character);
        return 1;
    }
    if (function == UINT8_C(0x06)) {
        const uint8_t requested = (uint8_t)cpu->regs[D2E_X86_DX];
        if (requested != UINT8_C(0xff)) {
            teletype(machine, cpu, requested, UINT8_C(0x07));
            set_al(cpu, requested);
            set_flag(cpu, D2E_X86_FLAG_ZF, 0);
        } else if (machine->key_count == 0U) {
            set_al(cpu, 0U);
            set_flag(cpu, D2E_X86_FLAG_ZF, 1);
        } else {
            const d2e_pc_at_key key = machine->key_queue[machine->key_head];
            machine->key_head = (uint8_t)((machine->key_head + 1U) %
                                           D2E_PC_AT_KEY_QUEUE_CAPACITY);
            --machine->key_count;
            set_al(cpu, key.ascii);
            set_flag(cpu, D2E_X86_FLAG_ZF, 0);
        }
        return 1;
    }
    if (function == UINT8_C(0x09)) {
        uint16_t offset = cpu->regs[D2E_X86_DX];
        unsigned count;
        for (count = 0U; count < UINT16_MAX; ++count) {
            const uint8_t character = d2e_x86_read8(
                cpu, d2e_x86_linear(cpu->segments[D2E_X86_DS], offset));
            if (character == (uint8_t)'$') {
                set_al(cpu, character);
                return 1;
            }
            teletype(machine, cpu, character, UINT8_C(0x07));
            offset = (uint16_t)(offset + UINT16_C(1));
            if (cpu->stop_reason != D2E_X86_RUNNING) {
                return 1;
            }
        }
        dos_error(cpu, UINT16_C(5));
        return 1;
    }
    if (function == UINT8_C(0x0b)) {
        set_al(cpu, machine->key_count != 0U ? UINT8_C(0xff) : 0U);
        return 1;
    }
    if (function == UINT8_C(0x0e)) {
        const uint8_t requested = (uint8_t)cpu->regs[D2E_X86_DX];
        if (requested == machine->dos_current_drive) {
            set_al(cpu, (uint8_t)(machine->dos_current_drive + 1U));
        } else {
            set_al(cpu, (uint8_t)(machine->dos_current_drive + 1U));
        }
        return 1;
    }
    if (function == UINT8_C(0x19)) {
        set_al(cpu, machine->dos_current_drive);
        return 1;
    }
    if (function == UINT8_C(0x1a)) {
        machine->dos_dta_segment = cpu->segments[D2E_X86_DS];
        machine->dos_dta_offset = cpu->regs[D2E_X86_DX];
        dos_success(cpu);
        return 1;
    }
    if (function == UINT8_C(0x30)) {
        cpu->regs[D2E_X86_AX] = UINT16_C(0x0005);
        cpu->regs[D2E_X86_BX] = UINT16_C(0xff00);
        cpu->regs[D2E_X86_CX] = 0U;
        dos_success(cpu);
        return 1;
    }
    if (function == UINT8_C(0x2f)) {
        cpu->segments[D2E_X86_ES] = machine->dos_dta_segment;
        cpu->regs[D2E_X86_BX] = machine->dos_dta_offset;
        return 1;
    }
    if (function == UINT8_C(0x25)) {
        const uint32_t vector = (uint32_t)get_al(cpu) * UINT32_C(4);
        d2e_x86_write16(cpu, vector, cpu->regs[D2E_X86_DX]);
        d2e_x86_write16(cpu, vector + UINT32_C(2),
                        cpu->segments[D2E_X86_DS]);
        if (cpu->stop_reason == D2E_X86_RUNNING) {
            dos_success(cpu);
        }
        return 1;
    }
    if (function == UINT8_C(0x35)) {
        const uint32_t vector = (uint32_t)get_al(cpu) * UINT32_C(4);
        cpu->regs[D2E_X86_BX] = d2e_x86_read16(cpu, vector);
        cpu->segments[D2E_X86_ES] =
            d2e_x86_read16(cpu, vector + UINT32_C(2));
        dos_success(cpu);
        return 1;
    }
    if (function == UINT8_C(0x38)) {
        static const uint8_t country_info[34] = {
            0U, 0U, '$', 0U, 0U, 0U, 0U, ',', 0U, '.', 0U, '/', 0U,
            ':', 0U, 0U, 2U, 0U, 0U, UINT8_C(0xff), 0U, UINT8_C(0xf0),
            ',', 0U,
        };
        size_t index;
        if (get_al(cpu) != 0U) {
            dos_error(cpu, UINT16_C(2));
            return 1;
        }
        for (index = 0U; index < sizeof(country_info); ++index) {
            d2e_x86_write8(
                cpu,
                d2e_x86_linear(
                    cpu->segments[D2E_X86_DS],
                    (uint16_t)(cpu->regs[D2E_X86_DX] + (uint16_t)index)),
                country_info[index]);
        }
        cpu->regs[D2E_X86_BX] = UINT16_C(1);
        if (cpu->stop_reason == D2E_X86_RUNNING) {
            dos_success(cpu);
        }
        return 1;
    }
    if (function == UINT8_C(0x33)) {
        const uint8_t subfunction = get_al(cpu);
        const uint8_t requested = (uint8_t)cpu->regs[D2E_X86_DX];
        if (subfunction == 0U) {
            cpu->regs[D2E_X86_DX] =
                (uint16_t)((cpu->regs[D2E_X86_DX] & UINT16_C(0xff00)) |
                           machine->dos_break_check);
            dos_success(cpu);
        } else if (subfunction == 1U || subfunction == 2U) {
            const uint8_t previous = machine->dos_break_check;
            machine->dos_break_check = requested != 0U ? 1U : 0U;
            if (subfunction == 2U) {
                cpu->regs[D2E_X86_DX] =
                    (uint16_t)((cpu->regs[D2E_X86_DX] & UINT16_C(0xff00)) |
                               previous);
            }
            dos_success(cpu);
        } else if (subfunction == UINT8_C(5)) {
            cpu->regs[D2E_X86_DX] =
                (uint16_t)((cpu->regs[D2E_X86_DX] & UINT16_C(0xff00)) | 3U);
            dos_success(cpu);
        } else if (subfunction == UINT8_C(6)) {
            cpu->regs[D2E_X86_BX] = UINT16_C(0x0500);
            cpu->regs[D2E_X86_DX] = 0U;
            dos_success(cpu);
        } else {
            dos_error(cpu, UINT16_C(1));
        }
        return 1;
    }
    if (function == UINT8_C(0x3d)) {
        char guest_path[D2E_PC_AT_DOS_PATH_CAPACITY];
        char host_path[D2E_PC_AT_DOS_PATH_CAPACITY];
        const uint8_t access = get_al(cpu) & UINT8_C(3);
        const char *mode = access == 0U ? "rb" : "r+b";
        size_t index;
        FILE *file;
        if (!dos_read_guest_string(cpu, cpu->segments[D2E_X86_DS],
                                   cpu->regs[D2E_X86_DX], guest_path,
                                   sizeof(guest_path)) ||
            !dos_resolve_path(machine, guest_path, host_path,
                              sizeof(host_path))) {
            dos_error(cpu, UINT16_C(3));
            return 1;
        }
        for (index = 0U; index < D2E_PC_AT_DOS_FILE_CAPACITY; ++index) {
            if (machine->dos_files[index] == NULL) {
                break;
            }
        }
        if (index == D2E_PC_AT_DOS_FILE_CAPACITY) {
            dos_error(cpu, UINT16_C(4));
            return 1;
        }
        file = fopen(host_path, mode);
        if (file == NULL) {
            dos_error(cpu, dos_errno());
        } else {
            machine->dos_files[index] = file;
            cpu->regs[D2E_X86_AX] = (uint16_t)(index + 5U);
            dos_success(cpu);
        }
        return 1;
    }
    if (function == UINT8_C(0x3e)) {
        FILE *const file = dos_file(machine, cpu->regs[D2E_X86_BX]);
        if (file == NULL) {
            dos_error(cpu, UINT16_C(6));
        } else {
            const size_t index = (size_t)(cpu->regs[D2E_X86_BX] - 5U);
            const int result = fclose(file);
            machine->dos_files[index] = NULL;
            if (result == 0) {
                dos_success(cpu);
            } else {
                dos_error(cpu, dos_errno());
            }
        }
        return 1;
    }
    if (function == UINT8_C(0x3f)) {
        FILE *const file = dos_file(machine, cpu->regs[D2E_X86_BX]);
        uint16_t remaining = cpu->regs[D2E_X86_CX];
        uint16_t offset = cpu->regs[D2E_X86_DX];
        uint16_t transferred = 0U;
        uint8_t buffer[256];
        if (file == NULL) {
            dos_error(cpu, UINT16_C(6));
            return 1;
        }
        while (remaining != 0U) {
            const size_t requested =
                remaining < sizeof(buffer) ? remaining : sizeof(buffer);
            const size_t count = fread(buffer, 1U, requested, file);
            size_t index;
            for (index = 0U; index < count; ++index) {
                d2e_x86_write8(
                    cpu,
                    d2e_x86_linear(cpu->segments[D2E_X86_DS], offset),
                    buffer[index]);
                offset = (uint16_t)(offset + UINT16_C(1));
            }
            transferred = (uint16_t)(transferred + (uint16_t)count);
            remaining = (uint16_t)(remaining - (uint16_t)count);
            if (count != requested || cpu->stop_reason != D2E_X86_RUNNING) {
                break;
            }
        }
        if (ferror(file)) {
            clearerr(file);
            dos_error(cpu, UINT16_C(5));
        } else {
            cpu->regs[D2E_X86_AX] = transferred;
            dos_success(cpu);
        }
        return 1;
    }
    if (function == UINT8_C(0x42)) {
        FILE *const file = dos_file(machine, cpu->regs[D2E_X86_BX]);
        const int32_t offset =
            (int32_t)(((uint32_t)cpu->regs[D2E_X86_CX] << 16U) |
                      cpu->regs[D2E_X86_DX]);
        const uint8_t origin = get_al(cpu);
        const int whence = origin == 0U ? SEEK_SET
                           : origin == 1U ? SEEK_CUR
                                          : SEEK_END;
        long position;
        if (file == NULL) {
            dos_error(cpu, UINT16_C(6));
        } else if (origin > 2U || fseek(file, (long)offset, whence) != 0 ||
                   (position = ftell(file)) < 0L) {
            dos_error(cpu, UINT16_C(1));
        } else {
            cpu->regs[D2E_X86_AX] = (uint16_t)(uint32_t)position;
            cpu->regs[D2E_X86_DX] = (uint16_t)((uint32_t)position >> 16U);
            dos_success(cpu);
        }
        return 1;
    }
    if (function == UINT8_C(0x44)) {
        const uint8_t subfunction = get_al(cpu);
        if (subfunction == 0U) {
            cpu->regs[D2E_X86_DX] =
                cpu->regs[D2E_X86_BX] < UINT16_C(5)
                    ? UINT16_C(0x0080)
                    : 0U;
            dos_success(cpu);
        } else if (subfunction == UINT8_C(0x08)) {
            cpu->regs[D2E_X86_AX] = 0U;
            dos_success(cpu);
        } else if (subfunction == UINT8_C(0x09)) {
            cpu->regs[D2E_X86_DX] = 0U;
            dos_success(cpu);
        } else if (subfunction == UINT8_C(0x0e) ||
                   subfunction == UINT8_C(0x0f)) {
            set_al(cpu, 0U);
            dos_success(cpu);
        } else {
            dos_error(cpu, UINT16_C(1));
        }
        return 1;
    }
    if (function == UINT8_C(0x47)) {
        const uint8_t requested = (uint8_t)cpu->regs[D2E_X86_DX];
        const uint8_t drive = requested == 0U
                                  ? machine->dos_current_drive
                                  : (uint8_t)(requested - 1U);
        size_t index;
        if (drive != machine->dos_current_drive) {
            dos_error(cpu, UINT16_C(15));
            return 1;
        }
        for (index = 0U;; ++index) {
            const uint8_t value =
                (uint8_t)machine->dos_current_directory[index];
            d2e_x86_write8(
                cpu,
                d2e_x86_linear(
                    cpu->segments[D2E_X86_DS],
                    (uint16_t)(cpu->regs[D2E_X86_SI] + (uint16_t)index)),
                value);
            if (value == 0U || cpu->stop_reason != D2E_X86_RUNNING) {
                break;
            }
        }
        if (cpu->stop_reason == D2E_X86_RUNNING) {
            dos_success(cpu);
        }
        return 1;
    }
    if (function == UINT8_C(0x4e)) {
        char guest_path[D2E_PC_AT_DOS_PATH_CAPACITY];
        char host_path[D2E_PC_AT_DOS_PATH_CAPACITY];
        char *separator;
        dos_close_find(machine);
        if (!dos_read_guest_string(cpu, cpu->segments[D2E_X86_DS],
                                   cpu->regs[D2E_X86_DX], guest_path,
                                   sizeof(guest_path)) ||
            !dos_resolve_path(machine, guest_path, host_path,
                              sizeof(host_path))) {
            dos_error(cpu, UINT16_C(3));
            return 1;
        }
        separator = strrchr(host_path, '/');
        if (separator == NULL) {
            separator = strrchr(host_path, '\\');
        }
        if (separator == NULL || separator[1] == '\0') {
            dos_error(cpu, UINT16_C(3));
            return 1;
        }
        (void)snprintf(machine->dos_find_pattern,
                       sizeof(machine->dos_find_pattern), "%s",
                       separator + 1);
        *separator = '\0';
        (void)snprintf(machine->dos_find_directory_path,
                       sizeof(machine->dos_find_directory_path), "%s",
                       host_path);
        machine->dos_find_attributes = cpu->regs[D2E_X86_CX];
        if (!dos_open_find(machine)) {
            dos_error(cpu, UINT16_C(3));
            return 1;
        }
        return dos_find_next(machine, cpu);
    }
    if (function == UINT8_C(0x4f)) {
        return dos_find_next(machine, cpu);
    }
    if (function == UINT8_C(0x48)) {
        const uint16_t memory_end = dos_memory_end(cpu);
        const uint16_t requested = cpu->regs[D2E_X86_BX];
        const uint16_t available =
            machine->dos_allocation_cursor < memory_end
                ? (uint16_t)(memory_end - machine->dos_allocation_cursor)
                : 0U;
        if (requested == 0U || requested > available) {
            cpu->regs[D2E_X86_BX] = available;
            dos_error(cpu, UINT16_C(8));
        } else {
            cpu->regs[D2E_X86_AX] = machine->dos_allocation_cursor;
            machine->dos_allocation_cursor =
                (uint16_t)(machine->dos_allocation_cursor + requested);
            dos_success(cpu);
        }
        return 1;
    }
    if (function == UINT8_C(0x49)) {
        dos_success(cpu);
        return 1;
    }
    if (function == UINT8_C(0x4a)) {
        const uint16_t memory_end = dos_memory_end(cpu);
        const uint16_t segment = cpu->segments[D2E_X86_ES];
        const uint16_t requested = cpu->regs[D2E_X86_BX];
        const uint16_t available =
            segment < memory_end ? (uint16_t)(memory_end - segment) : 0U;
        if (segment != machine->dos_psp_segment || requested == 0U ||
            requested > available) {
            cpu->regs[D2E_X86_BX] = available;
            dos_error(cpu, UINT16_C(8));
        } else {
            machine->dos_block_paragraphs = requested;
            machine->dos_allocation_cursor =
                (uint16_t)(segment + requested);
            dos_success(cpu);
        }
        return 1;
    }
    if (function == UINT8_C(0x58)) {
        const uint8_t subfunction = get_al(cpu);
        if (subfunction == 0U) {
            cpu->regs[D2E_X86_AX] = machine->dos_allocation_strategy;
            dos_success(cpu);
        } else if (subfunction == 1U &&
                   cpu->regs[D2E_X86_BX] <= UINT16_C(2)) {
            machine->dos_allocation_strategy =
                (uint8_t)cpu->regs[D2E_X86_BX];
            dos_success(cpu);
        } else {
            dos_error(cpu, UINT16_C(1));
        }
        return 1;
    }
    if (function == UINT8_C(0x59)) {
        const uint8_t previous_error = get_al(cpu);
        cpu->regs[D2E_X86_AX] = previous_error;
        cpu->regs[D2E_X86_BX] = UINT16_C(0x0803);
        cpu->regs[D2E_X86_CX] = UINT16_C(0x0100);
        cpu->regs[D2E_X86_DX] = 0U;
        dos_success(cpu);
        return 1;
    }
    return 0;
}

static int multiplex_interrupt(d2e_x86_cpu *cpu) {
    if (cpu->regs[D2E_X86_AX] == UINT16_C(0x1680)) {
        set_al(cpu, 0U);
        return 1;
    }
    return 0;
}

void d2e_pc_at_init(d2e_pc_at *machine, uint8_t *cga_vram,
                    size_t cga_vram_size) {
    unsigned channel;
    memset(machine, 0, sizeof(*machine));
#if defined(_WIN32)
    machine->dos_find_handle = (intptr_t)-1;
#endif
    d2e_cga_init(&machine->cga);
    machine->cga_vram = cga_vram;
    machine->cga_vram_size = cga_vram_size;
    machine->equipment_word = UINT16_C(0x0021);
    machine->conventional_kib = UINT16_C(640);
    machine->video_mode = 3U;
    machine->columns = 80U;
    machine->rows = 25U;
    machine->character_height = 8U;
    machine->cursor_start = 6U;
    machine->cursor_end = 7U;
    for (channel = 0U; channel < 3U; ++channel) {
        machine->pit_reload[channel] = UINT16_C(0xffff);
        machine->pit_counter[channel] = UINT16_C(0xffff);
        machine->pit_access[channel] = 3U;
        machine->pit_mode[channel] = 3U;
    }
    if (cga_vram != NULL) {
        memset(cga_vram, 0, cga_vram_size);
        clear_text_page(machine, 0U, UINT8_C(0x07));
    }
}

void d2e_pc_at_reset(d2e_pc_at *machine) {
    uint8_t *const cga_vram = machine->cga_vram;
    const size_t cga_vram_size = machine->cga_vram_size;
    d2e_pc_at_speaker_callback const speaker_callback =
        machine->speaker_callback;
    void *const speaker_context = machine->speaker_context;
    d2e_x86_cpu *const attached_cpu = machine->attached_cpu;
    char dos_drive_root[D2E_PC_AT_DOS_PATH_CAPACITY];
    char dos_current_directory[D2E_PC_AT_DOS_PATH_CAPACITY];
    const uint8_t dos_current_drive = machine->dos_current_drive;
    size_t file_index;

    (void)snprintf(dos_drive_root, sizeof(dos_drive_root), "%s",
                   machine->dos_drive_root);
    (void)snprintf(dos_current_directory, sizeof(dos_current_directory), "%s",
                   machine->dos_current_directory);
    for (file_index = 0U; file_index < D2E_PC_AT_DOS_FILE_CAPACITY;
         ++file_index) {
        if (machine->dos_files[file_index] != NULL) {
            (void)fclose((FILE *)machine->dos_files[file_index]);
        }
    }
    dos_close_find(machine);

    d2e_pc_at_init(machine, cga_vram, cga_vram_size);
    (void)snprintf(machine->dos_drive_root,
                   sizeof(machine->dos_drive_root), "%s", dos_drive_root);
    (void)snprintf(machine->dos_current_directory,
                   sizeof(machine->dos_current_directory), "%s",
                   dos_current_directory);
    machine->dos_current_drive = dos_current_drive;
    if (attached_cpu != NULL) {
        d2e_pc_at_attach(machine, attached_cpu);
    }
    if (speaker_callback != NULL) {
        d2e_pc_at_set_speaker_callback(machine, speaker_context,
                                       speaker_callback);
    }
}

void d2e_pc_at_attach(d2e_pc_at *machine, d2e_x86_cpu *cpu) {
    machine->attached_cpu = cpu;
    machine->waiting_keyboard_cpu = NULL;
    d2e_x86_map_cga_vram(cpu, machine->cga_vram);
    d2e_x86_configure_interrupts(cpu, machine, d2e_pc_at_interrupt);
    d2e_x86_configure_ports(cpu, machine, d2e_pc_at_port_in8,
                            d2e_pc_at_port_out8);
    update_video_bda(machine, cpu);
}

void d2e_pc_at_prepare_dos(d2e_pc_at *machine, uint16_t psp_segment) {
    uint16_t memory_end;
    if (machine == NULL || machine->attached_cpu == NULL) {
        return;
    }
    memory_end = dos_memory_end(machine->attached_cpu);
    machine->dos_psp_segment = psp_segment;
    machine->dos_dta_segment = psp_segment;
    machine->dos_dta_offset = UINT16_C(0x0080);
    machine->dos_block_paragraphs =
        psp_segment < memory_end ? (uint16_t)(memory_end - psp_segment) : 0U;
    machine->dos_allocation_cursor = memory_end;
}

void d2e_pc_at_set_dos_drive_root(d2e_pc_at *machine, char drive,
                                  const char *root) {
    const unsigned char upper =
        (unsigned char)toupper((unsigned char)drive);
    if (machine == NULL || root == NULL || upper < (unsigned char)'A' ||
        upper > (unsigned char)'Z') {
        return;
    }
    (void)snprintf(machine->dos_drive_root,
                   sizeof(machine->dos_drive_root), "%s", root);
    machine->dos_current_directory[0] = '\0';
    machine->dos_current_drive = (uint8_t)(upper - (unsigned char)'A');
}

void d2e_pc_at_set_speaker_callback(
    d2e_pc_at *machine, void *context,
    d2e_pc_at_speaker_callback callback) {
    machine->speaker_context = context;
    machine->speaker_callback = callback;
    notify_speaker(machine);
}

int d2e_pc_at_interrupt(void *context, d2e_x86_cpu *cpu,
                        uint8_t interrupt_number) {
    d2e_pc_at *const machine = (d2e_pc_at *)context;
    if (machine == NULL) {
        return 0;
    }
    switch (interrupt_number) {
        case 0x10:
            return video_interrupt(machine, cpu);
        case 0x11:
            cpu->regs[D2E_X86_AX] = machine->equipment_word;
            return 1;
        case 0x12:
            cpu->regs[D2E_X86_AX] = machine->conventional_kib;
            return 1;
        case 0x15:
            return services_interrupt(cpu);
        case 0x16:
            return keyboard_interrupt(machine, cpu);
        case 0x1a:
            return clock_interrupt(machine, cpu);
        case 0x21:
            return dos_interrupt(machine, cpu);
        case 0x28:
            return 1;
        case 0x2f:
            return multiplex_interrupt(cpu);
        case 0x33:
            return mouse_interrupt(cpu);
        default:
            return 0;
    }
}

int d2e_pc_at_port_in8(void *context, uint16_t port, uint8_t *value) {
    d2e_pc_at *const machine = (d2e_pc_at *)context;
    unsigned channel;
    if (machine == NULL || value == NULL) {
        return 0;
    }
    if (port == UINT16_C(0x0060)) {
        if (machine->scan_count == 0U) {
            *value = 0U;
        } else {
            *value = machine->scan_queue[machine->scan_head];
            machine->scan_head = (uint8_t)(
                (machine->scan_head + 1U) % D2E_PC_AT_SCAN_QUEUE_CAPACITY);
            --machine->scan_count;
        }
        return 1;
    }
    if (port == UINT16_C(0x0064)) {
        *value = machine->scan_count != 0U ? UINT8_C(0x01) : 0U;
        return 1;
    }
    if (port == UINT16_C(0x03d4)) {
        *value = machine->cga_crtc_index;
        return 1;
    }
    if (port == UINT16_C(0x03d5)) {
        *value = machine->cga_crtc[machine->cga_crtc_index & 31U];
        return 1;
    }
    if (port == UINT16_C(0x03da)) {
        machine->cga_status ^= UINT8_C(0x09);
        *value = machine->cga_status;
        return 1;
    }
    if (port >= UINT16_C(0x0040) && port <= UINT16_C(0x0042)) {
        uint16_t counter;
        channel = (unsigned)(port - UINT16_C(0x0040));
        if (machine->pit_access[channel] != 3U ||
            machine->pit_read_high_next[channel] == 0U) {
            machine->pit_counter[channel] =
                (uint16_t)(machine->pit_counter[channel] - UINT16_C(0x0101));
        }
        counter = machine->pit_counter[channel];
        if (machine->pit_access[channel] == 2U ||
            (machine->pit_access[channel] == 3U &&
             machine->pit_read_high_next[channel] != 0U)) {
            *value = (uint8_t)(counter >> 8U);
        } else {
            *value = (uint8_t)counter;
        }
        if (machine->pit_access[channel] == 3U) {
            machine->pit_read_high_next[channel] ^= 1U;
        }
        return 1;
    }
    if (port == UINT16_C(0x0061)) {
        machine->system_port_b ^= UINT8_C(0x10);
        *value = machine->system_port_b;
        return 1;
    }
    return 0;
}

int d2e_pc_at_port_out8(void *context, uint16_t port, uint8_t value) {
    d2e_pc_at *const machine = (d2e_pc_at *)context;
    unsigned channel;
    if (machine == NULL) {
        return 0;
    }
    if (port == UINT16_C(0x0020)) {
        if ((value & UINT8_C(0x20)) != 0U) {
            machine->keyboard_irq_active = 0U;
        }
        return 1;
    }
    if (port == UINT16_C(0x03d4)) {
        machine->cga_crtc_index = value & UINT8_C(0x1f);
        return 1;
    }
    if (port == UINT16_C(0x03d5)) {
        machine->cga_crtc[machine->cga_crtc_index & 31U] = value;
        return 1;
    }
    if (port == UINT16_C(0x03d8) || port == UINT16_C(0x03d9)) {
        d2e_cga_port_write(&machine->cga, port, value);
        return 1;
    }
    if (port == UINT16_C(0x0043)) {
        const unsigned selected = (unsigned)(value >> 6U);
        const uint8_t access = (uint8_t)((value >> 4U) & 3U);
        if (selected == 3U) {
            return 1;
        }
        channel = selected;
        if (access == 0U) {
            machine->pit_read_high_next[channel] = 0U;
            return 1;
        }
        machine->pit_access[channel] = access;
        machine->pit_mode[channel] = (uint8_t)((value >> 1U) & 7U);
        machine->pit_write_high_next[channel] = 0U;
        machine->pit_read_high_next[channel] = 0U;
        if (channel == 2U) {
            notify_speaker(machine);
        }
        return 1;
    }
    if (port >= UINT16_C(0x0040) && port <= UINT16_C(0x0042)) {
        uint16_t reload;
        int complete = 1;
        channel = (unsigned)(port - UINT16_C(0x0040));
        reload = machine->pit_reload[channel];
        if (machine->pit_access[channel] == 3U &&
            machine->pit_write_high_next[channel] == 0U) {
            machine->pit_write_latch[channel] = value;
            machine->pit_write_high_next[channel] = 1U;
            complete = 0;
        } else if (machine->pit_access[channel] == 2U ||
                   machine->pit_access[channel] == 3U) {
            if (machine->pit_access[channel] == 3U) {
                reload = (uint16_t)(machine->pit_write_latch[channel] |
                                    ((uint16_t)value << 8U));
                machine->pit_write_high_next[channel] = 0U;
            } else {
                reload = (uint16_t)((reload & UINT16_C(0x00ff)) |
                                    ((uint16_t)value << 8U));
            }
        } else {
            reload = (uint16_t)((reload & UINT16_C(0xff00)) | value);
        }
        if (complete) {
            machine->pit_reload[channel] = reload;
            machine->pit_counter[channel] = reload;
            if (channel == 2U) {
                notify_speaker(machine);
            }
        }
        return 1;
    }
    if (port == UINT16_C(0x0061)) {
        const uint8_t previous = machine->system_port_b;
        machine->system_port_b = value;
        if (((previous ^ value) & UINT8_C(0x03)) != 0U) {
            notify_speaker(machine);
        }
        return 1;
    }
    return 0;
}

int d2e_pc_at_enqueue_key(d2e_pc_at *machine, uint8_t ascii,
                          uint8_t scan) {
    uint8_t tail;
    uint8_t scan_tail;
    int delivered = 0;
    if (machine == NULL || scan == 0U) {
        return 0;
    }
    if (machine->scan_count <= D2E_PC_AT_SCAN_QUEUE_CAPACITY - 2U) {
        scan_tail = (uint8_t)((machine->scan_head + machine->scan_count) %
                              D2E_PC_AT_SCAN_QUEUE_CAPACITY);
        machine->scan_queue[scan_tail] = scan;
        scan_tail =
            (uint8_t)((scan_tail + 1U) % D2E_PC_AT_SCAN_QUEUE_CAPACITY);
        machine->scan_queue[scan_tail] = (uint8_t)(scan | UINT8_C(0x80));
        machine->scan_count = (uint8_t)(machine->scan_count + 2U);
        delivered = 1;
    }
    if (machine->waiting_keyboard_cpu != NULL) {
        machine->waiting_keyboard_cpu->regs[D2E_X86_AX] =
            (uint16_t)(((uint16_t)scan << 8U) | ascii);
        machine->waiting_keyboard_cpu = NULL;
        return 1;
    }
    if (machine->key_count >= D2E_PC_AT_KEY_QUEUE_CAPACITY) {
        return delivered;
    }
    tail = (uint8_t)((machine->key_head + machine->key_count) %
                     D2E_PC_AT_KEY_QUEUE_CAPACITY);
    machine->key_queue[tail].ascii = ascii;
    machine->key_queue[tail].scan = scan;
    ++machine->key_count;
    return 1;
}

int d2e_pc_at_dispatch_keyboard_irq(d2e_pc_at *machine) {
    d2e_x86_cpu *cpu;
    uint16_t handler_ip;
    uint16_t handler_cs;
    if (machine == NULL) {
        return 0;
    }
    cpu = machine->attached_cpu;
    if (cpu == NULL || machine->scan_count == 0U ||
        machine->keyboard_irq_active != 0U ||
        (cpu->flags & D2E_X86_FLAG_IF) == 0U) {
        return 0;
    }
    handler_ip = d2e_x86_read16(cpu, UINT32_C(9) * 4U);
    handler_cs = d2e_x86_read16(cpu, UINT32_C(9) * 4U + 2U);
    if (handler_ip == 0U && handler_cs == 0U) {
        return 0;
    }
    d2e_x86_push16(cpu, cpu->flags);
    d2e_x86_push16(cpu, cpu->segments[D2E_X86_CS]);
    d2e_x86_push16(cpu, cpu->ip);
    cpu->flags = (uint16_t)((cpu->flags &
        (uint16_t)~(D2E_X86_FLAG_IF | D2E_X86_FLAG_TF)) |
        D2E_X86_FLAG_FIXED);
    cpu->segments[D2E_X86_CS] = handler_cs;
    cpu->ip = handler_ip;
    machine->keyboard_irq_active = 1U;
    return 1;
}

void d2e_pc_at_set_timer_ticks(d2e_pc_at *machine, uint32_t ticks,
                               uint8_t midnight_rollover) {
    machine->timer_ticks = ticks;
    machine->midnight_rollover = midnight_rollover;
}
