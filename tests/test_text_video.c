#include "d2e/text_video.h"

#include <stdio.h>
#include <string.h>

static unsigned failures;

#define CHECK(expression)                                                       \
    do {                                                                        \
        if (!(expression)) {                                                    \
            fprintf(stderr, "%s:%d: CHECK failed: %s\n", __FILE__, __LINE__,  \
                    #expression);                                               \
            ++failures;                                                         \
        }                                                                       \
    } while (0)

static d2e_text_render_config config_for(uint8_t columns) {
    d2e_text_render_config config;
    memset(&config, 0, sizeof(config));
    config.columns = columns;
    config.rows = 25U;
    config.character_height = 8U;
    config.cursor_start = 6U;
    config.cursor_end = 7U;
    config.output_height = 200U;
    config.blink_on = 1U;
    return config;
}

static void test_cp437_and_attributes(void) {
    uint8_t vram[D2E_CGA_VRAM_SIZE];
    uint16_t row[D2E_TEXT_OUTPUT_WIDTH];
    d2e_text_render_config config = config_for(40U);
    d2e_cga cga;

    memset(vram, 0, sizeof(vram));
    d2e_cga_init(&cga);
    vram[0] = UINT8_C('A');
    vram[1] = UINT8_C(0x1e);
    d2e_text_render_320_row(&cga, vram, sizeof(vram), &config, 0U, row);
    CHECK(row[0] == cga.palette_rgb565[1]);
    CHECK(row[2] == cga.palette_rgb565[14]);
    CHECK(row[3] == cga.palette_rgb565[14]);

    vram[0] = UINT8_C('C');
    d2e_text_render_320_row(&cga, vram, sizeof(vram), &config, 2U, row);
    CHECK(row[0] == cga.palette_rgb565[14]);
    CHECK(row[1] == cga.palette_rgb565[14]);
    CHECK(row[6] == cga.palette_rgb565[1]);
    CHECK(row[7] == cga.palette_rgb565[1]);
    CHECK(d2e_cp437_font[UINT16_C(0xc4) * 8U + 3U] == UINT8_C(0xff));
}

static void test_80_column_downsample_and_cursor(void) {
    uint8_t vram[D2E_CGA_VRAM_SIZE];
    uint16_t row[D2E_TEXT_OUTPUT_WIDTH];
    d2e_text_render_config config = config_for(80U);
    d2e_cga cga;

    memset(vram, 0, sizeof(vram));
    d2e_cga_init(&cga);
    vram[0] = UINT8_C('A');
    vram[1] = UINT8_C(0x1e);
    d2e_text_render_320_row(&cga, vram, sizeof(vram), &config, 0U, row);
    CHECK(row[1] == cga.palette_rgb565[14]);

    config.cursor_visible = 1U;
    config.cursor_row = 0U;
    config.cursor_column = 0U;
    config.cursor_start = 0U;
    config.cursor_end = 0U;
    d2e_text_render_320_row(&cga, vram, sizeof(vram), &config, 0U, row);
    CHECK(row[0] == cga.palette_rgb565[14]);
    CHECK(row[1] == cga.palette_rgb565[1]);
}

static void test_blink_and_43_rows(void) {
    uint8_t vram[D2E_CGA_VRAM_SIZE];
    uint16_t row[D2E_TEXT_OUTPUT_WIDTH];
    d2e_text_render_config config = config_for(80U);
    d2e_cga cga;

    memset(vram, 0, sizeof(vram));
    d2e_cga_init(&cga);
    d2e_cga_port_write(&cga, UINT16_C(0x03d8), UINT8_C(0x20));
    vram[0] = UINT8_C('A');
    vram[1] = UINT8_C(0x9e);
    config.blink_on = 0U;
    d2e_text_render_320_row(&cga, vram, sizeof(vram), &config, 0U, row);
    CHECK(row[1] == cga.palette_rgb565[1]);

    config.rows = 43U;
    config.output_height = 240U;
    d2e_text_render_320_row(&cga, vram, sizeof(vram), &config, 239U, row);
    CHECK(row[319] == cga.palette_rgb565[0]);
}

int main(void) {
    test_cp437_and_attributes();
    test_80_column_downsample_and_cursor();
    test_blink_and_43_rows();
    if (failures != 0U) {
        fprintf(stderr, "%u text video test(s) failed\n", failures);
        return 1;
    }
    puts("CP437 text renderer tests passed");
    return 0;
}
