#!/usr/bin/python
# coding: utf-8
import os
import sys
import time
import tempfile
import shutil
import logging
import argparse
import subprocess

from lib import PhyloPrograms
from lib import Aligner

start_time = time.time()

### Option defining
parser = argparse.ArgumentParser(prog = "SeqIntegrator.py",
                                 description='''
    Add sequences to an alignment and merge sequences from defined species if they are phylogenetically enough close.''')
parser.add_argument('--version', action='version', version='%(prog)s 1.0')


##############
requiredOptions = parser.add_argument_group('Required arguments')
requiredOptions.add_argument('-ali', '--alignment', type=str,
                             help='Alignment file name.', required=True)
requiredOptions.add_argument('-fa', '--fasta', type=str, nargs='*',
                             help='Fasta file name', required=True)
requiredOptions.add_argument('-seq2tax', '--sequence2taxon', type=str, nargs='*',
                             help='Link file name. A tabular file, each line correspond to a sequence name and its species. ', required=True)
requiredOptions.add_argument('-out', '--output_prefix',  type=str, default = "./output",
                   help = "Output prefix (Default ./output)")
##############


##############
Options = parser.add_argument_group('Options')
Options.add_argument('--realign_ali',  action='store_true',
                    help = "A fasta file will be created at each iteration. (default: False)")
Options.add_argument('-tmp',  type=str,
                    help = "Directory to stock all intermediary files for the apytram run. (default: a directory in /tmp which will be removed at the end)",
                    default = "" )
Options.add_argument('-log', type=str, default="seqintegrator.log",
                   help = "a log file to report avancement (default: seq_integrator.log)")

### Option parsing
args = parser.parse_args()

### Read arguments
StartingAlignment = args.alignment

### Set up the log directory
if args.log:
    LogDirName = os.path.dirname(args.log)
    if not os.path.isdir(LogDirName) and LogDirName:
        os.makedirs(LogDirName)

### Set up the logger
LogFile = args.log
# create logger
logger = logging.getLogger("main")
logger.setLevel(logging.DEBUG)
# create file handler which logs even debug messages
fh = logging.FileHandler(LogFile)
fh.setLevel(logging.DEBUG)
# create console handler with a higher log level
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
# create formatter and add it to the handlers
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
fh.setFormatter(formatter)
ch.setFormatter(formatter)
# add the handlers to the logger
logger.addHandler(fh)
logger.addHandler(ch)

### Set up the working directory
if args.tmp:
    if os.path.isdir(args.tmp):
        logger.info("The temporary directory %s exists" %(args.tmp) )
    else:
        logger.info("The temporary directory %s does not exist, it will be created" % (args.tmp))
        os.makedirs(args.tmp)
    TmpDirName = args.tmp
else:
    TmpDirName = tempfile.mkdtemp(prefix='tmp_SeqIntegrator')

def end(ReturnCode):       
	### Remove tempdir if the option --tmp have not been use
	if not args.tmp:
		logger.debug("Remove the temporary directory")
		#Remove the temporary directory :
		if "tmp_SeqIntegrator" in TmpDirName:
			shutil.rmtree(TmpDirName)
	sys.exit(ReturnCode)
	
### Set up the output directory
if args.output_prefix:
    OutDirName = os.path.dirname(args.output_prefix)
    OutPrefixName = args.output_prefix
    if os.path.isdir(OutDirName):
        logger.info("The output directory %s exists" %(os.path.dirname(args.output_prefix)) )
    elif OutDirName: # if OutDirName is not a empty string we create the directory
        logger.info("The temporary directory %s does not exist, it will be created" % (os.path.dirname(args.output_prefix)))
        os.makedirs(os.path.dirname(args.output_prefix))
else:
    logger.error("The output prefix must be defined")
    end(1)

### Check that input files exist
if not os.path.isfile(StartingAlignment):
        logger.debug(StartingAlignment+" is not a file.")
        end(1)

StartingFastaFiles = []
for f in args.fasta:
	if os.path.isfile(f):
		StartingFastaFiles.append(f)

Seq2TaxonFiles = []	
for f in args.sequence2taxon:
	if os.path.isfile(f):
		Seq2TaxonFiles.append(f) 
        
### A function to cat input files
def cat(Files,OutputFile):
    (out, err, Output) = ("","","") 
    command = ["cat"]
   
    if len(Files) == 1:
        Output = Files[0]
    else:
        command.extend(Files)
        logger.debug(" ".join(command))
        p = subprocess.Popen(command,
                           stdout=open(OutputFile, 'w'),
                           stderr=subprocess.PIPE)
        (out, err) = p.communicate()
        if err:
            logger.error(err)
        Output = OutputFile
    return (out, err, Output)
    
# Check if their are seqeunces to add
if StartingFastaFiles and Seq2TaxonFiles:
	logger.info("Sequences to add")
	logger.debug(StartingFastaFiles)
	logger.debug(Seq2TaxonFiles)
	   
	### Concate all ses2taxon files and fasta files

	Seq2Taxon = "%s/StartingSeq2Taxon.txt" %(TmpDirName)
	StartingFasta = "%s/StartingFasta.fa" %(TmpDirName)
	logger.info("Concate all fasta files")
	(out, err, StartingFasta) = cat(StartingFastaFiles,StartingFasta)
	logger.info("Concate all seq2taxon files")
	(out, err, Seq2Taxon) = cat(Seq2TaxonFiles,Seq2Taxon)

	### Add the fasta file to the existing alignment
	logger.info("Add the fasta file to the existing alignment")
	MafftProcess = Aligner.Mafft(StartingAlignment)
	MafftProcess.AddOption = StartingFasta
	MafftProcess.AdjustdirectionOption = False
	MafftProcess.AutoOption = True
	MafftProcess.QuietOption = True
	MafftProcess.OutputFile = "%s/StartMafft.fa" %TmpDirName
	if os.path.isfile(StartingAlignment) and os.path.isfile(StartingFasta):
		(out,err) = MafftProcess.launch()
	else:
		logger.error("%s or %s is not a file" %(StartingAlignment,StartingFasta))
		end(1)

	#Remove _R_ add by mafft adjustdirection option
	#os.system("sed -i s/_R_//g %s" %MafftProcess.OutputFile)

	### Built a tree with the global alignment
	logger.info("Built a tree with the global alignment")
	FasttreeProcess = PhyloPrograms.Fasttree(MafftProcess.OutputFile)
	FasttreeProcess.Nt = True
	FasttreeProcess.Gtr = True
	FasttreeProcess.OutputTree = "%s/StartTree.tree" %TmpDirName
	if os.path.isfile(MafftProcess.OutputFile):
		FasttreeProcess.get_output()
	else:
		logger.error("%s is not a file. There was an issue with the previous step." %(MafftProcess.OutputFile))
		end(1)

	### Use phylomerge to merge sequence from a same species
	logger.info("Use phylomerge to merge sequence from a same species")
	PhylomergeProcess = PhyloPrograms.Phylomerge(MafftProcess.OutputFile, FasttreeProcess.OutputTree)
	PhylomergeProcess.SequenceToTaxon = Seq2Taxon
	PhylomergeProcess.RearrangeTree = True
	PhylomergeProcess.BootstrapThreshold = 0.8
	PhylomergeProcess.OutputSequenceFile = "%s/Merged.fa" %TmpDirName

	if os.path.isfile(MafftProcess.OutputFile) and \
	   os.path.isfile(FasttreeProcess.OutputTree) and \
	   os.path.isfile(PhylomergeProcess.SequenceToTaxon) :
	   PhylomergeProcess.launch()
	else:
		logger.error("%s or %s or %s is not a file. There was an issue with the previous step." \
		 %(MafftProcess.OutputFile, FasttreeProcess.OutputTree,PhylomergeProcess.SequenceToTaxon))
		end(1)
	LastAliToAlign = PhylomergeProcess.OutputSequenceFile
	logger.info("Realign the merge alignment")
	
else: #No sequences to add
	logger.warning("No sequences to add")
	LastAliToAlign = args.alignment
	logger.info("Realign the input alignment")
		
### Realign the last alignment
FinalMafftProcess = Aligner.Mafft(LastAliToAlign)
FinalMafftProcess.AutoOption = True
FinalMafftProcess.QuietOption = True
FinalMafftProcess.OutputFile = "%s.fa" %OutPrefixName


if os.path.isfile(FinalMafftProcess.InputFile):
	(out,err) = FinalMafftProcess.launch()
else:
	logger.error("%s is not a file. There was an issue with the previous step." %(FinalMafftProcess.InputFile))
	end(1)
		
### Built a tree with the final alignment
logger.info("Built a tree with the final alignment")
FinalFasttreeProcess = PhyloPrograms.Fasttree(FinalMafftProcess.OutputFile)
FinalFasttreeProcess.Nt = True
FinalFasttreeProcess.Gtr = True
FinalFasttreeProcess.OutputTree = "%s.tree" %OutPrefixName

if os.path.isfile(FinalMafftProcess.OutputFile):
    FinalFasttreeProcess.get_output()
else:
    logger.error("%s is not a file. There was an issue with the previous step." %(FinalMafftProcess.OutputFile))
    end(1)
        
logger.debug("--- %s seconds ---" % (time.time() - start_time))
end(0)
