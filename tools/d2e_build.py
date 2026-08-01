#!/usr/bin/env python3
"""Translate a DOS executable into deterministic ESP32 source inputs."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "tools"))

import d2e_analyze
import d2e_coverage
import d2e_translate


def write_text(path: pathlib.Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8", newline="\n")


def remove_previous_generated_files(output: pathlib.Path) -> None:
    manifest_path = output / "manifest.json"
    names: list[str] = ["game_native.h"]
    if manifest_path.is_file():
        try:
            previous = json.loads(manifest_path.read_text(encoding="utf-8"))
            names.extend(previous.get("generated_sources", []))
            names.extend(previous.get("generated_headers", []))
        except (OSError, ValueError, TypeError):
            pass
    for name in names:
        candidate = pathlib.Path(name)
        if candidate.name != name or candidate.suffix not in (".c", ".h"):
            continue
        try:
            (output / candidate).unlink()
        except FileNotFoundError:
            pass


def build_sources(
    data: bytes,
    source_name: str,
    image_format: str,
    name: str,
    load_segment: int,
    output: pathlib.Path,
) -> dict[str, Any]:
    image = d2e_analyze.identify(data, image_format, None, None)
    inventory = d2e_analyze.analyze(image, source_name)
    coverage = d2e_coverage.coverage(inventory)
    generated: list[str] = []
    generated_headers: list[str] = []
    blockers: list[dict[str, Any]] = []

    write_text(
        output / "inventory.json",
        json.dumps(inventory, indent=2, sort_keys=True) + "\n",
    )
    write_text(output / "inventory.md", d2e_analyze.render_markdown(inventory))
    write_text(
        output / "coverage.json",
        json.dumps(coverage, indent=2, sort_keys=True) + "\n",
    )
    write_text(output / "coverage.md", d2e_coverage.render_markdown(coverage))

    unsupported = coverage["summary"]["unsupported_instruction_count"]
    remove_previous_generated_files(output)
    if unsupported:
        if image.format == "mz":
            import d2e_pack_mz

            write_text(
                output / "game_image.c",
                d2e_pack_mz.emit(image, name, load_segment),
            )
            generated.append("game_image.c")
        blockers.append(
            {
                "kind": "translator_coverage",
                "unsupported_instruction_count": unsupported,
                "reasons": coverage["unsupported_reasons"],
            }
        )
    else:
        translation_image = image.module_bytes
        if image.format == "mz":
            translation_image = d2e_translate.relocate_mz_module(
                image.module_bytes, image.relocations, load_segment
            )
        decoded = d2e_translate.discover(
            translation_image,
            image.base,
            image.entry,
            (
                image.base + image.metadata["initial_cs"] * 16
                if image.format == "mz"
                else None
            ),
        )
        blocks = d2e_translate.make_blocks(decoded, image.entry)
        metadata = image.metadata
        if image.format == "mz":
            entry_cs = metadata["initial_cs"]
            entry_ip = metadata["initial_ip"]
            initial_ss = metadata["initial_ss"]
            initial_sp = metadata["initial_sp"]
        else:
            entry_cs = 0
            entry_ip = image.entry
            initial_ss = 0
            initial_sp = 0xFFFE
        files = d2e_translate.emit_source_files(
            image.module_bytes,
            image.relocations if image.format == "mz" else (),
            blocks,
            name,
            image.format,
            load_segment,
            entry_cs,
            entry_ip,
            initial_ss,
            initial_sp,
        )
        for filename, source in files.items():
            write_text(output / filename, source)
            if filename.endswith(".c"):
                generated.append(filename)
            else:
                generated_headers.append(filename)

    manifest = {
        "schema": "d2e-esp32-source-build-v1",
        "name": name,
        "source": {
            "filename": source_name,
            "format": image.format,
            "sha256": inventory["file"]["sha256"],
            "size": len(data),
        },
        "load_segment": load_segment,
        "status": "complete" if not blockers else "blocked",
        "generated_sources": generated,
        "generated_headers": generated_headers,
        "reports": ["inventory.json", "inventory.md", "coverage.json", "coverage.md"],
        "blockers": blockers,
    }
    write_text(output / "manifest.json", json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--name")
    parser.add_argument("--format", choices=("auto", "com", "mz", "raw"), default="auto")
    parser.add_argument("--load-segment", type=lambda value: int(value, 0), default=0x1000)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        data = args.input.read_bytes()
        manifest = build_sources(
            data,
            args.input.name,
            args.format,
            args.name or args.input.stem,
            args.load_segment,
            args.output,
        )
    except (OSError, ValueError, d2e_translate.TranslationError) as error:
        print(f"source build failed: {error}", file=sys.stderr)
        return 1
    print(
        f"EXE source build {manifest['status']}: {args.output / 'manifest.json'}"
    )
    if manifest["status"] != "complete":
        for blocker in manifest["blockers"]:
            print(f"blocker: {blocker['kind']}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
