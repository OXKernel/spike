#!/usr/bin/env python3
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from compiler import IndentedBraceLexer, Parser, CCodeGenerator

DEFAULT_LINKER_SCRIPT = """
ENTRY(_start)
SECTIONS {
    . = 1M;
    .text : ALIGN(4K) {
        *(.multiboot_header)
        *(.text*)
    }
    .rodata : ALIGN(4K) { *(.rodata*) }
    .data : ALIGN(4K) { *(.data*) }
    .bss : ALIGN(4K) {
        *(COMMON)
        *(.bss*)
    }
}
"""

class SpikeDriver:
    def __init__(self, args):
        self.args = args
        self.src_file = Path(args.input)
        self.output_name = args.output or self.src_file.stem
        self.mode = args.mode
        self.emit_c_only = args.emit_c
        self.format = args.format
        self.arch = args.arch
        self.build_dir = Path("build")

    def run(self):
        self.build_dir.mkdir(exist_ok=True)
        
        print(f"[*] Compiling {self.src_file} -> C...")
        with open(self.src_file, "r", encoding="utf-8") as f:
            src = f.read()

        tokens = IndentedBraceLexer(src).tokenize()
        ast = Parser(tokens).parse()
        gen = CCodeGenerator(ast, module_name="main")
        
        c_src = gen.generate_source()
        c_hdr = gen.generate_header()

        c_file = self.build_dir / f"{self.src_file.stem}.c"
        h_file = self.build_dir / f"{self.src_file.stem}.h"

        with open(c_file, "w", encoding="utf-8") as f: f.write(c_src)
        with open(h_file, "w", encoding="utf-8") as f: f.write(c_hdr)

        if self.emit_c_only:
            print(f"[✓] C translation unit emitted to {c_file}")
            return

        if self.mode == "host":
            cc = self.args.cc or "gcc"
            out_bin = f"{self.output_name}"
            cmd = [cc, "-O2", "-Iinclude", f"-I{self.build_dir}", "runtime/spike_rt.c", str(c_file), "-o", out_bin, "-pthread"]
            print(f"[*] Compiling Host Binary with {cc}...")
            res = subprocess.run(cmd)
            if res.returncode == 0:
                print(f"[✓] Host executable created: {out_bin}")
            sys.exit(res.returncode)

        elif self.mode == "kernel":
            cc = self.args.cc or (f"{self.arch}-elf-gcc" if shutil.which(f"{self.arch}-elf-gcc") else "gcc")
            objcopy = f"{self.arch}-elf-objcopy" if shutil.which(f"{self.arch}-elf-objcopy") else "objcopy"
            
            lds = self.build_dir / "linker.ld"
            if not lds.exists():
                with open(lds, "w") as f: f.write(DEFAULT_LINKER_SCRIPT)

            elf_out = self.build_dir / f"{self.output_name}.elf"
            kernel_flags = [
                "-O2", "-ffreestanding", "-nostdlib", "-fno-builtin",
                "-fno-stack-protector", "-mno-red-zone",
                "-Iinclude", f"-I{self.build_dir}", "-D_BAREMETAL=1",
                f"-T{lds}", str(c_file), "-o", str(elf_out)
            ]
            if self.arch == "i686":
                kernel_flags.insert(1, "-m32")

            print(f"[*] Building Freestanding Kernel with {cc}...")
            res = subprocess.run([cc] + kernel_flags)
            if res.returncode != 0:
                sys.exit(res.returncode)

            if self.format == "bin":
                bin_out = f"{self.output_name}.bin"
                subprocess.run([objcopy, "-O", "binary", str(elf_out), bin_out], check=True)
                print(f"[✓] Bootable Flat Binary created: {bin_out}")
            else:
                shutil.copy(elf_out, f"{self.output_name}.elf")
                print(f"[✓] Bootable Kernel ELF created: {self.output_name}.elf")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Spike Driver")
    parser.add_argument("input", help="Source file (.spike)")
    parser.add_argument("-o", "--output", help="Output binary name")
    parser.add_argument("--emit-c", action="store_true", help="Stop after C code generation")
    parser.add_argument("--mode", choices=["host", "kernel"], default="host", help="Target mode")
    parser.add_argument("--format", choices=["elf", "bin"], default="elf", help="Output format for kernel mode")
    parser.add_argument("--arch", choices=["x86_64", "i686"], default="x86_64", help="Architecture")
    parser.add_argument("--cc", help="Explicit C compiler")
    
    args = parser.parse_args()
    SpikeDriver(args).run()
