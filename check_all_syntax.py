# -*- coding: utf-8 -*-
import os
import ast
import py_compile

def check_file_syntax(filepath):
    """Compila el archivo para detectar errores de sintaxis reales."""
    try:
        py_compile.compile(filepath, doraise=True)
        return True, []
    except py_compile.PyCompileError as err:
        return False, [f"Error de sintaxis: {err.msg} en línea {err.lineno}"]

def check_file_ast(filepath):
    """Analiza el AST para detectar variables o módulos no definidos o errores comunes."""
    warnings = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        tree = ast.parse(content, filename=filepath)
        
        # Encontrar imports y definiciones
        imported_names = set()
        defined_names = set()
        used_names = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for name in node.names:
                    imported_names.add(name.asname or name.name.split('.')[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    for name in node.names:
                        imported_names.add(name.asname or name.name)
            elif isinstance(node, ast.FunctionDef):
                defined_names.add(node.name)
            elif isinstance(node, ast.ClassDef):
                defined_names.add(node.name)
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                defined_names.add(node.id)
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                used_names.append((node.id, node.lineno))
                
        # Nombres built-in estándar en python
        builtins = {'True', 'False', 'None', 'print', 'len', 'sum', 'float', 'int', 'str', 'list', 'dict', 'set', 'tuple',
                    'range', 'open', 'enumerate', 'zip', 'any', 'all', 'isinstance', 'issubclass', 'abs', 'round', 'min',
                    'max', 'sum', 'map', 'filter', 'sorted', 'reversed', 'getattr', 'setattr', 'hasattr', 'repr', 'super',
                    'ValueError', 'TypeError', 'KeyError', 'IndexError', 'Exception', 'AttributeError', 'StopIteration',
                    'classmethod', 'staticmethod', 'property', 'id', 'object', 'Exception', 'list', 'dict', 'set', 'tuple',
                    '__name__', '__file__', '__doc__', '__package__'}
        
        known_names = imported_names | defined_names | builtins
        
        # Buscar variables no declaradas
        for name, lineno in used_names:
            if name not in known_names:
                # Filtrar nombres comunes en Flask / SQLAlchemy inyectados dinámicamente si es necesario
                warnings.append(f"Nombre posiblemente no definido `{name}` en línea {lineno}")
                
    except Exception as e:
        warnings.append(f"Error analizando AST: {e}")
        
    return warnings

def run_project_diagnostic():
    print("==================================================")
    print("         DIAGNÓSTICO DE PROBLEMAS DE CÓDIGO       ")
    print("==================================================")
    
    root_dir = os.path.dirname(os.path.abspath(__file__))
    exclude_dirs = {'venv', '.git', '__pycache__', 'instance', 'migrations'}
    
    py_files = []
    
    # Buscar todos los archivos Python en el proyecto
    for root, dirs, files in os.walk(root_dir):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for file in files:
            if file.endswith('.py') and file != 'check_all_syntax.py':
                py_files.append(os.path.join(root, file))
                
    total_errors = 0
    total_warnings = 0
    
    for filepath in sorted(py_files):
        rel_path = os.path.relpath(filepath, root_dir)
        print(f"\nAnalizando: {rel_path} ...")
        
        # 1. Chequeo sintáctico duro
        is_ok, syntax_errors = check_file_syntax(filepath)
        if not is_ok:
            total_errors += len(syntax_errors)
            for err in syntax_errors:
                print(f"  [ERROR SINTAXIS] {err}")
            continue
            
        # 2. Chequeo de AST
        ast_warnings = check_file_ast(filepath)
        if ast_warnings:
            # Filtrar warnings muy específicos o falsos positivos dinámicos
            filtered_warnings = []
            for w in ast_warnings:
                # Evitar reportar falsos positivos de Flask o SQLAlchemy inyectados
                if any(x in w for x in ['`app`', '`request`', '`session`', '`g`', '`db`', '`flash`', '`redirect`', '`url_for`']):
                    continue
                filtered_warnings.append(w)
                
            if filtered_warnings:
                total_warnings += len(filtered_warnings)
                for warn in filtered_warnings:
                    print(f"  [WARNING AST] {warn}")
                    
    print("\n==================================================")
    print(f"DIAGNÓSTICO FINALIZADO:")
    print(f"  - Archivos analizados: {len(py_files)}")
    print(f"  - Errores de sintaxis encontrados: {total_errors}")
    print(f"  - Posibles advertencias/warnings: {total_warnings}")
    print("==================================================")

if __name__ == '__main__':
    run_project_diagnostic()
