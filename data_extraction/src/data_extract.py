#!/usr/bin/env python3
# coding: utf-8

import multiprocessing
import os

from src.data_extract_utils import *


def get_all_files(dir):
    filelist = []

    for root, dirs, files in os.walk(dir):
        for file in files:
            filelist.append(os.path.join(root, file))

    return filelist


def process_file(fname, onlyME=True):
    print("Worker %d is processing file %s\n" % (os.getpid(), fname))
    trial_name = fname[len(database_dir):].split('/')

    if onlyME and trial_name[0][-2:] == "MI":
        print("Worker %d is SKIPPING file %s\n" % (os.getpid(), fname))
        return

    run_idx = trial_name[1].split('.')
    run_idx = run_idx[0].split('_')
    trial_name = trial_name[0] + "_" + run_idx[-1]

    pwd = os.getcwd()
    processed_file_dir = pwd + "/processed_data"
    try:
        if not os.path.isdir(processed_file_dir):
            os.mkdir(processed_file_dir)
    except OSError as error:
        print("Cannot create directory. Exiting...")
        print(error)

    seq_v_class_fname = processed_file_dir + "/" + trial_name + ".pickle"
    reject_trials_fname = processed_file_dir + "/" + trial_name + "_reject_trials.pickle"
    noneeg_seqs_v_class_fname = processed_file_dir + "/" + trial_name + "_noneeg.pickle"

    t1 = time.time()
    HDR, data = read_data(fname)
    seqs_v_class_map = segregate_data_into_classes(HDR, data)
    noneeg_seqs_v_class_map = segregate_noneeg_data_into_classes(HDR, data)
    rejected_trials = reject_trials_from_map(seqs_v_class_map)

    rejected_trials_map = {}
    for key in seqs_v_class_map.keys():
        rejected_trials_map[key] = np.zeros(len(seqs_v_class_map[key]), dtype='uint8')

    for l in rejected_trials:
        rejected_trials_map[l[0]][l[1]] = 1

    pickle_data(seqs_v_class_map, seq_v_class_fname)
    pickle_data(rejected_trials_map, reject_trials_fname)
    pickle_data(noneeg_seqs_v_class_map, noneeg_seqs_v_class_fname)
    print("Worker %d is done processing file in %f s\n" %
          (os.getpid(), time.time() - t1))


database_dir = "/home/sweet/1-workdir/eeg001-2017/"
filelist = get_all_files(database_dir)
MAX_NPROCESS = multiprocessing.cpu_count() // 2

if __name__ == "__main__":
    print("There are a total of %d files in %s\n" % (len(filelist), database_dir))
    print("**********START PROCESSING ALL FILES**********")
    print("MAX NUMBER OF PROCESS = %d" % (MAX_NPROCESS))

    p = multiprocessing.Pool(MAX_NPROCESS)
    p.map(process_file, filelist)
