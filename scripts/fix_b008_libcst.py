#!/usr/bin/env python3
"""
Fix B008: Replace `param: Type = Depends(...)` with `param: Annotated[Type, Depends(...)]`
Using LibCST for accurate AST-based transformation.
Only fixes parameters that are safe to fix (last in chain or all subsequent have defaults).
"""

import libcst as cst
from pathlib import Path
import subprocess


class B008Transformer(cst.CSTTransformer):
    """Transforms function parameters with Depends defaults to Annotated form."""
    
    def __init__(self):
        super().__init__()
        self.changes = 0
        self.has_annotated_import = False
        
    def visit_Module(self, node):
        """Check if Annotated is already imported."""
        for stmt in node.body:
            if isinstance(stmt, cst.SimpleStatementLine):
                for small_stmt in stmt.body:
                    if isinstance(small_stmt, cst.ImportFrom):
                        if small_stmt.module and small_stmt.module.value == "typing":
                            for alias in small_stmt.names:
                                if alias.name.value == "Annotated":
                                    self.has_annotated_import = True
                                    break
        return True
    
    def leave_Parameters(self, original_node, updated_node):
        """Process all parameters together to maintain valid default ordering."""
        # Find all parameters with Depends defaults
        params = updated_node.params
        depends_indices = []
        
        for i, param in enumerate(params):
            if param.default is not None and isinstance(param.default, cst.Call):
                func = param.default.func
                if isinstance(func, cst.Name) and func.value == "Depends":
                    # Check if already Annotated
                    if param.annotation and isinstance(param.annotation, cst.Annotation):
                        ann = param.annotation.annotation
                        if isinstance(ann, cst.Subscript) and isinstance(ann.value, cst.Name) and ann.value.value == "Annotated":
                            continue
                    depends_indices.append(i)
        
        if not depends_indices:
            return updated_node
        
        # Check if we can safely fix these
        # We can only fix if all params after the last Depends also have defaults
        # OR if the Depends param is the last parameter
        last_depends = max(depends_indices)
        
        # Check if ALL params after last depends have defaults (or are *args/**kwargs)
        can_fix = True
        for i in range(last_depends + 1, len(params)):
            param = params[i]
            if param.default is None and param.star == '' and not param.kwonly_hack:
                # Check if it's *args or **kwargs
                if param.star == '':  # Not *args or **kwargs
                    can_fix = False
                    break
        
        if not can_fix:
            # Can only fix individual params that are at the end of the defaults chain
            # Find the last default in the chain
            last_default_idx = None
            for i in range(len(params) - 1, -1, -1):
                if params[i].default is not None or params[i].star != '' or params[i].kwonly_hack:
                    last_default_idx = i
                    break
            
            if last_default_idx is not None:
                depends_indices = [i for i in depends_indices if i >= last_default_idx]
            else:
                depends_indices = []
        
        if not depends_indices:
            return updated_node
        
        # Fix the identified parameters
        new_params = list(params)
        for i in depends_indices:
            param = new_params[i]
            
            # Check if already Annotated
            if param.annotation and isinstance(param.annotation, cst.Annotation):
                ann = param.annotation.annotation
                if isinstance(ann, cst.Subscript) and isinstance(ann.value, cst.Name) and ann.value.value == "Annotated":
                    continue
            
            if param.annotation and isinstance(param.annotation, cst.Annotation):
                ann = param.annotation.annotation
                new_annotation = cst.Annotation(
                    annotation=cst.Subscript(
                        value=cst.Name("Annotated"),
                        slice=[
                            cst.SubscriptElement(slice=cst.Index(value=param.annotation.annotation)),
                            cst.SubscriptElement(slice=cst.Index(value=param.default)),
                        ],
                    ),
                )
                
                new_param = cst.Param(
                    name=param.name,
                    annotation=new_annotation,
                    default=None,
                    equal=None,  # Remove AssignEqual
                    comma=param.comma,
                    star=param.star,
                    whitespace_after_star=param.whitespace_after_star,
                    whitespace_after_param=param.whitespace_after_param,
                )
                new_params[i] = new_param
                self.changes += 1
        
        if self.changes == 0:
            return updated_node
            
        # Update the Parameters node
        new_params_node = cst.Parameters(
            params=tuple(new_params),
            posonly_params=updated_node.posonly_params,
            kwonly_params=updated_node.kwonly_params,
            star_arg=updated_node.star_arg,
            posonly_ind=updated_node.posonly_ind,
        )
        
        return updated_node.with_changes(params=new_params_node)
    
    def leave_Module(self, original_node, updated_node):
        """Add Annotated import if needed."""
        if self.changes == 0 or self.has_annotated_import:
            return updated_node
            
        # Find existing typing import
        new_body = []
        import_added = False
        
        for stmt in updated_node.body:
            new_body.append(stmt)
            
            if isinstance(stmt, cst.SimpleStatementLine):
                for small_stmt in stmt.body:
                    if isinstance(small_stmt, cst.ImportFrom) and small_stmt.module and small_stmt.module.value == "typing":
                        if not any(a.name.value == "Annotated" for a in small_stmt.names):
                            new_names = list(small_stmt.names) + [cst.ImportAlias(name=cst.Name("Annotated"))]
                            new_stmt = small_stmt.with_changes(names=new_names)
                            new_body[-1] = stmt.with_changes(body=[new_stmt])
                        import_added = True
                        break
        
        if not import_added:
            new_import = cst.SimpleStatementLine(
                body=[
                    cst.ImportFrom(
                        module=cst.Name("typing"),
                        names=[cst.ImportAlias(name=cst.Name("Annotated"))],
                    )
                ],
                leading_lines=[cst.EmptyLine()] if new_body else [],
            )
            new_body.insert(0, new_import)
            import_added = True
        
        return updated_node.with_changes(body=new_body)


def fix_file(filepath):
    """Fix B008 in a single file. Returns number of changes."""
    with open(filepath, 'r') as f:
        source = f.read()
    
    try:
        module = cst.parse_module(source)
    except Exception as e:
        print(f"Parse error in {filepath}: {e}")
        return 0
    
    transformer = B008Transformer()
    wrapper = cst.metadata.MetadataWrapper(module)
    new_module = wrapper.visit(transformer)
    
    if transformer.changes > 0:
        new_code = new_module.code
        with open(filepath, 'w') as f:
            f.write(new_code)
        print(f"  Fixed {transformer.changes} in {filepath}")
    
    return transformer.changes


def main():
    root = Path('/opt/aitbc')
    
    # Get all files with B008
    result = subprocess.run([
        'ruff', 'check', '.', '--select=B008', '--output-format=concise'
    ], capture_output=True, text=True, cwd=root)
    
    files_with_b008 = set()
    for line in result.stdout.split('\n'):
        if 'B008' in line and ':' in line:
            file_path = line.split(':')[0]
            files_with_b008.add(root / file_path)
    
    print(f"Found {len(files_with_b008)} files with B008 violations")
    
    total_fixed = 0
    for filepath in sorted(files_with_b008):
        if not filepath.exists():
            continue
        if 'test' in str(filepath) or '__pycache__' in str(filepath):
            continue
        
        fixed = fix_file(filepath)
        total_fixed += fixed
    
    print(f"Total fixed: {total_fixed}")


if __name__ == '__main__':
    main()