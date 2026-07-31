#ifndef D2E_PC_INPUT_H
#define D2E_PC_INPUT_H

#include "d2e/pc_at.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct d2e_pc_input {
    uint8_t escape_state;
} d2e_pc_input;

void d2e_pc_input_init(d2e_pc_input *input);
int d2e_pc_input_feed_byte(d2e_pc_input *input, d2e_pc_at *machine,
                           uint8_t byte);

#ifdef __cplusplus
}
#endif

#endif
