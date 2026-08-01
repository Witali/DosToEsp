#ifndef D2E_PC_AT_H
#define D2E_PC_AT_H

#include "d2e/cga.h"
#include "d2e/pc_speaker.h"
#include "d2e/x86_cpu.h"

#ifdef __cplusplus
extern "C" {
#endif

#define D2E_PC_AT_KEY_QUEUE_CAPACITY 16U
#define D2E_PC_AT_SCAN_QUEUE_CAPACITY 32U
#define D2E_PC_AT_TEXT_PAGES 8U

typedef struct d2e_pc_at_key {
    uint8_t ascii;
    uint8_t scan;
} d2e_pc_at_key;

typedef void (*d2e_pc_at_speaker_callback)(
    void *context, const d2e_pc_speaker_control *control);

typedef struct d2e_pc_at {
    d2e_cga cga;
    uint8_t *cga_vram;
    size_t cga_vram_size;
    uint16_t equipment_word;
    uint16_t conventional_kib;
    uint32_t timer_ticks;
    uint8_t midnight_rollover;
    uint8_t video_mode;
    uint8_t columns;
    uint8_t rows;
    uint8_t character_height;
    uint8_t active_page;
    uint8_t cursor_start;
    uint8_t cursor_end;
    uint8_t cga_crtc_index;
    uint8_t cga_crtc[32];
    uint8_t cga_status;
    uint16_t pit_reload[3];
    uint16_t pit_counter[3];
    uint16_t pit_write_latch[3];
    uint8_t pit_access[3];
    uint8_t pit_mode[3];
    uint8_t pit_write_high_next[3];
    uint8_t pit_read_high_next[3];
    uint8_t system_port_b;
    uint8_t cursor_row[D2E_PC_AT_TEXT_PAGES];
    uint8_t cursor_column[D2E_PC_AT_TEXT_PAGES];
    uint8_t keyboard_shift_flags;
    d2e_pc_at_key key_queue[D2E_PC_AT_KEY_QUEUE_CAPACITY];
    uint8_t scan_queue[D2E_PC_AT_SCAN_QUEUE_CAPACITY];
    uint8_t key_head;
    uint8_t key_count;
    uint8_t scan_head;
    uint8_t scan_count;
    uint8_t keyboard_irq_active;
    uint32_t speaker_generation;
    d2e_pc_at_speaker_callback speaker_callback;
    void *speaker_context;
    d2e_x86_cpu *attached_cpu;
    d2e_x86_cpu *waiting_keyboard_cpu;
} d2e_pc_at;

void d2e_pc_at_init(d2e_pc_at *machine, uint8_t *cga_vram,
                    size_t cga_vram_size);
void d2e_pc_at_attach(d2e_pc_at *machine, d2e_x86_cpu *cpu);
int d2e_pc_at_interrupt(void *context, d2e_x86_cpu *cpu,
                        uint8_t interrupt_number);
int d2e_pc_at_port_in8(void *context, uint16_t port, uint8_t *value);
int d2e_pc_at_port_out8(void *context, uint16_t port, uint8_t value);
int d2e_pc_at_enqueue_key(d2e_pc_at *machine, uint8_t ascii,
                          uint8_t scan);
int d2e_pc_at_dispatch_keyboard_irq(d2e_pc_at *machine);
void d2e_pc_at_set_timer_ticks(d2e_pc_at *machine, uint32_t ticks,
                               uint8_t midnight_rollover);
void d2e_pc_at_set_speaker_callback(
    d2e_pc_at *machine, void *context,
    d2e_pc_at_speaker_callback callback);

#ifdef __cplusplus
}
#endif

#endif
