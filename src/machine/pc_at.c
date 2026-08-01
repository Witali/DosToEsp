#include "d2e/pc_at.h"
#include "d2e/text_video.h"

#include <string.h>

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
            const int set = (bits & (UINT8_C(0x80) >> glyph_x)) != 0U;
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

void d2e_pc_at_init(d2e_pc_at *machine, uint8_t *cga_vram,
                    size_t cga_vram_size) {
    unsigned channel;
    memset(machine, 0, sizeof(*machine));
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

void d2e_pc_at_attach(d2e_pc_at *machine, d2e_x86_cpu *cpu) {
    machine->attached_cpu = cpu;
    machine->waiting_keyboard_cpu = NULL;
    d2e_x86_map_cga_vram(cpu, machine->cga_vram);
    d2e_x86_configure_interrupts(cpu, machine, d2e_pc_at_interrupt);
    d2e_x86_configure_ports(cpu, machine, d2e_pc_at_port_in8,
                            d2e_pc_at_port_out8);
    update_video_bda(machine, cpu);
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
        return 1;
    }
    if (port >= UINT16_C(0x0040) && port <= UINT16_C(0x0042)) {
        uint16_t reload;
        channel = (unsigned)(port - UINT16_C(0x0040));
        reload = machine->pit_reload[channel];
        if (machine->pit_access[channel] == 2U ||
            (machine->pit_access[channel] == 3U &&
             machine->pit_write_high_next[channel] != 0U)) {
            reload = (uint16_t)((reload & UINT16_C(0x00ff)) |
                                ((uint16_t)value << 8U));
        } else {
            reload = (uint16_t)((reload & UINT16_C(0xff00)) | value);
        }
        machine->pit_reload[channel] = reload;
        machine->pit_counter[channel] = reload;
        if (machine->pit_access[channel] == 3U) {
            machine->pit_write_high_next[channel] ^= 1U;
        }
        return 1;
    }
    if (port == UINT16_C(0x0061)) {
        machine->system_port_b = value;
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
