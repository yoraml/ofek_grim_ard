from collections.abc import Iterator
from typing import List, Tuple, Set, Iterable, Dict
from typing import Sequence

import networkx as nx
import numpy as np
import pandas as pd
from tqdm import tqdm

from grma.match.graph_wrapper import Graph
from grma.utilities.geno_representation import HashableArray, ClassMinusOne
from grma.utilities.utils import donor_mismatch_format, \
    drop_less_than_7_matches, check_similarity, gl_string_to_integers, tuple_geno_to_int, print_time

DONORS_DB: pd.DataFrame = pd.DataFrame()
ZEROS: HashableArray = HashableArray([0])
ALLELES_IN_CLASS_I: int = 6
ALLELES_IN_CLASS_II: int = 4


def set_database(donors_db: pd.DataFrame = pd.DataFrame()):
    """
    Set a database for a search.
    Use this function before the matching if you wish to add fields for the result df.
    """
    global DONORS_DB
    DONORS_DB = donors_db


def _init_results_df(donors_info):
    """Initialize matching donors' df"""
    global DONORS_DB
    fields_in_results = {
        "Patient_ID": [], "Donor_ID": [],
        "Number_Of_Mismatches": [], "Matching_Probability": [],
        "Match_Probability_A_1": [], "Match_Probability_A_2": [],
        "Match_Probability_B_1": [], "Match_Probability_B_2": [],
        "Match_Probability_C_1": [], "Match_Probability_C_2": [],
        "Match_Probability_DQB1_1": [], "Match_Probability_DQB1_2": [],
        "Match_Probability_DRB1_1": [], "Match_Probability_DRB1_2": [],
        "Permissive/Non-Permissive": [],
        "Match_Between_Most_Commons_A": [],
        "Match_Between_Most_Commons_B": [],
        "Match_Between_Most_Commons_C": [],
        "Match_Between_Most_Commons_DQB": [],
        "Match_Between_Most_Commons_DRB": []
    }

    donors_db_fields = DONORS_DB.columns.values.tolist()
    for di in donors_info:
        if di in donors_db_fields:
            fields_in_results[di] = []
    return pd.DataFrame(fields_in_results)


def locuses_match_between_genos(geno1, geno2):
    matches = []
    for i in range(5):
        a1, b1 = geno1[2 * i], geno1[2 * i + 1]
        a2, b2 = geno2[2 * i], geno2[2 * i + 1]

        s1 = int(a1 == a2) + int(b1 == b2)
        s2 = int(a1 == b2) + int(b1 == a2)
        matches.append(max(s1, s2))

    return matches


class DonorsMatching(object):
    """DonorsMatching class is in charge of the matching process"""
    __slots__ = "_graph", "_patients_graph", "_genotype_candidates", "patients", "verbose"

    def __init__(self, graph: Graph, verbose: bool = False):
        self._graph: Graph = graph
        self._patients_graph: nx.DiGraph = nx.DiGraph()
        self._genotype_candidates: Dict[int, Dict[int, List[Tuple[float, int]]]] = {}  # AMIT ADD
        self.patients: Dict[int, Sequence[int]] = {}
        self.verbose = verbose

    def get_most_common_genotype(self, donor_id):
        """Takes a donor ID and return his/her most common genotype.
        """
        don_geno = []
        geno_max_prob = 0
        for geno in self._graph.neighbors(donor_id):
            if geno[1] > geno_max_prob:
                geno_max_prob = geno[1]
                don_geno = geno[0]

        return don_geno

    def print_most_common_genotype(self, don_id: int, pat_geno: Sequence[int]) -> str:
        """Takes a donor ID and a genotype.
        Returns the mismatch format of the most common genotype of the donor."""
        don_geno = []
        geno_max_prob = 0
        for geno in self._graph.neighbors(don_id):
            if geno[1] > geno_max_prob:
                geno_max_prob = geno[1]
                don_geno = geno[0]

        return donor_mismatch_format(don_geno, pat_geno)

    def probability_to_allele(self, don_id: int, pat_geno: Sequence[int]) -> List[float]:
        """Takes a donor ID and a genotype.
        Returns the probability of match for each allele"""
        probs = [0 for _ in range(10)]

        for i, allele in enumerate(pat_geno):
            p = 0
            for don_geno, don_weight in self._graph.neighbors(don_id):
                if allele in don_geno:
                    p += don_weight
            probs[i] = int(round(p * 100))

        return probs

    def __find_genotype_candidates_from_subclass(self, sub: int) -> np.ndarray:
        """Takes an integer subclass.
        Returns the genotypes which are connected to it in the graph"""
        return self._graph.neighbors_2nd(sub)

    def __find_genotype_candidates_from_class(self, clss: int) -> Tuple[np.ndarray, np.ndarray]:
        """Takes an integer subclass.
        Returns the genotypes (ids and values) which are connected to it in the graph"""
        return self._graph.class_neighbors(clss)

    def __find_donor_from_geno(self, geno_id: int) -> Sequence[int]:
        """Gets the LOL ID of a genotype.
        Return its neighbors - all the donors that has this genotype."""
        ids, _ = zip(*self._graph.neighbors(geno_id, search_lol_id=True))
        return list(ids)

    def __add_matched_genos_to_graph(self, genos: Iterator, genotypes_ids: np.ndarray, genotypes_values: np.ndarray,
                                     allele_range_to_check: np.ndarray, matched_alleles: int):
        for geno in genos:
            # check similarity between geno and all the candidates
            similarities = check_similarity(geno.np(),
                                            genotypes_values, allele_range_to_check,
                                            matched_alleles)

            candidates_to_iterate = drop_less_than_7_matches(genotypes_ids, similarities)

            for geno_candidate_id, similarity in candidates_to_iterate:
                # iterate over all the patients with the genotype
                for patient_id in self._patients_graph.neighbors(geno):
                    # patient's geno index (the number of the geno in the imputation file)
                    geno_num = self._patients_graph[geno][patient_id]["geno_num"]  # AMIT DELETE
                    probability = self._patients_graph[geno][patient_id]["probability"]  # patient's geno probability

                    # STUDY TEST CASE
                    # problem_node = 26529534
                    # problem_patient = 26477347
                    # if patient_id == problem_node and geno_candidate_id == problem_patient:
                    #     x = 1
                    # FINISH STUDY TEST CASE

                    # add the genotype id as a neighbor to the patient
                    # AMIT ADD
                    if geno_candidate_id in self._genotype_candidates[patient_id]:
                        self._genotype_candidates[patient_id][geno_candidate_id][geno_num] = (probability, similarity)
                    else:
                        self._genotype_candidates[patient_id][geno_candidate_id] = {geno_num: (probability, similarity)}
                    # AMIT END

                    # AMIT DELETE
                    """
                    if geno_candidate_id in self._patients_graph.adj[patient_id]:
                        self._patients_graph[patient_id][geno_candidate_id]['weight'][geno_num] = [probability,
                                                                                                   similarity]
                    else:
                        self._patients_graph.add_edge(patient_id, geno_candidate_id,
                                                      weight={geno_num: [probability, similarity]})
                    """

    def __classes_and_subclasses_from_genotype(self, genotype: HashableArray):
        subclasses = []
        classes = [genotype[:ALLELES_IN_CLASS_I], genotype[ALLELES_IN_CLASS_I:]]
        num_of_alleles_in_class = [ALLELES_IN_CLASS_I, ALLELES_IN_CLASS_II]

        int_classes = [tuple_geno_to_int(tuple(clss)) for clss in classes]
        for clss in int_classes:
            self._patients_graph.add_edge(clss, genotype)

        # class one is considered as 0.
        # class two is considered as 1.
        class_options = [0, 1]
        for class_num in class_options:
            for k in range(0, num_of_alleles_in_class[class_num]):
                # set the missing allele to always be the second allele in the locus
                if k % 2 == 0:
                    sub = tuple_geno_to_int(classes[class_num][0: k] + ZEROS + classes[class_num][k + 1:])
                else:
                    sub = tuple_geno_to_int(classes[class_num][0: k - 1] + ZEROS +
                                            classes[class_num][k - 1: k] + classes[class_num][k + 1:])

                # missing allele number is the index of the first allele of the locus the missing allele belongs to.
                # Could be [0, 2, 4, 6, 8]
                missing_allele_num = ALLELES_IN_CLASS_I * class_num + 2 * (k // 2)
                subclass = ClassMinusOne(subclass=sub,
                                         class_num=class_num,
                                         allele_num=missing_allele_num)

                # add subclass -> genotype edge to patients graph
                subclasses.append(subclass)

                self._patients_graph.add_edge(subclass, genotype)

        return int_classes, subclasses

    def create_patients_graph(self, f_patients: str):
        """
        create patients graph. \n
        *takes in consideration that grimm outputs for each patient different genotypes*
        """
        # AMIT - DELETE 'geno_num' from weights, was unnecessary
        self._patients_graph: nx.DiGraph = nx.DiGraph()
        prob_dict: dict = {}  # {geno: [i, prob]}
        total_prob: float = 0
        last_patient: int = -1
        # subclasses: list[ClassMinusOne] = []
        subclasses_by_patient: Dict[int, Set] = {}
        classes_by_patient: Dict[int, Set] = {}

        for line in open(f_patients).readlines():
            # retrieve all line's parameters
            line_values = line.strip().split(',')
            patient_id, geno, prob, index = line_values

            geno = gl_string_to_integers(geno)
            patient_id = int(patient_id)
            index = int(index)
            prob = float(prob)

            # handle new patient appearance in file
            if index == 0:
                # set normalized probabilities
                for HLA, probability in prob_dict.items():
                    self._patients_graph.edges[HLA, last_patient]['probability'] = probability / total_prob

                # initialize parameters
                prob_dict = {}
                total_prob = 0
                self.patients[patient_id] = geno
                self._genotype_candidates[patient_id] = {}  # AMIT ADD - initialize _genotype_candidates
                last_patient = patient_id

                subclasses_by_patient[patient_id] = set()
                classes_by_patient[patient_id] = set()

            # sort alleles for each HLA-X
            for x in range(0, 10, 2):
                geno[x: x + 2] = sorted(geno[x: x + 2])

            geno = HashableArray(geno)

            # add probabilities to probability dict
            total_prob += prob
            if geno not in prob_dict:
                prob_dict[geno] = prob
            else:
                prob_dict[geno] += prob

            # add genotype->ID edge
            self._patients_graph.add_edge(geno, patient_id, probability=0, geno_num=index)

            # add subclasses alleles
            classes, subclasses = self.__classes_and_subclasses_from_genotype(geno)

            subclasses_by_patient[patient_id] = subclasses_by_patient[patient_id].union(subclasses)
            classes_by_patient[patient_id] = classes_by_patient[patient_id].union(classes)

        # set normalized probabilities to the last patient in the file
        for HLA, probability in prob_dict.items():
            self._patients_graph.edges[HLA, last_patient]['probability'] = probability / total_prob

        # return subclasses_by_patient
        return subclasses_by_patient, classes_by_patient

    def find_geno_candidates_by_subclasses(self, subclasses):
        for subclass in tqdm(subclasses, desc="finding subclasses matching candidates", disable=not self.verbose):
            if self._graph.in_nodes(subclass.subclass):
                patient_genos = self._patients_graph.neighbors(subclass)  # The patient's genotypes which might be match
                genotypes_id, genotypes_value = self.__find_genotype_candidates_from_subclass(subclass.subclass)

                # Checks only the locuses that are not certain to match
                if subclass.class_num == 0:
                    allele_range_to_check = np.array([6, 8, subclass.allele_num], dtype=np.uint8)
                else:
                    allele_range_to_check = np.array([0, 2, 4, subclass.allele_num], dtype=np.uint8)

                # number of alleles that already match due to match in subclass
                matched_alleles: int = (ALLELES_IN_CLASS_II if subclass.class_num == 1 else ALLELES_IN_CLASS_I) - 2

                # Compares the candidate to the patient's genotypes, and adds the match geno candidates to the graph.
                self.__add_matched_genos_to_graph(patient_genos, genotypes_id, genotypes_value,
                                                  allele_range_to_check, matched_alleles)

    def find_geno_candidates_by_classes(self, classes):
        for clss in tqdm(classes, desc="finding classes matching candidates", disable=not self.verbose):
            if self._graph.in_nodes(clss):
                patient_genos = self._patients_graph.neighbors(clss)  # The patient's genotypes which might be match
                genotypes_ids, genotypes_values = self.__find_genotype_candidates_from_class(clss)

                # Checks only the locuses that are not certain to match (the locuses of the other class)
                # Class I appearances: 3 locuses = 6 alleles = 23/24 digits
                # Class II appearances: 2 locuses = 4 alleles = 15/16 digits
                if len(str(clss)) > 20:
                    allele_range_to_check = np.array([6, 8], dtype=np.uint8)
                    matched_alleles: int = 6
                else:
                    allele_range_to_check = np.array([0, 2, 4], dtype=np.uint8)
                    matched_alleles: int = 4

                # Compares the candidate to the patient's genotypes, and adds the match geno candidates to the graph.
                self.__add_matched_genos_to_graph(patient_genos, genotypes_ids, genotypes_values,
                                                  allele_range_to_check, matched_alleles)

                # Send the class and the genotypes of the patients that the class belong to
                # self.__add_class_candidates(clss, self._patients_graph.neighbors(clss))

    def find_geno_candidates_by_genotypes(self, patient_id: int):
        genos = self._patients_graph.predecessors(patient_id)

        for geno in genos:
            # if patient_id in self._patients_graph[geno]:
            #     print("Processing geno:", geno)
            #     print("Processing patient_id:", patient_id)
            # print("Dictionary contents:", self._patients_graph[geno][patient_id])

            # if "geno_num" in self._patients_graph[geno][patient_id]:
            #     print("Patient ID:", patient_id, "has 'geno_num'")
            geno_num = self._patients_graph[geno][patient_id]["geno_num"]  # patient's geno index # AMIT DELETE
            probability = self._patients_graph[geno][patient_id]["probability"]  # patient's geno probability

            int_geno = tuple_geno_to_int(geno)
            geno_id = self._graph.get_node_id(int_geno)
            if not geno_id:
                continue

            # This has to be a new edge because this is the first level (searching by genos),
            # and each patient connects only to their own genos, so we wouldn't override the weight dict.
            # self._patients_graph.add_edge(patient_id, geno_id, weight={geno_num: [probability, 10]}) # AMIT DELETE
            self._genotype_candidates[patient_id][geno_id] = {geno_num: (probability, 10)}  # AMIT ADD
            # else:
            #     print(f"Missing 'geno_num' for patient_id: {patient_id}")
            #     print("geno:", geno)
            #     print("patient_id:", patient_id)
            # else:
            #     print(f"Patient ID {patient_id} not found in self._patients_graph[geno]")
            #     print("geno:", geno)
            #     print("patient_id:", patient_id)

        """
        genos = self._patients_graph.predecessors(patient_id)
        for geno in genos:
            print(f"Processing geno: {geno}, patient_id: {patient_id}")

            # geno_num = self._patients_graph[geno][patient_id]["geno_num"]  # patient's geno index
            probability = self._patients_graph[geno][patient_id]["probability"]  # patient's geno probability

            int_geno = tuple_geno_to_int(geno)
            geno_id = self._graph.get_node_id(int_geno)
            if not geno_id:
                continue

            # This has to be a new edge, because this is the first level (searching by genos),
            # and each patient connect only to his own genos, so we wouldn't override the weight dict.
            # self._patients_graph.add_edge(patient_id, geno_id, weight={geno_num: [probability, 10]}) # AMIT DELETE
            self._genotype_candidates[patient_id][geno_id] = [(geno_num, probability, 10)] # AMIT ADD

        """

    def score_matches(self, mismatch: int, results_df: pd.DataFrame, donors_info: Iterable[str],
                      patient: int, threshold: float, cutof: int,
                      matched: Set[int]) -> Tuple[Set[int], int, pd.DataFrame]:
        """
        Given a number of mismatches and a patient, this function will return a dictionary
        of all matching donors found in the data with the specific number of mismatches,
        sorted by their probability for a match.

        :param mismatch: number of mismatch to search. could be 0, 1, 2, 3.
        :param results_df: A df storing the matching results.
        :param donors_info: a list of fields from Database to add to the matching results.
        :param patient: patient ID.
        :param threshold: Minimal score value for a valid match. default is 0.1.
        :param cutof: Maximum number of matches to return. default is 50.
        :param matched: A set of donors ID that have already matched for this patient.
        :return: a dictionary of all matching donors and their matching properties.
        """
        if len(matched) >= cutof:
            return matched, 0, results_df

        # a loop that set the scores for all the matching candidates.
        patient_scores = {}
        # for hla_id in self._patients_graph.neighbors(patient): # AMIT DELETE
        for hla_id, genotype_matches in self._genotype_candidates[patient].items():  # AMIT ADD
            for prob, matches in genotype_matches.values():  # AMIT CHANGE
                # match_info = (probability of patient's genotype, number of matches to patient's genotype)
                if matches != 10 - mismatch:
                    continue

                # add the probabilities multiplication of the patient and all the donors that has this genotype
                # to their matching probabilities.
                for donor in self.__find_donor_from_geno(hla_id):
                    donor_prob = self._graph.get_edge_data(node1=hla_id, node2=donor, node1_id=True)
                    if donor in patient_scores:
                        patient_scores[donor][0] += prob * donor_prob
                        if donor_prob > patient_scores[donor][2]:
                            patient_scores[donor][1:] = [hla_id, donor_prob]

                    else:
                        patient_scores[donor] = [prob * donor_prob, hla_id, donor_prob]

        ids_scores = []
        count_matches = 0

        # sort matching according to their probability
        for donor in patient_scores.keys():
            # do not count or match to an already matched donors.
            if donor in matched or patient_scores[donor][0] < threshold:
                continue

            count_matches += 1
            ids_scores.append((donor, patient_scores[donor][0]))

        ids_scores.sort(reverse=True, key=lambda x: x[1])

        add_donors = {col: [] for col in results_df.columns.values.tolist()}

        # write matching donors to results.
        for donor, score in ids_scores:
            if len(matched) >= cutof:
                break
            matched.add(donor)
            self.__append_matching_donor(add_donors, donors_info, patient, donor, score * 100, mismatch)

        results_df = pd.concat([results_df, pd.DataFrame(add_donors)], ignore_index=True)

        if self.verbose:
            print_time(f"({mismatch} MMs) Found {count_matches} matches")

        return matched, count_matches, results_df # 3433825

    def __append_matching_donor(self, add_donors: Dict, donors_info: Iterable[str],
                                patient: int, donor: int, match_prob: float, mm_number: int) -> None:
        """add a donor to the matches dictionary"""

        compare_commons = locuses_match_between_genos(self.patients[patient], self.get_most_common_genotype(donor))

        add_donors["Patient_ID"].append(patient)
        add_donors["Donor_ID"].append(donor)
        allele_prob = self.probability_to_allele(don_id=donor, pat_geno=self.patients[patient])
        add_donors["Match_Probability_A_1"].append(allele_prob[0])
        add_donors["Match_Probability_A_2"].append(allele_prob[1])
        add_donors["Match_Probability_B_1"].append(allele_prob[2])
        add_donors["Match_Probability_B_2"].append(allele_prob[3])
        add_donors["Match_Probability_C_1"].append(allele_prob[4])
        add_donors["Match_Probability_C_2"].append(allele_prob[5])
        add_donors["Match_Probability_DQB1_1"].append(allele_prob[6])
        add_donors["Match_Probability_DQB1_2"].append(allele_prob[7])
        add_donors["Match_Probability_DRB1_1"].append(allele_prob[8])
        add_donors["Match_Probability_DRB1_2"].append(allele_prob[9])

        add_donors["Match_Between_Most_Commons_A"].append(compare_commons[0])
        add_donors["Match_Between_Most_Commons_B"].append(compare_commons[1])
        add_donors["Match_Between_Most_Commons_C"].append(compare_commons[2])
        add_donors["Match_Between_Most_Commons_DQB"].append(compare_commons[3])
        add_donors["Match_Between_Most_Commons_DRB"].append(compare_commons[4])

        add_donors["Matching_Probability"].append(match_prob)
        add_donors["Number_Of_Mismatches"].append(mm_number)
        add_donors["Permissive/Non-Permissive"].append("-")  # TODO: add permissiveness algorithm

        # add the other given fields to the results
        for field in donors_info:
            add_donors[field].append(DONORS_DB.loc[donor, field])

    @property
    def patients_graph(self):
        return self._patients_graph