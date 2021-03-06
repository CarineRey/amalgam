open Core_kernel
open Bistro
open Defs
open Wutils

type t = {
  run_reconciliation : bool ;
  configuration_directory : Configuration_directory.t ;
  checked_used_families_all_together : text file ;
  fasta_reads : fasta file OSE_or_PE.t Rna_sample.assoc ;
  normalized_fasta_reads : fasta file OSE_or_PE.t Rna_sample.assoc ;
  trinity_assemblies : fasta file Rna_sample.assoc ;
  trinity_orfs : fasta file Rna_sample.assoc ;
  trinity_assemblies_stats : text file Rna_sample.assoc ;
  trinity_orfs_stats : text file Rna_sample.assoc ;
  trinity_annotated_fams : [`seq_dispatcher] directory Rna_sample.assoc ;
  ref_blast_dbs : blast_db file assoc ;
  reads_blast_dbs : Apytram.compressed_read_db Rna_sample.assoc ;
  apytram_orfs_ref_fams : (Family.t * (Rna_sample.t * Family.t * fasta file) list) list ;
  apytram_checked_families : (Family.t * (Rna_sample.t * Family.t * fasta file) list) list ;
  apytram_annotated_families : (Family.t * fasta file) list ;
  merged_families : (Family.t * [ `seq_integrator ] directory * [ `seq_integrator ] directory option) list ;
  merged_and_reconciled_families : (Family.t * Generax.phylotree directory * [ `seq_integrator ] directory) list ;
  merged_reconciled_and_realigned_families_dirs : [`merged_families_distributor] directory ;
  reconstructed_sequences : [`reconstructed_sequences] directory option ;
  orthologs_per_seq : [`extract_orthologs] directory ;
  final_plots : [`final_plots] directory ;
}

let rna_sample_needs_rna (s : Rna_sample.t) =
  match s.run_apytram, s.run_trinity, s.precomputed_assembly with
  | true, _, _          -> true
  | false, true, Some _ -> false
  | false, true, None   -> true
  | false, false, _     -> false

let check_used_families ~used_fam_list ~usable_fam_file =
  let open Bistro.Shell_dsl in
  let sorted_usable_fam_file = tmp // "usablefam.sorted.txt" in
  let sorted_all_used_fam_file = dest in
  let common_fam_file = tmp // "common_fam.txt" in
  let fam_subset_not_ok = tmp // "fam_subset_not_ok.txt" in
  let all_used_fam = Bistro.Template_dsl.(
      List.map used_fam_list ~f:(fun (fam : Family.t) -> seq [string fam.name])
      |> seq ~sep:"\n"
    )
  in

  let script_post ~fam_subset_not_ok =
    let args = [
      "FILE_EMPTY", fam_subset_not_ok ;
    ]
    in
    bash_script args {|
    if [ -s $FILE_EMPTY ]
    then
      echo "These families are not in the \"Usable\" families:"
      cat $FILE_EMPTY
      echo "Use the option --just-parse-input and --family-subset with an empty file to get the file UsableFamilies.txt"
      exit 3
    else
      exit 0
    fi
    |}
  in
  Workflow.shell ~descr:("check_used_families") [
    mkdir_p tmp;
    cmd "sort" ~stdout:sorted_usable_fam_file [ dep usable_fam_file;];
    cmd "sort" ~stdout:sorted_all_used_fam_file [ file_dump all_used_fam; ];
    cmd "join" ~stdout: common_fam_file [ string "-1 1"; sorted_all_used_fam_file; sorted_usable_fam_file];
    cmd "comm" ~stdout: fam_subset_not_ok [string "-3"; common_fam_file;sorted_all_used_fam_file];
    cmd "bash" [ file_dump (script_post ~fam_subset_not_ok)]
  ]

let fasta_reads (config : Dataset.t) =
  assoc_opt config.samples ~f:(fun s ->
      if rna_sample_needs_rna s then
        let open OSE_or_PE in
        let fq2fa ?(tag = "") x =
          let descr = id_concat [s.id ; s.species ; tag] in
          Trinity.fastq2fasta ~descr x
        in
        match s.sample_file with
        | Fasta_file fa -> Some (OSE_or_PE.map ~f:Workflow.input fa)
        | Fastq_file (Single_end se) ->
          Some (OSE_or_PE.se (fq2fa (Workflow.input se.reads)) se.orientation)
        | Fastq_file (Paired_end pe) ->
          Some (OSE_or_PE.pe
                  (fq2fa ~tag:"left" (Workflow.input pe.reads1))
                  (fq2fa ~tag:"right" (Workflow.input pe.reads2))
                  pe.orientation)
      else None
    )

let normalize_fasta_reads fasta_reads memory max_memory threads =
  assoc_map fasta_reads ~f:(fun (s : Rna_sample.t) fa ->
      let max_cov = 20 in
      let descr = id_concat [s.id ; s.species] in
      Trinity.fasta_read_normalization ~descr ~max_cov ~threads ~memory ~max_memory fa
    )

let trinity_assemblies_of_norm_fasta normalized_fasta_reads ~memory ~nthreads =
  assoc_filter_map normalized_fasta_reads ~f:(fun (s : Rna_sample.t) normalized_fasta_reads ->
      match s.run_trinity, s.precomputed_assembly with
      | true, None ->
        let tag = id_concat [s.id ; s.species] in
        Trinity.trinity_fasta ~tag ~no_normalization:true ~full_cleanup:true ~memory ~threads:nthreads normalized_fasta_reads
        |> Option.some
      | _, Some assembly_path -> Some (Workflow.input assembly_path)
      | (_, _)   -> None
    )

let transdecoder_orfs_of_trinity_assemblies trinity_assemblies ~memory ~nthreads =
  assoc_map trinity_assemblies ~f:(fun (s : Rna_sample.t) trinity_assembly ->
      match s.run_transdecoder, s.precomputed_assembly with
      | true, None ->
        let pep_min_length = 50 in
        let retain_long_orfs = 150 in
        let descr = id_concat ["Assembly" ; s.id ; s.species] in
        Transdecoder.transdecoder
          ~descr ~retain_long_orfs ~pep_min_length ~only_best_orf:false
          ~memory ~threads:nthreads
          trinity_assembly
      | (false, _ )
      | (true, Some _) -> trinity_assembly
    )

let assemblies_stats_of_assemblies assemblies =
  assoc_filter_map assemblies ~f:(fun (s : Rna_sample.t) assembly ->
      match s.precomputed_assembly with
      | Some _ -> None
      | None ->
        Some (Trinity.assembly_stats ~descr:(s.id ^ "_" ^ s.species) assembly)
    )

let ref_blast_dbs (config : Dataset.t) config_dir =
  assoc config.reference_species ~f:(fun ref_species ->
      let fasta = Configuration_directory.ref_transcriptome config_dir ref_species in
      let parse_seqids = true in
      let dbtype = "nucl" in
      BlastPlus.makeblastdb ~parse_seqids ~dbtype  ("DB_" ^ ref_species) fasta
    )

let reformat_cdhit_cluster ?tag cluster : fasta file =
  let open Bistro.Shell_dsl in
  Workflow.shell ~version:1 ~descr:(descr ?tag "reformat_cdhit_cluster2fasta.py") [
    cmd "python" ~img:caars_img [
      file_dump (string Scripts.reformat_cdhit_cluster2fasta);
      dep cluster ;
      ident dest]
  ]

let blast_dbs_of_norm_fasta norm_fasta =
  assoc_filter_map norm_fasta ~f:(fun (s : Rna_sample.t) norm_fasta ->
      if s.run_apytram then
        let concat_fasta = match norm_fasta with
          | OSE_or_PE.Single_end se -> se.reads
          | Paired_end pe ->
            fasta_concat ~tag:(id_concat [s.id ; "fasta_lr"]) [ pe.reads1 ; pe.reads2 ]
        in
        let tag = id_concat [s.id ; s.species] in
        (*Build biopython index*)
        let index_concat_fasta = build_biopythonindex ~tag concat_fasta in
        (*build overlapping read cluster*)
        let cluster_repo = Cdhit.lap ~tag concat_fasta in
        let rep_cluster_fasta = Cdhit.cluster_rep_of_lap cluster_repo in
        let cluster = Cdhit.cluster_of_lap cluster_repo in
        (*reformat cluster*)
        let reformated_cluster = reformat_cdhit_cluster ~tag cluster in
        (*build index for cluster*)
        let index_cluster = build_biopythonindex ~tag reformated_cluster in
        (*Build blast db of cluster representatives*)
        let parse_seqids = true in
        let hash_index = true in
        let dbtype = "nucl" in
        let cluster_rep_blast_db = BlastPlus.makeblastdb ~hash_index ~parse_seqids ~dbtype  (s.id ^ "_" ^ s.species) rep_cluster_fasta in
        Some {
          Apytram.s ; concat_fasta; index_concat_fasta;
          rep_cluster_fasta; reformated_cluster; index_cluster ;
          cluster_rep_blast_db
        }
      else
        None
    )

let trinity_annotated_families_of_trinity_assemblies config_dir assemblies ref_blast_dbs threads =
  assoc_map assemblies  ~f:(fun (s : Rna_sample.t) trinity_assembly ->
      let ref_db = List.map s.reference_species ~f:(fun r -> ref_blast_dbs $ r) in
      let query = trinity_assembly in
      let query_species= s.species in
      let query_id = s.id in
      let tag = id_concat s.reference_species in
      let ref_transcriptome =
        List.map s.reference_species ~f:(Configuration_directory.ref_transcriptome config_dir)
        |> fasta_concat ~tag:(tag ^ ".ref_transcriptome")
      in
      let seq2fam =
        List.map s.reference_species ~f:(Configuration_directory.ref_seq_fam_links config_dir)
        |> fasta_concat ~tag:(tag ^ ".seq2fam")
      in
      Seq_dispatcher.seq_dispatcher
        ~s2s_tab_by_family:true
        ~query
        ~query_species
        ~query_id
        ~ref_transcriptome
        ~seq2fam
        ~ref_db
        ~threads
    )

(* This is needed by [build_target_query] to concat a list of fasta
   in a directory without error, even if some requested files are
   not present. It seems that seq_dispatcher doesn't produce files
   for all families, hence the need to do this. *)
let concat_without_error ?tag l : fasta file =
  let open Bistro.Shell_dsl in
  let script =
    let vars = [
      "FILE", seq ~sep:"" l ;
      "DEST", dest ;
    ]
    in
    bash_script vars {|
        touch tmp
        cat tmp $FILE > tmp1
        mv tmp1 $DEST
        |}
  in
  Workflow.shell ~descr:(descr ?tag "concat_without_error") [
    mkdir_p tmp;
    cd tmp;
    cmd "sh" [ file_dump script];
  ]

let build_target_query dataset ref_species family (trinity_annotated_fams : [`seq_dispatcher] directory Rna_sample.assoc) apytram_group =
  let seq_dispatcher_results_dirs =
    assoc_opt (Dataset.apytram_samples dataset) ~f:(fun s ->
        if String.(s.group_id = apytram_group) && Poly.(s.reference_species = ref_species) && s.run_trinity then
          Some (List.Assoc.find_exn ~equal:Poly.( = ) trinity_annotated_fams s)
        else
          None
      )
  in
  let tag = family ^ ".seqdispatcher" in
  concat_without_error ~tag (
    List.map seq_dispatcher_results_dirs ~f:Bistro.Shell_dsl.(fun (s, dir) ->
        dep dir // Seq_dispatcher.fasta_file_name s family
      )
  )

let apytram_annotated_ref_fams_by_fam_by_groups (dataset : Dataset.t) configuration_dir trinity_annotated_fams reads_blast_dbs memory_per_sample =
  let apytram_groups = Dataset.apytram_groups dataset in
  let apytram_ref_species = Dataset.apytram_reference_species dataset in
  let apytram_samples = Dataset.apytram_samples dataset in
  List.map dataset.used_families ~f:(fun fam ->
      let fws =
        List.concat_map apytram_groups ~f:(fun apytram_group ->
            let pairs = List.cartesian_product apytram_ref_species [fam] in
            List.concat_map pairs ~f:(fun (ref_species, fam) ->
                let tag = id_concat [fam.name ; String.concat ~sep:"_" ref_species ; String.strip apytram_group] in
                let guide_query =
                  List.map ref_species ~f:(fun sp -> Configuration_directory.ref_fams configuration_dir sp fam.name)
                  |> fasta_concat ~tag
                in
                let target_query = build_target_query dataset ref_species fam.name trinity_annotated_fams apytram_group in
                let query = fasta_concat ~tag:(tag ^ ".+seqdispatcher") [guide_query; target_query] in
                let compressed_reads_dbs = List.filter_map reads_blast_dbs ~f:(fun ((s : Rna_sample.t), db) ->
                    if (List.equal String.equal s.reference_species ref_species && String.equal s.group_id apytram_group)
                    then Some db else None
                  )
                in
                let time_max = 18000 * List.length compressed_reads_dbs in
                let w =
                  Apytram.apytram_multi_species
                    ~descr:tag ~time_max ~no_best_file:true ~write_even_empty:true
                    ~mal:66 ~i:5 ~evalue:1e-10 ~out_by_species:true
                    ~memory:memory_per_sample ~fam:fam.name ~query compressed_reads_dbs in
                List.filter_map apytram_samples ~f:(fun s ->
                    if List.equal String.equal s.reference_species ref_species && String.(s.group_id = apytram_group) then
                      Some (s, fam, Apytram.get_fasta w ~family_name:fam.name ~sample_id:s.id )
                    else None
                  )
              )
          )
      in
      (fam, fws)
    )

let checkfamily
    ?(descr="")
    ~ref_db
    ~(input:fasta file)
    ~family
    ~ref_transcriptome
    ~seq2fam
    ~evalue
  : fasta file =
  let open Bistro.Shell_dsl in
  let tmp_checkfamily = tmp // "tmp" in
  let dest_checkfamily = dest // "sequences.fa" in

  Workflow.shell ~version:8 ~descr:("CheckFamily.py" ^ descr) [
    mkdir_p tmp_checkfamily;
    cd tmp_checkfamily;
    cmd "python" ~img:caars_img [
      file_dump (string Scripts.check_family);
      opt "-tmp" ident tmp_checkfamily ;
      opt "-i" dep input;
      opt "-t" dep ref_transcriptome ;
      opt "-f" string family;
      opt "-t2f" dep seq2fam;
      opt "-o" ident dest_checkfamily;
      opt "-d" ident (seq ~sep:"," (List.map ref_db ~f:(fun blast_db -> seq [dep blast_db ; string "/db"]) ));
      opt "-e" float evalue;
    ]
  ]
  |> Fn.flip Workflow.select [ "sequences.fa" ]

let apytram_checked_families_of_orfs_ref_fams apytram_orfs_ref_fams configuration_dir ref_blast_dbs =
  List.map apytram_orfs_ref_fams ~f:(fun (fam, fws) ->
      let checked_fws = List.map fws ~f:(fun ((s : Rna_sample.t), (f : Family.t), apytram_orfs_fasta) ->
          let input = apytram_orfs_fasta in
          let tag = id_concat s.reference_species in
          let ref_transcriptome =
            List.map s.reference_species ~f:(Configuration_directory.ref_transcriptome configuration_dir)
            |> fasta_concat ~tag:(tag ^ ".ref_transcriptome")
          in
          let seq2fam =
            List.map s.reference_species ~f:(Configuration_directory.ref_seq_fam_links configuration_dir)
            |> fasta_concat ~tag:(tag ^ ".seq2fam") in
          let ref_db =
            List.map s.reference_species ~f:(( $ ) ref_blast_dbs) in
          let checked_families_fasta =
            checkfamily ~descr:(":"^s.id^"."^f.name) ~input ~family:f.name ~ref_transcriptome ~seq2fam ~ref_db ~evalue:1e-6
          in
          (s, f, checked_families_fasta)
        ) in
      (fam, checked_fws)
    )

let parse_apytram_results apytram_annotated_ref_fams =
  let open Bistro.Shell_dsl in
  List.map apytram_annotated_ref_fams ~f:(fun (fam, fws) ->
      let config = Bistro.Template_dsl.(
          List.map fws ~f:(fun ((s : Rna_sample.t), (f : Family.t), w) ->
              seq ~sep:"\t" [ string s.species ; string s.id ; string f.name ; int f.id ; dep w ]
            )
          |> seq ~sep:"\n"
        )
      in
      let fw =
        Workflow.shell ~version:4 ~descr:("parse_apytram_results.py." ^ fam.Family.name) ~np:1  [
          cmd "python" ~img:caars_img [
            file_dump (string Scripts.parse_apytram_results) ;
            file_dump config ;
            dest ]
        ]
      in
      (fam, fw)
    )

let merged_families_of_families (dataset : Dataset.t) configuration_dir trinity_annotated_fams apytram_annotated_fams merge_criterion filter_threshold =
  List.map dataset.used_families ~f:(fun family ->
      let trinity_fam_results_dirs=
        List.map (Dataset.trinity_samples dataset) ~f:(fun s ->
            (s , List.Assoc.find_exn ~equal:Poly.( = ) trinity_annotated_fams s)
          )
      in
      let apytram_results_dir =  List.Assoc.find_exn ~equal:Poly.( = ) apytram_annotated_fams family in
      let alignment = Workflow.input (dataset.alignments_dir ^ "/" ^ family.name ^ ".fa")  in
      let alignment_sp2seq = Configuration_directory.ali_species2seq_links configuration_dir family.name  in
      let species_to_refine_list = List.map (Dataset.reference_samples dataset) ~f:(fun s -> s.species) in
      let w = if (List.length species_to_refine_list) = 0 then
          Seq_integrator.seq_integrator ~realign_ali:false ~resolve_polytomy:true ~no_merge:true ~family:family.name ~trinity_fam_results_dirs ~apytram_results_dir ~alignment_sp2seq ~merge_criterion alignment
        else
          Seq_integrator.seq_integrator ~realign_ali:false ~resolve_polytomy:true ~species_to_refine_list ~family:family.name ~trinity_fam_results_dirs ~apytram_results_dir ~alignment_sp2seq ~merge_criterion alignment
      in
      let tree = Seq_integrator.tree w family in
      let alignment = Seq_integrator.alignment w family in
      let sp2seq = Seq_integrator.sp2seq w family in

      let wf =
        if List.length species_to_refine_list > 0 then
          Some (Seq_integrator.seq_filter ~realign_ali:true ~resolve_polytomy:true ~filter_threshold ~species_to_refine_list ~family:family.name ~tree ~alignment ~sp2seq)
        else None
      in
      (family, w, wf )
    )

let generax_by_fam_of_merged_families (dataset : Dataset.t) merged_families memory threads =
  List.map  merged_families ~f:(fun ((fam : Family.t), merged_without_filter_family, merged_and_filtered_family) ->
      let merged_family = match merged_and_filtered_family with
        | Some w -> w
        | None -> merged_without_filter_family
      in

      let tree = Seq_integrator.tree merged_family fam in
      let alignment = Seq_integrator.alignment merged_family fam in
      let sp2seq = Seq_integrator.sp2seq merged_family fam in
      let sptreefile = Workflow.input dataset.species_tree_file in
      (fam, Generax.generax ~family:fam.name ~descr:(":" ^ fam.name) ~threads ~memory ~sptreefile ~link:sp2seq ~tree alignment, merged_family)
    )

let merged_families_distributor dataset merged_reconciled_and_realigned_families ~run_reconciliation ~refine_ali : [`merged_families_distributor] directory =
  let open Bistro.Shell_dsl in
  let more_than_one_sample_with_reference = Dataset.has_at_least_one_sample_with_reference dataset in
  let extension_list_merged = [(".fa","out/MSA_out");(".tree","out/GeneTree_out");(".sp2seq.txt","no_out/Sp2Seq_link")] in
  let extension_list_filtered = [(".discarded.fa","out/FilterSummary_out");(".filter_summary.txt","out/FilterSummary_out")] in

  let extension_list_reconciled = [("_ReconciledTree.nw","","out/GeneTreeReconciled_nw");
                                   ("_ReconciledTree.nhx", "", "out/GeneTreeReconciled_out");
                                   (".events.txt", "", "out/DL_out");
                                   (".orthologs.txt", "", "out/Orthologs_out")] in
  let dest_dir_preparation_commands = List.concat [
      [
        mkdir_p tmp;
        mkdir_p (dest // "out" // "MSA_out");
        mkdir_p (dest // "out" // "GeneTree_out");
        mkdir_p (dest // "no_out" // "Sp2Seq_link");
      ] ;

      if more_than_one_sample_with_reference
      then [ mkdir_p (dest // "out" // "FilterSummary_out") ]
      else [] ;

      if run_reconciliation then
        [
          mkdir_p (dest // "out" // "GeneTreeReconciled_out");
          mkdir_p (dest // "out" // "DL_out");
          mkdir_p (dest // "out" // "Orthologs_out");
        ]
      else [] ;

      if refine_ali && run_reconciliation then
        [mkdir_p (dest // "Realigned_fasta")]
      else []
    ]
  in
  let commands_for_one_family ((f : Family.t), reconciled_w, merged_w) =
    let open Bistro.Template_dsl in
    List.concat [
      List.map extension_list_merged ~f:(fun (ext,dir) ->
          let input = Workflow.select merged_w [ f.name ^ ext ] in
          let output = dest // dir // (f.name ^ ext)  in
          seq ~sep:" " [ string "cp"; dep input ; ident output ]
        ) ;
      if more_than_one_sample_with_reference then
        List.map extension_list_filtered ~f:(fun (ext,dir) ->
            let input = Workflow.select merged_w [ f.name  ^ ext ] in
            let output = dest // dir // (f.name  ^ ext)  in
            seq ~sep:" " [ string "cp"; dep input ; ident output ]
          )
      else [] ;
      if run_reconciliation then
        List.concat [
          List.map extension_list_reconciled ~f:(fun (ext,dirin,dirout) ->
              let input = Workflow.select reconciled_w [ dirin ^ f.name  ^ ext ] in
              let output = dest // dirout // (f.name  ^ ext)  in
              seq ~sep:" " [ string "cp"; dep input ; ident output ]
            )
          ;
        ]
      else [] ;
    ]
  in
  let script =
    List.concat_map merged_reconciled_and_realigned_families ~f:commands_for_one_family
    |> seq ~sep:"\n"
  in
  let commands = dest_dir_preparation_commands @ [ cmd "bash" [ file_dump script ] ] in
  Workflow.shell ~descr:"build_output_directory" ~version:1 commands

let get_reconstructed_sequences dataset merged_and_reconciled_families_dirs =
  let open Bistro.Shell_dsl in
  if Dataset.has_at_least_one_sample_with_reference dataset then
    let species_to_refine_list = List.map (Dataset.reference_samples dataset) ~f:(fun s -> s.species) in
    Some (Workflow.shell ~descr:"GetReconstructedSequences.py" ~version:6 [
        mkdir_p dest;
        cmd "python" ~img:caars_img [
          file_dump (string Scripts.get_reconstructed_sequences);
          dep merged_and_reconciled_families_dirs // "out/MSA_out";
          dep merged_and_reconciled_families_dirs // "no_out/Sp2Seq_link";
          seq ~sep:"," (List.map species_to_refine_list ~f:(fun sp -> string sp));
          ident dest
        ]
      ])
  else
    None

let write_orthologs_relationships dataset merged_and_reconciled_families_dirs ~run_reconciliation =
  let ortho_dir,species_to_refine_list =
    if run_reconciliation then
      Some (Workflow.select merged_and_reconciled_families_dirs ["out/Orthologs_out"]),
      Some (List.map (Dataset.reference_samples dataset) ~f:(fun s -> s.species))
    else (None, None)
  in
  let open Bistro.Shell_dsl in
  Workflow.shell ~descr:"ExtractOrthologs.py" ~version:7 [
    mkdir_p dest;
    cmd "python" ~img:caars_img [
      file_dump (string Scripts.extract_orthologs);
      ident dest;
      dep merged_and_reconciled_families_dirs // "no_out/Sp2Seq_link";
      option dep ortho_dir ;
      option (list ~sep:"," string) species_to_refine_list ;
    ]
  ]

let build_final_plots dataset orthologs_per_seq merged_reconciled_and_realigned_families_dirs ~run_reconciliation =
  let open Bistro.Shell_dsl in
  let formated_target_species =
    match Dataset.reference_samples dataset with
    | [] -> None
    | samples -> Some (
        List.map samples ~f:(fun s ->
            seq ~sep:":" [string s.species ; string s.id]
          )
      )
  in
  let dloutprefix = dest // "D_count" in
  Workflow.shell ~descr:"final_plots.py" ~version:19 (List.concat [
      [mkdir_p dest;
       cmd "python" ~img:caars_img [
         file_dump (string Scripts.final_plots);
         opt "-i_ortho" dep orthologs_per_seq;
         opt "-i_filter" dep (Workflow.select merged_reconciled_and_realigned_families_dirs ["out/"]);
         opt "-o" ident dest;
         option (opt "-t_sp" (seq ~sep:",")) formated_target_species;
       ];
      ];
      if run_reconciliation then
        [cmd "python" ~img:caars_img [
            file_dump (string Scripts.count_dl);
            opt "-o" ident dloutprefix;
            opt "-sp_tree" dep (Workflow.input (dataset.species_tree_file));
            opt "-rec_trees_dir" dep (Workflow.select merged_reconciled_and_realigned_families_dirs ["out/GeneTreeReconciled_out"])
          ];
        ]
      else
        []

    ])

let make
    ?(memory = 4) ?(nthreads = 2)
    ~merge_criterion ~filter_threshold
    ~refine_ali ~run_reconciliation
    (dataset : Dataset.t) =
  let memory_per_sample, threads_per_sample =
    let nb_samples = List.length dataset.samples in
    Int.(max 1 (memory / (max 1 nb_samples))), Stdlib.(max 1 (nthreads / (max 1 nb_samples)))
  in
  (* let memory_per_thread = Int.(max 1 (config.memory / config.nthreads)) in *)
  let config_dir = Configuration_directory.make ~memory dataset in
  let checked_used_families_all_together =
    check_used_families ~used_fam_list:dataset.used_families ~usable_fam_file:(Configuration_directory.usable_families config_dir)
  in
  let ref_blast_dbs = ref_blast_dbs dataset config_dir in
  let fasta_reads = fasta_reads dataset in
  let normalized_fasta_reads = normalize_fasta_reads fasta_reads memory_per_sample memory threads_per_sample in
  let trinity_assemblies = trinity_assemblies_of_norm_fasta normalized_fasta_reads ~memory:memory_per_sample ~nthreads:threads_per_sample in
  let trinity_orfs = transdecoder_orfs_of_trinity_assemblies trinity_assemblies ~memory:memory_per_sample ~nthreads:threads_per_sample in
  let trinity_assemblies_stats = assemblies_stats_of_assemblies trinity_assemblies in
  let trinity_orfs_stats = assemblies_stats_of_assemblies trinity_orfs in
  let trinity_annotated_fams = trinity_annotated_families_of_trinity_assemblies config_dir trinity_orfs ref_blast_dbs threads_per_sample in
  let reads_blast_dbs = blast_dbs_of_norm_fasta normalized_fasta_reads in
  let apytram_orfs_ref_fams =
    apytram_annotated_ref_fams_by_fam_by_groups dataset config_dir trinity_annotated_fams reads_blast_dbs memory_per_sample
  in
  let apytram_checked_families = apytram_checked_families_of_orfs_ref_fams apytram_orfs_ref_fams config_dir ref_blast_dbs in
  let apytram_annotated_families = parse_apytram_results apytram_checked_families in
  let merged_families = merged_families_of_families dataset config_dir trinity_annotated_fams apytram_annotated_families merge_criterion filter_threshold in
  let merged_and_reconciled_families = generax_by_fam_of_merged_families dataset merged_families memory nthreads in
  let merged_reconciled_and_realigned_families_dirs =
    merged_families_distributor dataset merged_and_reconciled_families ~refine_ali ~run_reconciliation
  in
  let reconstructed_sequences = get_reconstructed_sequences dataset merged_reconciled_and_realigned_families_dirs in
  let orthologs_per_seq = write_orthologs_relationships dataset merged_reconciled_and_realigned_families_dirs ~run_reconciliation in
  let final_plots = build_final_plots dataset orthologs_per_seq merged_reconciled_and_realigned_families_dirs ~run_reconciliation in
  { run_reconciliation ;
    configuration_directory = config_dir ; checked_used_families_all_together ;
    ref_blast_dbs ; fasta_reads ; normalized_fasta_reads ;
    trinity_assemblies ; trinity_orfs ; trinity_assemblies_stats ;
    trinity_orfs_stats ; trinity_annotated_fams ;
    reads_blast_dbs ; apytram_orfs_ref_fams ; apytram_checked_families ;
    apytram_annotated_families ; merged_families ;
    merged_and_reconciled_families ; merged_reconciled_and_realigned_families_dirs ;
    reconstructed_sequences ; orthologs_per_seq ; final_plots }
