#!/usr/bin/env python3
"""
planarity_check.py

Usage:
    python3 planarity_check.py INPUT_FILE

INPUT_FILE should contain one edge per line in the form:
    u,v
where u and v are node identifiers (strings or integers).
"""

import sys
import networkx as nx
from networkx.algorithms.planarity import check_planarity

def get_faces(embedding: nx.PlanarEmbedding):
    """
    Yield each face as a list of nodes (in cyclic order)
    by traversing every directed edge exactly once.
    """
    seen = set()
    for u in embedding.nodes():
        for v in embedding[u]:
            if (u, v) in seen:
                continue
            cycle = embedding.traverse_face(u, v)
            # mark all directed edges along this face as seen
            L = len(cycle)
            for i in range(L):
                a, b = cycle[i], cycle[(i+1) % L]
                seen.add((a, b))
            yield cycle

def read_graph(path):
    G = nx.Graph()
    with open(path, 'r') as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith('#'):  # skip blank/comment
                continue
            try:
                u, v = line.split(',')
            except ValueError:
                print(f"Error parsing line {lineno!r}: {line!r}", file=sys.stderr)
                sys.exit(1)
            G.add_edge(u.strip(), v.strip())
    return G

def main():
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        sys.exit(1)

    infile = sys.argv[1]
    G = read_graph(infile)

    is_planar, embedding_or_counter = check_planarity(G, counterexample=True)

    if is_planar:
        print("Result: graph IS planar.")
        for face in get_faces(embedding_or_counter):
            if len(face) != 3:
                print(face)
    else:
        print("Result: graph is NOT planar.")
        # Extract the Kuratowski subgraph whose edges force crossings
        print(embedding_or_counter.edges)
        print("Edges in the Kuratowski subgraph (must overlap in any drawing):")
        #for u, v in K.edges():
        #    print(f"  {u} – {v}")

if __name__ == "__main__":
    main()
