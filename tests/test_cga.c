#include "d2e/cga.h"

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

static void test_interleaved_rows(void) {
    CHECK(d2e_cga_row_offset(0) == 0U);
    CHECK(d2e_cga_row_offset(1) == UINT16_C(0x2000));
    CHECK(d2e_cga_row_offset(2) == D2E_CGA_BYTES_PER_ROW);
    CHECK(d2e_cga_row_offset(199) ==
          UINT16_C(0x2000) + 99U * D2E_CGA_BYTES_PER_ROW);
}

static void test_mode4_pixels(void) {
    uint8_t vram[D2E_CGA_VRAM_SIZE];
    uint16_t row[D2E_CGA_WIDTH];
    d2e_cga cga;

    memset(vram, 0, sizeof(vram));
    d2e_cga_init(&cga);
    vram[0] = UINT8_C(0x1b);
    vram[UINT16_C(0x2000)] = UINT8_C(0xe4);
    d2e_cga_render_320x200_row(&cga, vram, 0, row);
    CHECK(row[0] == cga.palette_rgb565[0]);
    CHECK(row[1] == cga.palette_rgb565[2]);
    CHECK(row[2] == cga.palette_rgb565[4]);
    CHECK(row[3] == cga.palette_rgb565[6]);

    d2e_cga_render_320x200_row(&cga, vram, 1, row);
    CHECK(row[0] == cga.palette_rgb565[6]);
    CHECK(row[1] == cga.palette_rgb565[4]);
    CHECK(row[2] == cga.palette_rgb565[2]);
    CHECK(row[3] == cga.palette_rgb565[0]);
}

static void test_palette_controls(void) {
    uint8_t vram[D2E_CGA_VRAM_SIZE];
    uint16_t row[D2E_CGA_WIDTH];
    d2e_cga cga;

    memset(vram, 0, sizeof(vram));
    vram[0] = UINT8_C(0x1b);
    d2e_cga_init(&cga);
    d2e_cga_port_write(&cga, UINT16_C(0x03d9), UINT8_C(0x32));
    d2e_cga_render_320x200_row(&cga, vram, 0, row);
    CHECK(row[0] == cga.palette_rgb565[2]);
    CHECK(row[1] == cga.palette_rgb565[11]);
    CHECK(row[2] == cga.palette_rgb565[13]);
    CHECK(row[3] == cga.palette_rgb565[15]);

    d2e_cga_set_mode(&cga, 5U);
    d2e_cga_port_write(&cga, UINT16_C(0x03d9), UINT8_C(0x10));
    d2e_cga_render_320x200_row(&cga, vram, 0, row);
    CHECK(row[0] == cga.palette_rgb565[0]);
    CHECK(row[1] == cga.palette_rgb565[11]);
    CHECK(row[2] == cga.palette_rgb565[12]);
    CHECK(row[3] == cga.palette_rgb565[15]);
}

static void test_mode6_downsampling(void) {
    uint8_t vram[D2E_CGA_VRAM_SIZE];
    uint16_t row[D2E_CGA_WIDTH];
    d2e_cga cga;

    memset(vram, 0, sizeof(vram));
    d2e_cga_init(&cga);
    d2e_cga_set_mode(&cga, 6U);
    d2e_cga_port_write(&cga, UINT16_C(0x03d9), UINT8_C(0x0e));
    vram[0] = UINT8_C(0x90);
    d2e_cga_render_320x200_row(&cga, vram, 0U, row);
    CHECK(row[0] == cga.palette_rgb565[14]);
    CHECK(row[1] == cga.palette_rgb565[14]);
    CHECK(row[2] == cga.palette_rgb565[0]);
    CHECK(row[3] == cga.palette_rgb565[0]);

    d2e_cga_port_write(&cga, UINT16_C(0x03d9), 0U);
    d2e_cga_render_320x200_row(&cga, vram, 0U, row);
    CHECK(row[0] == cga.palette_rgb565[15]);
}

int main(void) {
    test_interleaved_rows();
    test_mode4_pixels();
    test_palette_controls();
    test_mode6_downsampling();
    if (failures != 0U) {
        fprintf(stderr, "%u CGA test(s) failed\n", failures);
        return 1;
    }
    puts("CGA renderer tests passed");
    return 0;
}
