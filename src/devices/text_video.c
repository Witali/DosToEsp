#include "d2e/text_video.h"

static uint8_t glyph_pixel(uint8_t character, unsigned glyph_y,
                           unsigned glyph_x) {
    const uint8_t bits =
        d2e_cp437_font[(size_t)character * D2E_CP437_HEIGHT + glyph_y];
    return (uint8_t)((bits >> glyph_x) & 1U);
}

void d2e_text_render_320_row(const d2e_cga *cga, const uint8_t *vram,
                             size_t vram_size,
                             const d2e_text_render_config *config,
                             unsigned output_y, uint16_t *rgb565) {
    unsigned output_x;
    unsigned source_y;
    unsigned cell_row;
    unsigned glyph_y;
    unsigned source_width;

    if (cga == NULL || vram == NULL || config == NULL || rgb565 == NULL ||
        config->columns == 0U || config->rows == 0U ||
        config->character_height == 0U || config->output_height == 0U ||
        output_y >= config->output_height) {
        return;
    }
    source_y = output_y * (unsigned)config->rows *
               config->character_height / config->output_height;
    cell_row = source_y / config->character_height;
    glyph_y = (source_y % config->character_height) * D2E_CP437_HEIGHT /
              config->character_height;
    source_width = (unsigned)config->columns * 8U;

    for (output_x = 0U; output_x < D2E_TEXT_OUTPUT_WIDTH; ++output_x) {
        const unsigned source_begin =
            output_x * source_width / D2E_TEXT_OUTPUT_WIDTH;
        unsigned source_end =
            (output_x + 1U) * source_width / D2E_TEXT_OUTPUT_WIDTH;
        const unsigned cell_column = source_begin >> 3U;
        const size_t cell_offset =
            config->page_offset +
            ((size_t)cell_row * config->columns + cell_column) * 2U;
        uint8_t character = 0U;
        uint8_t attribute = 0U;
        uint8_t foreground;
        uint8_t background;
        uint8_t pixel_on = 0U;
        unsigned source_x;

        if (source_end <= source_begin) {
            source_end = source_begin + 1U;
        }
        if (cell_offset + 1U < vram_size) {
            character = vram[cell_offset];
            attribute = vram[cell_offset + 1U];
        }
        foreground = attribute & UINT8_C(0x0f);
        if ((cga->mode_control & UINT8_C(0x20)) != 0U) {
            background = (uint8_t)((attribute >> 4U) & 7U);
            if ((attribute & UINT8_C(0x80)) != 0U && config->blink_on == 0U) {
                foreground = background;
            }
        } else {
            background = (uint8_t)(attribute >> 4U);
        }
        for (source_x = source_begin; source_x < source_end; ++source_x) {
            if ((source_x >> 3U) == cell_column &&
                glyph_pixel(character, glyph_y, source_x & 7U) != 0U) {
                pixel_on = 1U;
            }
        }
        if (config->cursor_visible != 0U &&
            cell_row == config->cursor_row &&
            cell_column == config->cursor_column &&
            (source_y % config->character_height) >= config->cursor_start &&
            (source_y % config->character_height) <= config->cursor_end) {
            pixel_on ^= 1U;
        }
        rgb565[output_x] =
            cga->palette_rgb565[pixel_on != 0U ? foreground : background];
    }
}
