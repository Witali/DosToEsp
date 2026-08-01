#include "qemu_frame_dump.h"

#include <stdio.h>

#include "esp_rom_sys.h"

#define D2E_QEMU_DUMP_BYTES_PER_LINE 64U

void d2e_qemu_dump_cga(const d2e_pc_at *machine, const uint8_t *vram,
                       size_t vram_size) {
    static const char digits[] = "0123456789abcdef";
    size_t offset;
    if (machine == NULL || vram == NULL) {
        return;
    }
    esp_rom_printf(
        "D2E_VRAM_BEGIN,mode=%u,mode_control=%02x,color_control=%02x,"
        "size=%u\n",
        (unsigned)machine->video_mode, (unsigned)machine->cga.mode_control,
        (unsigned)machine->cga.color_control, (unsigned)vram_size);
    for (offset = 0U; offset < vram_size;
         offset += D2E_QEMU_DUMP_BYTES_PER_LINE) {
        char encoded[D2E_QEMU_DUMP_BYTES_PER_LINE * 2U + 1U];
        size_t count = vram_size - offset;
        size_t index;
        if (count > D2E_QEMU_DUMP_BYTES_PER_LINE) {
            count = D2E_QEMU_DUMP_BYTES_PER_LINE;
        }
        for (index = 0U; index < count; ++index) {
            encoded[index * 2U] = digits[vram[offset + index] >> 4U];
            encoded[index * 2U + 1U] =
                digits[vram[offset + index] & UINT8_C(0x0f)];
        }
        encoded[count * 2U] = '\0';
        esp_rom_printf("D2E_VRAM,%04x,%s\n", (unsigned)offset, encoded);
    }
    esp_rom_printf("D2E_VRAM_END\n");
    fflush(stdout);
}
