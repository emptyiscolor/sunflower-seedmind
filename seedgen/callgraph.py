import re
import networkx as nx
import matplotlib.pyplot as plt


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
    
    return levels, G

def visualize_call_tree(levels, G, coverage_info, num, runtime_folder):
    # Convert coverage_info into a dictionary for fast lookup by function name
    coverage_dict = {func['name']: func for func in coverage_info}

    # Create a temporary graph with only valid nodes
    tmp_G = nx.DiGraph()
    for node in G.nodes:
        level = levels.get(node, float('inf'))
        if level != float('inf'):
            tmp_G.add_node(node)
            for neighbor in G.neighbors(node):
                if levels.get(neighbor, float('inf')) != float('inf'):
                    tmp_G.add_edge(node, neighbor)
    
    # Define color map, position, and labels for each node based on coverage info
    color_map = []
    pos = {}
    labels = {}

    for node in tmp_G.nodes:
        level = levels[node]
        
        # Get the coverage information for the node if available
        coverage = coverage_dict.get(node, None)
        if coverage:
            coverage_text = f"{coverage['covered_edges']}/{coverage['total_edges']}"
            labels[node] = f"{node}\n{coverage_text}"
            # Set node color based on coverage
            if coverage['fully_covered']:
                color_map.append('yellow')  # Fully covered nodes
            elif level == 0:
                color_map.append('red')  # Entry points (root nodes)
            else:
                color_map.append('lightblue')  # Partially covered nodes
        else:
            labels[node] = node
            color_map.append('grey')  # Nodes without coverage info

        # Position nodes by their level
        pos[node] = (level, -list(tmp_G.nodes).index(node))

    # Draw the graph with positions and labels
    plt.figure(figsize=(12, 8))
    nx.draw(tmp_G, pos, with_labels=True, node_color=color_map, node_size=500, font_size=10, font_weight='bold', edge_color='grey', arrows=True, labels=labels)
    
    plt.title("Filtered Call Tree with Coverage Information")
    plt.savefig(f"{runtime_folder}/visualization/callgraph_{num}.png")

def select_candidate_branches(levels, G, coverage_info):
    pass