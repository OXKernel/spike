#!/usr/bin/env python3
"""
spike_driver.py - Build Driver & CLI for the Spike Programming Language.
Supports:
  1. User Mode: Transpiles with runtime headers, compiles & links `spike_rt.c`.
  2. Kernel Mode: Freestanding build with target formats:
     - .elf: Freestanding ELF binary or relocatable object.
     - .bin: Raw flat binary image (via objcopy or raw linker layout).
"""

from __future__ import annotations
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from compiler import Compiler


def run_command(cmd: list[str], verbose: bool = False) -> None:
    """Executes a subprocess command, exiting cleanly on failure."""
    if verbose:
        print(f"[CMD] {' '.join(cmd)}")
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        sys.stderr.write(f"\n[Driver Error] Build step failed with exit code {e.returncode}:\n")
        sys.stderr.write(f"  Command: {' '.join(cmd)}\n")
        sys.exit(e.returncode)
    except FileNotFoundError:
        sys.stderr.write(f"\n[Driver Error] Tool not found: '{cmd[0]}'. Verify toolchain in PATH.\n")
        sys.exit(1)


def locate_runtime_files(driver_dir: Path) -> tuple[Optional[Path], Optional[Path]]:
    """Searches common locations for spike_rt.h and spike_rt.c."""
    search_dirs = [
        driver_dir,
        driver_dir / "runtime",
        driver_dir / "include",
        Path.cwd(),
        Path.cwd() / "runtime",
    ]

    header_path, source_path = None, None
    for directory in search_dirs:
        h_candidate = directory / "spike_rt.h"
        c_candidate = directory / "spike_rt.c"
        if not header_path and h_candidate.is_file():
            header_path = h_candidate
        if not source_path and c_candidate.is_file():
            source_path = c_candidate

    return header_path, source_path


def compile_spike(
    source_file: str,
    output_file: Optional[str] = None,
    mode: str = "user",
    kernel_format: str = "elf",
    linker_script: Optional[str] = None,
    emit_c_only: bool = False,
    compile_only: bool = False,
    opt_level: str = "2",
    target_triple: Optional[str] = None,
    verbose: bool = False,
) -> None:
    src_path = Path(source_file).resolve()
    if not src_path.exists():
        sys.stderr.write(f"Error: Source file '{source_file}' does not exist.\n")
        sys.exit(1)

    driver_dir = Path(__file__).parent.resolve()
    is_kernel = (mode == "kernel")

    # 1. Read Spike Source
    with open(src_path, "r", encoding="utf-8") as f:
        source_code = f.read()

    # 2. Transpile Spike -> C via compiler.py
    if verbose:
        print(f"[*] Transpiling '{src_path.name}' [Mode: {mode.upper()}]...")

    try:
        compiler = Compiler(kernel_mode=is_kernel)
        c_code = compiler.compile(source_code)
    except SyntaxError as e:
        sys.stderr.write(f"\n[Spike Syntax Error] {e}\n")
        sys.exit(1)
    except Exception as e:
        sys.stderr.write(f"\n[Spike Compiler Error] {e}\n")
        sys.exit(1)

    # 3. Handle --emit-c
    c_out_path = src_path.with_suffix(".c")
    if emit_c_only:
        dest_c = Path(output_file) if output_file else c_out_path
        with open(dest_c, "w", encoding="utf-8") as f:
            f.write(c_code)
        if verbose:
            print(f"[+] Emitted C code to '{dest_c}'")
        return

    # Write intermediate C source
    with open(c_out_path, "w", encoding="utf-8") as f:
        f.write(c_code)

    # 4. Determine Output Paths
    if output_file:
        final_out = Path(output_file).resolve()
    else:
        if compile_only:
            final_out = src_path.with_suffix(".o")
        elif is_kernel:
            final_out = src_path.with_suffix(f".{kernel_format}")
        else:
            final_out = src_path.with_suffix("")

    cc = os.environ.get("CC", "gcc")
    objcopy = os.environ.get("OBJCOPY", "objcopy")
    intermediate_obj = src_path.with_suffix(".o")

    # 5. Build Execution
    try:
        if is_kernel:
            # -------------------------------------------------------------
            # KERNEL MODE PIPELINE (Freestanding, No Runtime)
            # -------------------------------------------------------------
            kernel_flags = [
                "-ffreestanding",
                "-m64",
                "-nostdlib",
                "-fno-builtin",
                "-fno-stack-protector",
                "-fno-pic",
                "-mno-red-zone",
                f"-O{opt_level}",
                "-Wall",
                "-Wextra",
            ]
            if target_triple:
                kernel_flags.extend(["--target", target_triple])

            if compile_only:
                # Direct object file compilation
                cmd = [cc] + kernel_flags + ["-c", str(c_out_path), "-o", str(final_out)]
                run_command(cmd, verbose=verbose)
                if verbose:
                    print(f"[+] Compiled freestanding kernel object: {final_out}")
            else:
                # Compile intermediate object
                cmd_obj = [cc] + kernel_flags + ["-c", str(c_out_path), "-o", str(intermediate_obj)]
                run_command(cmd_obj, verbose=verbose)

                # Link stage
                elf_target = final_out if kernel_format == "elf" else src_path.with_suffix(".elf")
                link_cmd = ["ld", "-m", "elf_x86_64", "-nostdlib", str(intermediate_obj)]
                
                if linker_script:
                    link_cmd.extend(["-T", linker_script])
                
                link_cmd.extend(["-o", str(elf_target)])
                run_command(link_cmd, verbose=verbose)

                if kernel_format == "bin":
                    # Convert ELF -> Raw Binary Image via objcopy
                    bin_cmd = [objcopy, "-O", "binary", str(elf_target), str(final_out)]
                    run_command(bin_cmd, verbose=verbose)
                    if verbose:
                        print(f"[+] Generated flat binary image: {final_out}")
                    
                    # Clean up temporary ELF if not explicitly requested
                    if not output_file and elf_target.exists():
                        elf_target.unlink()
                else:
                    if verbose:
                        print(f"[+] Linked freestanding kernel ELF: {final_out}")

        else:
            # -------------------------------------------------------------
            # USER MODE PIPELINE (Links spike_rt.h & spike_rt.c)
            # -------------------------------------------------------------
            header_path, rt_source_path = locate_runtime_files(driver_dir)
            user_flags = [f"-O{opt_level}", "-Wall", "-Wextra"]

            if header_path:
                user_flags.append(f"-I{header_path.parent}")

            if compile_only:
                cmd = [cc] + user_flags + ["-c", str(c_out_path), "-o", str(final_out)]
                run_command(cmd, verbose=verbose)
                if verbose:
                    print(f"[+] Compiled user-space object: {final_out}")
            else:
                cmd = [cc] + user_flags + [str(c_out_path)]
                if rt_source_path:
                    cmd.append(str(rt_source_path))
                cmd.extend(["-o", str(final_out)])

                run_command(cmd, verbose=verbose)
                if verbose:
                    print(f"[+] Linked user-space executable: {final_out}")

    finally:
        # Cleanup temporary files unless in verbose mode
        if not verbose:
            if c_out_path.exists() and not emit_c_only:
                c_out_path.unlink()
            if not compile_only and intermediate_obj.exists():
                intermediate_obj.unlink()


def build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Spike Language Compiler Driver",
        formatter_class=argparse.RawTextHelpFormatter,
    )

    parser.add_argument("source", help="Source file (.spike)")
    parser.add_argument("-o", "--output", help="Output path destination")

    # Mode Selection
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--user",
        dest="mode",
        action="store_const",
        const="user",
        default="user",
        help="Compile in User Space mode (includes spike_rt.h, links spike_rt.c) [Default]",
    )
    mode_group.add_argument(
        "-k", "--kernel",
        dest="mode",
        action="store_const",
        const="kernel",
        help="Compile in Freestanding Kernel mode (no runtime overhead/hooks)",
    )

    # Kernel Output Format
    parser.add_argument(
        "--format",
        dest="kernel_format",
        choices=["elf", "bin"],
        default="elf",
        help="Output format for kernel mode: 'elf' (default) or 'bin' (flat binary via objcopy)",
    )
    parser.add_argument(
        "-T", "--linker-script",
        dest="linker_script",
        help="Custom linker script for kernel mode (e.g., -T linker.ld)",
    )

    # General Controls
    parser.add_argument(
        "-c", "--compile-only",
        action="store_true",
        help="Compile to object file (.o) only",
    )
    parser.add_argument(
        "--emit-c",
        action="store_true",
        help="Emit intermediate C code without compiling backend",
    )
    parser.add_argument(
        "-O", "--opt",
        dest="opt_level",
        default="2",
        choices=["0", "1", "2", "3", "s", "fast"],
        help="Optimization level (default: 2)",
    )
    parser.add_argument(
        "--target",
        dest="target_triple",
        help="Cross-compilation target triple",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Print diagnostic messages and toolchain subcommands",
    )

    return parser


def main() -> None:
    parser = build_cli()
    args = parser.parse_args()

    compile_spike(
        source_file=args.source,
        output_file=args.output,
        mode=args.mode,
        kernel_format=args.kernel_format,
        linker_script=args.linker_script,
        emit_c_only=args.emit_c,
        compile_only=args.compile_only,
        opt_level=args.opt_level,
        target_triple=args.target_triple,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    main()
