#ifndef D2E_QEMU_FRAME_DUMP_H
#define D2E_QEMU_FRAME_DUMP_H

#include <stddef.h>
#include <stdint.h>

#include "d2e/pc_at.h"

void d2e_qemu_dump_cga(const d2e_pc_at *machine, const uint8_t *vram,
                       size_t vram_size);

#endif
