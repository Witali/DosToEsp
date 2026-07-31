#include "d2e/cga.h"

#include <string.h>

static const uint32_t cga_rgb888[16] = {
    UINT32_C(0x000000), UINT32_C(0x0000c4), UINT32_C(0x00c400),
    UINT32_C(0x00c4c4), UINT32_C(0xc40000), UINT32_C(0xc400c4),
    UINT32_C(0xc47e00), UINT32_C(0xc4c4c4), UINT32_C(0x4e4e4e),
    UINT32_C(0x4e4edc), UINT32_C(0x4edc4e), UINT32_C(0x4ef3f3),
    UINT32_C(0xdc4e4e), UINT32_C(0xf34ef3), UINT32_C(0xf3f34e),
    UINT32_C(0xffffff),
};

static const uint8_t cga_graphics_palette[3][2][4] = {
    {{0, 2, 4, 6}, {0, 10, 12, 14}},
    {{0, 3, 5, 7}, {0, 11, 13, 15}},
    {{0, 3, 4, 7}, {0, 11, 12, 15}},
};

static uint16_t rgb888_to_rgb565(uint32_t color) {
    const uint16_t red = (uint16_t)((color >> 16U) & UINT32_C(0xff));
    const uint16_t green = (uint16_t)((color >> 8U) & UINT32_C(0xff));
    const uint16_t blue = (uint16_t)(color & UINT32_C(0xff));
    return (uint16_t)(((red & UINT16_C(0xf8)) << 8U) |
                      ((green & UINT16_C(0xfc)) << 3U) | (blue >> 3U));
}

void d2e_cga_init(d2e_cga *cga) {
    unsigned index;
    memset(cga, 0, sizeof(*cga));
    cga->mode = 4U;
    cga->mode_control = UINT8_C(0x0a);
    for (index = 0; index < 16U; ++index) {
        cga->palette_rgb565[index] = rgb888_to_rgb565(cga_rgb888[index]);
    }
}

void d2e_cga_set_mode(d2e_cga *cga, uint8_t bios_mode) {
    cga->mode = bios_mode;
}

void d2e_cga_port_write(d2e_cga *cga, uint16_t port, uint8_t value) {
    if (port == UINT16_C(0x03d8)) {
        cga->mode_control = value;
    } else if (port == UINT16_C(0x03d9)) {
        cga->color_control = value;
    }
}

size_t d2e_cga_row_offset(unsigned y) {
    return (size_t)(y >> 1U) * D2E_CGA_BYTES_PER_ROW +
           (size_t)(y & 1U) * UINT16_C(0x2000);
}

void d2e_cga_render_320x200_row(const d2e_cga *cga, const uint8_t *vram,
                                unsigned y, uint16_t *rgb565) {
    const uint8_t intensity = (uint8_t)((cga->color_control >> 4U) & 1U);
    uint8_t palette_group = (uint8_t)((cga->color_control >> 5U) & 1U);
    const uint8_t background = cga->color_control & UINT8_C(0x0f);
    const uint8_t *palette;
    const uint8_t *source;
    unsigned byte_index;

    if (y >= D2E_CGA_HEIGHT) {
        return;
    }
    source = vram + d2e_cga_row_offset(y);
    if (cga->mode == 6U || (cga->mode_control & UINT8_C(0x10)) != 0U) {
        const uint8_t configured = cga->color_control & UINT8_C(0x0f);
        const uint8_t foreground = configured == 0U ? 15U : configured;
        unsigned output_x;
        for (output_x = 0U; output_x < D2E_CGA_WIDTH; ++output_x) {
            const unsigned input_x = output_x * 2U;
            const uint8_t packed = source[input_x >> 3U];
            const unsigned shift = 6U - (input_x & 6U);
            const uint8_t pair = (uint8_t)((packed >> shift) & 3U);
            rgb565[output_x] = cga->palette_rgb565[pair == 0U ? 0U
                                                               : foreground];
        }
        return;
    }
    if (cga->mode == 5U || (cga->mode_control & UINT8_C(0x04)) != 0U) {
        palette_group = 2U;
    }
    palette = cga_graphics_palette[palette_group][intensity];

    for (byte_index = 0; byte_index < D2E_CGA_BYTES_PER_ROW; ++byte_index) {
        const uint8_t packed = source[byte_index];
        unsigned pixel;
        for (pixel = 0; pixel < 4U; ++pixel) {
            const unsigned shift = 6U - pixel * 2U;
            const uint8_t selector = (uint8_t)((packed >> shift) & 3U);
            const uint8_t color = selector == 0U ? background : palette[selector];
            rgb565[byte_index * 4U + pixel] = cga->palette_rgb565[color];
        }
    }
}
