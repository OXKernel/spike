"""
compiler.py - Spike Language Compiler & C Transpiler
Supports user-space and freestanding kernel-mode compilation targets.
Supports calling external C functions via 'extern def', top-level 'c_decl', 
and scoped 'c_inline' blocks.
"""

from __future__ import annotations
import sys
from typing import Any, Dict, List, Optional, Set, Union


# ============================================================================
# 1. Lexer & Tokens
# ============================================================================

class TokenType:
    # Keywords
    CONST = "CONST"
    STRUCT = "STRUCT"
    CLASS = "CLASS"
    DEF = "DEF"
    STATIC = "STATIC"
    EXPORT = "EXPORT"
    EXTERN = "EXTERN"
    ASM = "ASM"
    C_INLINE = "C_INLINE"
    C_DECL = "C_DECL"
    AS = "AS"
    WHILE = "WHILE"
    IF = "IF"
    ELSE = "ELSE"
    RETURN = "RETURN"
    TRUE = "TRUE"
    FALSE = "FALSE"

    # Identifiers and Literals
    IDENTIFIER = "IDENTIFIER"
    INT_LITERAL = "INT_LITERAL"
    HEX_LITERAL = "HEX_LITERAL"
    STRING_LITERAL = "STRING_LITERAL"

    # Symbols and Operators
    LBRACE = "LBRACE"          # {
    RBRACE = "RBRACE"          # }
    LPAREN = "LPAREN"          # (
    RPAREN = "RPAREN"          # )
    COLON = "COLON"            # :
    SEMICOLON = "SEMICOLON"    # ;
    COMMA = "COMMA"            # ,
    DOT = "DOT"                # .
    ARROW = "ARROW"            # ->
    EQUALS = "EQUALS"          # =
    PLUS = "PLUS"              # +
    MINUS = "MINUS"            # -
    STAR = "STAR"              # *
    SLASH = "SLASH"            # /
    PERCENT = "PERCENT"        # %
    AMP = "AMP"                # &
    PIPE = "PIPE"              # |
    CARET = "CARET"            # ^
    BANG = "BANG"              # !
    LT = "LT"                  # <
    GT = "GT"                  # >
    LE = "LE"                  # <=
    GE = "GE"                  # >=
    EQ = "EQ"                  # ==
    NE = "NE"                  # !=

    EOF = "EOF"


KEYWORDS = {
    "const": TokenType.CONST,
    "struct": TokenType.STRUCT,
    "class": TokenType.CLASS,
    "def": TokenType.DEF,
    "static": TokenType.STATIC,
    "export": TokenType.EXPORT,
    "extern": TokenType.EXTERN,
    "asm": TokenType.ASM,
    "c_inline": TokenType.C_INLINE,
    "c_decl": TokenType.C_DECL,
    "as": TokenType.AS,
    "while": TokenType.WHILE,
    "if": TokenType.IF,
    "else": TokenType.ELSE,
    "return": TokenType.RETURN,
    "True": TokenType.TRUE,
    "False": TokenType.FALSE,
}


class Token:
    def __init__(self, type_: str, value: Any, line: int, col: int):
        self.type = type_
        self.value = value
        self.line = line
        self.col = col

    def __repr__(self) -> str:
        return f"Token({self.type}, {repr(self.value)}, L{self.line}:C{self.col})"


class Lexer:
    def __init__(self, source: str):
        self.source = source
        self.pos = 0
        self.line = 1
        self.col = 1
        self.length = len(source)

    def _peek(self, offset: int = 0) -> str:
        idx = self.pos + offset
        if idx >= self.length:
            return ""
        return self.source[idx]

    def _advance(self) -> str:
        if self.pos >= self.length:
            return ""
        char = self.source[self.pos]
        self.pos += 1
        if char == "\n":
            self.line += 1
            self.col = 1
        else:
            self.col += 1
        return char

    def tokenize(self) -> List[Token]:
        tokens: List[Token] = []

        while self.pos < self.length:
            char = self._peek()

            # Whitespace
            if char in (" ", "\t", "\r", "\n"):
                self._advance()
                continue

            # Single-line Python comments (#)
            if char == "#":
                while self._peek() and self._peek() != "\n":
                    self._advance()
                continue

            # C-style comments (// and /* */)
            if char == "/" and self._peek(1) == "/":
                while self._peek() and self._peek() != "\n":
                    self._advance()
                continue
            if char == "/" and self._peek(1) == "*":
                self._advance()
                self._advance()
                while self._peek() and not (self._peek() == "*" and self._peek(1) == "/"):
                    self._advance()
                if self._peek():
                    self._advance()
                    self._advance()
                continue

            start_line, start_col = self.line, self.col

            # Hex numbers (0x...)
            if char == "0" and self._peek(1) in ("x", "X"):
                self._advance()
                self._advance()
                num_str = "0x"
                while self._peek() in "0123456789abcdefABCDEF":
                    num_str += self._advance()
                tokens.append(Token(TokenType.HEX_LITERAL, int(num_str, 16), start_line, start_col))
                continue

            # Decimal numbers
            if char.isdigit():
                num_str = ""
                while self._peek().isdigit():
                    num_str += self._advance()
                tokens.append(Token(TokenType.INT_LITERAL, int(num_str), start_line, start_col))
                continue

            # Identifiers and Keywords
            if char.isalpha() or char == "_":
                ident = ""
                while self._peek().isalnum() or self._peek() == "_":
                    ident += self._advance()
                token_type = KEYWORDS.get(ident, TokenType.IDENTIFIER)
                tokens.append(Token(token_type, ident, start_line, start_col))
                continue

            # String literals
            if char in ('"', "'"):
                quote_type = self._advance()
                str_val = ""
                while self._peek() and self._peek() != quote_type:
                    if self._peek() == "\\":
                        self._advance()
                        str_val += "\\" + self._advance()
                    else:
                        str_val += self._advance()
                if self._peek() == quote_type:
                    self._advance()
                tokens.append(Token(TokenType.STRING_LITERAL, str_val, start_line, start_col))
                continue

            # Multi-character Operators
            if char == "-" and self._peek(1) == ">":
                self._advance()
                self._advance()
                tokens.append(Token(TokenType.ARROW, "->", start_line, start_col))
                continue
            if char == "=" and self._peek(1) == "=":
                self._advance()
                self._advance()
                tokens.append(Token(TokenType.EQ, "==", start_line, start_col))
                continue
            if char == "!" and self._peek(1) == "=":
                self._advance()
                self._advance()
                tokens.append(Token(TokenType.NE, "!=", start_line, start_col))
                continue
            if char == "<" and self._peek(1) == "=":
                self._advance()
                self._advance()
                tokens.append(Token(TokenType.LE, "<=", start_line, start_col))
                continue
            if char == ">" and self._peek(1) == "=":
                self._advance()
                self._advance()
                tokens.append(Token(TokenType.GE, ">=", start_line, start_col))
                continue

            single_char_tokens = {
                "{": TokenType.LBRACE,
                "}": TokenType.RBRACE,
                "(": TokenType.LPAREN,
                ")": TokenType.RPAREN,
                ":": TokenType.COLON,
                ";": TokenType.SEMICOLON,
                ",": TokenType.COMMA,
                ".": TokenType.DOT,
                "=": TokenType.EQUALS,
                "+": TokenType.PLUS,
                "-": TokenType.MINUS,
                "*": TokenType.STAR,
                "/": TokenType.SLASH,
                "%": TokenType.PERCENT,
                "&": TokenType.AMP,
                "|": TokenType.PIPE,
                "^": TokenType.CARET,
                "!": TokenType.BANG,
                "<": TokenType.LT,
                ">": TokenType.GT,
            }

            if char in single_char_tokens:
                self._advance()
                tokens.append(Token(single_char_tokens[char], char, start_line, start_col))
                continue

            self._advance()

        tokens.append(Token(TokenType.EOF, None, self.line, self.col))
        return tokens


# ============================================================================
# 2. Abstract Syntax Tree (AST) Nodes
# ============================================================================

class ASTNode:
    def __init__(self, line: int = 0, col: int = 0):
        self.line = line
        self.col = col

class ProgramNode(ASTNode):
    def __init__(self, declarations: List[ASTNode], line: int = 0, col: int = 0):
        super().__init__(line, col)
        self.declarations = declarations

class ExternDefNode(ASTNode):
    def __init__(self, name: str, params: List[tuple[str, str]], return_type: str, line: int = 0, col: int = 0):
        super().__init__(line, col)
        self.name = name
        self.params = params
        self.return_type = return_type

class CDeclBlockNode(ASTNode):
    def __init__(self, raw_lines: List[str], line: int = 0, col: int = 0):
        super().__init__(line, col)
        self.raw_lines = raw_lines

class CInlineBlockNode(ASTNode):
    def __init__(self, raw_lines: List[str], line: int = 0, col: int = 0):
        super().__init__(line, col)
        self.raw_lines = raw_lines

class ConstDeclNode(ASTNode):
    def __init__(self, name: str, var_type: str, value_expr: ASTNode, line: int = 0, col: int = 0):
        super().__init__(line, col)
        self.name = name
        self.var_type = var_type
        self.value_expr = value_expr

class StructFieldNode(ASTNode):
    def __init__(self, name: str, field_type: str, line: int = 0, col: int = 0):
        super().__init__(line, col)
        self.name = name
        self.field_type = field_type

class StructDeclNode(ASTNode):
    def __init__(self, name: str, fields: List[StructFieldNode], line: int = 0, col: int = 0):
        super().__init__(line, col)
        self.name = name
        self.fields = fields

class MethodDeclNode(ASTNode):
    def __init__(self, name: str, params: List[tuple[str, str]], return_type: str,
                 body: List[ASTNode], is_static: bool = False, is_export: bool = False,
                 line: int = 0, col: int = 0):
        super().__init__(line, col)
        self.name = name
        self.params = params
        self.return_type = return_type
        self.body = body
        self.is_static = is_static
        self.is_export = is_export

class ClassDeclNode(ASTNode):
    def __init__(self, name: str, methods: List[MethodDeclNode], line: int = 0, col: int = 0):
        super().__init__(line, col)
        self.name = name
        self.methods = methods

class VarDeclNode(ASTNode):
    def __init__(self, name: str, var_type: Optional[str], value_expr: ASTNode, line: int = 0, col: int = 0):
        super().__init__(line, col)
        self.name = name
        self.var_type = var_type
        self.value_expr = value_expr

class AssignStmtNode(ASTNode):
    def __init__(self, target_expr: ASTNode, value_expr: ASTNode, line: int = 0, col: int = 0):
        super().__init__(line, col)
        self.target_expr = target_expr
        self.value_expr = value_expr

class AsmBlockNode(ASTNode):
    def __init__(self, instructions: List[str], line: int = 0, col: int = 0):
        super().__init__(line, col)
        self.instructions = instructions

class WhileStmtNode(ASTNode):
    def __init__(self, condition: ASTNode, body: List[ASTNode], line: int = 0, col: int = 0):
        super().__init__(line, col)
        self.condition = condition
        self.body = body

class IfStmtNode(ASTNode):
    def __init__(self, condition: ASTNode, then_body: List[ASTNode],
                 else_body: Optional[List[ASTNode]] = None, line: int = 0, col: int = 0):
        super().__init__(line, col)
        self.condition = condition
        self.then_body = then_body
        self.else_body = else_body

class ReturnStmtNode(ASTNode):
    def __init__(self, value_expr: Optional[ASTNode], line: int = 0, col: int = 0):
        super().__init__(line, col)
        self.value_expr = value_expr

class ExprStmtNode(ASTNode):
    def __init__(self, expr: ASTNode, line: int = 0, col: int = 0):
        super().__init__(line, col)
        self.expr = expr

class BinaryOpNode(ASTNode):
    def __init__(self, left: ASTNode, op: str, right: ASTNode, line: int = 0, col: int = 0):
        super().__init__(line, col)
        self.left = left
        self.op = op
        self.right = right

class UnaryOpNode(ASTNode):
    def __init__(self, op: str, operand: ASTNode, line: int = 0, col: int = 0):
        super().__init__(line, col)
        self.op = op
        self.operand = operand

class CastExprNode(ASTNode):
    def __init__(self, expr: ASTNode, target_type: str, line: int = 0, col: int = 0):
        super().__init__(line, col)
        self.expr = expr
        self.target_type = target_type

class MemberAccessNode(ASTNode):
    def __init__(self, target: ASTNode, member: str, line: int = 0, col: int = 0):
        super().__init__(line, col)
        self.target = target
        self.member = member

class CallExprNode(ASTNode):
    def __init__(self, callee: ASTNode, args: List[ASTNode], line: int = 0, col: int = 0):
        super().__init__(line, col)
        self.callee = callee
        self.args = args

class IdentifierNode(ASTNode):
    def __init__(self, name: str, line: int = 0, col: int = 0):
        super().__init__(line, col)
        self.name = name

class LiteralNode(ASTNode):
    def __init__(self, value: Any, raw_type: str, line: int = 0, col: int = 0):
        super().__init__(line, col)
        self.value = value
        self.raw_type = raw_type


# ============================================================================
# 3. Recursive Descent Parser
# ============================================================================

class Parser:
    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.pos = 0

    def _peek(self, offset: int = 0) -> Token:
        idx = self.pos + offset
        if idx >= len(self.tokens):
            return self.tokens[-1]
        return self.tokens[idx]

    def _check(self, type_: str) -> bool:
        return self._peek().type == type_

    def _match(self, *types: str) -> bool:
        if self._peek().type in types:
            self.pos += 1
            return True
        return False

    def _consume(self, type_: str, error_msg: str = "") -> Token:
        tok = self._peek()
        if tok.type != type_:
            msg = error_msg or f"Expected token {type_}, got {tok.type} ('{tok.value}') at L{tok.line}:C{tok.col}"
            raise SyntaxError(msg)
        self.pos += 1
        return tok

    def parse(self) -> ProgramNode:
        declarations: List[ASTNode] = []
        start_tok = self._peek()
        while not self._check(TokenType.EOF):
            declarations.append(self._parse_top_level_declaration())
        return ProgramNode(declarations, line=start_tok.line, col=start_tok.col)

    def _parse_top_level_declaration(self) -> ASTNode:
        if self._check(TokenType.EXTERN):
            return self._parse_extern_declaration()
        elif self._check(TokenType.C_DECL):
            return self._parse_c_decl_block()
        elif self._check(TokenType.CONST):
            return self._parse_const_declaration()
        elif self._check(TokenType.STRUCT):
            return self._parse_struct_declaration()
        elif self._check(TokenType.CLASS):
            return self._parse_class_declaration()
        else:
            tok = self._peek()
            raise SyntaxError(f"Unexpected top-level token: {tok.type} ('{tok.value}') at L{tok.line}:C{tok.col}")

    def _parse_extern_declaration(self) -> ExternDefNode:
        start_tok = self._consume(TokenType.EXTERN)
        self._consume(TokenType.DEF)
        name_tok = self._consume(TokenType.IDENTIFIER)
        self._consume(TokenType.LPAREN)

        params: List[tuple[str, str]] = []
        if not self._check(TokenType.RPAREN):
            while True:
                pname = self._consume(TokenType.IDENTIFIER).value
                self._consume(TokenType.COLON)
                ptype = self._parse_type()
                params.append((pname, ptype))
                if not self._match(TokenType.COMMA):
                    break

        self._consume(TokenType.RPAREN)

        return_type = "none"
        if self._match(TokenType.COLON) or self._match(TokenType.ARROW):
            return_type = self._parse_type()

        self._match(TokenType.SEMICOLON)
        return ExternDefNode(name_tok.value, params, return_type, line=start_tok.line, col=start_tok.col)

    def _parse_c_decl_block(self) -> CDeclBlockNode:
        start_tok = self._consume(TokenType.C_DECL)
        self._consume(TokenType.LBRACE)
        lines: List[str] = []

        while not self._check(TokenType.RBRACE) and not self._check(TokenType.EOF):
            token = self._consume(TokenType.STRING_LITERAL)
            lines.append(str(token.value))
            self._match(TokenType.SEMICOLON)

        self._consume(TokenType.RBRACE)
        return CDeclBlockNode(lines, line=start_tok.line, col=start_tok.col)

    def _parse_c_inline_block(self) -> CInlineBlockNode:
        start_tok = self._consume(TokenType.C_INLINE)
        self._consume(TokenType.LBRACE)
        lines: List[str] = []

        while not self._check(TokenType.RBRACE) and not self._check(TokenType.EOF):
            token = self._consume(TokenType.STRING_LITERAL)
            lines.append(str(token.value))
            self._match(TokenType.SEMICOLON)

        self._consume(TokenType.RBRACE)
        return CInlineBlockNode(lines, line=start_tok.line, col=start_tok.col)

    def _parse_const_declaration(self) -> ConstDeclNode:
        start_tok = self._consume(TokenType.CONST)
        name_tok = self._consume(TokenType.IDENTIFIER)
        self._consume(TokenType.COLON)
        var_type = self._parse_type()
        self._consume(TokenType.EQUALS)
        value_expr = self._parse_expression()
        self._match(TokenType.SEMICOLON)
        return ConstDeclNode(name_tok.value, var_type, value_expr, line=start_tok.line, col=start_tok.col)

    def _parse_struct_declaration(self) -> StructDeclNode:
        start_tok = self._consume(TokenType.STRUCT)
        name_tok = self._consume(TokenType.IDENTIFIER)
        self._consume(TokenType.LBRACE)
        fields: List[StructFieldNode] = []

        while not self._check(TokenType.RBRACE) and not self._check(TokenType.EOF):
            fname_tok = self._consume(TokenType.IDENTIFIER)
            self._consume(TokenType.COLON)
            ftype = self._parse_type()
            self._match(TokenType.COMMA)
            self._match(TokenType.SEMICOLON)
            fields.append(StructFieldNode(fname_tok.value, ftype, line=fname_tok.line, col=fname_tok.col))

        self._consume(TokenType.RBRACE)
        return StructDeclNode(name_tok.value, fields, line=start_tok.line, col=start_tok.col)

    def _parse_class_declaration(self) -> ClassDeclNode:
        start_tok = self._consume(TokenType.CLASS)
        name_tok = self._consume(TokenType.IDENTIFIER)
        self._consume(TokenType.LBRACE)
        methods: List[MethodDeclNode] = []

        while not self._check(TokenType.RBRACE) and not self._check(TokenType.EOF):
            is_export = self._match(TokenType.EXPORT)
            is_static = self._match(TokenType.STATIC)
            if not is_export and self._match(TokenType.EXPORT):
                is_export = True

            methods.append(self._parse_method_declaration(is_static, is_export))

        self._consume(TokenType.RBRACE)
        return ClassDeclNode(name_tok.value, methods, line=start_tok.line, col=start_tok.col)

    def _parse_method_declaration(self, is_static: bool, is_export: bool) -> MethodDeclNode:
        start_tok = self._consume(TokenType.DEF)
        name_tok = self._consume(TokenType.IDENTIFIER)
        self._consume(TokenType.LPAREN)

        params: List[tuple[str, str]] = []
        if not self._check(TokenType.RPAREN):
            while True:
                pname = self._consume(TokenType.IDENTIFIER).value
                self._consume(TokenType.COLON)
                ptype = self._parse_type()
                params.append((pname, ptype))
                if not self._match(TokenType.COMMA):
                    break

        self._consume(TokenType.RPAREN)

        return_type = "none"
        if self._match(TokenType.COLON) or self._match(TokenType.ARROW):
            return_type = self._parse_type()

        self._consume(TokenType.LBRACE)
        body = self._parse_block()
        self._consume(TokenType.RBRACE)

        return MethodDeclNode(
            name_tok.value, params, return_type, body,
            is_static=is_static, is_export=is_export,
            line=start_tok.line, col=start_tok.col
        )

    def _parse_block(self) -> List[ASTNode]:
        statements: List[ASTNode] = []
        while not self._check(TokenType.RBRACE) and not self._check(TokenType.EOF):
            statements.append(self._parse_statement())
        return statements

    def _parse_statement(self) -> ASTNode:
        if self._check(TokenType.ASM):
            return self._parse_asm_statement()
        elif self._check(TokenType.C_INLINE):
            return self._parse_c_inline_block()
        elif self._check(TokenType.WHILE):
            return self._parse_while_statement()
        elif self._check(TokenType.IF):
            return self._parse_if_statement()
        elif self._check(TokenType.RETURN):
            return self._parse_return_statement()
        
        # Explicit Type Declaration: `name: Type = expr;`
        elif self._check(TokenType.IDENTIFIER) and self._peek(1).type == TokenType.COLON:
            name_tok = self._consume(TokenType.IDENTIFIER)
            self._consume(TokenType.COLON)
            var_type = self._parse_type()
            self._consume(TokenType.EQUALS)
            val = self._parse_expression()
            self._match(TokenType.SEMICOLON)
            return VarDeclNode(name_tok.value, var_type, val, line=name_tok.line, col=name_tok.col)

        # Assignment / Expression Statement
        else:
            expr = self._parse_expression()
            if self._match(TokenType.EQUALS):
                val = self._parse_expression()
                self._match(TokenType.SEMICOLON)
                return AssignStmtNode(expr, val, line=expr.line, col=expr.col)
            self._match(TokenType.SEMICOLON)
            return ExprStmtNode(expr, line=expr.line, col=expr.col)

    def _parse_asm_statement(self) -> AsmBlockNode:
        start_tok = self._consume(TokenType.ASM)
        self._consume(TokenType.LBRACE)
        instructions: List[str] = []

        while not self._check(TokenType.RBRACE) and not self._check(TokenType.EOF):
            token = self._consume(TokenType.STRING_LITERAL)
            raw_text = str(token.value)
            for part in raw_text.split(";"):
                clean = part.strip()
                if clean:
                    instructions.append(clean)
            self._match(TokenType.SEMICOLON)

        self._consume(TokenType.RBRACE)
        return AsmBlockNode(instructions, line=start_tok.line, col=start_tok.col)

    def _parse_while_statement(self) -> WhileStmtNode:
        start_tok = self._consume(TokenType.WHILE)
        condition = self._parse_expression()
        self._consume(TokenType.LBRACE)
        body = self._parse_block()
        self._consume(TokenType.RBRACE)
        return WhileStmtNode(condition, body, line=start_tok.line, col=start_tok.col)

    def _parse_if_statement(self) -> IfStmtNode:
        start_tok = self._consume(TokenType.IF)
        cond = self._parse_expression()
        self._consume(TokenType.LBRACE)
        then_body = self._parse_block()
        self._consume(TokenType.RBRACE)

        else_body = None
        if self._match(TokenType.ELSE):
            self._consume(TokenType.LBRACE)
            else_body = self._parse_block()
            self._consume(TokenType.RBRACE)

        return IfStmtNode(cond, then_body, else_body, line=start_tok.line, col=start_tok.col)

    def _parse_return_statement(self) -> ReturnStmtNode:
        start_tok = self._consume(TokenType.RETURN)
        val = None
        if not self._check(TokenType.SEMICOLON) and not self._check(TokenType.RBRACE):
            val = self._parse_expression()
        self._match(TokenType.SEMICOLON)
        return ReturnStmtNode(val, line=start_tok.line, col=start_tok.col)

    def _parse_type(self) -> str:
        if self._match(TokenType.STAR):
            qualifier = ""
            if self._peek().type == TokenType.IDENTIFIER and self._peek().value in ("mut", "const"):
                qualifier = self._advance_token().value + " "
            base_type = self._parse_type()
            return f"*{qualifier}{base_type}"

        tok = self._consume(TokenType.IDENTIFIER)
        return tok.value

    def _advance_token(self) -> Token:
        tok = self._peek()
        self.pos += 1
        return tok

    def _parse_expression(self) -> ASTNode:
        return self._parse_cast_expression()

    def _parse_cast_expression(self) -> ASTNode:
        expr = self._parse_comparison()
        while self._match(TokenType.AS):
            target_type = self._parse_type()
            expr = CastExprNode(expr, target_type, line=expr.line, col=expr.col)
        return expr

    def _parse_comparison(self) -> ASTNode:
        expr = self._parse_additive()
        while self._peek().type in (TokenType.LT, TokenType.GT, TokenType.LE, TokenType.GE, TokenType.EQ, TokenType.NE):
            op_tok = self._advance_token()
            right = self._parse_additive()
            expr = BinaryOpNode(expr, op_tok.value, right, line=expr.line, col=expr.col)
        return expr

    def _parse_additive(self) -> ASTNode:
        expr = self._parse_multiplicative()
        while self._peek().type in (TokenType.PLUS, TokenType.MINUS):
            op_tok = self._advance_token()
            right = self._parse_multiplicative()
            expr = BinaryOpNode(expr, op_tok.value, right, line=expr.line, col=expr.col)
        return expr

    def _parse_multiplicative(self) -> ASTNode:
        expr = self._parse_unary()
        while self._peek().type in (TokenType.STAR, TokenType.SLASH, TokenType.PERCENT):
            op_tok = self._advance_token()
            right = self._parse_unary()
            expr = BinaryOpNode(expr, op_tok.value, right, line=expr.line, col=expr.col)
        return expr

    def _parse_unary(self) -> ASTNode:
        if self._peek().type in (TokenType.STAR, TokenType.BANG, TokenType.MINUS):
            op_tok = self._advance_token()
            operand = self._parse_unary()
            return UnaryOpNode(op_tok.value, operand, line=op_tok.line, col=op_tok.col)
        return self._parse_postfix()

    def _parse_postfix(self) -> ASTNode:
        expr = self._parse_primary()
        while True:
            if self._match(TokenType.DOT):
                member_tok = self._consume(TokenType.IDENTIFIER)
                expr = MemberAccessNode(expr, member_tok.value, line=expr.line, col=expr.col)
            elif self._match(TokenType.LPAREN):
                args: List[ASTNode] = []
                if not self._check(TokenType.RPAREN):
                    while True:
                        args.append(self._parse_expression())
                        if not self._match(TokenType.COMMA):
                            break
                self._consume(TokenType.RPAREN)
                expr = CallExprNode(expr, args, line=expr.line, col=expr.col)
            else:
                break
        return expr

    def _parse_primary(self) -> ASTNode:
        tok = self._peek()
        if self._match(TokenType.INT_LITERAL, TokenType.HEX_LITERAL):
            return LiteralNode(tok.value, "int", line=tok.line, col=tok.col)
        elif self._match(TokenType.STRING_LITERAL):
            return LiteralNode(tok.value, "string", line=tok.line, col=tok.col)
        elif self._match(TokenType.TRUE):
            return LiteralNode(True, "bool", line=tok.line, col=tok.col)
        elif self._match(TokenType.FALSE):
            return LiteralNode(False, "bool", line=tok.line, col=tok.col)
        elif self._match(TokenType.IDENTIFIER):
            return IdentifierNode(tok.value, line=tok.line, col=tok.col)
        elif self._match(TokenType.LPAREN):
            inner = self._parse_expression()
            self._consume(TokenType.RPAREN)
            return inner
        else:
            raise SyntaxError(f"Unexpected token in expression: {tok.type} ('{tok.value}') at L{tok.line}:C{tok.col}")


# ============================================================================
# 4. C Code Generator
# ============================================================================

class CCodeGenerator:
    TYPE_MAP = {
        "u8": "uint8_t",
        "u16": "uint16_t",
        "u32": "uint32_t",
        "u64": "uint64_t",
        "i8": "int8_t",
        "i16": "int16_t",
        "i32": "int32_t",
        "i64": "int64_t",
        "bool": "bool",
        "none": "void",
        "void": "void",
        "noreturn": "void",
    }

    def __init__(self, kernel_mode: bool = False):
        self.kernel_mode = kernel_mode
        self.output: List[str] = []
        self.indent_level = 0
        self.current_class: Optional[str] = None
        self.struct_types: Set[str] = set()
        self.class_types: Set[str] = set()
        self.extern_functions: Set[str] = set()
        
        # Scoped Symbol Tracking
        self.declared_symbols: Set[str] = set()
        self.symbol_types: Dict[str, str] = {}

    def _emit(self, line: str = ""):
        indent = "    " * self.indent_level
        self.output.append(f"{indent}{line}")

    def map_type(self, spike_type: Optional[str]) -> str:
        if not spike_type:
            return "void"

        spike_type = spike_type.strip()
        if spike_type.startswith("*"):
            clean = spike_type[1:].strip()
            is_const = clean.startswith("const")
            if is_const:
                clean = clean[5:].strip()
            elif clean.startswith("mut"):
                clean = clean[3:].strip()
            
            c_base = self.map_type(clean)
            return f"const {c_base}*" if is_const else f"{c_base}*"

        if spike_type in self.TYPE_MAP:
            return self.TYPE_MAP[spike_type]

        if spike_type in self.struct_types or spike_type in self.class_types:
            return f"struct {spike_type}"

        return spike_type

    def infer_type(self, node: ASTNode) -> Optional[str]:
        if isinstance(node, IdentifierNode):
            return self.symbol_types.get(node.name)
        if isinstance(node, CastExprNode):
            return node.target_type
        if isinstance(node, BinaryOpNode):
            left_type = self.infer_type(node.left)
            right_type = self.infer_type(node.right)
            if left_type and left_type.startswith("*"):
                return left_type
            if right_type and right_type.startswith("*"):
                return right_type
            return left_type or right_type
        if isinstance(node, UnaryOpNode):
            if node.op == "*":
                operand_type = self.infer_type(node.operand)
                if operand_type and operand_type.startswith("*"):
                    clean = operand_type[1:].strip()
                    if clean.startswith("mut") or clean.startswith("const"):
                        clean = clean.split(maxsplit=1)[1]
                    return clean
            return self.infer_type(node.operand)
        return None

    def is_pointer_type(self, node: ASTNode) -> bool:
        t = self.infer_type(node)
        return bool(t and t.strip().startswith("*"))

    def generate(self, root: ProgramNode) -> str:
        self.output.clear()

        # 1. Standard Header Directives
        if self.kernel_mode:
            self._emit("/* Generated by Spike Compiler - Standalone Kernel Mode */")
            self._emit("#include <stdint.h>")
            self._emit("#include <stddef.h>")
            self._emit("#include <stdbool.h>")
            self._emit("")
        else:
            self._emit("/* Generated by Spike Compiler - User Space */")
            self._emit('#include "spike_rt.h"')
            self._emit("#include <stdint.h>")
            self._emit("#include <stdbool.h>")
            self._emit("")

        # 2. Emit Top-Level c_decl Blocks (Verbatim C code, includes, macros)
        for decl in root.declarations:
            if isinstance(decl, CDeclBlockNode):
                for line in decl.raw_lines:
                    self._emit(line)
                self._emit("")

        # 3. Collect Structs, Classes & Extern Functions
        for decl in root.declarations:
            if isinstance(decl, StructDeclNode):
                self.struct_types.add(decl.name)
            elif isinstance(decl, ClassDeclNode):
                self.class_types.add(decl.name)
            elif isinstance(decl, ExternDefNode):
                self.extern_functions.add(decl.name)

        # 4. Forward Struct & Class Declarations
        for decl in root.declarations:
            if isinstance(decl, StructDeclNode):
                self._emit(f"struct {decl.name};")
            elif isinstance(decl, ClassDeclNode):
                self._emit(f"struct {decl.name} {{ int _dummy; }};")
        if self.struct_types or self.class_types:
            self._emit("")

        # 5. Emit 'extern def' Prototypes
        for decl in root.declarations:
            if isinstance(decl, ExternDefNode):
                self._visit(decl)
        if self.extern_functions:
            self._emit("")

        # 6. Generate All Other Top-Level Declarations
        for decl in root.declarations:
            if not isinstance(decl, (CDeclBlockNode, ExternDefNode)):
                self._visit(decl)
                self._emit("")

        return "\n".join(self.output)

    def _visit(self, node: ASTNode) -> str:
        method_name = f"_visit_{type(node).__name__}"
        visitor = getattr(self, method_name, self._generic_visit)
        return visitor(node)

    def _generic_visit(self, node: ASTNode):
        raise NotImplementedError(f"No visitor defined for AST node: {type(node).__name__}")

    def _visit_ExternDefNode(self, node: ExternDefNode):
        c_ret = self.map_type(node.return_type)
        params_list = []
        for pname, ptype in node.params:
            c_type = self.map_type(ptype)
            params_list.append(f"{c_type} {pname}")
        params_str = ", ".join(params_list) if params_list else "void"
        self._emit(f"extern {c_ret} {node.name}({params_str});")

    def _visit_ConstDeclNode(self, node: ConstDeclNode):
        c_type = self.map_type(node.var_type)
        val = self._visit(node.value_expr)
        self.symbol_types[node.name] = node.var_type
        self.declared_symbols.add(node.name)
        self._emit(f"static const {c_type} {node.name} = {val};")

    def _visit_StructDeclNode(self, node: StructDeclNode):
        self._emit(f"struct {node.name} {{")
        self.indent_level += 1
        for field in node.fields:
            c_type = self.map_type(field.field_type)
            self._emit(f"{c_type} {field.name};")
        self.indent_level -= 1
        self._emit("};")

    def _visit_ClassDeclNode(self, node: ClassDeclNode):
        self.current_class = node.name
        for method in node.methods:
            self._visit(method)
            self._emit("")
        self.current_class = None

    def _visit_MethodDeclNode(self, node: MethodDeclNode):
        self.declared_symbols.clear()
        self.symbol_types.clear()

        c_ret = self.map_type(node.return_type)
        if self.current_class:
            c_name = f"{self.current_class}_{node.name}"
            if node.name == "main" and (node.is_export or node.is_static):
                c_name = "main" if not self.kernel_mode else "kernel_main"
        else:
            c_name = node.name

        params_list = []
        for pname, ptype in node.params:
            c_type = self.map_type(ptype)
            params_list.append(f"{c_type} {pname}")
            self.declared_symbols.add(pname)
            self.symbol_types[pname] = ptype

        params_str = ", ".join(params_list) if params_list else "void"
        export_prefix = "" if (node.is_export or c_name == "kernel_main") else "static "

        self._emit(f"{export_prefix}{c_ret} {c_name}({params_str}) {{")
        self.indent_level += 1
        for stmt in node.body:
            self._visit(stmt)
        self.indent_level -= 1
        self._emit("}")

    def _visit_VarDeclNode(self, node: VarDeclNode):
        c_type = self.map_type(node.var_type)
        val = self._visit(node.value_expr)
        self.declared_symbols.add(node.name)
        if node.var_type:
            self.symbol_types[node.name] = node.var_type
        self._emit(f"{c_type} {node.name} = {val};")

    def _visit_AssignStmtNode(self, node: AssignStmtNode):
        # Strict enforcement: target identifier must be explicitly typed earlier
        if isinstance(node.target_expr, IdentifierNode):
            name = node.target_expr.name
            if name not in self.declared_symbols:
                loc = f"L{node.line}:C{node.col}" if node.line > 0 else "unknown location"
                raise SyntaxError(
                    f"Variable '{name}' assigned before explicit type declaration at {loc}.\n"
                    f"  Expected '{name}: <Type> = ...' instead of bare assignment."
                )

        target = self._visit(node.target_expr)
        val = self._visit(node.value_expr)
        self._emit(f"{target} = {val};")

    def _visit_ExprStmtNode(self, node: ExprStmtNode):
        expr_str = self._visit(node.expr)
        self._emit(f"{expr_str};")

    def _visit_CInlineBlockNode(self, node: CInlineBlockNode):
        for line in node.raw_lines:
            self._emit(line)

    def _visit_AsmBlockNode(self, node: AsmBlockNode):
        if not node.instructions:
            return

        self._emit("__asm__ __volatile__ (")
        self.indent_level += 1
        for inst in node.instructions:
            self._emit(f'"{inst}\\n\\t"')
        self.indent_level -= 1
        self._emit(");")

    def _visit_WhileStmtNode(self, node: WhileStmtNode):
        cond = self._visit(node.condition)
        self._emit(f"while ({cond}) {{")
        self.indent_level += 1
        for stmt in node.body:
            self._visit(stmt)
        self.indent_level -= 1
        self._emit("}")

    def _visit_IfStmtNode(self, node: IfStmtNode):
        cond = self._visit(node.condition)
        self._emit(f"if ({cond}) {{")
        self.indent_level += 1
        for stmt in node.then_body:
            self._visit(stmt)
        self.indent_level -= 1
        self._emit("}")

        if node.else_body:
            self._emit("else {")
            self.indent_level += 1
            for stmt in node.else_body:
                self._visit(stmt)
            self.indent_level -= 1
            self._emit("}")

    def _visit_ReturnStmtNode(self, node: ReturnStmtNode):
        if node.value_expr:
            val = self._visit(node.value_expr)
            self._emit(f"return {val};")
        else:
            self._emit("return;")

    # Expression Visitors
    def _visit_BinaryOpNode(self, node: BinaryOpNode) -> str:
        left = self._visit(node.left)
        right = self._visit(node.right)
        return f"({left} {node.op} {right})"

    def _visit_UnaryOpNode(self, node: UnaryOpNode) -> str:
        operand = self._visit(node.operand)
        return f"({node.op}{operand})"

    def _visit_CastExprNode(self, node: CastExprNode) -> str:
        target_c_type = self.map_type(node.target_type)
        expr_str = self._visit(node.expr)
        return f"(({target_c_type})({expr_str}))"

    def _visit_MemberAccessNode(self, node: MemberAccessNode) -> str:
        if isinstance(node.target, IdentifierNode):
            t_name = node.target.name
            if t_name in self.class_types:
                return f"{t_name}_{node.member}"
            var_type = self.symbol_types.get(t_name)
            if var_type and var_type in self.class_types:
                return f"{var_type}_{node.member}"

        target_str = self._visit(node.target)
        if self.is_pointer_type(node.target):
            return f"{target_str}->{node.member}"

        return f"{target_str}.{node.member}"

    def _visit_CallExprNode(self, node: CallExprNode) -> str:
        args_str = ", ".join(self._visit(a) for a in node.args)

        # 1. External C function call or global function
        if isinstance(node.callee, IdentifierNode) and node.callee.name in self.extern_functions:
            return f"{node.callee.name}({args_str})"

        # 2. Struct Constructor: StructName(...) -> (struct StructName){ ... }
        if isinstance(node.callee, IdentifierNode):
            c_name = node.callee.name
            if c_name in self.struct_types:
                return f"(struct {c_name}){{ {args_str} }}"
            if c_name in self.class_types:
                return f"(struct {c_name}){{ 0 }}"

        # 3. Class Method: ClassName.method(...) or instance.method(...)
        if isinstance(node.callee, MemberAccessNode):
            member = node.callee.member
            if isinstance(node.callee.target, IdentifierNode):
                tgt_name = node.callee.target.name
                if tgt_name in self.class_types:
                    return f"{tgt_name}_{member}({args_str})"
                var_type = self.symbol_types.get(tgt_name)
                if var_type in self.class_types:
                    return f"{var_type}_{member}({args_str})"

        callee_str = self._visit(node.callee)
        return f"{callee_str}({args_str})"

    def _visit_IdentifierNode(self, node: IdentifierNode) -> str:
        return node.name

    def _visit_LiteralNode(self, node: LiteralNode) -> str:
        if node.raw_type == "string":
            return f'"{node.value}"'
        elif node.raw_type == "bool":
            return "true" if node.value else "false"
        elif isinstance(node.value, int):
            return hex(node.value) if node.value > 9 else str(node.value)
        return str(node.value)


# ============================================================================
# 5. Compiler Interface
# ============================================================================

class Compiler:
    def __init__(self, kernel_mode: bool = False):
        self.kernel_mode = kernel_mode

    def compile(self, source_code: str) -> str:
        lexer = Lexer(source_code)
        tokens = lexer.tokenize()

        parser = Parser(tokens)
        ast_root = parser.parse()

        generator = CCodeGenerator(kernel_mode=self.kernel_mode)
        c_code = generator.generate(ast_root)

        return c_code
