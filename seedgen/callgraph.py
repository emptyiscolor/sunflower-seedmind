import re
import networkx as nx

def is_stl_function(func_name):
    stl_patterns = [
        r'std::',  # Standard library namespace
        r'__gnu_cxx::',  # GNU C++ library namespace
        r'operator new',  # New operator
        r'operator delete',  # Delete operator
        r'__cxa',  # C++ ABI functions
    ]
    for pattern in stl_patterns:
        if re.search(pattern, func_name):
            return True
    return False

def parse_log(file_path):
    calls = []
    with open(file_path, 'r') as f:
        for line in f:
            match = re.match(r'(\d+)\|(.+)\|(.+)', line)
            if match:
                thread_id, callee, caller = match.groups()
                calls.append((int(thread_id), callee, caller))
    return calls

def filter_calls(calls):
    filtered_calls = []
    calls_per_thread = {}

    for thread_id, callee, caller in calls:
        if thread_id not in calls_per_thread:
            calls_per_thread[thread_id] = []
        calls_per_thread[thread_id].append((callee, caller))
    
    for thread_id, calls in calls_per_thread.items():
        calling_initiator = {}

        for callee, caller in calls:
            if not is_stl_function(callee) and not is_stl_function(caller):
                filtered_calls.append((callee, caller))
            elif is_stl_function(callee) and not is_stl_function(caller):
                calling_initiator[callee] = caller
            elif is_stl_function(callee) and is_stl_function(caller) and caller in calling_initiator:
                if caller in calling_initiator:
                    calling_initiator[callee] = calling_initiator[caller]
            elif not is_stl_function(callee) and is_stl_function(caller):
                if caller in calling_initiator:
                    filtered_calls.append((callee, calling_initiator[caller]))
                else:
                    print("No initiator found for callee: ", callee)
    return filtered_calls

def assign_levels(G, initial_nodes):
    levels = {node: float('inf') for node in G.nodes}
    for node in initial_nodes:
        if node in levels:
            levels[node] = 0
    
    queue = initial_nodes.copy()
    while queue:
        current = queue.pop(0)
        current_level = levels[current]
        for neighbor in G.neighbors(current):
            if levels[neighbor] > current_level + 1:
                levels[neighbor] = current_level + 1
                queue.append(neighbor)
    
    return levels

def process_call_graph(log_file_path):
    calls = parse_log(log_file_path)
    filtered_calls = filter_calls(calls)

    G = nx.DiGraph()
    added_edges = set()
    for callee, caller in filtered_calls:
        if callee == caller:
            continue
        if (caller, callee) not in added_edges:
            G.add_edge(caller, callee)
            added_edges.add((caller, callee))
    
    initial_nodes = ['LLVMFuzzerTestOneInput']
    levels = assign_levels(G, initial_nodes)
    return levels
