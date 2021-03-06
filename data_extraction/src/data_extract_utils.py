import bz2
import pickle
import sys
import time

from scipy import signal

import src.biosig as biosig
from src.biosig import HDR_TYPE
from src.data_preprocess import *

# map event type to event label
# class 1: 0x600 = 1536 (elbow flexion)
# class 2: 0x601 = 1537 (elbow extension)
# class 3: 0x602 = 1538 (supination)
# class 4: 0x603 = 1539 (pronation)
# class 5: 0x604 = 1540 (hand close)
# class 6: 0x605 = 1541 (hand open)
# class 7: 0x606 = 1542 (rest)

# also, there are event types that signify start of trials, computer beep, cross on screen
# 0x300 = 768 (start of trial)
# 0x311 = 785 (beep)
# 0x312 = 786 (cross on screen)
# numbers that are OR-ed with 0x8000 signify end of event.
event_map = {
    1536: 1,
    1537: 2,
    1538: 3,
    1539: 4,
    1540: 5,
    1541: 6,
    1542: 7
}


def read_data(f_name):
    t1 = time.time()
    HDR = HDR_TYPE()
    HDR = biosig.sopen(f_name, 'r', HDR)
    # print("Read header of %s in %f s\n" % (f_name, time.time()-t1))

    t1 = time.time()
    data = biosig.sread(HDR, HDR.NRec, 0)
    # print("Read data of %s in %f s\n" % (f_name, time.time()-t1))

    biosig.sclose(HDR)

    return HDR, data


def segregate_data_into_classes(HDR, data):
    t1 = time.time()

    seqs_v_class_map = {}

    for key in event_map:
        seqs_v_class_map[event_map[key]] = []

    event_hit = 0
    start_frame = 0
    end_frame = 0
    for i in range(len(HDR.EVENT.TYP)):
        code = HDR.EVENT.TYP[i]
        if event_hit == 0 and code in event_map:
            event_hit = code
            start_frame = HDR.EVENT.POS[i]

        if code == event_hit + 32768:
            end_frame = HDR.EVENT.POS[i]
            seqs_v_class_map[event_map[event_hit]].append(
                signal_processing(data[start_frame:end_frame + 1, 0:64]))
            event_hit = 0

    # print("Finished segregating data into classes in %f s\n" % (time.time()-t1))

    return seqs_v_class_map


def segregate_noneeg_data_into_classes(HDR, data):
    t1 = time.time()

    seqs_v_class_map = {}

    for key in event_map:
        seqs_v_class_map[event_map[key]] = []

    event_hit = 0
    start_frame = 0
    end_frame = 0
    for i in range(len(HDR.EVENT.TYP)):
        code = HDR.EVENT.TYP[i]
        if event_hit == 0 and code in event_map:
            event_hit = code
            start_frame = HDR.EVENT.POS[i]

        if code == event_hit + 32768:
            end_frame = HDR.EVENT.POS[i]
            seqs_v_class_map[event_map[event_hit]].append(
                signal_processing(data[start_frame:end_frame + 1, 64:]))
            event_hit = 0

    # print("Finished segregating data into classes in %f s\n" % (time.time()-t1))

    return seqs_v_class_map


def butter_bandpass(lowcut, highcut, fs, order=5):
    nyq = 0.5 * fs
    low = lowcut / nyq
    high = highcut / nyq
    b, a = signal.butter(order, [low, high], btype='band')
    return b, a


def butter_bandpass_filter(data, lowcut, highcut, fs, order=5):
    b, a = butter_bandpass(lowcut, highcut, fs, order=order)
    y = signal.lfilter(b, a, data)
    return y


def signal_processing(data):
    data = signal.decimate(data, 4, 5, axis=0)

    return data


# compress segregated data into zip file
def pickle_data(data, f_name, is_compress=False):
    t1 = time.time()
    f = open(f_name, "wb")
    i_str = pickle.dumps(data)
    if is_compress:
        i_str = bz2.compress(i_str)
    f_size = sys.getsizeof(i_str) / 1048576
    f.write(i_str)
    f.close()


def reject_trials_from_map(seqs_v_class_map):
    # set parameters
    nBins = 20
    threshold = 5  # in standard deviation
    thresholdSig = 200  # in uV
    copyLib = True
    EOG_Chann = [61, 62, 63]

    rejChanProb = np.array([[]])
    rejChanKurt = np.array([[]])
    rejChanThresh = np.array([[]])

    # TODO: There is some bug here when doing
    # counts, bin_edges = np.histogram(sigTmp,nBins,(sigTmp.min()-1, sigTmp.max()+1))
    # in data_preprocess.py module
    # ValueError: supplied range of [nan, nan] is not finite
    # rejects based on joint probability
    try:
        rejChanProb = markArtifactJointProb(seqs_v_class_map, nBins, threshold)
    except:
        print("Not successful in mark artifact joint prob")

    # reject based on kurtosis
    try:
        rejChanKurt = markArtifactKurtosis(seqs_v_class_map, threshold)
    except:
        print("Not successful in mark artifact kurtosis")

    # reject based on eeg signal value
    try:
        rejChanThresh = markArtifactSigVal(seqs_v_class_map, thresholdSig)
    except:
        print("Not successful in mark artifact kurtosis")

    # concatenate the index of the rejected channels
    rejChan = np.zeros((1, 3), dtype=int)
    rejChan = np.concatenate((rejChan, rejChanProb), axis=0) if np.size(rejChanProb) > 1 else rejChan
    rejChan = np.concatenate((rejChan, rejChanKurt), axis=0) if np.size(rejChanKurt) > 1 else rejChan
    rejChan = np.concatenate((rejChan, rejChanThresh), axis=0) if np.size(rejChanThresh) > 1 else rejChan
    rejChan = np.delete(rejChan, (0), axis=0)

    # get the trials that should be rejected because the EOG detected eye movement
    rejTrial = np.zeros((1, 3), dtype=int)
    c = []
    for i in range(0, np.shape(rejChan)[0]):
        if rejChan[i, 2] in EOG_Chann:
            rejTrial = np.append(rejTrial, [rejChan[i, :]], axis=0)

    rejTrial = np.delete(rejTrial, (0), axis=0)

    # set the rejected channels to 0
    # seqs_v_class_map_noArtifact = rejectChannels(seqs_v_class_map, rejChan, copyLib)

    # reject entire trials by setting all values to 0 when the EOG of that trial is rejected as an artifact
    return rejTrial
