#ifndef D2E_PC_SPEAKER_AUDIO_H
#define D2E_PC_SPEAKER_AUDIO_H

#include "d2e/pc_at.h"
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

#define D2E_PC_SPEAKER_SAMPLE_RATE UINT32_C(16000)

esp_err_t pc_speaker_audio_init(d2e_pc_at *machine);

#ifdef __cplusplus
}
#endif

#endif
