"""
browserbot/agents/code_generator/validator.py — Step 4.2: AST DSL Validator.

Implements static analysis validation of LLM-generated Playwright code.
Ensures the generated statements match the approved Playwright DSL and
rejects any dangerous, external, or arbitrary Python commands.
"""

from __future__ import annotations

import ast
from typing import Any

from browserbot.logging import get_logger

log = get_logger(__name__)

# The set of permitted method names in the Playwright DSL
APPROVED_METHODS = {
    # Page methods
    "goto",
    "wait_for_selector",
    "wait_for_timeout",
    "locator",
    "get_by_role",
    "get_by_label",
    "get_by_placeholder",
    "get_by_text",
    "get_by_test_id",
    # Locator methods and helpers
    "fill",
    "click",
    "press",
    "text_content",
    "inner_text",
    "first",
    "nth",
}

# Explicitly forbidden builtin functions / globals
FORBIDDEN_CALLS = {
    "eval",
    "exec",
    "open",
    "__import__",
    "globals",
    "locals",
    "getattr",
    "setattr",
    "delattr",
    "hasattr",
    "compile",
    "print",
    "input",
}


class DSLValidationError(ValueError):
    """Raised when generated code violates the DSL or security invariants."""


def _get_call_attribute_names(node: ast.expr) -> list[str]:
    """
    Recursively extract the attribute methods called in a chain.
    E.g. `page.locator(...).click(...)` -> returns ['page', 'locator', 'click']
    """
    if isinstance(node, ast.Name):
        return [node.id]
    elif isinstance(node, ast.Attribute):
        return _get_call_attribute_names(node.value) + [node.attr]
    elif isinstance(node, ast.Call):
        return _get_call_attribute_names(node.func)
    elif isinstance(node, ast.Await):
        return _get_call_attribute_names(node.value)
    return []


class DSLSecurityVisitor(ast.NodeVisitor):
    """
    AST Visitor that walks the parsed code to check security invariants and
    enforce the approved Playwright DSL.
    """

    def __init__(self, allowed_variables: set[str] | None = None) -> None:
        # Variables that are legally in scope or created via assignment
        self.allowed_variables = allowed_variables or set()
        # Always allow 'page' as the entry point
        self.allowed_variables.add("page")
        self.allowed_variables.add("resolve_locator")
        self.allowed_variables.add("resilient_click")
        self.allowed_variables.add("resilient_fill")
        self.errors: list[str] = []

    def visit_Import(self, node: ast.Import) -> None:
        self.errors.append("Imports are strictly forbidden in generated body (line %d)" % node.lineno)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        self.errors.append("Imports are strictly forbidden in generated body (line %d)" % node.lineno)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.errors.append("Function definitions are forbidden in generated body (line %d)" % node.lineno)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.errors.append("Function definitions are forbidden in generated body (line %d)" % node.lineno)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.errors.append("Class definitions are forbidden in generated body (line %d)" % node.lineno)

    def visit_For(self, node: ast.For) -> None:
        self.errors.append("Loops (for) are forbidden in generated body (line %d)" % node.lineno)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self.errors.append("Loops (async for) are forbidden in generated body (line %d)" % node.lineno)

    def visit_While(self, node: ast.While) -> None:
        self.errors.append("Loops (while) are forbidden in generated body (line %d)" % node.lineno)

    def visit_If(self, node: ast.If) -> None:
        self.errors.append("Conditional statements (if) are forbidden in generated body (line %d)" % node.lineno)

    def visit_Try(self, node: ast.Try) -> None:
        self.errors.append("Try-except blocks are forbidden in generated body (line %d)" % node.lineno)

    def visit_Raise(self, node: ast.Raise) -> None:
        self.errors.append("Raise statements are forbidden in generated body (line %d)" % node.lineno)

    def visit_Assign(self, node: ast.Assign) -> None:
        # Record newly assigned variable names so they can be referenced
        for target in node.targets:
            if isinstance(target, ast.Name):
                self.allowed_variables.add(target.id)
            elif isinstance(target, (ast.Tuple, ast.List)):
                for elt in target.elts:
                    if isinstance(elt, ast.Name):
                        self.allowed_variables.add(elt.id)
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load):
            if node.id not in self.allowed_variables:
                self.errors.append(f"Use of unauthorized variable '{node.id}' (line {node.lineno})")

    def visit_Call(self, node: ast.Call) -> None:
        # 1. Check for forbidden builtin/global function calls (eval, exec, etc.)
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
            if func_name in FORBIDDEN_CALLS:
                self.errors.append(f"Forbidden function call '{func_name}' is rejected (line {node.lineno})")
            elif func_name not in self.allowed_variables:
                self.errors.append(f"Call to unauthorized function/variable '{func_name}' (line {node.lineno})")

        # 2. Check Playwright method attribute calls (page.goto, locator.click, etc.)
        chain = _get_call_attribute_names(node)
        if chain:
            base = chain[0]
            # Ensure the call chain starts with a valid/assigned variable (e.g. page, or a locator variable)
            if base not in self.allowed_variables:
                self.errors.append(f"Call chain starts with unauthorized base name '{base}' (line {node.lineno})")

            # Check that every method in the call chain is in our approved list
            for method in chain[1:]:
                if method not in APPROVED_METHODS:
                    self.errors.append(
                        f"Playwright method '{method}' is not in the approved DSL (line {node.lineno})"
                    )

        self.generic_visit(node)


def validate_dsl(code: str, allowed_variables: set[str] | None = None) -> None:
    """
    Validate that the provided code block strictly matches the Playwright DSL
    and contains no unauthorized Python constructs.

    Args:
        code:              The raw Python code string to validate.
        allowed_variables: Additional variables (like parameters) permitted.

    Raises:
        DSLValidationError: If validation fails.
    """
    # Verify code parses as valid Python first
    try:
        root = ast.parse(code)
    except SyntaxError as syntax_err:
        raise DSLValidationError(
            f"Generated code is not syntactically valid Python: {syntax_err}"
        ) from syntax_err

    # Run security visitor checks
    visitor = DSLSecurityVisitor(allowed_variables=allowed_variables)
    visitor.visit(root)

    if visitor.errors:
        raise DSLValidationError(
            "DSL Validation Failed:\n" + "\n".join(f"  • {e}" for e in visitor.errors)
        )
    log.debug("DSL Validation passed successfully")
