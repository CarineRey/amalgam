#!/usr/bin/python
# coding: utf-8

# File: SeqFilter.py
# Created by: Carine Rey
# Created on: February 2017
#
#
# Copyright 2017 Carine Rey
# This software is a computer program whose purpose is to assembly
# sequences from RNA-Seq data (paired-end or single-end) using one or
# more reference homologous sequences.
# This software is governed by the CeCILL license under French law and
# abiding by the rules of distribution of free software.  You can  use,
# modify and/ or redistribute the software under the terms of the CeCILL
# license as circulated by CEA, CNRS and INRIA at the following URL
# "http://www.cecill.info".
# As a counterpart to the access to the source code and  rights to copy,
# modify and redistribute granted by the license, users are provided only
# with a limited warranty  and the software's author,  the holder of the
# economic rights,  and the successive licensors  have only  limited
# liability.
# In this respect, the user's attention is drawn to the risks associated
# with loading,  using,  modifying and/or developing or reproducing the
# software by the user in light of its specific status of free software,
# that may mean  that it is complicated to manipulate,  and  that  also
# therefore means  that it is reserved for developers  and  experienced
# professionals having in-depth computer knowledge. Users are therefore
# encouraged to load and test the software's suitability as regards their
# requirements in conditions enabling the security of their systems and/or
# data to be ensured and,  more generally, to use and operate it in the
# same conditions as regards security.
# The fact that you are presently reading this means that you have had
# knowledge of the CeCILL license and that you accept its terms.

import os
import re
import sys
import time
import tempfile
import shutil
import logging
import argparse
import subprocess

import Aligner
import PhyloPrograms

from ete2 import Tree

start_time = time.time()


#SeqFilter.py -tmp example/working_dir/_bistro/tmp/015040fd9b1c0ddf57563c15db351e9d/dest/tmp \
# -log example/working_dir/_bistro/tmp/015040fd9b1c0ddf57563c15db351e9d/dest/tmp/SeqFilter.fam_test.log \
#   -ali example/working_dir/_bistro/cache/b9b56c6117af9be3c28f38d6ea3dba15/fam_test.fa
#   -t /home/crey02/Documents/Projets/Convergences/Pipeline/AMALGAM/amalgam_git/example/working_dir/_bistro/cache/b9b56c6117af9be3c28f38d6ea3dba15/fam_test.tree \
#   --realign_ali --resolve_polytomy -sptorefine Mus_musculus,Mesocricetus_auratus
#   -sp2seq example/working_dir/_bistro/cache/b9b56c6117af9be3c28f38d6ea3dba15/fam_test.sp2seq.txt
#   -out example/working_dir/_bistro/tmp/015040fd9b1c0ddf57563c15db351e9d/dest/fam_test


### Option defining
parser = argparse.ArgumentParser(prog="SeqFilter.py",
                                 description='''Remove sequences if they have a percentage of alignement with its sister sequence under a given threshold.''')
parser.add_argument('--version', action='version', version='%(prog)s 1.0')


##############
requiredOptions = parser.add_argument_group('Required arguments')
requiredOptions.add_argument('-ali', '--alignment', type=str,
                             help='Alignment filename.', required=True)
requiredOptions.add_argument('-t', '--tree', type=str,
                             help='Gene tree filename.')
requiredOptions.add_argument('-sp2seq', type=str,
                             help='Link file name. A tabular file, each line correspond to a sequence name and its species. File names delimited by comas.', required=True)
requiredOptions.add_argument('-out', '--output_prefix', type=str, default="./output",
                   help="Output prefix (Default ./output)")
##############


##############
Options = parser.add_argument_group('Options')
Options.add_argument('-sptorefine', type=str, default="",
                    help="A list of species names delimited by commas. These species will be concerned by merging. (default: All species will be concerned)")
Options.add_argument('--realign_ali', action='store_true', default=False,
                    help="Realign the ali even if no sequences to add. (default: False)")
Options.add_argument('--resolve_polytomy', action='store_true', default=False,
                    help="resolve polytomy. (default: False)")
Options.add_argument('--filter_threshold', type=float, default=0,
                    help="Sequence with a percentage of alignement with its sister sequence is discarded (default: 0)")
Options.add_argument('-tmp', type=str,
                    help="Directory to stock all intermediary files for the job. (default: a directory in /tmp which will be removed at the end)",
                    default="")
Options.add_argument('-log', type=str, default="SeqFilter.log",
                   help="a log file to report avancement (default: seq_filter.log)")
Options.add_argument('--debug', action='store_true', default=False,
                   help="debug mode, default False")

### Option parsing
args = parser.parse_args()


### Read arguments
StartingAlignment = args.alignment
SpToRefine = []
if args.sptorefine:
    SpToRefine = set(args.sptorefine.split(","))

TreeFilename = args.tree

Sp2SeqFilename = args.sp2seq

### Set up the log directory
if args.log:
    LogDirName = os.path.dirname(args.log)
    if not os.path.isdir(LogDirName) and LogDirName:
        os.makedirs(LogDirName)

### Set up the logger
LogFile = args.log
# create logger
logger = logging.getLogger("main")
logger.setLevel(logging.INFO)
# create file handler which logs even debug messages
fh = logging.FileHandler(LogFile)
fh.setLevel(logging.INFO)
# create console handler with a higher log level
ch = logging.StreamHandler()
if args.debug:
    ch.setLevel(logging.DEBUG)
    fh.setLevel(logging.DEBUG)
    logger.setLevel(logging.DEBUG)
else:
    ch.setLevel(logging.WARNING)
# create formatter and add it to the handlers
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
fh.setFormatter(formatter)
ch.setFormatter(formatter)
# add the handlers to the logger
logger.addHandler(fh)
logger.addHandler(ch)


logger.debug(sys.argv)

### Set up the working directory
if args.tmp:
    if os.path.isdir(args.tmp):
        logger.info("The temporary directory %s exists", args.tmp)
    else:
        logger.info("The temporary directory %s does not exist, it will be created", args.tmp)
        os.makedirs(args.tmp)
    TmpDirName = args.tmp
else:
    TmpDirName = tempfile.mkdtemp(prefix='tmp_SeqFilter')

def end(ReturnCode):
    ### Remove tempdir if the option --tmp have not been use
    if not args.tmp:
        logger.debug("Remove the temporary directory")
        #Remove the temporary directory :
        if "tmp_SeqIntegrator" in TmpDirName:
            shutil.rmtree(TmpDirName)
    logger.debug("--- %s seconds ---", str(time.time() - start_time))
    sys.exit(ReturnCode)

### Set up the output directory
if args.output_prefix:
    OutDirName = os.path.dirname(args.output_prefix)
    OutPrefixName = args.output_prefix
    if os.path.isdir(OutDirName):
        logger.info("The output directory %s exists", os.path.dirname(args.output_prefix))
    elif OutDirName: # if OutDirName is not a empty string we create the directory
        logger.info("The output directory %s does not exist, it will be created", os.path.dirname(args.output_prefix))
        os.makedirs(os.path.dirname(args.output_prefix))
else:
    logger.error("The output prefix must be defined")
    end(1)

### Check that input files exist

for inputfile in [StartingAlignment, TreeFilename, Sp2SeqFilename]:
    if not os.path.isfile(inputfile):
        logger.error(inputfile +" is not a file.")
        end(1)

StartingAli = StartingAlignment
StartingTree = TreeFilename
StartingSp2Seq = Sp2SeqFilename

TmpAli = "%s/tmp.fa" %TmpDirName

FinalAli = "%s.fa" %OutPrefixName
FinalTree = "%s.tree" %OutPrefixName
FinalSp2Seq = "%s.sp2seq.txt" %OutPrefixName


def write_in_file(String,Filename,mode = "w"):
    if mode in ["w","a"]:
        with open(Filename,mode) as File:
            File.write(String)

def cp(In, Out):
    (out, err) = ("", "")
    command = ["cp", In, Out]

    logger.debug(" ".join(command))
    p = subprocess.Popen(command,
                       stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE)
    (out, err) = p.communicate()
    if err:
        logger.error(err)

    return (out, err)

class Fasta(object):
    def __init__(self):
        self.d = {}

    def __str__(self):
        string = []
        for s in self.d.values():
            string.extend([str(s)])
        return("".join(string))

    def append(self,new_sequence):
        assert isinstance(new_sequence, Sequence), "Sequence must belong to the Sequence class"
        self.d[new_sequence.Name] = new_sequence

    def get(self, name, default=""):
        if name in self.d.keys():
            return self.d[name].Sequence
        else:
            return default

    def read_fasta(self, FastaFilename = "" , String = ""):
        if String:
            Fasta = String.strip().split("\n")
        elif os.path.isfile(FastaFilename):
            with open(FastaFilename,"r") as File:
                Fasta = File.read().strip().split("\n")
        else:
            Fasta = []

        name = ""
        sequence_list = []

        for line in Fasta + [">"]:
            if re.match(">",line):
                # This is a new sequence write the previous sequence if it exists
                if sequence_list:
                    new_sequence = Sequence()
                    new_sequence.Name = name
                    new_sequence.Sequence = "".join(sequence_list)
                    self.append(new_sequence)
                    sequence_list = []

                name = line.split()[0][1:] # remove the >

            elif name != "":
                sequence_list.append(line)
            else:
                pass

    def filter_fasta(self, SelectedNames):
        FilteredFasta = Fasta()
        for s in self.d.values():
            if s.Name in SelectedNames:
                FilteredFasta.append(s)
        return FilteredFasta

    def dealign_fasta(self):
        DealignedFasta = Fasta()
        for s in  self.d.values():
            s.Sequence = s.Sequence.replace("-", "")
            DealignedFasta.append(s)
        return DealignedFasta

    def write_fasta(self, OutFastaFile):
        # Write all sequences in the file
        write_in_file(str(self), OutFastaFile)


class Sequence(object):
    def __init__(self,):
        self.Name = ""
        self.Sequence = ""

        ### Caracteristics
        self.Complement = False

    def __str__(self):
        return(">" + self.Name + "\n" + '\n'.join(self.Sequence[i:i+60] for i in range(0, len(self.Sequence), 60)) + "\n")


if args.filter_threshold > 0:
    logger.info("All sequences with a percentage of alignement with its sister sequence under %s will be discarded.", args.filter_threshold)
    sequenceTodiscard = []
    sequenceTokeep = []

    #Read fasta
    prefilter_fasta = Fasta()
    prefilter_fasta.read_fasta(FastaFilename = StartingAli)

    #Read tree
    tree = Tree(StartingTree)

    #Read seq2sp
    list_refineseq = []
    list_otherseq = []
    seq2sp_dict = {}
    with open(StartingSp2Seq,"r") as sp2seqFile:
        lines = sp2seqFile.read().strip().split("\n")
        for line in lines:
            (sp, seq) = line .split(":")
            seq2sp_dict[seq] = sp
            if sp in SpToRefine:
                list_refineseq.append(seq)
            else:
                list_otherseq.append(seq)
    
    sequenceTokeep.extend(list_otherseq)

    for seqR_name in list_refineseq:
        m = 10000
        closest_name = ""
        # get the closest sequence not in sp to refine
        for seqO_name in list_otherseq:
            d = tree.get_distance(seqR_name, seqO_name)
            if d <= m:
                closest_name = seqO_name

        seqR_sequence = prefilter_fasta.get(seqR_name)
        closest_sequence = prefilter_fasta.get(closest_name)

        #Count number of aligned position
        l=0
        c=0
        for i in range(len(closest_sequence)):
            if closest_sequence[i] != "-":
                l +=1
                if seqR_sequence[i] != "-":
                    c+=1

        ali_len = c/float(l) *100

        if ali_len > args.filter_threshold:
            sequenceTokeep.append(seqR_name)
        else:
            sequenceTodiscard.append(seqR_name)
            logger.info("%s will be discarded because its alignemnt lenght (%s) is < to %s", seqR_name, ali_len, args.filter_threshold)

    #Filter fasta and sp2seq
    if len(sequenceTodiscard) > 0:
        filteredfasta = prefilter_fasta.filter_fasta(sequenceTokeep)
        lines = []
        for (seq, sp) in seq2sp_dict.items():
            if seq not in sequenceTodiscard:
                line = "%s:%s\n" %(sp, seq)
                lines.append(line)
        with open(FinalSp2Seq,"w") as sp2seqFile:
            sp2seqFile.write("".join(lines))

        if not args.realign_ali:
            filteredfasta.write_fasta(FinalAli)
        else:
            AfterfilteringFasta = TmpAli
            filteredfasta.write_fasta(AfterfilteringFasta)
            ### Realign the final alignment
            MafftProcess = Aligner.Mafft(TmpAli)
            MafftProcess.Maxiterate = 1000
            MafftProcess.QuietOption = True
            MafftProcess.OutputFile = FinalAli

            if os.path.isfile(TmpAli):
                logger.info("Realign the filtered alignment")
                _ = MafftProcess.launch()
                StartingAlignment = MafftProcess.OutputFile
            else:
                logger.error("%s is not a file.", TmpAli)
                end(1)

        ### Built a tree with the final alignment
        logger.info("Built a tree with the final alignment")
        FinalFasttreeProcess = PhyloPrograms.Fasttree(FinalAli)
        FinalFasttreeProcess.Nt = True
        FinalFasttreeProcess.Gtr = True
        FinalFasttreeProcess.Gamma = True
        FinalFasttreeProcess.OutputTree = FinalTree

        if os.path.isfile(FinalAli):
            FinalFasttreeProcess.get_output()
        else:
            logger.error("%s is not a file. There was an issue with the previous step.", FinalAli)
            end(1)

        ### Resolve Polytomy
        if not os.path.isfile(FinalTree):
            logger.error("%s is not a file. There was an issue with the previous step.", FinalTree)
            end(1)
        if not os.path.getsize(FinalTree):
            logger.error("%s is empty. There was an issue with the previous step.", FinalTree)
            end(1)

        if args.resolve_polytomy:
            logger.info("Resolve polytomy in %s", FinalTree)
            t = Tree(FinalTree)
            t.resolve_polytomy(recursive=True)
            t.write(format=0, outfile=FinalTree)

        if not os.path.isfile(FinalTree):
            FinalFasttreeProcess.get_output()
            logger.error("%s is not a file. There was an issue with the previous step.", FinalTree)
            end(1)

        if not os.path.getsize(FinalTree):
            logger.error("%s is empty. There was an issue with the previous step.", FinalTree)
            end(1)

    else:
        cp(StartingAli, FinalAli)
        cp(StartingSp2Seq, FinalSp2Seq)
        cp(StartingTree, FinalTree)
        end(0)

else:
    logger.warning("No threshol, input files will be output files.")
    cp(StartingAli, FinalAli)
    cp(StartingSp2Seq, FinalSp2Seq)
    cp(StartingTree, FinalTree)
    end(0)
