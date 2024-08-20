import clang.cindex
import os

def set_libclang_path(libclang_path):
    """
    Set the path to the libclang.so file.
    """
    clang.cindex.Config.set_library_file(libclang_path)

def _find_function_definition(node, func_name):
    """
    Recursively search for the function definition in the AST.
    """
    if node.kind in {clang.cindex.CursorKind.FUNCTION_DECL, clang.cindex.CursorKind.CXX_METHOD} and node.spelling == func_name and node.is_definition():
        return node
    for child in node.get_children():
        result = _find_function_definition(child, func_name)
        if result is not None:
            return result
    return None

def _extract_function_source(node):
    """
    Extract the source code for the function from the AST node.
    Return an array of tuples containing line number and content.
    """
    start = node.extent.start
    end = node.extent.end
    with open(start.file.name, 'r') as f:
        lines = f.readlines()
        func_lines = lines[start.line - 1:end.line]
        result = [(i + start.line, line.rstrip()) for i, line in enumerate(func_lines)]
    return result

def _get_function_implementation(file_path, func_name):
    """
    Get the implementation of the specified function from the source file.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Source file {file_path} not found.")

    # Initialize Clang Index
    index = clang.cindex.Index.create()

    # treat the source file as C++ code
    translation_unit = index.parse(file_path, args=['-x', 'c++', '-std=c++11'])

    if not translation_unit:
        raise RuntimeError(f"Unable to parse the source file {file_path}.")

    # Find the function definition in the AST
    function_node = _find_function_definition(translation_unit.cursor, func_name)
    if function_node is None:
        print(f"[!] Function {func_name} not found in the source file {file_path}.")
        return None

    # Extract the function source code
    function_source = _extract_function_source(function_node)
    return function_source

def get_function_source(file_path, func_name):
    """
    Public interface to get the function source code.
    """
    return _get_function_implementation(file_path, func_name)
