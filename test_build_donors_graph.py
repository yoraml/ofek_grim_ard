from grma.donorsgraph.build_donors_graph import BuildMatchingGraph

PATH_TO_DONORS_DIR = "./data/donors_dir"
PATH_TO_DONORS_GRAPH = "./data/donors_graph.pkl"

build_matching = BuildMatchingGraph(PATH_TO_DONORS_DIR)
graph = build_matching.graph  # access the donors' graph

build_matching.to_pickle(PATH_TO_DONORS_GRAPH)  # save the donors' graph to pickle