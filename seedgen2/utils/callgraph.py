import json
import networkx as nx
import matplotlib.pyplot as plt


def build_graph_from_json(data: str) -> nx.DiGraph:
    """
    Build a directed graph from the call graph JSON data.
    """
    data = json.loads(data)
    print(data)
    G = nx.DiGraph()
    for caller, callees in data.items():
        for callee in callees:
            G.add_edge(caller, callee)
    return G


def visualize_graph(G, output_path):
    plt.figure(figsize=(12, 8))
    pos = nx.spring_layout(G)
    nx.draw(G, pos, with_labels=True, node_size=500, font_size=10,
            font_weight='bold', edge_color='grey', arrows=True)
    plt.title("Call Graph Visualization")
    plt.savefig(output_path)
