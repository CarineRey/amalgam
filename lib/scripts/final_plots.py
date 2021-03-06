#!/usr/bin/python
# coding: utf-8

#  final_plots.py
#
#  Copyright 2017 Carine Rey <carine.rey@ens-lyon.fr>
#
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA 02110-1301, USA.
#
#

import os, sys
import glob
import time
import argparse
import pandas as pd
#import numpy as np
import matplotlib.pyplot as plt


##########
# inputs #
##########
start_time = time.time()

### Option defining
parser = argparse.ArgumentParser(prog="final_plots.py",
                                 description='')
parser.add_argument('--version', action='version', version='%(prog)s 1.0')

##############
requiredOptions = parser.add_argument_group('Required arguments')
requiredOptions.add_argument('-i_ortho', "--input_dir_ortho", type=str,
                             help='input dir', required=True)
requiredOptions.add_argument('-i_filter', "--input_dir_filter", type=str,
                             help='input dir', required=True)
requiredOptions.add_argument('-o', '--output_dir', type=str,
                   help="Output dir", required=True)
##############
Options = parser.add_argument_group('Options')
Options.add_argument('-t_sp', '--target_species', type=str, metavar="sp1:ID1,sp2:ID2",
                    help="", default="")
##############

### Option parsing
args = parser.parse_args()

OutDirName = args.output_dir
InputDirName_filter = args.input_dir_filter
InputDirName_ortho = args.input_dir_ortho

print "InputDirName_filter = \"%s\"" %(args.input_dir_filter)
print "InputDirName_ortho = \"%s\"" %(args.input_dir_ortho)
print "OutDirName = \"%s\"" %(args.output_dir)

### Set up the output directory
if os.path.isdir(OutDirName):
    pass
    #logger.info("The output directory %s exists", OutDirName)
elif OutDirName: # if OutDirName is not a empty string we create the directory
    #logger.info("The output directory %s does not exist, it will be created", OutDirName)
    os.makedirs(OutDirName)


all_fam_orthologs_fn = "%s/%s" %(InputDirName_ortho, "all_fam.orthologs.tsv")
all_fam_seq2sp_fn = "%s/%s" %(InputDirName_ortho, "all_fam.seq2sp.tsv")


if os.path.isfile(all_fam_orthologs_fn):
    print "all_fam_orthologs_fn = \"" + all_fam_orthologs_fn + "\""
else:
    print "all_fam_orthologs_fn not ok:" + all_fam_orthologs_fn

if os.path.isfile(all_fam_seq2sp_fn):
    print "all_fam_seq2sp_fn = \"" + all_fam_seq2sp_fn + "\""
else:
    print "all_fam_seq2sp_fn not ok:" + all_fam_seq2sp_fn

target_species_d = {}
target_species_l = []

if args.target_species:
    target_species_tmp = args.target_species.strip().split(",")
    for x in target_species_tmp:
        sp, sp_id = x.split(":")
        target_species_d[sp_id] = sp
        target_species_l.append(sp)

print "target_species_l = %s" %(target_species_l)
#### Read data

df_seq2sp = pd.read_table(all_fam_seq2sp_fn, names=["seq", "sp", "fam", "subfam"])


#### Fig param
plt.style.use('seaborn-white')
plt.rcParams['font.family'] = 'serif'
plt.rcParams['font.serif'] = 'Ubuntu'
plt.rcParams['font.monospace'] = 'Ubuntu Mono'
plt.rcParams['font.size'] = 10
plt.rcParams['axes.labelsize'] = 10
plt.rcParams['axes.labelweight'] = 'bold'
plt.rcParams['axes.titlesize'] = 10
plt.rcParams['xtick.labelsize'] = 8
plt.rcParams['ytick.labelsize'] = 8
plt.rcParams['legend.fontsize'] = 10
plt.rcParams['figure.titlesize'] = 12
plt.rcParams['figure.autolayout'] = True


if df_seq2sp.empty:
    print "no data"
    sys.exit(0)


#### Fig 1

df_sp = df_seq2sp.groupby(['sp']).size().reset_index(name='counts')
df_sp["target_sp"] = df_sp["sp"].isin(target_species_l)
df_sp.sort_values('target_sp', inplace=True)
color_di = {True:"#90EE90", False: "blue"}
df_sp["color"] =  df_sp["target_sp"].replace(color_di)

if os.environ.has_key("DISPLAY"):
    plt.figure();
    fig1 = df_sp.plot(kind='barh', x="sp", y="counts", title= "# of total sequences", stacked=True, color=df_sp["color"], legend=False)
    fig1_plot = fig1.get_figure()
    fig1_plot.savefig("%s/total_seqs.svg" %(OutDirName))

if os.path.isfile(all_fam_orthologs_fn):

    df_seq2sp["fam_subfam"] = df_seq2sp["fam"] + "_" + df_seq2sp["subfam"]


    #### Fig 2

    df_subfam = df_seq2sp.groupby(['fam_subfam']).size().reset_index(name='counts')
    df_subfam.to_csv("%s/total_sp_per_subfam.tsv" %(OutDirName), index = False)
    nb_line = df_subfam.shape[0]

    if os.environ.has_key("DISPLAY"):
        df_subfam_tmp = df_subfam[df_subfam["counts"]>1]
        nb_1 = nb_line - df_subfam_tmp.shape[0]
        plt.figure();
        fig2 = df_subfam_tmp.plot.hist(by='counts', bins=50, legend=False, color="b", range=[0,max(df_subfam["counts"])], title= "(%i subfamilies with 1 sp)" %nb_1 )
        fig2.set_xlabel("# of sequences (=species) per subfamily")
        fig2_plot = fig2.get_figure()
        fig2_plot.savefig("%s/total_sp_per_subfam.svg" %(OutDirName))

    #### Fig 3
    df_subfam2 = df_seq2sp.groupby(['fam_subfam', "sp"]).size().reset_index(name='counts')
    df_subfam2.to_csv("%s/total_sp_per_subfam_sp.tsv" %(OutDirName), index = False)
    
    df_subfam_per_sp = pd.crosstab(index=df_subfam2['fam_subfam'], columns=[df_subfam2['sp']])
    nb_sp = df_subfam_per_sp.shape[1]
    df_subfam_per_sp["sum"] = df_subfam_per_sp.sum(1)
    df_subfam_per_sp["%_sum"] = df_subfam_per_sp["sum"] * 100. / float(nb_sp)
    df_subfam_per_sp.to_csv("%s/nb_seq_per_sp_per_subfam.tsv" %(OutDirName))
    nb_line = df_subfam_per_sp.shape[0]

    if os.environ.has_key("DISPLAY"):
        df_subfam_per_sp = df_subfam_per_sp[df_subfam_per_sp["%_sum"]>100. / float(nb_sp)]
        nb_1 = nb_line - df_subfam_per_sp.shape[0]
        plt.figure();
        fig3 = df_subfam_per_sp["%_sum"].plot.hist(bins=50, legend=False, color="b", range=[0,100], title= "(%i subfamilies with 1 sp)" %nb_1 )
        fig3.set_xlabel("% of the number of species per subfamily")
        fig3_plot = fig3.get_figure()
        fig3_plot.savefig("%s/presence_sp_per_subfam.svg" %(OutDirName))

if os.path.isdir(os.path.join(InputDirName_filter, "FilterSummary_out/")):

    #### Fig 4
    summary_files =  glob.glob(os.path.join(InputDirName_filter, "FilterSummary_out/*.filter_summary.txt"))

    print summary_files
    print InputDirName_filter
    list_df = []
    for f in summary_files:
        if os.path.exists(f) and os.path.getsize(f) > 1:
            list_df.append(pd.read_table(f, names=["seq", "n_seq", "%_id", "%_ali", "t", "s"]))

    if list_df:
        df_filter_summary = pd.concat(list_df)

        def get_id(seq):
            seq = seq.split("_")[0]
            sp_id = ''.join([x for x in seq if x.isalpha()][2:])
            return target_species_d[sp_id]


        df_filter_summary["sp"] = df_filter_summary["seq"].map(get_id)
        df_filter_summary["color"] =  df_filter_summary["s"].replace({"K":"#09BB21", "K2":"#FFA500", "D":"#D80002"})

        for t_sp in target_species_l:
            print t_sp
            df_filter_summary_sp = df_filter_summary.copy()
            df_filter_summary_sp = df_filter_summary_sp[df_filter_summary.sp.eq(t_sp)]
            df_filter_summary_sp.to_csv("%s/%s.filter_stats.tsv" %(OutDirName, t_sp))

            #df_filter_summary_sp_melt = pd.melt(df_filter_summary_sp[["seq", "%_id", "%_ali", "s"]], id_vars=['seq', "s"], value_vars=["%_id", "%_ali"])
            #print df_filter_summary_sp_melt
            #p = ggplot(aes(x="value", fill = "s"), data=df_filter_summary_sp_melt) + theme_bw() +\
            #    geom_histogram(bins = 100, color="black") + facet_grid("variable ~ .", scales="free") + \
            #    ggtitle(t_sp)
            #ggsave(plot = p, filename = OutDirName + "/" + t_sp+'.pdf')

            if os.environ.has_key("DISPLAY"):

                K_values_id = df_filter_summary_sp["%_id"][df_filter_summary_sp["s"].isin(["K","K2"])].values
                D_values_id = df_filter_summary_sp["%_id"][df_filter_summary_sp["s"].eq("D")].values

                color_id = []
                values_id = []
                if len(K_values_id):
                    color_id.append("#008000")
                    values_id.append(K_values_id)
                if len(D_values_id):
                    color_id.append("#C41C00")
                    values_id.append(D_values_id)

                K_values_ali = df_filter_summary_sp["%_ali"][df_filter_summary_sp["s"].isin(["K","K2"])].values
                D_values_ali = df_filter_summary_sp["%_ali"][df_filter_summary_sp["s"].eq("D")].values

                color_ali = []
                values_ali = []
                if len(K_values_ali):
                    color_ali.append("#008000")
                    values_ali.append(K_values_ali)
                if len(D_values_ali):
                    color_ali.append("#C41C00")
                    values_ali.append(D_values_ali)


                if len(values_id):
                    plt.figure(1)
                    fig, (ax1, ax2) = plt.subplots(nrows=2, ncols=1, figsize=(4,4))

                    ax1.hist(values_id, stacked=True, color=color_id, bins=50, label=["K", "D"], range=[0,100])
                    handles, labels = ax1.get_legend_handles_labels()
                    ax1.legend(handles, labels)
                    ax1.set_xlabel("%_id")
                    ax1.set_title(t_sp)

                    ax2.hist(values_ali, stacked=True, color=color_ali, bins=50, label=["K", "D"], range=[0,100])
                    ax2.set_xlabel("%_ali")
                    handles2, labels2 = ax2.get_legend_handles_labels()
                    ax2.legend(handles2, labels2)

                    plt.tight_layout()
                    plt.savefig(OutDirName + "/" + t_sp+'.filter_stats.svg')


