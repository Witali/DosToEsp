#ifndef D2E_PC_SPEAKER_H
#define D2E_PC_SPEAKER_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define D2E_PIT_INPUT_HZ UINT32_C(1193182)
#define D2E_PC_SPEAKER_SILENCE UINT8_C(128)
#define D2E_PC_SPEAKER_LOW UINT8_C(32)
#define D2E_PC_SPEAKER_HIGH UINT8_C(224)

typedef struct d2e_pc_speaker_control {
    uint32_t generation;
    uint16_t reload;
    uint8_t mode;
    uint8_t gate;
    uint8_t speaker_data;
} d2e_pc_speaker_control;

typedef struct d2e_pc_speaker_synth {
    d2e_pc_speaker_control control;
    uint32_t sample_rate;
    uint64_t elapsed_q32;
    uint64_t pit_step_q32;
} d2e_pc_speaker_synth;

void d2e_pc_speaker_synth_init(d2e_pc_speaker_synth *synth,
                               uint32_t sample_rate);
void d2e_pc_speaker_render(d2e_pc_speaker_synth *synth,
                           const d2e_pc_speaker_control *control,
                           uint8_t *samples, size_t sample_count);
uint32_t d2e_pc_speaker_divisor(const d2e_pc_speaker_control *control);
uint32_t d2e_pc_speaker_frequency_hz(
    const d2e_pc_speaker_control *control);

#ifdef __cplusplus
}
#endif

#endif
