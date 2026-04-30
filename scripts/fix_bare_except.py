#!/usr/bin/env python3
"""Fix bare except clauses by replacing 'except:' with 'except Exception:'"""

import ast
import sys
from pathlib import Path


def fix_bare_except(file_path):
    """Fix bare except clauses in a Python file"""
    try:
        with open(file_path, 'r') as f:
            content = f.read()
        
        # Parse the file to check for syntax errors
        try:
            ast.parse(content)
        except SyntaxError:
            print(f"Skipping {file_path}: syntax error")
            return False
        
        # Split into lines
        lines = content.split('\n')
        modified = False
        new_lines = []
        
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            
            # Check if this is a bare except statement
            if stripped == 'except:':
                # Check if the previous line is a try block
                if i > 0 and 'try:' in lines[i-1]:
                    # Replace with except Exception:
                    new_lines.append(line.replace('except:', 'except Exception:'))
                    modified = True
                else:
                    new_lines.append(line)
            else:
                new_lines.append(line)
            
            i += 1
        
        if modified:
            with open(file_path, 'w') as f:
                f.write('\n'.join(new_lines))
            print(f"Fixed {file_path}")
            return True
        return False
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return False


def main():
    """Main function"""
    if len(sys.argv) > 1:
        root = Path(sys.argv[1])
    else:
        root = Path('.')
    
    # Find all Python files
    py_files = list(root.rglob('*.py'))
    
    fixed_count = 0
    for py_file in py_files:
        if fix_bare_except(py_file):
            fixed_count += 1
    
    print(f"\nFixed {fixed_count} files")


if __name__ == '__main__':
    main()
