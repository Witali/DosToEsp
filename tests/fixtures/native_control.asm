bits 16
org 0x100

    xor dx, dx
    jne near_handler
    jne after_near_jump
    jne far_handler
    jne final_target
    mov ax, near_handler
    call ax
    mov bx, after_near_jump
    jmp bx

near_handler:
    inc cx
    ret

after_near_jump:
    int3
    into
    mov ax, 0x7fff
    add ax, 1
    into
    call 0x1000:far_handler
    call far [far_pointer]
    jmp far [final_pointer]

far_handler:
    inc si
    retf

final_target:
    hlt

far_pointer:
    dw far_handler, 0x1000
final_pointer:
    dw final_target, 0x1000
