# Volkov Commander 4.00 translation baseline

This baseline covers the user-supplied English Volkov Commander 4.00 archive.
The distribution remains under the Git-ignored `games/` directory and is not
redistributed by DosToEsp. Its primary executable is `VC.COM`, not an MZ EXE.

## Binary identity

- Filename: `VC.COM`
- Size: 65,142 bytes
- SHA-256: `f0a1fa6e78aa79268c8374d3603d45444484c598f6307fe9c0eb8c2c3aab8904`
- Format: DOS COM
- Load base and entry: `0100h`
- CPU profile: documented Intel 8086

The automatic source attempt is reproduced with:

```powershell
.\scripts\translate-game.ps1 `
    -InputPath games\volkov-commander-4.00\VC.COM `
    -Name volkov-commander-4.00
```

Generated reports are written to the ignored
`out/generated/volkov-commander-4.00/` directory.

## Static result

- 12,449 reachable instruction sites
- 4,005 basic blocks
- 6,449 CFG edges
- 6 unresolved indirect control transfers
- 0 decode, overlap or out-of-image issues
- 12,291 currently translatable sites (98.73%)
- 158 unsupported sites

The COM target exposed and validated correct 16-bit wrapping of high near
branch targets. It also exposed a Capstone mnemonic mismatch for opcode `98h`;
the frontend now normalizes it to 8086 `CBW`. Native `CBW` and `CWD` semantics
pass both the host suite and the Xtensa assembly audit.

## Remaining source-generation blockers

The largest semantic groups are:

- `LEA`: 31 sites
- `REPNE SCASB`: 28 sites
- `SBB`: 23 sites
- `DIV`: 20 sites
- `REPE CMPSB`: 16 sites
- `CMC`: 12 sites
- remaining `SCAS/CMPS`, `NEG`, `LDS` and `ROR`: 22 sites
- indirect/far `CALL` or `JMP`: 6 sites, representing 6 unresolved targets

The unresolved sites are:

- `00A68h`: `CALL [0BC1h]`
- `02F6Eh`: `JMP CS:[BX+SI]`
- `09382h`: `JMP CS:[SI-2]`
- `09E50h`: `CALL CS:[BP+4]`
- `0A333h`: `CALL ES:[0BC1h]`
- `0CB0Ch`: `CALL ES:[0ABBh]`

The strict frontend therefore emits reports and a `blocked` manifest, but no
partial `game_native.c`. A reference execution trace is required to prove the
dynamic targets. After that, the remaining instruction groups can be added as
general 8086 translations and the automatic source build can be retried.

## Machine boundary

The static inventory contains 143 software interrupts across video, keyboard,
time, DOS, mouse and multiplex services (`INT 10h`, `15h`, `16h`, `1Ah`, `21h`,
`28h`, `2Fh` and `33h`), plus dynamic-port input. Volkov Commander therefore
requires a substantially broader PC/AT DOS environment and filesystem model
than the first Alley Cat execution probe.
