import json
import networkx as nx
import matplotlib.pyplot as plt

from seedgen2.utils.grpc import SeedD

from typing import List


def _build_graph_from_json(json_str: str) -> nx.DiGraph:
    """
    Build a directed graph from the call graph JSON data.
    """
    data = json.loads(json_str)
    G = nx.DiGraph()
    for caller, callees in data.items():
        for callee in callees:
            G.add_edge(caller, callee)
    return G


def get_current_callgraph(seedd: SeedD) -> nx.DiGraph:
    resp = seedd.get_call_graph()
    return _build_graph_from_json(resp.call_graph)


def visualize_graph(G, output_path):
    plt.figure(figsize=(12, 8))
    pos = nx.spring_layout(G)
    nx.draw(G, pos, with_labels=True, node_size=500, font_size=10,
            font_weight='bold', edge_color='grey', arrows=True)
    plt.title("Call Graph Visualization")
    plt.savefig(output_path)


def get_ancestors(G: nx.DiGraph, target_function: str) -> List[str]:
    # TODO: handle function overrides
    # we just ignore C++ can override functions for now, but it's very important to handle them in the future

    # TODO: handle file name case
    # in some cases, the target function is named as "file_name:function_name", we just drop the file name for now
    target_function = target_function.split(":")[-1]
    return list(nx.ancestors(G, target_function))


def get_successors(G: nx.DiGraph, target_function: str) -> List[str]:
    # TODO: handle function overrides
    # we just ignore C++ can override functions for now, but it's very important to handle them in the future

    # TODO: handle file name case
    # in some cases, the target function is named as "file_name:function_name", we just drop the file name for now
    target_function = target_function.split(":")[-1]
    return list(nx.descendants(G, target_function))
