#!/usr/bin/env python3
"""
B008 Refactor: Convert `Type = Depends(...)` to `Annotated[Type, Depends(...)]`
Using LibCST for safe AST-based transformation.
"""

from pathlib import Path

import libcst as cst


class DependsAnnotatedTransformer(cst.CSTTransformer):
    """
    Transforms `param: Type = Depends(...)` to `param: Annotated[Type, Depends(...)]`
    Handles proper typing imports and edge cases.
    """

    def __init__(self):
        super().__init__()
        self.has_annotated_import = False
        self.has_typing_import = False
        self.requires_annotated = False

    def visit_Import(self, node: cst.Import) -> bool | None:
        """Check if typing is already imported"""
        for alias in node.names:
            if alias.name.value == "typing":
                self.has_typing_import = True
                return False
        return True

    def visit_ImportFrom(self, node: cst.ImportFrom) -> bool | None:
        """Check for Annotated import from typing"""
        if node.module and node.module.value == "typing":
            for alias in node.names:
                if alias.name.value == "Annotated":
                    self.has_annotated_import = True
                # Track typing import
                self.has_typing_import = True
        return True

    def leave_Module(self, original_node: cst.Module, updated_node: cst.Module) -> cst.Module:
        """Add imports if needed"""
        if not self.requires_annotated:
            return updated_node

        # Check if Annotated is already imported
        if self.has_annotated_import:
            return updated_node

        # Find the first import section or add at top
        body = list(updated_node.body)

        # Find where to insert typing import
        insert_idx = 0
        for i, stmt in enumerate(body):
            if isinstance(stmt, cst.Import | cst.ImportFrom):
                insert_idx = i + 1
            elif isinstance(stmt, cst.SimpleStatementLine):
                # Check if it's just comments or docstring
                if not any(isinstance(s, cst.Expr) and isinstance(s.value, cst.SimpleString) for s in stmt.body):
                    insert_idx = i
                    break

        # Create the import statement
        if self.has_typing_import:
            # Add Annotated to existing typing import
            new_import = cst.ImportFrom(
                module=cst.Name("typing"),
                names=[cst.ImportAlias(name=cst.Name("Annotated"))],
            )
        else:
            new_import = cst.ImportFrom(
                module=cst.Name("typing"),
                names=[
                    cst.ImportAlias(name=cst.Name("Annotated")),
                    cst.ImportAlias(name=cst.Name("Depends")),
                ],
            )

        body.insert(insert_idx, cst.SimpleStatementLine(body=[new_import]))
        return updated_node.with_changes(body=body)

    def visit_AnnAssign(self, node: cst.AnnAssign) -> bool | None:
        """Track parameters with Depends defaults - AnnAssign is for variable annotations, not parameters"""
        return True

    def visit_Param(self, node: cst.Param) -> bool | None:
        """Check each parameter for Depends defaults"""
        if node.default is not None:
            # Check if default is a Depends call
            if isinstance(node.default, cst.Call):
                if isinstance(node.default.func, cst.Name) and node.default.func.value == "Depends":
                    self.requires_annotated = True
                elif isinstance(node.default.func, cst.Attribute):
                    attr = node.default.func
                    if isinstance(attr.value, cst.Name) and attr.value.value == "Depends":
                        self.requires_annotated = True
        return True

    def leave_Param(self, original_node: cst.Param, updated_node: cst.Param) -> cst.Param:
        """Transform parameter with Depends default to Annotated type"""
        if updated_node.default is not None:
            default = updated_node.default
            # Check if default is Depends(...)
            is_depends = False
            if isinstance(default, cst.Call):
                if isinstance(default.func, cst.Name) and default.func.value == "Depends":
                    is_depends = True
                elif isinstance(default.func, cst.Attribute):
                    attr = default.func
                    if isinstance(attr.value, cst.Name) and attr.value.value == "Depends":
                        is_depends = True

            if is_depends:
                # Check if already has Annotated with Depends inside
                if updated_node.annotation is not None:
                    ann = updated_node.annotation.annotation
                    if isinstance(ann, cst.Subscript) and isinstance(ann.value, cst.Name) and ann.value.value == "Annotated":
                        # Check if the inner slice contains the Depends
                        for element in ann.slice:
                            if isinstance(element, cst.SubscriptElement):
                                idx = element.slice
                                if isinstance(idx, cst.Index) and isinstance(idx.value, cst.Call):
                                    if isinstance(idx.value.func, cst.Name) and idx.value.func.value == "Depends":
                                        # Already properly annotated, skip
                                        return updated_node

                # Get the original type annotation
                if updated_node.annotation is not None:
                    type_annotation = updated_node.annotation.annotation
                    # Handle if it's already Annotated - extract the inner type
                    if (
                        isinstance(type_annotation, cst.Subscript)
                        and isinstance(type_annotation.value, cst.Name)
                        and type_annotation.value.value == "Annotated"
                    ):
                        # Extract the first slice element (the actual type)
                        for element in type_annotation.slice:
                            if isinstance(element, cst.SubscriptElement):
                                idx = element.slice
                                if isinstance(idx, cst.Index):
                                    type_annotation = idx.value
                                    break
                else:
                    # No type annotation, default to Any
                    type_annotation = cst.Name("Any")

                # Create Annotated[type, Depends(...)]
                new_annotation = cst.Subscript(
                    value=cst.Name("Annotated"),
                    slice=[
                        cst.SubscriptElement(slice=cst.Index(value=type_annotation)),
                        cst.SubscriptElement(slice=cst.Index(value=default.deep_clone())),
                    ],
                )

                # Return new param with Annotated annotation and KEEP the default
                return updated_node.with_changes(
                    annotation=cst.Annotation(annotation=new_annotation),
                    default=default,  # Keep the default!
                )

        return updated_node
        return updated_node


def transform_file(filepath: Path) -> bool:
    """Transform a single Python file"""
    try:
        source = filepath.read_text()
        module = cst.parse_module(source)
        transformer = DependsAnnotatedTransformer()
        new_module = module.visit(transformer)

        if new_module.code != source:
            filepath.write_text(new_module.code)
            return True
        return False
    except Exception as e:
        print(f"Error processing {filepath}: {e}")
        return False


def main():
    # Get all Python files in apps/ directory
    apps_dir = Path("apps")
    if not apps_dir.exists():
        print("apps directory not found")
        return

    python_files = list(apps_dir.rglob("*.py"))
    print(f"Found {len(python_files)} Python files in apps/")

    transformed = 0
    for filepath in python_files:
        if transform_file(filepath):
            print(f"Transformed: {filepath}")
            transformed += 1

    print(f"\nTransformed {transformed} files")


if __name__ == "__main__":
    main()
