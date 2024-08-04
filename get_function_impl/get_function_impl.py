import clang.cindex
import sys
import os

def find_function_definition(node, func_name):
    """
    Recursively search for the function definition in the AST.
    """
    if node.kind in {clang.cindex.CursorKind.FUNCTION_DECL, clang.cindex.CursorKind.CXX_METHOD} and node.spelling == func_name and node.is_definition():
        return node
    for child in node.get_children():
        result = find_function_definition(child, func_name)
        if result is not None:
            return result
    return None

def extract_function_source(node):
    """
    Extract the source code for the function from the AST node.
    """
    start = node.extent.start
    end = node.extent.end
    with open(start.file.name, 'r') as f:
        lines = f.readlines()
        func_lines = lines[start.line - 1:end.line]
        func_lines[0] = func_lines[0][start.column - 1:]
        func_lines[-1] = func_lines[-1][:end.column - 1]
        return ''.join(func_lines)

def get_function_implementation(file_path, func_name):
    """
    Get the implementation of the specified function from the source file.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Source file {file_path} not found.")

    # Initialize Clang Index
    index = clang.cindex.Index.create()
    translation_unit = index.parse(file_path, args=['-std=c++11'])

    if not translation_unit:
        raise RuntimeError(f"Unable to parse the source file {file_path}.")

    # Find the function definition in the AST
    function_node = find_function_definition(translation_unit.cursor, func_name)
    if function_node is None:
        raise ValueError(f"Function {func_name} not found in the source file {file_path}.")

    # Extract the function source code
    function_source = extract_function_source(function_node)
    return function_source

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python get_function_implementation.py <source_file> <function_name>")
        sys.exit(1)
    
    # Set libclang path
    clang.cindex.Config.set_library_file('/usr/lib/llvm-18/lib/libclang.so')

    source_file = sys.argv[1]
    function_name = sys.argv[2]

    try:
        function_source = get_function_implementation(source_file, function_name)
        print(function_source)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
