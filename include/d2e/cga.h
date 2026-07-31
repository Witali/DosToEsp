#ifndef D2E_CGA_H
#define D2E_CGA_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define D2E_CGA_WIDTH 320U
#define D2E_CGA_HEIGHT 200U
#define D2E_CGA_BYTES_PER_ROW 80U
#define D2E_CGA_VRAM_SIZE UINT16_C(0x4000)

typedef struct d2e_cga {
    uint8_t mode;
    uint8_t mode_control;
    uint8_t color_control;
    uint16_t palette_rgb565[16];
} d2e_cga;

void d2e_cga_init(d2e_cga *cga);
void d2e_cga_set_mode(d2e_cga *cga, uint8_t bios_mode);
void d2e_cga_port_write(d2e_cga *cga, uint16_t port, uint8_t value);
size_t d2e_cga_row_offset(unsigned y);
void d2e_cga_render_320x200_row(const d2e_cga *cga, const uint8_t *vram,
                                unsigned y, uint16_t *rgb565);

#ifdef __cplusplus
}
#endif

#endif

