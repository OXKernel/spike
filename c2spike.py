#!/usr/bin/env python3
"""
c2spike.py - Robust C to Spike Transpiler
- Fixes brace-depth desynchronization on `for` loops.
- Accurately transpiles all methods (kopendir, kclosedir, krewinddir, kreaddir, krmdir, kmkdir, main).
- Supports C labels (`LABEL:`) and `goto LABEL;`.
- Preserves array subscripting (`arr[idx]`).
- Converts `#include "header.h"` to `#include <header.h>`.
- Injects `#define printk printf` into c_decl.
"""

from __future__ import annotations
import argparse
import os
import re
import sys
from pathlib import Path
from typing import List, Optional, Set, Tuple


MULTI_WORD_TYPES = [
    ("unsigned long long", "u64"),
    ("signed long long",   "i64"),
    ("unsigned long",      "u64"),
    ("signed long",        "i64"),
    ("unsigned int",       "u32"),
    ("signed int",         "i32"),
    ("unsigned short",     "u16"),
    ("signed short",       "i16"),
    ("unsigned char",      "u8"),
    ("signed char",        "i8"),
    ("long long",          "i64"),
]

TYPE_MAP = {
    "uint8_t": "u8",
    "uint16_t": "u16",
    "uint32_t": "u32",
    "uint64_t": "u64",
    "int8_t": "i8",
    "int16_t": "i16",
    "int32_t": "i32",
    "int64_t": "i64",
    "short": "i16",
    "int": "i32",
    "long": "i64",
    "char": "u8",
    "size_t": "u64",
    "uintptr_t": "u64",
    "intptr_t": "i64",
    "void": "none",
    "bool": "bool",
    "_Bool": "bool",
    "unsigned": "u32",
    "time_t": "i64",
}

BUILTIN_LIBC_HEADERS = {
    "stdio.h", "stdlib.h", "string.h", "time.h", "stdint.h", "limits.h", "stddef.h"
}


def clean_type(raw: str) -> str:
    s = re.sub(r'\b(static|inline|__inline__|__inline|extern|volatile|register|const)\b', '', raw).strip()
    s = re.sub(r'\bstruct\s+', '', s).strip()
    ptr_depth = s.count('*')
    base = s.replace('*', '').strip()
    base = re.sub(r'\s+', ' ', base)

    parts = base.split()
    if len(parts) > 1:
        for cand in reversed(parts):
            if cand.isidentifier() and cand not in ("define", "ifdef", "ifndef", "endif", "else"):
                base = cand
                break

    for mwt, st in MULTI_WORD_TYPES:
        if base == mwt:
            base = st
            break
    else:
        base = TYPE_MAP.get(base, base)

    return f"{'*' * ptr_depth}{base}"


def collapse_multiline_parentheses(code: str) -> str:
    result = []
    depth = 0
    in_str = False
    quote = ''
    i = 0
    n = len(code)

    while i < n:
        c = code[i]
        if in_str:
            result.append(c)
            if c == '\\' and i + 1 < n:
                i += 1
                result.append(code[i])
            elif c == quote:
                in_str = False
        else:
            if c in ('"', "'"):
                in_str = True
                quote = c
                result.append(c)
            elif c == '(':
                depth += 1
                result.append(c)
            elif c == ')':
                if depth > 0:
                    depth -= 1
                result.append(c)
            elif c == '\n' and depth > 0:
                result.append(' ')
            else:
                result.append(c)
        i += 1

    return "".join(result)


def pre_normalize_c_source(code: str) -> str:
    code = collapse_multiline_parentheses(code)

    string_literals: List[str] = []

    def mask_str(m):
        idx = len(string_literals)
        string_literals.append(m.group(0))
        return f"__SPIKE_STR_{idx}__"

    str_pat = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'')
    code = str_pat.sub(mask_str, code)

    code = re.sub(r'//.*', '', code)
    code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
    code = re.sub(r'^\s*#.*$', '', code, flags=re.MULTILINE)
    code = re.sub(r'\(\s*void\s*\)\s*[a-zA-Z_][a-zA-Z0-9_]*\s*;', '', code)

    code = re.sub(r'\+\+\s*\(\s*([a-zA-Z0-9_\->\.\[\]]+)\s*\)', r'\1 = \1 + 1', code)
    code = re.sub(r'\+\+\s*([a-zA-Z0-9_\->\.\[\]]+)', r'\1 = \1 + 1', code)
    code = re.sub(r'--\s*\(\s*([a-zA-Z0-9_\->\.\[\]]+)\s*\)', r'\1 = \1 - 1', code)
    code = re.sub(r'--\s*([a-zA-Z0-9_\->\.\[\]]+)', r'\1 = \1 - 1', code)

    def cast_sub(m):
        raw_t = m.group(1).strip()
        stars = m.group(2)
        has_amp = bool(m.group(3))
        expr = m.group(4).strip()
        target_t = clean_type(f"{stars}{raw_t}")
        amp_prefix = "&" if has_amp else ""
        return f"(({amp_prefix}{expr}) as {target_t})"

    cast_pat = re.compile(
        r'\(\s*([a-zA-Z_][a-zA-Z0-9_]*|\b(?:unsigned|signed)?\s*(?:char|int|short|long|void)\b)\s*(\*+)\s*\)\s*(&)?\s*([a-zA-Z_][a-zA-Z0-9_\->\.\[\]]*)'
    )
    code = cast_pat.sub(cast_sub, code)

    for mwt, st in MULTI_WORD_TYPES:
        code = re.sub(r'\b' + mwt.replace(' ', r'\s+') + r'\b', st, code)

    for ct, st in TYPE_MAP.items():
        if ct not in ("unsigned", "char", "int", "short", "long"):
            code = re.sub(r'\b' + ct + r'\b', st, code)

    code = re.sub(r'\*\s+([a-zA-Z_][a-zA-Z0-9_]*)', r'*\1', code)

    for idx, s_val in enumerate(string_literals):
        code = code.replace(f"__SPIKE_STR_{idx}__", s_val)

    return code


def _find_matching_paren(tokens: List[str], start_idx: int) -> int:
    if start_idx >= len(tokens) or tokens[start_idx] != "(":
        return -1
    depth = 0
    for idx in range(start_idx, len(tokens)):
        if tokens[idx] == "(":
            depth += 1
        elif tokens[idx] == ")":
            depth -= 1
            if depth == 0:
                return idx
    return -1


def translate_tokens(tokens: List[str]) -> str:
    out_tokens: List[str] = []
    i = 0
    n = len(tokens)

    while i < n:
        t = tokens[i]
        if t == "NULL":
            out_tokens.append("0 as *none")
        elif t == "true":
            out_tokens.append("True")
        elif t == "false":
            out_tokens.append("False")
        else:
            if re.match(r'^\d+[uU]$', t):
                out_tokens.append(t[:-1])
            else:
                out_tokens.append(t)
        i += 1

    expr_str = " ".join(out_tokens)
    expr_str = re.sub(r'\s*->\s*', '->', expr_str)
    expr_str = re.sub(r'\s*\.\s*', '.', expr_str)
    expr_str = re.sub(r'([a-zA-Z0-9_\-\>\.]+)\s*\+\+', r'\1 = \1 + 1', expr_str)
    expr_str = re.sub(r'([a-zA-Z0-9_\-\>\.]+)\s*--', r'\1 = \1 - 1', expr_str)
    expr_str = re.sub(r'\+\+\s*([a-zA-Z0-9_\-\>\.]+)', r'\1 = \1 + 1', expr_str)
    expr_str = re.sub(r'--\s*([a-zA-Z0-9_\-\>\.]+)', r'\1 = \1 - 1', expr_str)
    expr_str = re.sub(r'\s*\[\s*', '[', expr_str)
    expr_str = re.sub(r'\s*\]', ']', expr_str)
    return expr_str


class CTokenizer:
    def __init__(self, code: str):
        self.code = code

    def get_tokens(self) -> List[str]:
        tokens = []
        token_spec = [
            ("STRING",    r'"(?:\\.|[^"\\])*"'),
            ("CHAR",      r'\'(?:\\.|[^\'\\])*\''),
            ("HEX",       r'0[xX][0-9a-fA-F]+'),
            ("OCTAL",     r'0[0-7]+'),
            ("NUMBER",    r'\d+[uU]?'),
            ("OP_MULTI",  r'<<=|>>=|<<|>>|\+\+|--|->|<=|>=|==|!=|&&|\|\||\+=|-=|\*=|/=|%=|&=|\|=|\^='),
            ("OP_SINGLE", r'[{}();,:\.=\+\-\*/%&|^!<>~\[\]?]'),
            ("IDENT",     r'[a-zA-Z_][a-zA-Z0-9_]*'),
            ("WS",        r'\s+'),
        ]
        master_re = re.compile('|'.join(f'(?P<{name}>{pattern})' for name, pattern in token_spec))
        for match in master_re.finditer(self.code):
            kind = match.lastgroup
            val = match.group(0)
            if kind != "WS":
                tokens.append(val)
        return tokens


class BlockParser:
    def __init__(self, tokens: List[str]):
        self.tokens = tokens
        self.pos = 0
        self.length = len(tokens)

    def peek(self, offset: int = 0) -> str:
        idx = self.pos + offset
        return self.tokens[idx] if idx < self.length else ""

    def advance(self) -> str:
        tok = self.peek()
        self.pos += 1
        return tok

    def parse_balanced_block(self) -> List[str]:
        if self.peek() != "{":
            return []
        self.advance()
        depth = 1
        block_tokens = []
        while self.pos < self.length and depth > 0:
            tok = self.advance()
            if tok == "{":
                depth += 1
            elif tok == "}":
                depth -= 1
                if depth == 0:
                    break
            block_tokens.append(tok)
        return block_tokens


class HeaderResolver:
    def __init__(self, base_dir: Path, follow_headers: bool = False, freestanding: bool = False):
        self.base_dir = base_dir
        self.follow_headers = follow_headers
        self.freestanding = freestanding
        self.visited: Set[Path] = set()
        self.c_decls: List[str] = [
            "struct dirent;",
            "typedef struct dirent dirent;",
            "#define printk printf"
        ]

    def resolve(self, code: str, current_dir: Optional[Path] = None) -> str:
        if current_dir is None:
            current_dir = self.base_dir

        lines: List[str] = []
        for line in code.splitlines():
            line_str = line.strip()

            m_fwd = re.match(r'^typedef\s+struct\s+([a-zA-Z_][a-zA-Z0-9_]*)\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*;', line_str)
            if m_fwd:
                struct_tag = m_fwd.group(1)
                alias_name = m_fwd.group(2)
                self.c_decls.append(f"struct {struct_tag};")
                self.c_decls.append(f"typedef struct {struct_tag} {alias_name};")
                continue

            if re.match(r'^typedef\s+[^\{]+;$', line_str):
                self.c_decls.append(line_str)
                continue

            inc_match = re.match(r'^#include\s+["<](.+?)[">]', line_str)
            if inc_match:
                inc_target = inc_match.group(1)
                header_path = (current_dir / inc_target).resolve()

                if self.freestanding and inc_target in BUILTIN_LIBC_HEADERS:
                    continue

                if self.follow_headers and header_path.is_file() and header_path not in self.visited:
                    self.visited.add(header_path)
                    try:
                        with open(header_path, "r", encoding="utf-8", errors="replace") as f:
                            header_code = f.read()
                        inlined = self.resolve(header_code, header_path.parent)
                        lines.append(f"// --- Inlined from {inc_target} ---")
                        lines.append(inlined)
                        lines.append(f"// --- End of {inc_target} ---")
                    except Exception as ex:
                        print(f"[-] Warning: Failed to inline {header_path}: {ex}", file=sys.stderr)
                        self.c_decls.append(f"#include <{inc_target}>")
                else:
                    self.c_decls.append(f"#include <{inc_target}>")
            else:
                lines.append(line)

        return "\n".join(lines)


def format_code_block(lines: List[str], base_indent: int = 1) -> List[str]:
    formatted = []
    level = base_indent

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue

        is_label = bool(re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*:$', line))

        if line.startswith("}") or is_label:
            curr_level = max(0, level - 1)
        else:
            curr_level = level

        indent_str = "    " * curr_level
        formatted.append(f"{indent_str}{line}")

        opens = line.count("{")
        closes = line.count("}")
        level += (opens - closes)
        if level < 0:
            level = 0

    return formatted


class C2Spike:
    def __init__(self, class_name: Optional[str] = None, c_decls: Optional[List[str]] = None):
        self.class_name = class_name or "Native"
        self.c_decls = c_decls or []
        self.structs: List[str] = []
        self.struct_names: List[str] = []
        self.constants: List[str] = []
        self.methods: List[List[str]] = []

    def transpile(self, c_code: str) -> str:
        for line in c_code.splitlines():
            line = line.strip()
            m = re.match(r'^#define\s+([a-zA-Z_][a-zA-Z0-9_]*)\s+(.+)$', line)
            if m:
                name = m.group(1)
                val_raw = m.group(2).strip().rstrip(';')
                if not val_raw.startswith("(") and name != "printk":
                    val = translate_tokens(CTokenizer(val_raw).get_tokens())
                    vtype = "*u8" if val.startswith('"') else "u32"
                    self.constants.append(f"const {name}: {vtype} = {val}")

        normalized_c = pre_normalize_c_source(c_code)
        tokens = CTokenizer(normalized_c).get_tokens()
        parser = BlockParser(tokens)

        while parser.pos < parser.length:
            tok = parser.peek()

            if tok == "#":
                while parser.pos < parser.length and parser.advance() != "\n":
                    pass
                continue

            if self._is_struct_definition(parser):
                self._parse_struct(parser)
                continue

            if self._is_function_header(parser):
                self._parse_function(parser)
                continue

            parser.advance()

        out = ["# Transpiled by c2spike.py", ""]

        for sname in self.struct_names:
            self.c_decls.append(f"typedef struct {sname} {sname};")

        if self.c_decls:
            seen_decls = set()
            ordered_decls = []
            for decl in self.c_decls:
                cleaned = decl.strip()
                if cleaned not in seen_decls:
                    seen_decls.add(cleaned)
                    ordered_decls.append(cleaned)

            out.append("c_decl {")
            for d in ordered_decls:
                d_clean = d.rstrip(";") if d.startswith("#") else (d if d.endswith(";") else f"{d};")
                escaped = d_clean.replace('\\', '\\\\').replace('"', '\\"')
                out.append(f'    "{escaped}";')
            out.append("}")
            out.append("")

        if self.constants:
            out.extend(self.constants)
            out.append("")

        if self.structs:
            out.extend(self.structs)
            out.append("")

        out.append(f"class {self.class_name} {{")
        for method in self.methods:
            out.extend(method)
            out.append("")
        out.append("}")

        return "\n".join(out)

    def _is_struct_definition(self, p: BlockParser) -> bool:
        if p.peek() not in ("struct", "typedef"):
            return False

        idx = p.pos
        has_struct = False
        while idx < p.length and idx - p.pos < 30:
            t = p.tokens[idx]
            if t == "struct":
                has_struct = True
            if t == "(":
                return False
            if t == "{":
                return has_struct
            if t == ";":
                return False
            idx += 1
        return False

    def _parse_struct(self, p: BlockParser):
        header_tokens = []
        while p.pos < p.length and p.peek() != "{":
            header_tokens.append(p.advance())

        struct_name = ""
        for i, t in enumerate(header_tokens):
            if t == "struct" and i + 1 < len(header_tokens) and header_tokens[i+1] != "{":
                struct_name = header_tokens[i+1]

        body_tokens = p.parse_balanced_block()

        trailing_name = ""
        while p.pos < p.length:
            t = p.advance()
            if t == ";":
                break
            if t.isidentifier():
                trailing_name = t

        final_name = trailing_name or struct_name or "AnonymousStruct"
        self.struct_names.append(final_name)

        fields = []
        field_str = " ".join(body_tokens)
        for field in field_str.split(";"):
            f = field.strip()
            if not f:
                continue
            parts = f.rsplit(maxsplit=1)
            if len(parts) == 2:
                ftype = clean_type(parts[0])
                fname = parts[1].replace("*", "")
                if "*" in parts[1]:
                    ftype = f"*{ftype}"
                fields.append(f"    {fname}: {ftype}")

        s_code = [f"struct {final_name} {{", ",\n".join(fields), "}"]
        self.structs.append("\n".join(s_code))

    def _is_function_header(self, p: BlockParser) -> bool:
        idx = p.pos
        paren_found = False
        while idx < p.length:
            t = p.tokens[idx]
            if t == ";":
                return False
            if t == "(":
                paren_found = True
            if paren_found and t == "{":
                return True
            idx += 1
            if idx - p.pos > 300:
                break
        return False

    def _parse_function(self, p: BlockParser):
        header_tokens = []
        while p.pos < p.length and p.peek() != "(":
            header_tokens.append(p.advance())

        if not header_tokens:
            p.advance()
            return

        func_name = header_tokens[-1].strip("*")
        raw_ret = " ".join(header_tokens[:-1])
        ret_type = clean_type(raw_ret) if raw_ret else "none"

        p.advance()  # consume '('
        param_tokens = []
        depth = 1
        while p.pos < p.length and depth > 0:
            tok = p.advance()
            if tok == "(":
                depth += 1
            elif tok == ")":
                depth -= 1
                if depth == 0:
                    break
            param_tokens.append(tok)

        param_str = " ".join(param_tokens)
        params_out = []
        if param_str and param_str != "void":
            for ppart in param_str.split(","):
                ppart = ppart.strip()
                if not ppart:
                    continue
                parts = ppart.rsplit(maxsplit=1)
                if len(parts) == 2:
                    ptype = clean_type(parts[0])
                    pname = parts[1].replace("*", "")
                    if "*" in parts[1]:
                        ptype = f"*{ptype}"
                    params_out.append(f"{pname}: {ptype}")

        body_tokens = p.parse_balanced_block()
        body_lines = self._transpile_block(body_tokens)

        is_main = (func_name == "main")
        prefix = "export " if is_main else "static "
        ret_clause = f": {ret_type}" if ret_type != "none" else ""
        header = f"    {prefix}def {func_name}({', '.join(params_out)}){ret_clause} {{"

        formatted_body = format_code_block(body_lines, base_indent=2)
        res = [header] + formatted_body + ["    }"]
        self.methods.append(res)

    def _transpile_block(self, tokens: List[str]) -> List[str]:
        out = []
        i = 0
        n = len(tokens)
        step_stack: List[List[str]] = []

        while i < n:
            tok = tokens[i]

            # 1. Label definition: IDENTIFIER COLON
            if tok.isidentifier() and i + 1 < n and tokens[i+1] == ":" and (i + 2 >= n or tokens[i+2] != "="):
                out.append(f"{tok}:;")
                i += 2
                continue

            # 2. Goto statement
            if tok == "goto" and i + 1 < n and tokens[i+1].isidentifier():
                out.append(f"goto {tokens[i+1]}")
                i += 2
                if i < n and tokens[i] == ";":
                    i += 1
                continue

            # 3. While loop
            if tok == "while":
                cond_tokens, next_i = self._read_paren_group(tokens, i + 1)
                cond_raw = " ".join(cond_tokens)

                assign_match = re.search(r'([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(.+)', cond_raw)
                if assign_match:
                    var_name = assign_match.group(1).strip()
                    assign_expr = assign_match.group(2).rstrip(')').strip()

                    clean_target = assign_expr.replace("++", "").strip()
                    deref_match = re.search(r'\*\s*([a-zA-Z_][a-zA-Z0-9_]*)', clean_target)
                    ptr_name = deref_match.group(1) if deref_match else None

                    norm_expr = translate_tokens(CTokenizer(clean_target).get_tokens())
                    out.append(f"{var_name} = {norm_expr}")
                    if ptr_name:
                        out.append(f"{ptr_name} = {ptr_name} + 1")
                    out.append(f"while ({var_name} != 0) {{")

                    i = next_i
                    if i < n and tokens[i] == "{":
                        i += 1
                        step_stack.append([])
                    continue
                else:
                    cond_str = translate_tokens(cond_tokens)
                    i = next_i
                    if i < n and tokens[i] != "{":
                        stmt_toks, next_stmt_i = self._read_single_statement(tokens, i)
                        inner_stmt = self._transpile_stmt_str(stmt_toks)
                        if inner_stmt:
                            out.append(f"while ({cond_str}) {{")
                            out.append(inner_stmt)
                            out.append("}")
                        i = next_stmt_i
                    else:
                        out.append(f"while ({cond_str}) {{")
                        if i < n and tokens[i] == "{":
                            i += 1
                            step_stack.append([])
                    continue

            # 4. Do-while loop
            if tok == "do":
                i += 1
                body_toks = []
                if i < n and tokens[i] == "{":
                    depth = 1
                    i += 1
                    while i < n and depth > 0:
                        if tokens[i] == "{":
                            depth += 1
                        elif tokens[i] == "}":
                            depth -= 1
                            if depth == 0:
                                break
                        body_toks.append(tokens[i])
                        i += 1

                if i < n and tokens[i] == "while":
                    cond_tokens, next_i = self._read_paren_group(tokens, i + 1)
                    cond_str = translate_tokens(cond_tokens)
                    i = next_i
                    if i < n and tokens[i] == ";":
                        i += 1

                    out.append("while (True) {")
                    for stmt_line in self._transpile_block(body_toks):
                        out.append(stmt_line)
                    out.append(f"if (!({cond_str})) {{")
                    out.append("break")
                    out.append("}")
                    out.append("}")
                    continue

            # 5. For loop
            if tok == "for":
                for_tokens, next_i = self._read_paren_group(tokens, i + 1)
                for_str = " ".join(for_tokens)
                parts = for_str.split(";")
                init_part = parts[0].strip() if len(parts) > 0 else ""
                cond_part = translate_tokens(CTokenizer(parts[1].strip()).get_tokens()) if len(parts) > 1 and parts[1].strip() else "True"
                step_part = parts[2].strip() if len(parts) > 2 else ""

                if init_part:
                    for init_sub in init_part.split(","):
                        init_sub = init_sub.strip()
                        if init_sub:
                            out.append(self._transpile_stmt_str(CTokenizer(init_sub).get_tokens()))

                step_stmts = []
                if step_part:
                    for s_sub in step_part.split(","):
                        s_sub = s_sub.strip()
                        if s_sub:
                            step_stmts.append(translate_tokens(CTokenizer(s_sub).get_tokens()))

                i = next_i
                if i < n and tokens[i] != "{":
                    stmt_toks, next_stmt_i = self._read_single_statement(tokens, i)
                    inner_stmt = self._transpile_stmt_str(stmt_toks)
                    if inner_stmt:
                        out.append(f"while ({cond_part}) {{")
                        out.append(inner_stmt)
                        for s_stmt in step_stmts:
                            out.append(s_stmt)
                        out.append("}")
                    i = next_stmt_i
                else:
                    out.append(f"while ({cond_part}) {{")
                    if i < n and tokens[i] == "{":
                        i += 1
                        step_stack.append(step_stmts)
                    continue

            # 6. If statement
            if tok == "if":
                cond_tokens, next_i = self._read_paren_group(tokens, i + 1)
                cond_str = translate_tokens(cond_tokens)
                i = next_i

                if i < n and tokens[i] != "{":
                    stmt_toks, next_stmt_i = self._read_single_statement(tokens, i)
                    inner_stmt = self._transpile_stmt_str(stmt_toks)
                    if inner_stmt:
                        out.append(f"if ({cond_str}) {{")
                        out.append(inner_stmt)
                        out.append("}")
                    i = next_stmt_i
                else:
                    out.append(f"if ({cond_str}) {{")
                    if i < n and tokens[i] == "{":
                        i += 1
                        step_stack.append([])
                continue

            # 7. Else statement
            if tok == "else":
                prev_closed = bool(out and out[-1] == "}")

                if i + 1 < n and tokens[i+1] == "if":
                    cond_tokens, next_i = self._read_paren_group(tokens, i + 2)
                    cond_str = translate_tokens(cond_tokens)
                    i = next_i
                    prefix = "} else if" if prev_closed else "else if"
                    if prev_closed:
                        out.pop()

                    if i < n and tokens[i] != "{":
                        stmt_toks, next_stmt_i = self._read_single_statement(tokens, i)
                        inner_stmt = self._transpile_stmt_str(stmt_toks)
                        if inner_stmt:
                            out.append(f"{prefix} ({cond_str}) {{")
                            out.append(inner_stmt)
                            out.append("}")
                        i = next_stmt_i
                    else:
                        out.append(f"{prefix} ({cond_str}) {{")
                        if i < n and tokens[i] == "{":
                            i += 1
                            step_stack.append([])
                    continue
                else:
                    i += 1
                    prefix = "} else {" if prev_closed else "else {"
                    if prev_closed:
                        out.pop()

                    if i < n and tokens[i] != "{":
                        stmt_toks, next_stmt_i = self._read_single_statement(tokens, i)
                        inner_stmt = self._transpile_stmt_str(stmt_toks)
                        if inner_stmt:
                            out.append(prefix)
                            out.append(inner_stmt)
                            out.append("}")
                        i = next_stmt_i
                    else:
                        out.append(prefix)
                        if i < n and tokens[i] == "{":
                            i += 1
                            step_stack.append([])
                    continue

            # 8. Block closure
            if tok == "}":
                if step_stack:
                    steps = step_stack.pop()
                    for st in steps:
                        out.append(st)
                out.append("}")
                i += 1
                continue

            stmt_toks, next_i = self._read_single_statement(tokens, i)
            if next_i == i:
                i += 1
            else:
                i = next_i

            stmt_line = self._transpile_stmt_str(stmt_toks)
            if stmt_line:
                for line_part in stmt_line.splitlines():
                    out.append(line_part.strip())

        return out

    def _read_paren_group(self, tokens: List[str], start: int) -> Tuple[List[str], int]:
        if start >= len(tokens) or tokens[start] != "(":
            return [], start
        depth = 0
        group = []
        i = start
        while i < len(tokens):
            t = tokens[i]
            if t == "(":
                depth += 1
                if depth > 1:
                    group.append(t)
            elif t == ")":
                depth -= 1
                if depth == 0:
                    i += 1
                    break
                group.append(t)
            else:
                group.append(t)
            i += 1
        return group, i

    def _read_single_statement(self, tokens: List[str], start: int) -> Tuple[List[str], int]:
        stmt = []
        i = start
        paren_depth = 0
        bracket_depth = 0
        brace_depth = 0

        while i < len(tokens):
            t = tokens[i]

            if t == "(":
                paren_depth += 1
            elif t == ")":
                paren_depth -= 1
            elif t == "[":
                bracket_depth += 1
            elif t == "]":
                bracket_depth -= 1
            elif t == "{":
                brace_depth += 1
            elif t == "}":
                if brace_depth > 0:
                    brace_depth -= 1
                else:
                    if not stmt:
                        i += 1
                    break

            if paren_depth == 0 and bracket_depth == 0 and brace_depth == 0:
                if t == ";":
                    i += 1
                    break
                if t in ("{", "}") and not stmt:
                    i += 1
                    break
                if t in ("else", "if", "while", "for", "do", "goto") and stmt:
                    break
                if t.isidentifier() and i + 1 < len(tokens) and tokens[i+1] == ":" and stmt:
                    break

            stmt.append(t)
            i += 1
        return stmt, i

    def _transpile_stmt_str(self, tokens: List[str]) -> str:
        if not tokens:
            return ""

        processed_toks = []
        for t in tokens:
            if t == "[" and processed_toks:
                processed_toks[-1] = f"{processed_toks[-1]}["
            elif t == "]" and processed_toks and processed_toks[-1].endswith("["):
                processed_toks[-1] = f"{processed_toks[-1]}]"
            elif processed_toks and processed_toks[-1].endswith("["):
                processed_toks[-1] = f"{processed_toks[-1]}{t}"
            elif t == "]" and processed_toks:
                processed_toks[-1] = f"{processed_toks[-1]}]"
            else:
                processed_toks.append(t)

        stmt = " ".join(processed_toks).strip()
        stmt = re.sub(r'\s*->\s*', '->', stmt)
        stmt = re.sub(r'\s*\.\s*', '.', stmt)
        stmt = re.sub(r'\[\s+', '[', stmt)
        stmt = re.sub(r'\s+\]', ']', stmt)

        if re.match(r'^\(\s*void\s*\)\s*[a-zA-Z_][a-zA-Z0-9_]*$', stmt):
            return ""

        is_call = bool(re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*\s*\(', stmt))

        stmt_strings: List[str] = []
        def mask_inner_str(m):
            s_idx = len(stmt_strings)
            stmt_strings.append(m.group(0))
            return f"__STMT_STR_{s_idx}__"

        stmt_masked = re.sub(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'', mask_inner_str, stmt)

        def restore_stmt_str(s: str) -> str:
            for s_idx, s_txt in enumerate(stmt_strings):
                s = s.replace(f"__STMT_STR_{s_idx}__", s_txt)
            return s

        if not is_call and stmt_masked.count("=") > 1 and "==" not in stmt_masked and "!=" not in stmt_masked and "<=" not in stmt_masked and ">=" not in stmt_masked and not stmt_masked.startswith("def ") and not stmt_masked.startswith("struct "):
            if "," not in stmt_masked:
                parts = [p.strip() for p in re.split(r'(?<![!<>=+*/%&|^])=(?![=])', stmt_masked)]
                if len(parts) > 2:
                    final_val = translate_tokens(CTokenizer(restore_stmt_str(parts[-1])).get_tokens())
                    targets = [restore_stmt_str(p) for p in parts[:-1]]
                    unrolled = [f"{tgt} = {final_val}" for tgt in reversed(targets)]
                    return "\n".join(unrolled)

        ternary_m = re.match(r'^(return\s+)?(.+?)\s*\?\s*(.+?)\s*:\s*(.+)$', stmt_masked)
        if ternary_m and not is_call:
            ret_prefix = "return " if ternary_m.group(1) else ""
            cond = translate_tokens(CTokenizer(restore_stmt_str(ternary_m.group(2))).get_tokens())
            true_v = translate_tokens(CTokenizer(restore_stmt_str(ternary_m.group(3))).get_tokens())
            false_v = translate_tokens(CTokenizer(restore_stmt_str(ternary_m.group(4))).get_tokens())
            return f"if ({cond}) {{\n    {ret_prefix}{true_v}\n}} else {{\n    {ret_prefix}{false_v}\n}}"

        if stmt.startswith("return"):
            parts = stmt.split(maxsplit=1)
            if len(parts) > 1:
                val = translate_tokens(CTokenizer(parts[1]).get_tokens())
                return f"return {val}"
            return "return"

        if stmt.startswith("goto "):
            return stmt

        # Multi-variable declarations
        if "," in stmt and "=" in stmt and "(" not in stmt:
            first_part = stmt.split(",")[0].strip()
            is_type_decl = bool(re.match(r'^(?:const\s+)?([a-zA-Z_][a-zA-Z0-9_]*|\b(?:u8|u16|u32|u64|i8|i16|i32|i64|int|char|short|long|void)\b)\s*(\*+)?\s+[a-zA-Z_][a-zA-Z0-9_]*\s*=', first_part))
            if is_type_decl:
                decl_match = re.match(r'^(?:const\s+)?([a-zA-Z_][a-zA-Z0-9_\s\*]+?)\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(.+)$', first_part)
                if decl_match:
                    raw_type = clean_type(decl_match.group(1))
                    subbed = re.sub(r'\{([^}]+)\}', lambda m: m.group(0).replace(',', '§'), stmt)
                    parts = subbed.split(",")
                    res_decls = []
                    for p in parts:
                        sub = p.replace('§', ',').strip()
                        m_sub = re.match(r'^([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(.+)$', sub)
                        if m_sub:
                            sname = m_sub.group(1)
                            sval_raw = m_sub.group(2).strip()
                            if sval_raw.startswith("{") and sval_raw.endswith("}"):
                                args = sval_raw[1:-1].strip()
                                sval = f"{raw_type}({args})"
                            else:
                                sval = translate_tokens(CTokenizer(sval_raw).get_tokens())
                            res_decls.append(f"{sname}: {raw_type} = {sval}")
                        else:
                            m_full = re.match(r'^(?:const\s+)?([a-zA-Z_][a-zA-Z0-9_\s\*]+?)\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(.+)$', sub)
                            if m_full:
                                sname = m_full.group(2)
                                sval_raw = m_full.group(3).strip()
                                if sval_raw.startswith("{") and sval_raw.endswith("}"):
                                    args = sval_raw[1:-1].strip()
                                    sval = f"{raw_type}({args})"
                                else:
                                    sval = translate_tokens(CTokenizer(sval_raw).get_tokens())
                            res_decls.append(f"{sname}: {raw_type} = {sval}")
                    return "\n".join(res_decls)

        arr_match = re.match(r'^(?:const\s+)?([a-zA-Z_][a-zA-Z0-9_\s\*]+?)\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\[\s*([^\]]+)\s*\]$', stmt)
        if arr_match:
            raw_type = clean_type(arr_match.group(1))
            arr_name = arr_match.group(2)
            return f"{arr_name}: *{raw_type} = 0 as *{raw_type}"

        decl_eq = re.match(r'^(?:const\s+)?([a-zA-Z_][a-zA-Z0-9_\s\*]+?)\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(.+)$', stmt)
        if decl_eq:
            raw_type = decl_eq.group(1).strip()
            name = decl_eq.group(2).strip()
            val_raw = decl_eq.group(3).strip()
            if not raw_type.startswith("return") and raw_type not in ("else", "goto"):
                stype = clean_type(raw_type)
                if val_raw.startswith("{") and val_raw.endswith("}"):
                    args = val_raw[1:-1].strip()
                    val = f"{stype}({args})"
                else:
                    val = translate_tokens(CTokenizer(val_raw).get_tokens())
                return f"{name}: {stype} = {val}"

        decl_uninit = re.match(r'^(?:const\s+)?([a-zA-Z_][a-zA-Z0-9_\s\*]+?)\s+([a-zA-Z_][a-zA-Z0-9_]*)$', stmt)
        if decl_uninit:
            raw_type = decl_uninit.group(1).strip()
            name = decl_uninit.group(2).strip()
            if raw_type not in ("return", "break", "continue", "else", "goto"):
                stype = clean_type(raw_type)
                zero_val = "0 as *none" if stype.startswith("*") else "0"
                return f"{name}: {stype} = {zero_val}"

        return translate_tokens(CTokenizer(stmt).get_tokens())


def determine_output_path(input_file: Path, requested_out: Optional[str]) -> Path:
    input_dir = input_file.parent.resolve()
    base_stem = input_file.stem
    if requested_out:
        return Path(requested_out).resolve()
    clean_stem = re.sub(r'(_transpiled)+$', '', base_stem)
    return input_dir / f"{clean_stem}_transpiled.spike"


def main():
    parser = argparse.ArgumentParser(description="Robust C to Spike Transpiler")
    parser.add_argument("input_file", help="Path to input C source file")
    parser.add_argument("-o", "--output", help="Output .spike file path")
    parser.add_argument("-c", "--class-name", help="Enclosing class name (defaults to TitleCase filename stem)")
    parser.add_argument(
        "--follow-headers",
        action="store_true",
        default=False,
        help="Recursively resolve and inline local #include headers (default: disabled)"
    )
    parser.add_argument(
        "-k", "--kernel",
        action="store_true",
        default=False,
        help="Freestanding kernel mode: suppress standard libc headers"
    )
    args = parser.parse_args()

    input_path = Path(args.input_file).resolve()
    if not input_path.is_file():
        print(f"[-] Error: Input file '{args.input_file}' does not exist.", file=sys.stderr)
        sys.exit(1)

    with open(input_path, "r", encoding="utf-8", errors="replace") as f:
        raw_c = f.read()

    inferred_class_name = args.class_name or input_path.stem.replace("_", " ").title().replace(" ", "")

    resolver = HeaderResolver(input_path.parent, follow_headers=args.follow_headers, freestanding=args.kernel)
    resolved_c = resolver.resolve(raw_c)

    transpiler = C2Spike(
        class_name=inferred_class_name,
        c_decls=resolver.c_decls
    )
    spike_code = transpiler.transpile(resolved_c)

    out_path = determine_output_path(input_path, args.output)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(spike_code)

    print(f"[+] Successfully transpiled {input_path.name} -> {out_path.name} (Class: {inferred_class_name})")


if __name__ == "__main__":
    main()
