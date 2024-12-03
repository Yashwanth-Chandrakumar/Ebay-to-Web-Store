#!/usr/bin/env python3
import ast
import re
import sys


def get_imported_packages(code):
    """Extract all imported package names from Python code."""
    imported_packages = set()
    
    try:
        tree = ast.parse(code)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_packages.update(alias.name.split('.')[0] for alias in node.names)
            
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imported_packages.add(node.module.split('.')[0])
    
    except SyntaxError:
        print("Error parsing the Python code.")
    
    return imported_packages

def clean_requirements_file(code_path, requirements_path):
    """Remove unused packages from requirements.txt"""
    with open(code_path, 'r') as f:
        code = f.read()
    
    imported_packages = get_imported_packages(code)
    
    with open(requirements_path, 'r') as f:
        requirements = f.readlines()
    
    cleaned_requirements = []
    for req in requirements:
        package_name = re.split(r'[=<>]', req.strip())[0].lower()
        
        if any(imp.lower() in package_name for imp in imported_packages):
            cleaned_requirements.append(req)
    
    with open(requirements_path, 'w') as f:
        f.writelines(cleaned_requirements)
    
    print(f"Cleaned requirements file. Removed {len(requirements) - len(cleaned_requirements)} unused packages.")

def main():
    if len(sys.argv) != 3:
        print("Usage: python script.py <python_code_path> <requirements_path>")
        sys.exit(1)
    
    code_path = sys.argv[1]
    requirements_path = sys.argv[2]
    
    clean_requirements_file(code_path, requirements_path)

if __name__ == "__main__":
    main()