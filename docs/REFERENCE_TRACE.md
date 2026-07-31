# Reference trace contract

DosToEsp uses a reference runner only to discover code targets and observable
PC hardware/API behaviour. The trace is an analysis input; no CPU execution
code from the reference emulator is linked into the translator or firmware.

## JSONL format

The first line fingerprints the exact binary:

```json
{"event":"meta","schema":"d2e-reference-trace-v1","sha256":"<64 hex digits>"}
```

Subsequent lines use these records:

```json
{"event":"exec","cs":4096,"ip":256}
{"event":"interrupt","number":33,"cs":4096,"ip":278}
{"event":"port_in","port":96,"width":8,"value":0}
{"event":"port_out","port":985,"width":8,"value":48}
{"event":"mem_write","address":753664,"width":8,"value":170}
```

Numeric fields are JSON integers. A producer should restrict `mem_write` to
CGA `B8000h..BBFFFh` and translated-code ranges to keep traces small. `exec`
can be deduplicated or sampled for exploratory runs, but deterministic
acceptance traces retain every instruction in order.

Summarize and fingerprint a trace against its static inventory with:

```powershell
python .\tools\d2e_trace.py .\out\alley-cat.jsonl `
    --inventory .\out\analysis\alley-cat.json `
    --output .\out\analysis\alley-cat-trace.json
```

The tool refuses a trace whose binary SHA-256 differs from the static report.

## Pico-286 observation points

The local reference tree is
`C:/Work/r36sx_disasm/homebrew/pico_286/pico-286`. It currently has no complete
instruction trace mode. A minimal diagnostic-only build can emit the contract
above from these boundaries:

- `src/emulator/cpu.c`, `exec86`: emit `exec` immediately after
  `firstip = CPU_IP`, before opcode/prefix fetching;
- `src/emulator/cpu.c`, `intcall86`: emit `interrupt` before changing guest
  control state;
- `src/emulator/ports.c`, `portin`, `portin16`, `portout`, `portout16`: emit
  port events at the public device-dispatch boundary;
- `src/emulator/memory.c`, `write86_ob`, `write86_mp`, `write86_sw`: emit only
  writes intersecting CGA or the target's translated code ranges.

The hook should be enabled only in the desktop reference build, buffer output,
cap the event count and include a clean-shutdown flush. Instruction tracing on
the microcontroller reference target would distort timing and is unnecessary.
