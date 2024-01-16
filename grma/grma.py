import json
from collections import defaultdict
import pickle
from donorsgraph.build_donors_graph import BuildMatchingGraph
from match import Graph, find_matches
import csv
import os
from grim import grim
from pathlib import Path


def load_patients_data(patients_file):
    """
        Load patient data from a file.

        Args:
            patients_file (str): Path to the patients data file.

        Returns:
            list: List of lines containing patient data.
        """
    with open(patients_file, 'r') as file:
        lines = file.readlines()
    return lines

def preprocess_patient_data(lines):
    """
        Preprocess patient data and group by patient ID.

        Args:
            lines (list): List of lines containing patient data.

        Returns:
            tuple: A tuple containing:
                - dict: Dictionary mapping patient IDs to their data.
                - dict: Dictionary mapping old patient IDs to new ones.
        """
    patient_data = defaultdict(list)
    new_patient_ids = {}
    patient_counter = 1

    for line in lines:
        parts = line.strip().split(',')
        old_patient_id = parts[0].split(':')[0]
        if old_patient_id not in new_patient_ids:
            new_patient_ids[old_patient_id] = patient_counter
            patient_counter += 1
        new_patient_id = new_patient_ids[old_patient_id]
        new_line = line.replace(old_patient_id, f'{new_patient_id:04d}')
        patient_data[new_patient_id].append(new_line)

    return patient_data, new_patient_ids

def create_patient_files(patient_data):
    """
        Create patient files from grouped patient data.

        Args:
            patient_data (dict): Dictionary mapping patient IDs to their data.
        """
    base_directory = './patients_dir_temp'
    os.makedirs(base_directory, exist_ok=True)

    for patient_id, data in patient_data.items():
        filename = f'patient_{patient_id}.txt'
        filepath = os.path.join(base_directory, filename)

        counter = 1
        while os.path.exists(filepath):
            filename = f'patient_{patient_id}_{counter}.txt'
            filepath = os.path.join(base_directory, filename)
            counter += 1

        with open(filepath, 'w') as file:
            file.writelines(data)

def save_new_patient_ids(new_patient_ids):
    """
        Save the dictionary of new patient IDs to a pickle file.

        Args:
            new_patient_ids (dict): Dictionary mapping old patient IDs to new ones.
        """
    with open('new_patient_ids_for_D4.pkl', 'wb') as pickle_file:
        pickle.dump(new_patient_ids, pickle_file)

def process_and_save_results(patients_dir, donors_graph, cutof=100, threshold=0.1, result_dir='./result_dir'):
    """
        Process patient files for matching and save results.

        Args:
            patients_dir (str): Path to the directory containing patient files.
            donors_graph (Graph): Donors graph for matching.
            cutof (int, optional): Cutoff parameter for matching. Default is 100.
            threshold (float, optional): Threshold parameter for matching. Default is 0.1.
            result_dir (str, optional): Directory where result files will be saved. Default is './result_dir'.
        """
    os.makedirs(result_dir, exist_ok=True)

    for filename in os.listdir(patients_dir):
        if filename.endswith(".txt"):
            patient_file_path = os.path.join(patients_dir, filename)

            matching_results = find_matches(patient_file_path, donors_graph, cutof=cutof, threshold=threshold)

            for patient, df in matching_results.items():
                result_filename = os.path.join(result_dir, f"{patient}.csv")

                with open(result_filename, 'w', newline='') as result_file:
                    writer = csv.writer(result_file)
                    writer.writerow(df.columns)
                    writer.writerows(df.values)

def GetResultPatients(config_grim_file, path_donors_graph, dir_result, cutof=100, threshold=0.1, build_grim_graph=True):
    """
        Process patient data, perform matching, and save results.

        Args:
            patients_file (str): Path to the patients data file.
            path_donors_graph (str): Path to the donors graph pickle file.
            dir_result (str): Directory where result files will be saved.
            cutof (int, optional): Cutoff parameter for matching. Default is 100.
            threshold (float, optional): Threshold parameter for matching. Default is 0.1.
        """
    donors_graph = Graph.from_pickle(path_donors_graph)
    with open(config_grim_file) as f:
        json_conf = json.load(f)
    output_dir = json_conf.get("imuptation_out_path", "output")
    patients_file =  output_dir + json_conf.get("imputation_out_umug_freq_filename")
    run_grim(config_grim_file,build_grim_graph)
    # add code that use imputation for patients file.
    # after_imputation_patients_file = imputation(patients_file) , and after that change the patients_file to after_imputation_patients_file
    lines = load_patients_data(patients_file)
    patient_data, new_patient_ids = preprocess_patient_data(lines)
    create_patient_files(patient_data)
    save_new_patient_ids(new_patient_ids)
    process_and_save_results('./patients_dir_temp', donors_graph, cutof=cutof, threshold=threshold, result_dir=dir_result)
    # in the end return to the files result the name id or maybe its enough that the name of the file is the name of the id???


def BuildDonorsGraph(donors_dir, result_dir):

    # need to see how the donors csv looks like because i need to split to one file per donor!!!!!
    build_matching = BuildMatchingGraph(donors_dir)
    build_matching.to_pickle(result_dir)





def run_grim( grim_config_path, build_grim_graph=True):
    """
    run 3 parts of gram (gram, grim, post-gram)
    :param input_file_path: file with input from user
    :param alleles_names: ['A', 'B', 'C', 'DRB1', 'DQB1']
    :param output_dir: output directory path
    :param is_serology: whether the input data is serology
    :param race_dict: a dictionary that contains the races of the families that the user inserted
    :param grim_config_path: path the grim configuration file
    :param build_grim_graph: flag - whether run the function 'grim.graph_freqs'
           (that build the frequencies graph for grimm). its required in the first running only.
    :param open_ambiguity_sim: relevalnt in simulation files
    """

    if build_grim_graph:
        grim.graph_freqs(conf_file=grim_config_path)
    grim.impute(conf_file=grim_config_path)








if __name__ == '__main__':
    #Example usage
    GetResultPatients('minimal-configuration.json', 'donors_graph.pkl', './result_dir', cutof=100, threshold=0.1)




