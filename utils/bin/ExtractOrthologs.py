#!/usr/bin/python
# coding: utf-8

# File: ExtractOrthologs.py
# Created by: Carine Rey
# Created on: June 2017
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

import sys
import os
import glob
import logging
import re


### Set up the logger
# create logger with 'spam_application'
logger = logging.getLogger('ExtractOrthologs')
logger.setLevel(logging.WARN)
# create file handler which logs even debug messages
# create console handler with a higher log level
ch = logging.StreamHandler()
ch.setLevel(logging.WARN) #WARN
# create formatter and add it to the handlers
formatter = logging.Formatter('%(name)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
# add the handlers to the logger
logger.addHandler(ch)

logger.debug(" ".join(sys.argv))

if not len(sys.argv) in [3,4,5]:
    logger.error("3 or 4 or 5 arguments are required")
    sys.exit(1)

sep = "\t"
out_dir = sys.argv[1]
sp2seq_dir = sys.argv[2]


if len(sys.argv) >= 4:
    ortho_dir = sys.argv[3]
    ### Check input data
    if not os.path.isdir(ortho_dir):
        logger.error("The orthologs directory %s does not exist", ortho_dir)
        sys.exit(1)
else:
    ortho_dir = ""
if len(sys.argv) >= 5:
    RefinedSpecies = set(sys.argv[4].split(","))
else:
    RefinedSpecies = ""



if not os.path.isdir(sp2seq_dir):
    logger.debug("The sequences2species diectory %s does not exist", sp2seq_dir)
    sys.exit(1)


### Set up the  output directory
for o_dir in [out_dir]:
    if os.path.isdir(o_dir):
        logger.info("The output directory %s exists", o_dir)
    else: # we create the directory
        logger.warning("The output directory %s does not exist, it will be created.", o_dir)
        os.makedirs(o_dir)

### Read all files in sp2seq_dir
def read_seq2species_file(Seq2Sp_dict, RefinedSpecies, File):
    logger.debug("Read %s", File)
    fam = os.path.basename(File).split('.')[0]

    if os.path.isfile(File):
        f = open(File, "r")
        for line in f:
            line = line.replace("\n", "")
            if line.replace(":","") == line:
                logger.debug("Line (%s) has a problem", line)
            else:
                (sp, seq) = line.split(":")
                Seq2Sp_dict[seq] = (sp, fam)
        f.close()


    return (Seq2Sp_dict)

Seq2Sp_dict = {}
for f in glob.glob("%s/*sp2seq.txt" %sp2seq_dir):
    Seq2Sp_dict  = read_seq2species_file(Seq2Sp_dict, RefinedSpecies, f)

SeqSpLink_File = "%s/all_fam.seq2sp.tsv" %(out_dir)

if not ortho_dir:
    with open(SeqSpLink_File, "w") as f_rewrite:
        for (seq,(sp, fam)) in Seq2Sp_dict.items():
            f_rewrite.write("\n".join("%s%s%s" %(seq, sep, sp)) + "\n")

    sys.exit(0)


### Read all orthologs file in ortho_dir
def read_ortho_file(OrthoFile):
    logger.debug("Read %s", OrthoFile)
    name = ""
    OrthoDict = {}
    Seqs = []
    if os.path.isfile(OrthoFile):
        f = open(OrthoFile, "r")
        for line in f:
            if re.match('[\s\n]', line):
                pass
            elif re.match("ORTHOLOGY RELATIONSHIP: ", line):
                line = line.replace("ORTHOLOGY RELATIONSHIP: ","").strip()
                o_groups = line.replace(", ",",").replace(" <===> ", ",").split(",")
                o_groups_size = len(o_groups)
                OrthoDict.setdefault(o_groups_size, [])
                OrthoDict[o_groups_size].append(o_groups)
                Seqs.extend(o_groups)
            else:
                pass
        f.close()
    Seqs = set(Seqs)
    return (OrthoDict, Seqs)


### Define orthology relationships for each seq:

def define_orthologs_groups(OrthoDict, ListSeqs, Seq2Sp_dict = {}):
    ResDict = {}
    SizeRange = OrthoDict.keys()
    MinSize = min(SizeRange)
    MaxSize = max(SizeRange)

    MaxOrthogGroups_dict = {}
    MaxOrthogGroups_i = 1

    for Seq in ListSeqs:
        SeqFromRefinedSpecies = False
        (Sp, Fam) = Seq2Sp_dict[Seq]
        if Sp in RefinedSpecies:
            SeqFromRefinedSpecies = True
        MinOrthogGroups = []
        MinOrthogGroupsR = []
        MaxOrthogGroups = []

        i = MinSize
        while (not MinOrthogGroups) and (i <= MaxSize):
            if i not in SizeRange:
                i+=1
                continue
            for g in OrthoDict[i]:
                #print OrthoDict[i]
                if Seq in g:
                    if SeqFromRefinedSpecies:
                        if all([Seq2Sp_dict[s][0] in RefinedSpecies for s in g]):
                            continue
                    if SeqFromRefinedSpecies:
                        for s in g:
                            if s != Seq:
                                if not Seq2Sp_dict[s][0] in RefinedSpecies:
                                    MinOrthogGroups.append(s)
                                else:
                                    MinOrthogGroupsR.append(s)
                    else:
                        MinOrthogGroups = [s for s in g if s != Seq]
                    break
            i+=1

        i = MaxSize
        while (not MaxOrthogGroups)  and (i > MinSize):
            if i not in SizeRange:
                i-=1
                continue
            for g in OrthoDict[i]:
                if Seq in g:
                    MaxOrthogGroups = g
                    MaxOrthogGroups.sort()
                    if not ",".join(MaxOrthogGroups) in MaxOrthogGroups_dict.keys():
                        MaxOrthogGroups_dict[",".join(MaxOrthogGroups)] = MaxOrthogGroups_i
                        MaxOrthogGroups_i += 1
                    break
            i-=1
        ResDict[Seq] = [Sp, MinOrthogGroups, MinOrthogGroupsR, MaxOrthogGroups_dict[",".join(MaxOrthogGroups)]]

    return ResDict

def write_orthologs_groups(OrthoDefDict):
    String_ortho=[]
    String_sp_seq=[]
    for Seq in OrthoDefDict:
        [Sp, MinOrthogGroups, MinOrthogGroupsR, MaxOrthogGroups_i] = OrthoDefDict[Seq]

        if MinOrthogGroupsR:
                        String_ortho.append("\t".join([Seq, "".join([",".join(MinOrthogGroups),",[",",".join(MinOrthogGroupsR),"]"])]))
        else:
                        String_ortho.append("\t".join([Seq, ",".join(MinOrthogGroups)]))

        String_sp_seq.append("\t".join([Seq, Sp, Fam, "s%i" %(MaxOrthogGroups_i)]))

    return ["\n".join(String_ortho),"\n".join(String_sp_seq)]


SeqSpLink_File = "%s/all_fam.seq2sp.tsv" %(out_dir)
Orthologs_File = "%s/all_fam.orthologs.tsv" %(out_dir)
with open(Orthologs_File, "w") as o_write:
    with open(SeqSpLink_File, "w") as s_write:
        for f in glob.glob("%s/*orthologs.txt" %ortho_dir):
            Fam = os.path.basename(f).split('.')[0]
            (OrthoDict, Seqs) = read_ortho_file(f)
            OrthoDefDict = define_orthologs_groups(OrthoDict, Seqs, Seq2Sp_dict)
            o_string, s_string = write_orthologs_groups(OrthoDefDict)
            o_write.write(o_string+"\n")
            s_write.write(s_string+"\n")

sys.exit(0)

