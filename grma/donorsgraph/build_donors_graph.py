from __future__ import annotations

import os
import pickle
from typing import Union, List

from tqdm import tqdm

from grma.donorsgraph import Edge
from grma.donorsgraph.create_lol import LolBuilder
from grma.match.graph_wrapper import Graph
from grma.utilities.geno_representation import HashableArray
from grma.utilities.utils import gl_string_to_integers, tuple_geno_to_int, print_time

CLASS_I_END = 6


class BuildMatchingGraph:
    """
    This class responsible for building the graph with the genotypes, classes and subclasses of the donors.
    It gets a path to directory with the donors' file, builds the graph and saved it as LOL graph using Cython.
    """

    __slots__ = '_verbose', "_graph", "_edges"

    def __init__(self, path_to_donors_directory: str, verbose: bool = False):
        """
        Build a donor's graph from the donor's genotypes.
        Args:
            path_to_donors_directory: The path to the donors files directory
            verbose: A boolean flag for whether to print the documentation. default is False
        """
        self._verbose = verbose
        self._graph = None  # LOL dict-representation
        self._edges: List[Edge] = []  # edge-list
        self._save_graph_as_edges(path_to_donors_directory)

    def _create_classes_edges(self, geno, class_, layers):
        int_class = tuple_geno_to_int(class_)

        self._edges.append(Edge(int_class, geno, 0))

        # check if the class node was created
        if int_class not in layers["CLASS"]:
            layers["CLASS"].add(int_class)
            self._create_subclass_edges(class_, int_class, layers)

    def _create_subclass_edges(self, class_, int_class, layers):
        """
        subclasses edges are created by dropping an allele from a class.
        each allele we drop, will be replaced with zero,
        and will be shifted to the second place in the locus.
        """
        # create subclasses from class
        num_of_alleles = len(class_)

        subclass_alleles = set()
        # set the missing allele to always be the second allele in the locus
        for i in range(num_of_alleles):
            if i % 2 == 0:
                subclass_alleles.add(tuple_geno_to_int(tuple(class_[0: i] + (0,) + class_[i + 1:])))
            else:
                subclass_alleles.add(tuple_geno_to_int(tuple(class_[0: i - 1] + (0, class_[i - 1]) + class_[i + 1:])))

        # add subclass->class edges
        for sub in subclass_alleles:
            self._edges.append(Edge(sub, int_class, 0))
            if sub not in layers["SUBCLASS"]:
                layers["SUBCLASS"].add(sub)

    def _save_graph_as_edges(self, path_to_donors_directory: str | os.PathLike):
        """
        Process donors imputation files and save them to self._graph as an edgelist
        """
        print_time("(0/6) donorsgraph edgelist")
        files = sorted(list(os.listdir(path_to_donors_directory)))

        # dict of sets of nodes in each layer
        layers = {
            "ID": set(),
            "GENOTYPE": set(),
            "CLASS": set(),  # map classes to mp.uint32 objects
            "SUBCLASS": set()
        }
        count_donors = 0

        probability_dict = {}  # {genotype: probability} for each patient
        total_probability = 0
        last_id = 0

        for filename in files:
            with open(os.path.join(path_to_donors_directory, filename)) as f:
                for line in tqdm(f.readlines(), desc=f"Processing {filename}", disable=not self._verbose):
                    # retrieve all line's parameters
                    donor_id, geno, probability, index = line.strip().split(',')
                    donor_id = int(donor_id)
                    index = int(index)
                    probability = float(probability)

                    # convert geno to list of integers
                    geno = gl_string_to_integers(geno)

                    # sort alleles for each HLA-X
                    for x in range(0, 10, 2):
                        geno[x: x + 2] = sorted(geno[x: x + 2])
                    geno = HashableArray(geno)

                    # handle new donor appearance in file
                    if index == 0:
                        count_donors += 1

                        # add id<->geno nodes to edgelist
                        for HLA, geno_probability in probability_dict.items():
                            self._edges.append(Edge(HLA, last_id, geno_probability / total_probability))
                            self._edges.append(Edge(last_id, HLA, geno_probability / total_probability))

                        # initialize parameters
                        total_probability = 0
                        last_id = donor_id
                        probability_dict = {}
                        layers["ID"].add(last_id)

                    # continue creation of classes and subclasses
                    if geno not in layers["GENOTYPE"]:
                        layers["GENOTYPE"].add(geno)
                        geno_class1 = tuple(geno[:CLASS_I_END])
                        geno_class2 = tuple(geno[CLASS_I_END:])
                        self._create_classes_edges(geno, geno_class1, layers)
                        self._create_classes_edges(geno, geno_class2, layers)

                    # add probabilities to probability dict
                    total_probability += probability
                    if geno in probability_dict:
                        probability_dict[geno] += probability
                    else:
                        probability_dict[geno] = probability

        # add the last donor to edgelist
        for HLA, probability in probability_dict.items():
            self._edges.append(Edge(HLA, last_id, probability / total_probability))
            self._edges.append(Edge(last_id, HLA, probability / total_probability))

        count_donors += 1
        if self._verbose:
            print(f"Total number of donors:{count_donors}")

        # create graph's dict-representation of LOL
        self._graph = LolBuilder(directed=True, weighted=True, verbose=self._verbose).build(self._edges, layers)

    @property
    def graph(self):
        return Graph(self._graph)

    def to_pickle(self, path: Union[str, os.PathLike]):
        """
        Save a pickle of the graph.
        To get the graph after pickling use:

        >>> from grma.match.graph_wrapper import Graph
        >>> Graph.from_pickle(path)

        :param path: A path to save the pickled object
        """
        pickle.dump(self._graph, open(path, "wb"))
