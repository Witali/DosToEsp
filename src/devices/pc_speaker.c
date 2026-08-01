#include "d2e/pc_speaker.h"

#include <string.h>

static uint8_t canonical_mode(uint8_t mode) {
    mode &= UINT8_C(7);
    if (mode == 6U) {
        return 2U;
    }
    if (mode == 7U) {
        return 3U;
    }
    return mode;
}

uint32_t d2e_pc_speaker_divisor(const d2e_pc_speaker_control *control) {
    if (control == NULL || control->reload == 0U) {
        return UINT32_C(65536);
    }
    return control->reload;
}

uint32_t d2e_pc_speaker_frequency_hz(
    const d2e_pc_speaker_control *control) {
    const uint32_t divisor = d2e_pc_speaker_divisor(control);
    return (D2E_PIT_INPUT_HZ + divisor / 2U) / divisor;
}

void d2e_pc_speaker_synth_init(d2e_pc_speaker_synth *synth,
                               uint32_t sample_rate) {
    memset(synth, 0, sizeof(*synth));
    synth->sample_rate = sample_rate == 0U ? 1U : sample_rate;
    synth->pit_step_q32 =
        ((uint64_t)D2E_PIT_INPUT_HZ << 32U) / synth->sample_rate;
}

static int timer_output(const d2e_pc_speaker_synth *synth) {
    const uint8_t mode = canonical_mode(synth->control.mode);
    const uint64_t tick = UINT64_C(1) << 32U;
    const uint64_t divisor =
        (uint64_t)d2e_pc_speaker_divisor(&synth->control) << 32U;
    uint64_t phase;

    if (synth->control.gate == 0U) {
        return mode == 2U || mode == 3U || mode == 4U || mode == 5U;
    }
    if (mode == 0U || mode == 1U) {
        return synth->elapsed_q32 >= divisor;
    }
    if (mode == 2U) {
        phase = synth->elapsed_q32 % divisor;
        return phase < divisor - tick;
    }
    if (mode == 3U) {
        const uint64_t high =
            ((uint64_t)(d2e_pc_speaker_divisor(&synth->control) + 1U) / 2U)
            << 32U;
        phase = synth->elapsed_q32 % divisor;
        return phase < high;
    }
    if (mode == 4U || mode == 5U) {
        return synth->elapsed_q32 < divisor ||
               synth->elapsed_q32 >= divisor + tick;
    }
    return 1;
}

static void advance_timer(d2e_pc_speaker_synth *synth) {
    const uint8_t mode = canonical_mode(synth->control.mode);
    const uint64_t divisor =
        (uint64_t)d2e_pc_speaker_divisor(&synth->control) << 32U;
    const uint64_t terminal = divisor + (UINT64_C(1) << 32U);
    if (synth->control.gate == 0U) {
        return;
    }
    synth->elapsed_q32 += synth->pit_step_q32;
    if (mode == 2U || mode == 3U) {
        synth->elapsed_q32 %= divisor;
    } else if (synth->elapsed_q32 > terminal) {
        synth->elapsed_q32 = terminal;
    }
}

void d2e_pc_speaker_render(d2e_pc_speaker_synth *synth,
                           const d2e_pc_speaker_control *control,
                           uint8_t *samples, size_t sample_count) {
    size_t index;
    const int retrigger =
        control->generation != synth->control.generation &&
        (control->reload != synth->control.reload ||
         canonical_mode(control->mode) != canonical_mode(synth->control.mode) ||
         (control->gate != 0U && synth->control.gate == 0U) ||
         canonical_mode(control->mode) == 1U ||
         canonical_mode(control->mode) == 5U);
    if (retrigger) {
        synth->elapsed_q32 = 0U;
    }
    synth->control = *control;
    for (index = 0; index < sample_count; ++index) {
        if (control->speaker_data == 0U) {
            samples[index] = D2E_PC_SPEAKER_SILENCE;
        } else {
            samples[index] = timer_output(synth) ? D2E_PC_SPEAKER_HIGH
                                                  : D2E_PC_SPEAKER_LOW;
        }
        advance_timer(synth);
    }
}
