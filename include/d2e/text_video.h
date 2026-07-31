#ifndef D2E_TEXT_VIDEO_H
#define D2E_TEXT_VIDEO_H

#include "d2e/cga.h"

#ifdef __cplusplus
extern "C" {
#endif

#define D2E_CP437_GLYPHS 256U
#define D2E_CP437_HEIGHT 8U
#define D2E_TEXT_OUTPUT_WIDTH 320U

typedef struct d2e_text_render_config {
    uint8_t columns;
    uint8_t rows;
    uint8_t character_height;
    uint16_t page_offset;
    uint8_t cursor_row;
    uint8_t cursor_column;
    uint8_t cursor_start;
    uint8_t cursor_end;
    uint8_t cursor_visible;
    uint8_t blink_on;
    uint16_t output_height;
} d2e_text_render_config;

extern const uint8_t
    d2e_cp437_font[D2E_CP437_GLYPHS * D2E_CP437_HEIGHT];

void d2e_text_render_320_row(const d2e_cga *cga, const uint8_t *vram,
                             size_t vram_size,
                             const d2e_text_render_config *config,
                             unsigned output_y, uint16_t *rgb565);

#ifdef __cplusplus
}
#endif

#endif
