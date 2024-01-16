from grma.match import Graph, matching

def main():
    PATH_TO_DONORS_GRAPH = "./data/donors_graph.pkl"
    PATH_CONGIF_FILE = "./data/minimal-configuration.json"
    

    # The donors' graph we built earlier
    donors_graph = Graph.from_pickle(PATH_TO_DONORS_GRAPH)


    # matching_results is a dict - {patient_id: the patient's result dataframe}
    matching_results = matching(donors_graph,PATH_CONGIF_FILE, search_id=1, donors_info=[],
                                        threshold=0.1, cutof=100, save_to_csv=True)

if __name__ == '__main__':
    main()