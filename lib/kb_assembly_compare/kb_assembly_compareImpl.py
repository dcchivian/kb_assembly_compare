# -*- coding: utf-8 -*-
#BEGIN_HEADER
import math
import os
import re
import sys
import uuid
from datetime import datetime
from pprint import pprint, pformat

import matplotlib.pyplot as plt
import numpy as np

from installed_clients.AssemblyUtilClient import AssemblyUtil
from installed_clients.DataFileUtilClient import DataFileUtil as DFUClient
from installed_clients.KBaseReportClient import KBaseReport
from installed_clients.SetAPIServiceClient import SetAPI
from installed_clients.WorkspaceClient import Workspace as workspaceService

[OBJID_I, NAME_I, TYPE_I, SAVE_DATE_I, VERSION_I, SAVED_BY_I, WSID_I, WORKSPACE_I, CHSUM_I,
 SIZE_I, META_I] = list(range(11))  # object_info tuple
#END_HEADER


class kb_assembly_compare:
    '''
    Module Name:
    kb_assembly_compare

    Module Description:
    ** A KBase module: kb_assembly_compare
**
** This module contains Apps for comparing, combining, and benchmarking assemblies
    '''

    ######## WARNING FOR GEVENT USERS ####### noqa
    # Since asynchronous IO can lead to methods - even the same method -
    # interrupting each other, you must be *very* careful when using global
    # state. A method could easily clobber the state set by another while
    # the latter method is running.
    ######################################### noqa
    VERSION = "1.1.4"
    GIT_URL = "https://github.com/kbaseapps/kb_assembly_compare.git"
    GIT_COMMIT_HASH = "f148606736966821e865d6aa61cf5ff70ab695a8"

    #BEGIN_CLASS_HEADER
    workspaceURL     = None
    shockURL         = None
    handleURL        = None
    serviceWizardURL = None
    callbackURL      = None
    scratch          = None

    # wrapped program(s)
    MUMMER_bin = '/usr/local/bin/mummer'
    NUCMER_bin = '/usr/local/bin/nucmer'

    # log
    def log(self, target, message):
        timestamp = str(datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3])
        if target is not None:
            target.append('['+timestamp+'] '+message)
        print('['+timestamp+'] '+message)
        sys.stdout.flush()

    #END_CLASS_HEADER

    # config contains contents of config file in a hash or None if it couldn't
    # be found
    def __init__(self, config):
        #BEGIN_CONSTRUCTOR
        self.workspaceURL = config['workspace-url']
        self.shockURL = config['shock-url']
        self.handleURL = config['handle-service-url']
        self.serviceWizardURL = config['srv-wiz-url']
        self.callbackURL = os.environ['SDK_CALLBACK_URL']
        self.scratch = os.path.abspath(config['scratch'])

        pprint(config)

        if not os.path.exists(self.scratch):
            os.makedirs(self.scratch)
        #END_CONSTRUCTOR
        pass


    def run_filter_contigs_by_length(self, ctx, params):
        """
        :param params: instance of type "Filter_Contigs_by_Length_Params"
           (filter_contigs_by_length() ** **  Remove Contigs that are under a
           minimum threshold) -> structure: parameter "workspace_name" of
           type "workspace_name" (** The workspace object refs are of form:
           ** **    objects = ws.get_objects([{'ref':
           params['workspace_id']+'/'+params['obj_name']}]) ** ** "ref" means
           the entire name combining the workspace id and the object name **
           "id" is a numerical identifier of the workspace or object, and
           should just be used for workspace ** "name" is a string identifier
           of a workspace or object.  This is received from Narrative.),
           parameter "input_assembly_refs" of type "data_obj_ref", parameter
           "min_contig_length" of Long, parameter "output_name" of type
           "data_obj_name"
        :returns: instance of type "Filter_Contigs_by_Length_Output" ->
           structure: parameter "report_name" of type "data_obj_name",
           parameter "report_ref" of type "data_obj_ref"
        """
        # ctx is the context object
        # return variables are: returnVal
        #BEGIN run_filter_contigs_by_length

        #### Step 0: basic init
        ##
        console = []
        invalid_msgs = []
        report_text = ''
        self.log(console, 'Running run_filter_contigs_by_length(): ')
        self.log(console, "\n"+pformat(params))

        # Auth
        token = ctx['token']
        headers = {'Authorization': 'OAuth '+token}
        env = os.environ.copy()
        env['KB_AUTH_TOKEN'] = token

        # API Clients
        #SERVICE_VER = 'dev'  # DEBUG
        SERVICE_VER = 'release'
        # wsClient
        try:
            wsClient = workspaceService(self.workspaceURL, token=token)
        except Exception as e:
            raise ValueError('Unable to instantiate wsClient with workspaceURL: '+ self.workspaceURL +' ERROR: ' + str(e))
        # setAPI_Client
        try:
            #setAPI_Client = SetAPI (url=self.callbackURL, token=ctx['token'])  # for SDK local.  local doesn't work for SetAPI
            setAPI_Client = SetAPI (url=self.serviceWizardURL, token=ctx['token'])  # for dynamic service
        except Exception as e:
            raise ValueError('Unable to instantiate setAPI_Client with serviceWizardURL: '+ self.serviceWizardURL +' ERROR: ' + str(e))
        # auClient
        try:
            auClient = AssemblyUtil(self.callbackURL, token=ctx['token'], service_ver=SERVICE_VER)
        except Exception as e:
            raise ValueError('Unable to instantiate auClient with callbackURL: '+ self.callbackURL +' ERROR: ' + str(e))
        # dfuClient
        try:
            dfuClient = DFUClient(self.callbackURL)
        except Exception as e:
            raise ValueError('Unable to instantiate dfu_Client with callbackURL: '+ self.callbackURL +' ERROR: ' + str(e))

        # param checks
        required_params = ['workspace_name',
                           'input_assembly_refs',
                           'min_contig_length',
                           'output_name'
                          ]
        for arg in required_params:
            if arg not in params or params[arg] == None or params[arg] == '':
                raise ValueError ("Must define required param: '"+arg+"'")

        # load provenance
        provenance = [{}]
        if 'provenance' in ctx:
            provenance = ctx['provenance']
        provenance[0]['input_ws_objects']=[]
        for input_ref in params['input_assembly_refs']:
            provenance[0]['input_ws_objects'].append(input_ref)

        # set the output paths
        timestamp = int((datetime.utcnow() - datetime.utcfromtimestamp(0)).total_seconds()*1000)
        output_dir = os.path.join(self.scratch,'output.'+str(timestamp))
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        html_output_dir = os.path.join(output_dir,'html')
        if not os.path.exists(html_output_dir):
            os.makedirs(html_output_dir)


        #### STEP 1: get assembly refs
        ##
        if len(invalid_msgs) == 0:
            set_obj_type = "KBaseSets.AssemblySet"
            assembly_obj_types = ["KBaseGenomeAnnotations.Assembly", "KBaseGenomes.ContigSet"]
            accepted_input_types = [set_obj_type] + assembly_obj_types
            assembly_refs = []
            assembly_names = []
            assembly_refs_seen = dict()

            for i,input_ref in enumerate(params['input_assembly_refs']):

                # assembly obj info
                try:

                    input_obj_info = wsClient.get_object_info_new ({'objects':[{'ref':input_ref}]})[0]
                    #print ("INPUT_OBJ_INFO")
                    #pprint(input_obj_info)  # DEBUG
                    input_obj_type = re.sub ('-[0-9]+\.[0-9]+$', "", input_obj_info[TYPE_I])  # remove trailing version
                    input_obj_name = input_obj_info[NAME_I]
                    self.log (console, "Adding ASSEMBLY: "+str(input_ref)+" "+str(input_obj_name))  # DEBUG
                except Exception as e:
                    raise ValueError('Unable to get object from workspace: (' + input_ref +'): ' + str(e))

                if input_obj_type not in accepted_input_types:
                    raise ValueError ("Input object of type '"+input_obj_type+"' not accepted.  Must be one of "+", ".join(accepted_input_types))

                # add members to assembly_ref list
                if input_obj_type in assembly_obj_types:
                    try:
                        assembly_seen = assembly_refs_seen[input_ref]
                        continue
                    except:
                        assembly_refs_seen[input_ref] = True
                        assembly_refs.append(input_ref)
                        assembly_names.append(input_obj_name)
                elif input_obj_type != set_obj_type:
                    raise ValueError ("bad obj type for input_ref: "+input_ref)
                else:  # add assembly set members

                    try:
                        assemblySet_obj = setAPI_Client.get_assembly_set_v1 ({'ref':input_ref, 'include_item_info':1})
                    except Exception as e:
                        raise ValueError('Unable to get object from workspace: (' + input_ref +')' + str(e))

                    for assembly_obj in assemblySet_obj['data']['items']:
                        this_assembly_ref = assembly_obj['ref']
                        try:
                            assembly_seen = assembly_refs_seen[this_assembly_ref]
                            continue
                        except:
                            assembly_refs_seen[this_assembly_ref] = True
                            assembly_refs.append(this_assembly_ref)
                            try:

                                this_input_obj_info = wsClient.get_object_info_new ({'objects':[{'ref':this_assembly_ref}]})[0]
                                this_input_obj_type = re.sub ('-[0-9]+\.[0-9]+$', "", input_obj_info[TYPE_I])  # remove trailing version
                                this_input_obj_name = this_input_obj_info[NAME_I]
                                assembly_names.append(this_input_obj_name)
                            except Exception as e:
                                raise ValueError('Unable to get object from workspace: (' + this_assembly_ref +')' + str(e))


        #### STEP 2: Get assemblies to score as fasta files
        ##
        if len(invalid_msgs) == 0:
            self.log (console, "Retrieving Assemblies")  # DEBUG

            #assembly_outdir = os.path.join (output_dir, 'score_assembly')
            #if not os.path.exists(assembly_outdir):
            #    os.makedirs(assembly_outdir)
            score_assembly_file_paths = []

            for ass_i,input_ref in enumerate(assembly_refs):
                self.log (console, "\tAssembly: "+assembly_names[ass_i]+" ("+assembly_refs[ass_i]+")")  # DEBUG
                contig_file = auClient.get_assembly_as_fasta({'ref':assembly_refs[ass_i]}).get('path')
                sys.stdout.flush()
                contig_file_path = dfuClient.unpack_file({'file_path': contig_file})['file_path']
                score_assembly_file_paths.append(contig_file_path)
                #clean_ass_ref = assembly_ref.replace('/','_')
                #assembly_outfile_path = os.join(assembly_outdir, clean_assembly_ref+".fna")
                #shutil.move(contig_file_path, assembly_outfile_path)


        #### STEP 3: Get contig attributes and create filtered output files
        ##
        if len(invalid_msgs) == 0:
            filtered_contig_file_paths = []
            original_contig_count = []
            filtered_contig_count = []

            # score fasta lens in contig files
            read_buf_size  = 65536
            write_buf_size = 65536

            lens = []
            for ass_i,assembly_file_path in enumerate(score_assembly_file_paths):
                ass_name = assembly_names[ass_i]
                self.log (console, "Reading contig lengths in assembly: "+ass_name)  # DEBUG

                original_contig_count.append(0)
                filtered_contig_count.append(0)
                filtered_file_path = assembly_file_path+".min_contig_length="+str(params['min_contig_length'])+"bp"
                filtered_contig_file_paths.append(filtered_file_path)
                with open (assembly_file_path, 'r', read_buf_size) as ass_handle, \
                     open (filtered_file_path, 'w', write_buf_size) as filt_handle:
                    seq_buf = ''
                    last_header = ''
                    for fasta_line in ass_handle:
                        if fasta_line.startswith('>'):
                            if seq_buf != '':
                                original_contig_count[ass_i] += 1
                                seq_len = len(seq_buf)
                                if seq_len >= int(params['min_contig_length']):
                                    filtered_contig_count[ass_i] += 1
                                    filt_handle.write(last_header)  # last_header already has newline
                                    filt_handle.write(seq_buf+"\n")
                                seq_buf = ''
                                last_header = fasta_line
                        else:
                            seq_buf += ''.join(fasta_line.split())
                    if seq_buf != '':
                        original_contig_count[ass_i] += 1
                        seq_len = len(seq_buf)
                        if seq_len >= int(params['min_contig_length']):
                            filtered_contig_count[ass_i] += 1
                            filt_handle.write(last_header)  # last_header already has newline
                            filt_handle.write(seq_buf+"\n")
                        seq_buf = ''

                # DEBUG
                #with open (filtered_file_path, 'r', read_buf_size) as ass_handle:
                #    for fasta_line in ass_handle:
                #        print ("FILTERED LINE: '"+fasta_line+"'")


        #### STEP 4: save the filtered assemblies
        ##
        if len(invalid_msgs) == 0:
            non_zero_output_seen = False
            filtered_contig_refs  = []
            filtered_contig_names = []
            #assemblyUtil = AssemblyUtil(self.callbackURL)
            for ass_i,filtered_contig_file in enumerate(filtered_contig_file_paths):
                if filtered_contig_count[ass_i] == 0:
                    self.log (console, "SKIPPING totally filtered assembled contigs from "+assembly_names[ass_i])
                    filtered_contig_refs.append(None)
                    filtered_contig_names.append(None)
                else:
                    non_zero_output_seen = True
                    if len(assembly_refs) == 1:
                        output_obj_name = params['output_name']
                    else:
                        output_obj_name = assembly_names[ass_i]+".min_contig_length"+str(params['min_contig_length'])+"bp"
                    output_data_ref = auClient.save_assembly_from_fasta({
                        'file': {'path': filtered_contig_file},
                        'workspace_name': params['workspace_name'],
                        'assembly_name': output_obj_name
                    })
                    filtered_contig_refs.append(output_data_ref)
                    filtered_contig_names.append(output_obj_name)
            # save AssemblySet
            if len(assembly_refs) > 1 and non_zero_output_seen:
                items = []
                for ass_i,filtered_contig_file in enumerate(filtered_contig_file_paths):
                    if filtered_contig_count[ass_i] == 0:
                        continue
                    self.log (console, "adding filtered assembly: "+filtered_contig_names[ass_i])
                    items.append({'ref': filtered_contig_refs[ass_i],
                                  'label': filtered_contig_names[ass_i],
                                  #'data_attachment': ,
                                  #'info'
                              })

                # load the method provenance from the context object                 
                self.log(console,"SETTING PROVENANCE")  # DEBUG
                provenance = [{}]
                if 'provenance' in ctx:
                    provenance = ctx['provenance']
                # add additional info to provenance here, in this case the input data object reference                                                           
                provenance[0]['input_ws_objects'] = []
                for assRef in params['input_assembly_refs']:
                    provenance[0]['input_ws_objects'].append(assRef)
                provenance[0]['service'] = 'kb_assembly_compare'
                provenance[0]['method'] = 'run_filter_contigs_by_length'

                # save AssemblySet
                self.log(console,"SAVING ASSEMBLY_SET")  # DEBUG
                output_assemblySet_obj = { 'description': params['output_name']+" filtered by min_contig_length >= "+str(params['min_contig_length'])+"bp",
                                           'items': items
                                       }
                output_assemblySet_name = params['output_name']
                try:
                    output_assemblySet_ref = setAPI_Client.save_assembly_set_v1 ({'workspace_name': params['workspace_name'],
                                                                                  'output_object_name': output_assemblySet_name,
                                                                                  'data': output_assemblySet_obj
                                                                              })['set_ref']
                except Exception as e:
                    raise ValueError('SetAPI FAILURE: Unable to save assembly set object to workspace: (' + params['workspace_name']+")\n" + str(e))


        #### STEP 5: generate and save the report
        ##
        if len(invalid_msgs) > 0:
            report_text += "\n".join(invalid_msgs)
            objects_created = None
        else:
            # report text
            if len(assembly_refs) > 1 and non_zero_output_seen:
                report_text += 'AssemblySet saved to: ' + params['workspace_name'] + '/' + params['output_name'] + "\n\n"
            for ass_i,filtered_contig_file in enumerate(filtered_contig_file_paths):
                report_text += 'ORIGINAL Contig count: '+str(original_contig_count[ass_i])+"\t"+'in Assembly '+assembly_names[ass_i]+"\n"
                report_text += 'FILTERED Contig count: '+str(filtered_contig_count[ass_i])+"\t"+'in Assembly '+filtered_contig_names[ass_i]+"\n\n"
                if filtered_contig_count[ass_i] == 0:
                    report_text += "  (no output object created for "+filtered_contig_names[ass_i]+")"+"\n"

            # created objects
            objects_created = None
            if non_zero_output_seen:
                objects_created = []
                if len(assembly_refs) > 1:
                    objects_created.append({'ref': output_assemblySet_ref, 'description': params['output_name']+" filtered min_contig_length >= "+str(params['min_contig_length'])+"bp"})
                for ass_i,filtered_contig_ref in enumerate(filtered_contig_refs):
                    if filtered_contig_count[ass_i] == 0:
                        continue
                    objects_created.append({'ref': filtered_contig_refs[ass_i], 'description': filtered_contig_names[ass_i]+" filtered min_contig_length >= "+str(params['min_contig_length'])+"bp"})

        # Save report
        print('Saving report')
        kbr = KBaseReport(self.callbackURL)
        report_info = kbr.create_extended_report(
            {'message': report_text,
             'objects_created': objects_created,
             'report_object_name': 'kb_filter_contigs_by_length_report_' + str(uuid.uuid4()),
             'workspace_name': params['workspace_name']
             })

        # STEP 6: contruct the output to send back
        returnVal = {'report_name': report_info['name'], 'report_ref': report_info['ref']}

        #END run_filter_contigs_by_length

        # At some point might do deeper type checking...
        if not isinstance(returnVal, dict):
            raise ValueError('Method run_filter_contigs_by_length return value ' +
                             'returnVal is not type dict as required.')
        # return the results
        return [returnVal]

    def run_contig_distribution_compare(self, ctx, params):
        """
        :param params: instance of type "Contig_Distribution_Compare_Params"
           (contig_distribution_compare() ** **  Compare Assembly Contig
           Length Distributions) -> structure: parameter "workspace_name" of
           type "workspace_name" (** The workspace object refs are of form:
           ** **    objects = ws.get_objects([{'ref':
           params['workspace_id']+'/'+params['obj_name']}]) ** ** "ref" means
           the entire name combining the workspace id and the object name **
           "id" is a numerical identifier of the workspace or object, and
           should just be used for workspace ** "name" is a string identifier
           of a workspace or object.  This is received from Narrative.),
           parameter "input_assembly_refs" of type "data_obj_ref"
        :returns: instance of type "Contig_Distribution_Compare_Output" ->
           structure: parameter "report_name" of type "data_obj_name",
           parameter "report_ref" of type "data_obj_ref"
        """
        # ctx is the context object
        # return variables are: returnVal
        #BEGIN run_contig_distribution_compare

        # very strange, re import from above isn't being retained in this scope
        import re

        #### STEP 0: basic init
        ##
        console = []
        invalid_msgs = []
        report_text = ''
        self.log(console, 'Running run_contig_distribution_compare(): ')
        self.log(console, "\n"+pformat(params))

        # Auth
        token = ctx['token']
        headers = {'Authorization': 'OAuth '+token}
        env = os.environ.copy()
        env['KB_AUTH_TOKEN'] = token

        # API Clients
        #SERVICE_VER = 'dev'  # DEBUG
        SERVICE_VER = 'release'
        # wsClient
        try:
            wsClient = workspaceService(self.workspaceURL, token=token)
        except Exception as e:
            raise ValueError('Unable to instantiate wsClient with workspaceURL: '+ self.workspaceURL +' ERROR: ' + str(e))
        # setAPI_Client
        try:
            #setAPI_Client = SetAPI (url=self.callbackURL, token=ctx['token'])  # for SDK local.  local doesn't work for SetAPI
            setAPI_Client = SetAPI (url=self.serviceWizardURL, token=ctx['token'])  # for dynamic service
        except Exception as e:
            raise ValueError('Unable to instantiate setAPI_Client with serviceWizardURL: '+ self.serviceWizardURL +' ERROR: ' + str(e))
        # auClient
        try:
            auClient = AssemblyUtil(self.callbackURL, token=ctx['token'], service_ver=SERVICE_VER)
        except Exception as e:
            raise ValueError('Unable to instantiate auClient with callbackURL: '+ self.callbackURL +' ERROR: ' + str(e))
        # dfuClient
        try:
            dfuClient = DFUClient(self.callbackURL)
        except Exception as e:
            raise ValueError('Unable to instantiate dfu_Client with callbackURL: '+ self.callbackURL +' ERROR: ' + str(e))

        # param checks
        required_params = ['workspace_name',
                           'input_assembly_refs'
                          ]
        for arg in required_params:
            if arg not in params or params[arg] == None or params[arg] == '':
                raise ValueError ("Must define required param: '"+arg+"'")

        # load provenance
        provenance = [{}]
        if 'provenance' in ctx:
            provenance = ctx['provenance']
        provenance[0]['input_ws_objects']=[]
        for input_ref in params['input_assembly_refs']:
            provenance[0]['input_ws_objects'].append(input_ref)

        # set the output paths
        timestamp = int((datetime.utcnow() - datetime.utcfromtimestamp(0)).total_seconds()*1000)
        output_dir = os.path.join(self.scratch,'output.'+str(timestamp))
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        html_output_dir = os.path.join(output_dir,'html')
        if not os.path.exists(html_output_dir):
            os.makedirs(html_output_dir)
        hist_folder_name = 'histograms'
        hist_output_dir = os.path.join(html_output_dir,hist_folder_name)
        if not os.path.exists(hist_output_dir):
            os.makedirs(hist_output_dir)


        #### STEP 1: get assembly refs
        ##
        if len(invalid_msgs) == 0:
            set_obj_type = "KBaseSets.AssemblySet"
            assembly_obj_types = ["KBaseGenomeAnnotations.Assembly", "KBaseGenomes.ContigSet"]
            accepted_input_types = [set_obj_type] + assembly_obj_types
            assembly_refs = []
            assembly_names = []
            assembly_refs_seen = dict()

            for i,input_ref in enumerate(params['input_assembly_refs']):
                # assembly obj info
                try:

                    input_obj_info = wsClient.get_object_info_new ({'objects':[{'ref':input_ref}]})[0]
                    input_obj_type = re.sub ('-[0-9]+\.[0-9]+$', "", input_obj_info[TYPE_I])  # remove trailing version
                    input_obj_name = input_obj_info[NAME_I]

                    self.log (console, "GETTING ASSEMBLY: "+str(input_ref)+" "+str(input_obj_name))  # DEBUG

                except Exception as e:
                    raise ValueError('Unable to get object from workspace: (' + input_ref +'): ' + str(e))
                if input_obj_type not in accepted_input_types:
                    raise ValueError ("Input object of type '"+input_obj_type+"' not accepted.  Must be one of "+", ".join(accepted_input_types))

                # add members to assembly_ref list
                if input_obj_type in assembly_obj_types:
                    try:
                        assembly_seen = assembly_refs_seen[input_ref]
                        continue
                    except:
                        assembly_refs_seen[input_ref] = True
                        assembly_refs.append(input_ref)
                        assembly_names.append(input_obj_name)
                elif input_obj_type != set_obj_type:
                    raise ValueError ("bad obj type for input_ref: "+input_ref)
                else:  # add assembly set members

                    try:
                        assemblySet_obj = setAPI_Client.get_assembly_set_v1 ({'ref':input_ref, 'include_item_info':1})
                    except Exception as e:
                        raise ValueError('Unable to get object from workspace: (' + input_ref +')' + str(e))

                    for assembly_obj in assemblySet_obj['data']['items']:
                        this_assembly_ref = assembly_obj['ref']
                        try:
                            assembly_seen = assembly_refs_seen[this_assembly_ref]
                            continue
                        except:
                            assembly_refs_seen[this_assembly_ref] = True
                            assembly_refs.append(this_assembly_ref)
                            try:

                                this_input_obj_info = wsClient.get_object_info_new ({'objects':[{'ref':this_assembly_ref}]})[0]
                                this_input_obj_type = re.sub ('-[0-9]+\.[0-9]+$', "", input_obj_info[TYPE_I])  # remove trailing version
                                this_input_obj_name = this_input_obj_info[NAME_I]
                                assembly_names.append(this_input_obj_name)
                            except Exception as e:
                                raise ValueError('Unable to get object from workspace: (' + this_assembly_ref +')' + str(e))


        #### STEP 2: Get assemblies to score as fasta files
        ##
        if len(invalid_msgs) == 0:
            self.log (console, "Retrieving Assemblies")  # DEBUG

            #assembly_outdir = os.path.join (output_dir, 'score_assembly')
            #if not os.path.exists(assembly_outdir):
            #    os.makedirs(assembly_outdir)
            score_assembly_file_paths = []

            for ass_i,input_ref in enumerate(assembly_refs):
                self.log (console, "\tAssembly: "+assembly_names[ass_i]+" ("+assembly_refs[ass_i]+")")  # DEBUG
                contig_file = auClient.get_assembly_as_fasta({'ref':assembly_refs[ass_i]}).get('path')
                sys.stdout.flush()
                contig_file_path = dfuClient.unpack_file({'file_path': contig_file})['file_path']
                score_assembly_file_paths.append(contig_file_path)
                #clean_ass_ref = assembly_ref.replace('/','_')
                #assembly_outfile_path = os.join(assembly_outdir, clean_assembly_ref+".fna")
                #shutil.move(contig_file_path, assembly_outfile_path)


        #### STEP 3: Get distributions of contig attributes
        ##
        if len(invalid_msgs) == 0:

            # score fasta lens in contig files
            read_buf_size  = 65536
            #write_buf_size = 65536

            lens = []
            for ass_i,assembly_file_path in enumerate(score_assembly_file_paths):
                ass_name = assembly_names[ass_i]
                self.log (console, "Reading contig lengths in assembly: "+ass_name)  # DEBUG

                lens.append([])
                with open (assembly_file_path, 'r', read_buf_size) as ass_handle:
                    seq_buf = ''
                    for fasta_line in ass_handle:
                        if fasta_line.startswith('>'):
                            if seq_buf != '':
                                seq_len = len(seq_buf)
                                lens[ass_i].append(seq_len)
                                seq_buf = ''
                        else:
                            seq_buf += ''.join(fasta_line.split())
                    if seq_buf != '':
                        seq_len = len(seq_buf)
                        lens[ass_i].append(seq_len)
                        seq_buf = ''

            # sort lens (absolutely critical to subsequent steps)
            for ass_i,ass_name in enumerate(assembly_names):
                self.log (console, "Sorting contig lens for "+ass_name)  # DEBUG
                lens[ass_i].sort(key=int, reverse=True)  # sorting is critical.  this sort() is in place

            # get min_max ranges
            huge_val = 100000000000000000
            len_buckets = [ 1000000, 100000, 10000, 1000, 500, 1 ]
            percs = [50, 75, 90]
            max_len = 0
            max_lens = []
            best_val = { 'len': 0,
                         'N': {},
                         'L': {},
                         'summary_stats': {},
                         'cumulative_len_stats': {}
                         }
            worst_val = { 'len': huge_val,
                          'N': {},
                          'L': {},
                          'summary_stats': {},
                          'cumulative_len_stats': {}
                          }
            for perc in percs:
                best_val['N'][perc] = 0
                best_val['L'][perc] = huge_val
                worst_val['N'][perc] = huge_val
                worst_val['L'][perc] = 0
            for bucket in len_buckets:
                best_val['summary_stats'][bucket] = 0
                best_val['cumulative_len_stats'][bucket] = 0
                worst_val['summary_stats'][bucket] = huge_val
                worst_val['cumulative_len_stats'][bucket] = huge_val

            for ass_i,ass_name in enumerate(assembly_names):
                self.log (console, "Getting max lens "+ass_name)  # DEBUG
                this_max_len = lens[ass_i][0]
                max_lens.append(this_max_len)
                if this_max_len > max_len:
                    max_len = this_max_len

            # Sum cumulative plot data
            max_total = 0
            total_lens = []
            cumulative_lens = []
            for ass_i,ass_name in enumerate(assembly_names):
                self.log (console, "Summing cumulative lens for "+ass_name)  # DEBUG
                total_lens.append(0)
                cumulative_lens.append([])
                for val in lens[ass_i]:
                    cumulative_lens[ass_i].append(total_lens[ass_i]+val)
                    total_lens[ass_i] += val
            for ass_i,ass_name in enumerate(assembly_names):
                if total_lens[ass_i] > max_total:
                    max_total = total_lens[ass_i]

            """
            # DEBUG
            self.log (console, "SORTED VALS\n================================")
            for ass_i,ass_name in enumerate(assembly_names):
                self.log (console, ass_name)
                self.log (console, "\t\t"+"TOTAL_LEN: "+str(total_lens[ass_i]))
                for val_i,val in enumerate(lens[ass_i]):
                    self.log (console, "\t\t\t"+"VAL: "+str(val))
                for len_i,length in enumerate(cumulative_lens[ass_i]):
                    self.log (console, "\t\t\t"+"LEN: "+str(length))
            # END DEBUG
            """

            # get N50 and L50 (and 75s, and 90s)
            N = dict()
            L = dict()
            for perc in percs:
                N[perc] = []
                L[perc] = []
            for perc in percs:
                frac = perc/100.0
                for ass_i,ass_name in enumerate(assembly_names):
                    self.log (console, "Getting N/L"+str(perc)+" for "+ass_name)  # DEBUG
                    for val_i,val in enumerate(lens[ass_i]):
                        if cumulative_lens[ass_i][val_i] >= frac * total_lens[ass_i]:
                            N[perc].append(val)
                            L[perc].append(val_i+1)
                            break

            """
            # DEBUG
            self.log (console, "N50, etc.\n================================")
            for ass_i,ass_name in enumerate(assembly_names):
                self.log (console, ass_name)
                for perc in percs:
                    self.log (console, "\t"+"N"+str(perc)+": "+str(N[perc][ass_i]))
                    self.log (console, "\t"+"L"+str(perc)+": "+str(L[perc][ass_i]))
            # END DEBUG
            """

            # count buckets and make hist without lens < 10K

            # count buckets and transform lens to log of length for hist
            #hist_window_width = 10000  # make it log scale?
            #N_hist_windows = int(max_len % hist_window_width)
            #len_buckets = [ 1000000, 500000, 100000, 50000, 10000, 5000, 1000, 500, 0 ]
            summary_stats = []
            cumulative_len_stats = []
            hist_vals = []
            hist_cnt_by_bin = []  # just to get shared heights for separate hist graphs
            top_hist_cnt = [0, 0, 0]
            #hist_binwidth = [500, 5000, 20000]
            long_contig_nbins = 70
            hist_binwidth = [500, 5000, (max_len // long_contig_nbins)]
            min_hist_val_accept = [0, 10000, 100000]
            max_hist_val_accept = [10000, 100000, 100000000000000000000]
            #log_lens = []
            #max_log_len = 0
            for ass_i,ass_name in enumerate(assembly_names):
                self.log (console, "Building summary and histograms from assembly: "+ass_name)  # DEBUG
                #lens[ass_i].sort(key=int, reverse=True)  # sorting is critical.  Already sorted

                # hist
                """
                # get log lens
                log_lens.append([])
                for val in lens[ass_i]:
                    log10_val = math.log10(val)
                    if log10_val > max_log_len:
                        max_log10_len = log10_val
                    log_lens[ass_i].append(log10_val)
                """
                hist_vals.append([])
                hist_cnt_by_bin.append([])
                for hist_i,top_cnt in enumerate(top_hist_cnt):
                    hist_vals[ass_i].append([])
                    hist_cnt_by_bin[ass_i].append([])
                    long_len = max_len
                    if hist_i < len(top_hist_cnt)-1:
                        long_len = max_hist_val_accept[hist_i]
                    for bin_i in range((long_len // hist_binwidth[hist_i])+1):
                        hist_cnt_by_bin[ass_i][hist_i].append(0)

                for val in lens[ass_i]:
                    this_hist_i = 0
                    for hist_i,top_cnt in enumerate(top_hist_cnt):
                        if val >= min_hist_val_accept[hist_i] and val < max_hist_val_accept[hist_i]:
                            this_hist_i = hist_i
                            break
                    bin_i = val // hist_binwidth[this_hist_i]
                    hist_cnt_by_bin[ass_i][this_hist_i][bin_i] += 1
                    hist_vals[ass_i][this_hist_i].append(val)
                    if hist_cnt_by_bin[ass_i][this_hist_i][bin_i] > top_hist_cnt[this_hist_i]:
                        top_hist_cnt[this_hist_i] = hist_cnt_by_bin[ass_i][this_hist_i][bin_i]

                # summary stats
                summary_stats.append(dict())
                cumulative_len_stats.append(dict())
                for bucket in len_buckets:
                    summary_stats[ass_i][bucket] = 0
                    cumulative_len_stats[ass_i][bucket] = 0
                curr_bucket_i = 0
                for val in lens[ass_i]:
                    for bucket_i in range(curr_bucket_i,len(len_buckets)):
                        bucket = len_buckets[bucket_i]
                        if val >= bucket:
                            summary_stats[ass_i][bucket] += 1
                            cumulative_len_stats[ass_i][bucket] += val
                            #curr_bucket_i = bucket_i
                            #break
                        else:
                            curr_bucket_i = bucket_i + 1

            # adjust best and worst values
            for ass_i,ass_name in enumerate(assembly_names):
                if max_lens[ass_i] > best_val['len']:
                    best_val['len'] = max_lens[ass_i]
                if max_lens[ass_i] < worst_val['len']:
                    worst_val['len'] = max_lens[ass_i]

                for perc in percs:
                    if N[perc][ass_i] > best_val['N'][perc]:
                        best_val['N'][perc] = N[perc][ass_i]
                    if N[perc][ass_i] < worst_val['N'][perc]:
                        worst_val['N'][perc] = N[perc][ass_i]
                    if L[perc][ass_i] < best_val['L'][perc]:
                        best_val['L'][perc] = L[perc][ass_i]
                    if L[perc][ass_i] > worst_val['L'][perc]:
                        worst_val['L'][perc] = L[perc][ass_i]

                for bucket in len_buckets:
                    if summary_stats[ass_i][bucket] > best_val['summary_stats'][bucket]:
                        best_val['summary_stats'][bucket] = summary_stats[ass_i][bucket]
                    if summary_stats[ass_i][bucket] < worst_val['summary_stats'][bucket]:
                        worst_val['summary_stats'][bucket] = summary_stats[ass_i][bucket]
                    if cumulative_len_stats[ass_i][bucket] > best_val['cumulative_len_stats'][bucket]:
                        best_val['cumulative_len_stats'][bucket] = cumulative_len_stats[ass_i][bucket]
                    if cumulative_len_stats[ass_i][bucket] < worst_val['cumulative_len_stats'][bucket]:
                        worst_val['cumulative_len_stats'][bucket] = cumulative_len_stats[ass_i][bucket]


        #### STEP 4: build text report
        ##
        if len(invalid_msgs) == 0:
            for ass_i,ass_name in enumerate(assembly_names):
                report_text += "ASSEMBLY STATS for "+ass_name+"\n"

                report_text += "\t"+"Len longest contig: "+str(max_lens[ass_i])+" bp"+"\n"
                for perc in percs:
                    report_text += "\t"+"N"+str(perc)+" (L"+str(perc)+"):\t"+str(N[perc][ass_i])+" ("+str(L[perc][ass_i])+")"+"\n"
                for bucket in len_buckets:
                    report_text += "\t"+"Num contigs >= "+str(bucket)+" bp:\t"+str(summary_stats[ass_i][bucket])+"\n"
                report_text += "\n"

                for bucket in len_buckets:
                    report_text += "\t"+"Len contigs >= "+str(bucket)+" bp:\t"+str(cumulative_len_stats[ass_i][bucket])+" bp"+"\n"
                report_text += "\n"

        self.log(console, report_text)  # DEBUG


        #### STEP 5: Make figures with matplotlib
        ##
        file_links = []
        shared_img_in_height = 4.0
        total_ass = len(assembly_names)

        # Key
        plot_name = "key_plot"
        plot_name_desc = "KEY"
        self.log (console, "GENERATING PLOT "+plot_name_desc)
        img_dpi = 200
        img_units = "in"
        #spacing = 1.0 / float(total_ass+3)
        spacing = 1.0
        img_in_width  = 6.0
        img_in_height = 0.5 * (total_ass)
        x_text_margin = 0.01
        y_text_margin = 0.01
        title_fontsize = 12
        #text_color = "#606060"
        text_color = "#303030"
        text_fontsize = 10
        fig = plt.figure()
        fig.set_size_inches(img_in_width, img_in_height)
        ax = plt.subplot2grid ( (1,1), (0,0), rowspan=1, colspan=1)
        #ax = fig.axes[0]
        # Let's turn off visibility of all tic labels and boxes here
        for ax in fig.axes:
            ax.xaxis.set_visible(False)  # remove axis labels and tics
            ax.yaxis.set_visible(False)
            for t in ax.get_xticklabels()+ax.get_yticklabels():  # remove tics
                t.set_visible(False)
            #ax.spines['top'].set_visible(False)     # Get rid of top axis line
            #ax.spines['bottom'].set_visible(False)  # bottom axis line
            #ax.spines['left'].set_visible(False)    # left axis line
            #ax.spines['right'].set_visible(False)   # right axis line
        #ax.grid(True)
        #ax.set_title (plot_name_desc)
        #ax.set_xlabel ('sorted contig order (longest to shortest)')
        #ax.set_ylabel ('sum of contig lengths (Mbp)')
        #plt.tight_layout()

        # build x and y coord lists
        x0 = 1
        x1 = 2
        x_indent = 0.1
        x_coords = [x0, x1]
        ax.set_xlim(x0-x_indent, x1+x_indent)
        #ax.set_ylim(-1*spacing, (total_ass+1)*spacing)
        ax.set_ylim(0, (total_ass+1)*spacing)
        for ass_i,ass_name in enumerate(assembly_names):
            y_pos = (total_ass - ass_i) * spacing
            y_coords = [y_pos, y_pos]
            plt.plot(x_coords, y_coords, lw=2)
            ax.text (x0+x_text_margin, y_pos+y_text_margin, ass_name, verticalalignment="bottom", horizontalalignment="left", color=text_color, fontsize=text_fontsize, zorder=1)
        #ax.text (0.5*(x0+x1), -1*spacing+y_text_margin, plot_name_desc, verticalalignment="bottom", horizontalalignment="center", color=text_color, fontsize=title_fontsize, zorder=2)
        ax.text (0.5*(x0+x1), 0+y_text_margin, plot_name_desc, verticalalignment="bottom", horizontalalignment="center", color=text_color, fontsize=title_fontsize, zorder=2)

        # save plot
        self.log (console, "SAVING PLOT "+plot_name_desc)
        key_png_file = png_file = plot_name+".png"
        key_pdf_file = pdf_file = plot_name+".pdf"
        output_png_file_path = os.path.join (html_output_dir, png_file)
        output_pdf_file_path = os.path.join (html_output_dir, pdf_file)
        fig.savefig (output_png_file_path, dpi=img_dpi)
        fig.savefig (output_pdf_file_path, format='pdf')

        # upload PNG
        try:
            upload_ret = dfuClient.file_to_shock({'file_path': output_png_file_path,
                                                  'make_handle': 0})
            file_links.append({'shock_id': upload_ret['shock_id'],
                               'name': png_file,
                               'label': plot_name_desc+' PNG'
                               }
                              )
        except:
            raise ValueError ('Logging exception loading png_file '+png_file+' to shock')
        # upload PDF
        try:
            upload_ret = dfuClient.file_to_shock({'file_path': output_pdf_file_path,
                                                  'make_handle': 0})
            file_links.append({'shock_id': upload_ret['shock_id'],
                               'name': pdf_file,
                               'label': plot_name_desc+' PDF'
                               }
                              )
        except:
            raise ValueError ('Logging exception loading pdf_file '+pdf_file+' to shock')


        # Cumulative len plot
        plot_name = "cumulative_len_plot"
        plot_name_desc = "Cumulative Length (in Mbp)"
        self.log (console, "GENERATING PLOT "+plot_name_desc)
        val_scale_shift = 1000000.0  # to make Mbp
        img_dpi = 200
        img_units = "in"
        img_in_width  = 6.0
        img_in_height = shared_img_in_height
        x_margin = 0.01
        y_margin = 0.01
        title_fontsize = 12
        text_color = "#606060"
        fig = plt.figure()
        fig.set_size_inches(img_in_width, img_in_height)
        ax = plt.subplot2grid ( (1,1), (0,0), rowspan=1, colspan=1)
        #ax = fig.axes[0]
        """
        # Let's turn off visibility of all tic labels and boxes here
        for ax in fig.axes:
            ax.xaxis.set_visible(False)  # remove axis labels and tics
            ax.yaxis.set_visible(False)
            for t in ax.get_xticklabels()+ax.get_yticklabels():  # remove tics
                t.set_visible(False)
            ax.spines['top'].set_visible(False)     # Get rid of top axis line
            ax.spines['bottom'].set_visible(False)  # bottom axis line
            ax.spines['left'].set_visible(False)    # left axis line
            ax.spines['right'].set_visible(False)   # right axis line
        """
        ax.grid(True)
        ax.set_title (plot_name_desc)
        ax.set_xlabel ('sorted contig order (longest to shortest)')
        ax.set_ylabel ('sum of contig lengths (Mbp)')
        plt.tight_layout()
        #ax.text (x_margin, 1.0-(y_margin), plot_name, verticalalignment="bottom", horizontalalignment="left", color=text_color, fontsize=title_fontsize, zorder=1)

        # build x and y coord lists
        for ass_i,ass_name in enumerate(assembly_names):
            x_coords = []
            y_coords = []
            for val_i,val in enumerate(cumulative_lens[ass_i]):
                x_coords.append(val_i+1)
                #y_coords.append(val)
                y_coords.append(float(val) / val_scale_shift)
            plt.plot(x_coords, y_coords, lw=2)

        """
        # capture data into pandas
        cumulative_lens_by_ass_name = dict()
        for ass_i,ass_name in enumerate(assembly_names):
            cumulative_lens_by_ass_name[ass_name] = pd.Series(cumulative_lens[ass_i])
        cumulative_lens_df = pd.DataFrame(cumulative_lens_by_ass_name)
        cumulative_lens_plot = cumulative_lens_df \
                                .plot(kind="line", figsize=(15,5), ylim=(0,max_total), fontsize=15, lw=5)
        cumulative_lens_plot.xaxis.grid(True)
        cumulative_lens_plot.yaxis.grid(True) 
        fig = cumulative_lens_plot.get_figure()
        """

        # save plot
        self.log (console, "SAVING PLOT "+plot_name_desc)
        cumulative_lens_png_file = png_file = plot_name+".png"
        cumulative_lens_pdf_file = pdf_file = plot_name+".pdf"
        output_png_file_path = os.path.join (html_output_dir, png_file)
        output_pdf_file_path = os.path.join (html_output_dir, pdf_file)
        fig.savefig (output_png_file_path, dpi=img_dpi)
        fig.savefig (output_pdf_file_path, format='pdf')

        # upload PNG
        try:
            upload_ret = dfuClient.file_to_shock({'file_path': output_png_file_path,
                                                  'make_handle': 0})
            file_links.append({'shock_id': upload_ret['shock_id'],
                               'name': png_file,
                               'label': plot_name_desc+' PNG'
                               }
                              )
        except:
            raise ValueError ('Logging exception loading png_file '+png_file+' to shock')
        # upload PDF
        try:
            upload_ret = dfuClient.file_to_shock({'file_path': output_pdf_file_path,
                                                  'make_handle': 0})
            file_links.append({'shock_id': upload_ret['shock_id'],
                               'name': pdf_file,
                               'label': plot_name_desc+' PDF'
                               }
                              )
        except:
            raise ValueError ('Logging exception loading pdf_file '+pdf_file+' to shock')


        # Sorted Contig len plot
        plot_name = "sorted_contig_lengths"
        plot_name_desc = "Sorted Contig Lengths (in Mbp)"
        self.log (console, "GENERATING PLOT "+plot_name_desc)
        val_scale_shift = 1000000.0  # to make Mbp
        img_dpi = 200
        img_units = "in"
        img_in_width  = 6.0
        img_in_height = shared_img_in_height
        x_margin = 0.01
        y_margin = 0.01
        title_fontsize = 12
        text_color = "#606060"
        fig = plt.figure()
        fig.set_size_inches(img_in_width, img_in_height)
        ax = plt.subplot2grid ( (1,1), (0,0), rowspan=1, colspan=1)
        #ax = fig.axes[0]
        """
        # Let's turn off visibility of all tic labels and boxes here
        for ax in fig.axes:
            ax.xaxis.set_visible(False)  # remove axis labels and tics
            ax.yaxis.set_visible(False)
            for t in ax.get_xticklabels()+ax.get_yticklabels():  # remove tics
                t.set_visible(False)
            ax.spines['top'].set_visible(False)     # Get rid of top axis line
            ax.spines['bottom'].set_visible(False)  # bottom axis line
            ax.spines['left'].set_visible(False)    # left axis line
            ax.spines['right'].set_visible(False)   # right axis line
        """
        ax.grid(True)
        ax.set_title (plot_name_desc)
        ax.set_xlabel ('sum of sorted contig lengths (Mbp)')
        ax.set_ylabel ('sorted contig lengths (Mbp)')
        plt.tight_layout()
        #ax.text (x_margin, 1.0-(y_margin), plot_name, verticalalignment="bottom", horizontalalignment="left", color=text_color, fontsize=title_fontsize, zorder=1)

        # build x and y coord lists
        mini_delta = .000001
        for ass_i,ass_name in enumerate(assembly_names):
            x_coords = []
            y_coords = []
            running_sum = 0
            for val_i,val in enumerate(lens[ass_i]):
                x_coords.append(float(running_sum + mini_delta) / val_scale_shift)
                y_coords.append(float(val) / val_scale_shift)
                running_sum += val
                x_coords.append(float(running_sum) / val_scale_shift)
                y_coords.append(float(val) / val_scale_shift)
            plt.plot(x_coords, y_coords, lw=2)

        # save plot
        self.log (console, "SAVING PLOT "+plot_name_desc)
        sorted_lens_png_file = png_file = plot_name+".png"
        sorted_pens_pdf_file = pdf_file = plot_name+".pdf"
        output_png_file_path = os.path.join (html_output_dir, png_file)
        output_pdf_file_path = os.path.join (html_output_dir, pdf_file)
        fig.savefig (output_png_file_path, dpi=img_dpi)
        fig.savefig (output_pdf_file_path, format='pdf')

        # upload PNG
        try:
            upload_ret = dfuClient.file_to_shock({'file_path': output_png_file_path,
                                                  'make_handle': 0})
            file_links.append({'shock_id': upload_ret['shock_id'],
                               'name': png_file,
                               'label': plot_name_desc+' PNG'
                               }
                              )
        except:
            raise ValueError ('Logging exception loading png_file '+png_file+' to shock')
        # upload PDF
        try:
            upload_ret = dfuClient.file_to_shock({'file_path': output_pdf_file_path,
                                                  'make_handle': 0})
            file_links.append({'shock_id': upload_ret['shock_id'],
                               'name': pdf_file,
                               'label': plot_name_desc+' PDF'
                               }
                              )
        except:
            raise ValueError ('Logging exception loading pdf_file '+pdf_file+' to shock')


        # Hist plots for each assembly
        hist_lens_png_files = []
        hist_lens_pdf_files = []
        units            = ['Kbp', 'Kbp', 'Mbp']
        val_scale_adjust = [1000, 1000, 1000000]
        img_in_width     = [3.0, 3.0, 7.0]
        for ass_i,ass_name in enumerate(assembly_names):
            hist_lens_png_files.append([])
            hist_lens_pdf_files.append([])
            for hist_i,top_cnt in enumerate(top_hist_cnt):
                if len(hist_vals[ass_i][hist_i]) == 0:
                    continue
                long_len = max_len
                if hist_i < len(top_hist_cnt)-1:
                    long_len = max_hist_val_accept[hist_i]
                plot_name = "hist_len_plot-"+ass_name+"_hist_window_"+str(min_hist_val_accept[hist_i])+"-"+str(long_len)
                plot_name_desc = "Histogram of Contig Lengths "+str(min_hist_val_accept[hist_i])+"-"+str(long_len)+" (in bp)"
                self.log (console, "GENERATING PLOT for "+ass_name+" "+plot_name_desc)
                img_dpi = 200
                img_units = "in"
                #img_in_width  = 6.0
                img_in_height = 3.0
                x_margin = 0.01
                y_margin = 0.01
                title_fontsize = 12
                text_color = "#606060"
                hist_color = "slateblue"
                fig = plt.figure()
                fig.set_size_inches(img_in_width[hist_i], img_in_height)
                ax = plt.subplot2grid ( (1,1), (0,0), rowspan=1, colspan=1)
                #ax = fig.axes[0]
                """
                # Let's turn off visibility of all tic labels and boxes here
                for ax in fig.axes:
                    ax.xaxis.set_visible(False)  # remove axis labels and tics
                    ax.yaxis.set_visible(False)
                    for t in ax.get_xticklabels()+ax.get_yticklabels():  # remove tics
                        t.set_visible(False)
                    ax.spines['top'].set_visible(False)     # Get rid of top axis line
                    ax.spines['bottom'].set_visible(False)  # bottom axis line
                    ax.spines['left'].set_visible(False)    # left axis line
                    ax.spines['right'].set_visible(False)   # right axis line
                """
                ax.grid(True)
                min_hist_bin_beg = 0
                max_hist_bin_end = float(long_len) / val_scale_adjust[hist_i]
                binwidth = float (hist_binwidth[hist_i]) / val_scale_adjust[hist_i]
                ax.set_xlim ([0, max_hist_bin_end + 2*binwidth])
                ax.set_ylim ([0, top_hist_cnt[hist_i] + top_hist_cnt[hist_i] // 10])
                ax.set_xlabel ('contig length bin ('+units[hist_i]+')')
                ax.set_ylabel ('# contigs')
                plt.tight_layout()
                #ax.set_title (plot_name_desc)  # given in table column header

                # plot hist
                #min_log10_len = 0
                ##max_log10_len  # set above
                #log10_binwidth = 0.1

                #plt.hist(hist_vals[ass_i][hist_i], log=False, bins=range(min_hist_bin_beg, max_hist_bin_end + binwidth, binwidth))
                scaled_hist_vals = []
                for val in hist_vals[ass_i][hist_i]:
                    scaled_hist_vals.append(float(val) / val_scale_adjust[hist_i])
                plt.hist(scaled_hist_vals, color=hist_color, log=False, bins=np.arange(min_hist_bin_beg, max_hist_bin_end + 3*binwidth, binwidth))

                # save plot
                self.log (console, "SAVING PLOT "+plot_name_desc)
                png_file = plot_name+".png"
                hist_lens_png_files[ass_i].append(hist_folder_name+'/'+png_file)
                pdf_file = plot_name+".pdf"
                hist_lens_pdf_files[ass_i].append(hist_folder_name+'/'+pdf_file)
                output_png_file_path = os.path.join (hist_output_dir, png_file)
                output_pdf_file_path = os.path.join (hist_output_dir, pdf_file)
                fig.savefig (output_png_file_path, dpi=img_dpi)
                fig.savefig (output_pdf_file_path, format='pdf')

                """
                # upload PNG
                try:
                    upload_ret = dfuClient.file_to_shock({'file_path': output_png_file_path,
                                                          'make_handle': 0})
                    file_links.append({'shock_id': upload_ret['shock_id'],
                                       'name': png_file,
                                       'label': plot_name_desc+' PNG'
                                       }
                                      )
                except:
                    raise ValueError ('Logging exception loading png_file '+png_file+' to shock')
                # upload PDF
                try:
                    upload_ret = dfuClient.file_to_shock({'file_path': output_pdf_file_path,
                                                          'make_handle': 0})
                    file_links.append({'shock_id': upload_ret['shock_id'],
                                       'name': pdf_file,
                                       'label': plot_name_desc+' PDF'
                                       }
                                      )
                except:
                    raise ValueError ('Logging exception loading pdf_file '+pdf_file+' to shock')
                """

        #### STEP 6: Create and Upload HTML Report
        ##
        self.log (console, "CREATING HTML REPORT")
        def get_cell_color (val, best, worst, low_good=False):
            #self.log (console, "VAL: "+str(val)+" BEST: "+str(best)+" WORST: "+str(worst))  # DEBUG

            if best == worst:
                return '#ffffff'
            val_color_map = { 0: '00',
                              1: '11',
                              2: '22',
                              3: '33',
                              4: '44',
                              5: '55',
                              6: '66',
                              7: '77',
                              8: '88',
                              9: '99',
                              10: 'aa',
                              11: 'bb',
                              12: 'cc',
                              13: 'dd',
                              14: 'ee',
                              15: 'ff'
                             }
            base_intensity = 11
            top = 15 - base_intensity
            mid = 0.5 * (best + worst)
            if val == mid:
                return '#ffffff'
            if low_good:
                if val < mid:
                    rescaled_val = int(0.5 + top * (val-best) / (mid-best))
                    #self.log (console, "A, MID: "+str(mid)+" RESCALED_VAL: "+str(rescaled_val))  # DEBUG
                    r = val_color_map[base_intensity + rescaled_val]
                    g = val_color_map[base_intensity + rescaled_val]
                    b = 'ff'
                else:
                    rescaled_val = int(0.5 + top * (val-worst) / (mid-worst))
                    #self.log (console, "B, MID: "+str(mid)+" RESCALED_VAL: "+str(rescaled_val))  # DEBUG
                    r = 'ff'
                    g = val_color_map[base_intensity + rescaled_val]
                    b = val_color_map[base_intensity + rescaled_val]
            else:
                if val > mid:
                    rescaled_val = int(0.5 + top * (val-best) / (mid-best))
                    #self.log (console, "C, MID: "+str(mid)+" RESCALED_VAL: "+str(rescaled_val))  # DEBUG
                    r = val_color_map[base_intensity + rescaled_val]
                    g = val_color_map[base_intensity + rescaled_val]
                    b = 'ff'
                else:
                    rescaled_val = int(0.5 + top * (val-worst) / (mid-worst))
                    #self.log (console, "D, MID: "+str(mid)+" RESCALED_VAL: "+str(rescaled_val))  # DEBUG
                    r = 'ff'
                    g = val_color_map[base_intensity + rescaled_val]
                    b = val_color_map[base_intensity + rescaled_val]
            #self.log (console, "RGB: "+r+g+b)  # DEBUG
            return '#'+r+g+b

        subtab_N_rows = 6
        hist_colspan = 3 # in cells
        non_hist_colspan = 7 # in cells
        key_img_width = 475  # in pixels
        big_img_height = 300  # in pixels
        hist_img_height = 200  # in pixels
        head_color = "#eeeeff"
        border_head_color = "#ffccff"
        text_fontsize = "2"
        text_color = '#606060'
        border_body_color = "#cccccc"
        key_border_color = border_body_color
        base_cell_color = "#eeeeee"
        cellpadding = "3"
        cellspacing = "2"
        subtab_cellpadding = "1"
        subtab_cellspacing = "2"
        border = "0"
        sp = '&nbsp;'

        html_report_lines = []
        html_report_lines += ['<html>']
        html_report_lines += ['<head>']
        html_report_lines += ['<title>KBase Assembled Contig Distributions</title>']
#        html_report_lines += ['<style>']
#        html_report_lines += [".vertical-text {\ndisplay: inline-block;\noverflow: hidden;\nwidth: 0.65em;\n}\n.vertical-text__inner {\ndisplay: inline-block;\nwhite-space: nowrap;\nline-height: 1.1;\ntransform: translate(0,100%) rotate(-90deg);\ntransform-origin: 0 0;\n}\n.vertical-text__inner:after {\ncontent: \"\";\ndisplay: block;\nmargin: 0.0em 0 100%;\n}"]
#        html_report_lines += [".vertical-text_title {\ndisplay: inline-block;\noverflow: hidden;\nwidth: 1.0em;\n}\n.vertical-text__inner_title {\ndisplay: inline-block;\nwhite-space: nowrap;\nline-height: 1.0;\ntransform: translate(0,100%) rotate(-90deg);\ntransform-origin: 0 0;\n}\n.vertical-text__inner_title:after {\ncontent: \"\";\ndisplay: block;\nmargin: 0.0em 0 100%;\n}"]
#        html_report_lines += ['</style>']
        html_report_lines += ['</head>']
        html_report_lines += ['<body bgcolor="white">']

        #html_report_lines += ['<tr><td valign=top align=left rowspan=1><div class="vertical-text_title"><div class="vertical-text__inner_title"><font color="'+text_color+'">'+label+'</font></div></div></td>']

        html_report_lines += ['<table cellpadding='+str(cellpadding)+' cellspacing='+str(cellspacing)+' border='+str(border)+'>']
        html_report_lines += ['<tr><td valign=top align=left rowspan=1 colspan='+str(non_hist_colspan+hist_colspan)+'><img src="'+key_png_file+'" width='+str(key_img_width)+'></td></tr>']
        html_report_lines += ['<tr><td valign=top align=left rowspan=1 colspan='+str(non_hist_colspan-1)+'><img src="'+cumulative_lens_png_file+'" height='+str(big_img_height)+'></td>']
        html_report_lines += ['<td valign=top align=left rowspan=1 colspan='+str(hist_colspan)+'><img src="'+sorted_lens_png_file+'" height='+str(big_img_height)+'></td></tr>']

        # key
        best = 10
        worst = 1
        html_report_lines += ['<tr><td>'+sp+'</td></tr>']
        html_report_lines += ['<tr><td></td><td colspan='+str(non_hist_colspan+hist_colspan-1)+'><table cellpadding=5 cellspacing=0 border=1 bordercolor="'+key_border_color+'"><tr>']
        html_report_lines += ['<td bgcolor="'+get_cell_color(best, best, worst)+'"><font color="'+text_color+'" size='+text_fontsize+'>'+'BEST'+'</font></td>']
        for i in [9,8,7,6,5,4,3,2]:
            html_report_lines += ['<td bgcolor="'+get_cell_color(i, best, worst)+'"><font size='+text_fontsize+'>'+sp+'</font></td>']
        html_report_lines += ['<td bgcolor="'+get_cell_color(worst, best, worst)+'"><font color="'+text_color+'" size='+text_fontsize+'>'+'WORST'+'</font></td>']
        html_report_lines += ['</tr></table></td></tr>']

        # header
        html_report_lines += ['<tr bgcolor="'+head_color+'">']
        # name
        html_report_lines += ['<td style="border-right:solid 2px '+border_head_color+'; border-bottom:solid 2px '+border_head_color+'"><font color="'+text_color+'" size='+text_fontsize+' align="left">'+'ASSEMBLY'+'</font></td>']
        # Longest Len
        html_report_lines += ['<td align="center" style="border-right:solid 2px '+border_head_color+'; border-bottom:solid 2px '+border_head_color+'"><font color="'+text_color+'" size='+text_fontsize+'>'+'LONGEST<br>CONTIG<br>(bp)'+'</font></td>']
        # N50,L50 etc.
        html_report_lines += ['<td align="center" style="border-right:solid 2px '+border_head_color+'; border-bottom:solid 2px '+border_head_color+'" colspan=2><font color="'+text_color+'" size='+text_fontsize+'>'+'Nx (Lx)'+'</font></td>']
        # Summary Stats
        html_report_lines += ['<td align="center" style="border-right:solid 2px '+border_head_color+'; border-bottom:solid 2px '+border_head_color+'"><font color="'+text_color+'" size='+text_fontsize+'>'+'LENGTH<br>(bp)'+'</font></td>']
        html_report_lines += ['<td align="center" style="border-right:solid 2px '+border_head_color+'; border-bottom:solid 2px '+border_head_color+'"><font color="'+text_color+'" size='+text_fontsize+'>'+'NUM<br>CONTIGS'+'</font></td>']
        html_report_lines += ['<td align="center" style="border-right:solid 2px '+border_head_color+'; border-bottom:solid 2px '+border_head_color+'"><font color="'+text_color+'" size='+text_fontsize+'>'+'SUM<br>LENGTH<br>(bp)'+'</font></td>']
        # hists
        html_report_lines += ['<td align="center" style="border-right:solid 2px '+border_head_color+'; border-bottom:solid 2px '+border_head_color+'" colspan='+str(1)+'><font color="'+text_color+'" size='+text_fontsize+'>'+'Contig Length Histogram<br>(1bp <= len < 10Kbp)'+'</font></td>']
        html_report_lines += ['<td align="center" style="border-right:solid 2px '+border_head_color+'; border-bottom:solid 2px '+border_head_color+'" colspan='+str(1)+'><font color="'+text_color+'" size='+text_fontsize+'>'+'Contig Length Histogram<br>(10Kbp <= len < 100Kbp)'+'</font></td>']
        html_report_lines += ['<td align="center" style="border-right:solid 2px '+border_head_color+'; border-bottom:solid 2px '+border_head_color+'" colspan='+str(1)+'><font color="'+text_color+'" size='+text_fontsize+'>'+'Contig Length Histogram<br>(len >= 100Kbp)'+'</font></td>']
        html_report_lines += ['</tr>']

        # report stats
        for ass_i,ass_name in enumerate(assembly_names):
            html_report_lines += ['<tr>']
            # name
            html_report_lines += ['<td align="left" bgcolor="'+base_cell_color+'" rowspan='+str(subtab_N_rows)+'><font color="'+text_color+'" size='+text_fontsize+'>'+ass_name+'</font></td>']

            # longest contig
            cell_color = get_cell_color (max_lens[ass_i], best_val['len'], worst_val['len'])
            html_report_lines += ['<td bgcolor="'+cell_color+'" align="center" valign="middle" rowspan='+str(subtab_N_rows)+'><font color="'+text_color+'" size='+text_fontsize+'>'+str(max_lens[ass_i])+'</font></td>']

            # subtable
            edges = ' style="border-right:solid 2px '+border_body_color+'"'
            bottom_edge = ''
            for sub_i in range(subtab_N_rows):
                perc = percs[sub_i // 2]
                bucket = len_buckets[sub_i]
                if sub_i == subtab_N_rows-1:
                    edges = ' style="border-right:solid 2px '+border_body_color+'; border-bottom:solid 2px '+border_body_color+'"'
                    bottom_edge = ' style="border-bottom:solid 2px '+border_body_color+'"'

                # N50, L50, etc.
                if sub_i > 0:
                    html_report_lines += ['<tr>']

                if (sub_i % 2) == 0:
                    cell_color = get_cell_color (N[perc][ass_i], best_val['N'][perc], worst_val['N'][perc])
                    html_report_lines += ['<td align="center"'+bottom_edge+'>'+'<font color="'+text_color+'" size='+text_fontsize+'>'+'N'+str(perc)+':</font></td><td bgcolor="'+cell_color+'" align="right"'+edges+'>'+'<font color="'+text_color+'" size='+text_fontsize+'>'+sp+str(N[perc][ass_i])+'</font></td>']
                else:
                    cell_color = get_cell_color (L[perc][ass_i], best_val['L'][perc], worst_val['L'][perc], low_good=True)
                    html_report_lines += ['<td align="center"'+bottom_edge+'>'+'<font color="'+text_color+'" size='+text_fontsize+'>'+'L'+str(perc)+':</font></td><td bgcolor="'+cell_color+'" align="right"'+edges+'>'+'<font color="'+text_color+'" size='+text_fontsize+'>'+sp+'('+str(L[perc][ass_i])+')'+'</font></td>']

                # Summary Stats
                html_report_lines += ['<td align="center"'+bottom_edge+'>'+'<font color="'+text_color+'" size='+text_fontsize+'>']
                if bucket >= 1000:
                    html_report_lines += ['<nobr>'+'&gt;= '+'10'+'<sup>'+str(int(math.log(bucket,10)+0.1))+'</sup>'+'</nobr>']
                else:
                    html_report_lines += ['<nobr>'+'&gt;= '+str(bucket)+'</nobr>']
                html_report_lines += ['</font></td>']

                cell_color = get_cell_color (summary_stats[ass_i][bucket], best_val['summary_stats'][bucket], worst_val['summary_stats'][bucket])
                html_report_lines += ['<td bgcolor="'+cell_color+'" align="right"'+bottom_edge+'>'+'<font color="'+text_color+'" size='+text_fontsize+'>'+str(summary_stats[ass_i][bucket])+'</font></td>']

                cell_color = get_cell_color (cumulative_len_stats[ass_i][bucket], best_val['cumulative_len_stats'][bucket], worst_val['cumulative_len_stats'][bucket])
                html_report_lines += ['<td bgcolor="'+cell_color+'" align="right"'+edges+'>'+'<font color="'+text_color+'" size='+text_fontsize+'>'+str(cumulative_len_stats[ass_i][bucket])+'</font></td>']
                if sub_i > 0:
                    html_report_lines += ['</tr>']
                else:
                    # Hist
                    hist_edge = ' style="border-bottom:solid 2px '+border_body_color+'"'
                    for hist_i,hist_lens_png_file in enumerate(hist_lens_png_files[ass_i]):
                        if hist_i == len(hist_lens_png_files[ass_i])-1:
                            hist_edge = ' style="border-right:solid 2px '+border_body_color+'; border-bottom:solid 2px '+border_body_color+'"'
                        html_report_lines += ['<td valign=top align=left rowspan='+str(subtab_N_rows)+' colspan=1'+hist_edge+'><img src="'+hist_lens_png_file+'" height='+str(hist_img_height)+'></td>']
                    html_report_lines += ['</tr>']

        html_report_lines += ['</table>']
        html_report_lines += ['</body>']
        html_report_lines += ['</html>']

        # write html to file and upload
        self.log (console, "SAVING AND UPLOADING HTML REPORT")
        html_report_str = "\n".join(html_report_lines)
        html_file = 'contig_distribution_report.html'
        html_file_path = os.path.join (html_output_dir, html_file)
        with open (html_file_path, 'w') as html_handle:
            html_handle.write(html_report_str)
        try:
            html_upload_ret = dfuClient.file_to_shock({'file_path': html_output_dir,
                                                       'make_handle': 0,
                                                       'pack': 'zip'})
        except:
            raise ValueError ('Logging exception loading html_report to shock')


        #### STEP 7
        ##
        try:
            hist_upload_ret = dfuClient.file_to_shock({'file_path': hist_output_dir,
                                                       'make_handle': 0,
                                                       'pack': 'zip'})
            file_links.append({'shock_id': hist_upload_ret['shock_id'],
                               'name': 'histogram_figures.zip',
                               'label': 'Histogram Figures'
                           })
        except:
            raise ValueError ('Logging exception loading html_report to shock')



        #### STEP 8: Build report
        ##
        reportName = 'run_contig_distribution_compare_report_'+str(uuid.uuid4())
        reportObj = {'objects_created': [],
                     #'text_message': '',  # or is it 'message'?
                     'message': '',  # or is it 'text_message'?
                     'direct_html': '',
                     #'direct_html_link_index': 0,
                     'file_links': [],
                     'html_links': [],
                     'workspace_name': params['workspace_name'],
                     'report_object_name': reportName
                     }

        # message
        if len(invalid_msgs) > 0:
            report_text = "\n".join(invalid_msgs)
        reportObj['message'] = report_text

        if len(invalid_msgs) == 0:

            # html report
            reportObj['direct_html_link_index'] = 0
            reportObj['html_links'] = [{'shock_id': html_upload_ret['shock_id'],
                                        'name': html_file,
                                        'label': 'Contig Distribution Report'+' HTML'
                                    }
                                   ]
            reportObj['file_links'] = file_links


        # save report object
        #
        SERVICE_VER = 'release'
        reportClient = KBaseReport(self.callbackURL, token=ctx['token'], service_ver=SERVICE_VER)
        #report_info = report.create({'report':reportObj, 'workspace_name':params['workspace_name']})
        report_info = reportClient.create_extended_report(reportObj)

        returnVal = { 'report_name': report_info['name'], 'report_ref': report_info['ref'] }
        #END run_contig_distribution_compare

        # At some point might do deeper type checking...
        if not isinstance(returnVal, dict):
            raise ValueError('Method run_contig_distribution_compare return value ' +
                             'returnVal is not type dict as required.')
        # return the results
        return [returnVal]

    def run_benchmark_assemblies_against_genomes_with_MUMmer4(self, ctx, params):
        """
        :param params: instance of type
           "Benchmark_assemblies_against_genomes_with_MUMmer4_Params"
           (benchmark_assemblies_against_genomes_with_MUMmer4() ** **  Align
           benchmark genomes to assembly contigs) -> structure: parameter
           "workspace_name" of type "workspace_name" (** The workspace object
           refs are of form: ** **    objects = ws.get_objects([{'ref':
           params['workspace_id']+'/'+params['obj_name']}]) ** ** "ref" means
           the entire name combining the workspace id and the object name **
           "id" is a numerical identifier of the workspace or object, and
           should just be used for workspace ** "name" is a string identifier
           of a workspace or object.  This is received from Narrative.),
           parameter "input_genome_refs" of type "data_obj_ref", parameter
           "input_assembly_refs" of type "data_obj_ref", parameter "desc" of
           String
        :returns: instance of type
           "Benchmark_assemblies_against_genomes_with_MUMmer4_Output" ->
           structure: parameter "report_name" of type "data_obj_name",
           parameter "report_ref" of type "data_obj_ref"
        """
        # ctx is the context object
        # return variables are: returnVal
        #BEGIN run_benchmark_assemblies_against_genomes_with_MUMmer4

        #### STEP 0: basic init
        ##
        console = []
        invalid_msgs = []
        report_text = ''
        self.log(console, 'Running run_benchmark_assemblies_against_genomes_with_MUMmer4(): ')
        self.log(console, "\n"+pformat(params))

        # Auth
        token = ctx['token']
        headers = {'Authorization': 'OAuth '+token}
        env = os.environ.copy()
        env['KB_AUTH_TOKEN'] = token

        # API Clients
        #SERVICE_VER = 'dev'  # DEBUG
        SERVICE_VER = 'release'
        # wsClient
        try:
            wsClient = workspaceService(self.workspaceURL, token=token)
        except Exception as e:
            raise ValueError('Unable to instantiate wsClient with workspaceURL: '+ self.workspaceURL +' ERROR: ' + str(e))
        # setAPI_Client
        try:
            #setAPI_Client = SetAPI (url=self.callbackURL, token=ctx['token'])  # for SDK local.  local doesn't work for SetAPI
            setAPI_Client = SetAPI (url=self.serviceWizardURL, token=ctx['token'])  # for dynamic service
        except Exception as e:
            raise ValueError('Unable to instantiate setAPI_Client with serviceWizardURL: '+ self.serviceWizardURL +' ERROR: ' + str(e))
        # auClient
        try:
            auClient = AssemblyUtil(self.callbackURL, token=ctx['token'], service_ver=SERVICE_VER)
        except Exception as e:
            raise ValueError('Unable to instantiate auClient with callbackURL: '+ self.callbackURL +' ERROR: ' + str(e))
        # dfuClient
        try:
            dfuClient = DFUClient(self.callbackURL)
        except Exception as e:
            raise ValueError('Unable to instantiate dfu_Client with callbackURL: '+ self.callbackURL +' ERROR: ' + str(e))

        # param checks
        required_params = ['workspace_name',
                           'input_genome_refs',
                           'input_assembly_refs',
                           'desc'
                          ]
        for arg in required_params:
            if arg not in params or params[arg] == None or params[arg] == '':
                raise ValueError ("Must define required param: '"+arg+"'")

        # load provenance
        provenance = [{}]
        if 'provenance' in ctx:
            provenance = ctx['provenance']
        provenance[0]['input_ws_objects']=[]
        for input_ref in params['input_genome_refs']:
            provenance[0]['input_ws_objects'].append(input_ref)
        for input_ref in params['input_assembly_refs']:
            provenance[0]['input_ws_objects'].append(input_ref)

        # set the output paths
        timestamp = int((datetime.utcnow() - datetime.utcfromtimestamp(0)).total_seconds()*1000)
        output_dir = os.path.join(self.scratch,'output.'+str(timestamp))
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        html_output_dir = os.path.join(output_dir,'html')
        if not os.path.exists(html_output_dir):
            os.makedirs(html_output_dir)


        #### STEP 1: get benchmark genome refs
        ##
        if len(invalid_msgs) == 0:
            set_obj_type = "KBaseSearch.GenomeSet"
            genome_obj_type = "KBaseGenomes.Genome"
            accepted_input_types = [set_obj_type, genome_obj_type]
            genome_refs = []
            genome_refs_seen = dict()

            for i,input_ref in enumerate(params['input_genome_refs']):
                # genome obj info
                try:

                    input_obj_info = wsClient.get_object_info_new ({'objects':[{'ref':input_ref}]})[0]
                    input_obj_type = re.sub ('-[0-9]+\.[0-9]+$', "", input_obj_info[TYPE_I])  # remove trailing version

                except Exception as e:
                    raise ValueError('Unable to get object from workspace: (' + input_ref +')' + str(e))
                if input_obj_type not in accepted_input_types:
                    raise ValueError ("Input object of type '"+input_obj_type+"' not accepted.  Must be one of "+", ".join(accepted_input_types))

                # add members to genome_ref list
                if input_obj_type == genome_obj_type:
                    try:
                        genome_seen = genome_refs_seen[input_ref]
                        continue
                    except:
                        genome_refs_seen[input_ref] = True
                    genome_refs.append(input_ref)
                elif input_obj_type != set_obj_type:
                    raise ValueError ("bad obj type for input_ref: "+input_ref)
                else:  # add genome set members
                    try:
                        objects= wsClient.get_objects2({'objects':[{'ref':input_ref}]})['data']
                    except Exception as e:
                        raise ValueError('Unable to get object from workspace: (' + input_ref +')' + str(e))
                    data = objects[0]['data']
                    info = objects[0]['info']
                    set_obj = data

                    # get Genome items from Genome Set
                    for genome_id in sorted(set_obj['elements'].keys()):
                        genome_ref = set_obj['elements'][genome_id]['ref']
                        try:
                            genome_seen = genome_refs_seen[genome_ref]
                            continue
                        except:
                            genome_refs_seen[genome_ref] = True
                            genome_refs.append(genome_ref)


        #### STEP 2: get benchmark genome assembly seqs and other attributes
        ##
        if len(invalid_msgs) == 0:
            genome_obj_names = []
            genome_sci_names = []
            genome_assembly_refs = []

            for i,input_ref in enumerate(genome_refs):
                # genome obj data
                try:

                    objects = wsClient.get_objects2({'objects':[{'ref':input_ref}]})['data']
                    genome_obj = objects[0]['data']
                    genome_obj_info = objects[0]['info']
                    genome_obj_names.append(genome_obj_info[NAME_I])
                    genome_sci_names.append(genome_obj['scientific_name'])
                except:
                    raise ValueError ("unable to fetch genome: "+input_ref)

                # Get genome_assembly_refs
                if ('contigset_ref' not in genome_obj or genome_obj['contigset_ref'] == None) \
                   and ('assembly_ref' not in genome_obj or genome_obj['assembly_ref'] == None):
                    msg = "Genome "+genome_obj_names[i]+" (ref:"+input_ref+") "+genome_sci_names[i]+" MISSING BOTH contigset_ref AND assembly_ref.  Cannot process.  Exiting."
                    self.log(console, msg)
                    self.log(invalid_msgs, msg)
                    continue
                elif 'assembly_ref' in genome_obj and genome_obj['assembly_ref'] != None:
                    msg = "Genome "+genome_obj_names[i]+" (ref:"+input_ref+") "+genome_sci_names[i]+" USING assembly_ref: "+str(genome_obj['assembly_ref'])
                    self.log (console, msg)
                    genome_assembly_refs.append(genome_obj['assembly_ref'])
                elif 'contigset_ref' in genome_obj and genome_obj['contigset_ref'] != None:
                    msg = "Genome "+genome_obj_names[i]+" (ref:"+input_ref+") "+genome_sci_names[i]+" USING contigset_ref: "+str(genome_obj['contigset_ref'])
                    self.log (console, msg)
                    genome_assembly_refs.append(genome_obj['contigset_ref'])

        # get fastas for scaffolds
        if len(invalid_msgs) == 0:
            #genomes_outdir = os.path.join (output_dir, 'benchmark_genomes')
            #if not os.path.exists(genomes_outdir):
            #    os.makedirs(genomes_outdir)
            read_buf_size  = 65536
            write_buf_size = 65536
            benchmark_assembly_file_paths = []

            for genome_i,input_ref in enumerate(genome_refs):
                contig_file = auClient.get_assembly_as_fasta({'ref':genome_assembly_refs[genome_i]}).get('path')
                sys.stdout.flush()
                contig_file_path = dfuClient.unpack_file({'file_path': contig_file})['file_path']
                benchmark_assembly_file_paths.append(contig_file_path)
                #clean_genome_ref = genome_ref.replace('/','_')
                #genome_outfile_path = os.join(benchmark_outdir, clean_genome_ref+".fna")
                #shutil.move(contig_file_path, genome_outfile_path)


        #### STEP 3: get assembly refs
        ##
        if len(invalid_msgs) == 0:
            set_obj_type = "KBaseSets.AssemblySet"
            assembly_obj_types = ["KBaseGenomeAnnotations.Assembly", "KBaseGenomes.ContigSet"]
            accepted_input_types = [set_obj_type] + assembly_obj_types
            assembly_refs = []
            assembly_refs_seen = dict()

            for i,input_ref in enumerate(params['input_assembly_refs']):
                # assembly obj info
                try:
                    input_obj_info = wsClient.get_object_info_new ({'objects':[{'ref':input_ref}]})[0]
                    input_obj_type = re.sub ('-[0-9]+\.[0-9]+$', "", input_obj_info[TYPE_I])  # remove trailing version

                    # DEBUG
                    input_obj_name = input_obj_info[NAME_I]
                    self.log (console, "GETTING ASSEMBLY: "+str(input_ref)+" "+str(input_obj_name))

                except Exception as e:
                    raise ValueError('Unable to get object from workspace: (' + input_ref +')' + str(e))
                if input_obj_type not in accepted_input_types:
                    raise ValueError ("Input object of type '"+input_obj_type+"' not accepted.  Must be one of "+", ".join(accepted_input_types))

                # add members to assembly_ref list
                if input_obj_type in assembly_obj_types:
                    try:
                        assembly_seen = assembly_refs_seen[input_ref]
                        continue
                    except:
                        assembly_refs_seen[input_ref] = True
                        assembly_refs.append(input_ref)
                elif input_obj_type != set_obj_type:
                    raise ValueError ("bad obj type for input_ref: "+input_ref)
                else:  # add assembly set members

                    try:
                        assemblySet_obj = setAPI_Client.get_assembly_set_v1 ({'ref':input_ref, 'include_item_info':1})
                    except Exception as e:
                        raise ValueError('Unable to get object from workspace: (' + input_ref +')' + str(e))

                    for assembly_obj in assemblySet_obj['data']['items']:
                        this_assembly_ref = assembly_obj['ref']
                        try:
                            assembly_seen = assembly_refs_seen[this_assembly_ref]
                            continue
                        except:
                            assembly_refs_seen[this_assembly_ref] = True
                            assembly_refs.append(this_assembly_ref)


        #### STEP 4: Get assemblies to score as fasta files
        ##
        if len(invalid_msgs) == 0:
            #assembly_outdir = os.path.join (output_dir, 'score_assembly')
            #if not os.path.exists(assembly_outdir):
            #    os.makedirs(assembly_outdir)
            read_buf_size  = 65536
            write_buf_size = 65536
            score_assembly_file_paths = []

            for ass_i,input_ref in enumerate(assembly_refs):
                contig_file = auClient.get_assembly_as_fasta({'ref':assembly_refs[ass_i]}).get('path')
                sys.stdout.flush()
                contig_file_path = dfuClient.unpack_file({'file_path': contig_file})['file_path']
                score_assembly_file_paths.append(contig_file_path)
                #clean_ass_ref = assembly_ref.replace('/','_')
                #assembly_outfile_path = os.join(assembly_outdir, clean_assembly_ref+".fna")
                #shutil.move(contig_file_path, assembly_outfile_path)



        #### STEP 5: Run MUMmer
        ##
        if len(invalid_msgs) == 0:
            cmd = []
            cmd.append (self.NUCMER_bin)
#            # output
#            cmd.append ('-base_name')
#            cmd.append (params['output_name'])
#            cmd.append ('-output_dir')
#            cmd.append (output_dir)
#            # contigs input
#            cmd.append ('-reference_file')
#            cmd.append (genomes_src_db_file_path)


            # RUN
            cmd_str = " ".join(cmd)
            self.log (console, "===========================================")
            self.log (console, "RUNNING: "+cmd_str)
            self.log (console, "===========================================")

            """
            cmdProcess = subprocess.Popen(cmd_str, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True)
            outputlines = []
            while True:
                line = cmdProcess.stdout.readline()
                outputlines.append(line)
                if not line: break
                self.log(console, line.replace('\n', ''))
                
            cmdProcess.stdout.close()
            cmdProcess.wait()
            self.log(console, 'return code: ' + str(cmdProcess.returncode) + '\n')
            if cmdProcess.returncode != 0:
                raise ValueError('Error running run_benchmark_assemblies_against_genomes_with_MUMmer4, return code: ' +
                                 str(cmdProcess.returncode) + '\n')

            #report_text += "\n".join(outputlines)
            #report_text += "cmdstring: " + cmdstring + " stdout: " + stdout + " stderr " + stderr
            """


        #### STEP 5: Build report
        ##
        reportName = 'run_benchmark_assemblies_against_genomes_with_MUMmer4_report_'+str(uuid.uuid4())
        reportObj = {'objects_created': [],
                     #'text_message': '',  # or is it 'message'?
                     'message': '',  # or is it 'text_message'?
                     'direct_html': '',
                     #'direct_html_link_index': 0,
                     'file_links': [],
                     'html_links': [],
                     'workspace_name': params['workspace_name'],
                     'report_object_name': reportName
                     }

        # message
        if len(invalid_msgs) > 0:
            report_text = "\n".join(invalid_msgs)
        reportObj['message'] = report_text

        if len(invalid_msgs) == 0:

            # html report
            """
            try:
                html_upload_ret = dfuClient.file_to_shock({'file_path': html_output_dir,
                                                     'make_handle': 0,
                                                     'pack': 'zip'})
            except:
                raise ValueError ('error uploading html report to shock')
            reportObj['direct_html_link_index'] = 0
            reportObj['html_links'] = [{'shock_id': html_upload_ret['shock_id'],
                                        'name': html_file,
                                        'label': params['output_name']+' HTML'
                                    }
                                   ]
            """


        # save report object
        #
        SERVICE_VER = 'release'
        reportClient = KBaseReport(self.callbackURL, token=ctx['token'], service_ver=SERVICE_VER)
        #report_info = report.create({'report':reportObj, 'workspace_name':params['workspace_name']})
        report_info = reportClient.create_extended_report(reportObj)

        returnVal = { 'report_name': report_info['name'], 'report_ref': report_info['ref'] }
        #END run_benchmark_assemblies_against_genomes_with_MUMmer4

        # At some point might do deeper type checking...
        if not isinstance(returnVal, dict):
            raise ValueError('Method run_benchmark_assemblies_against_genomes_with_MUMmer4 return value ' +
                             'returnVal is not type dict as required.')
        # return the results
        return [returnVal]
    def status(self, ctx):
        #BEGIN_STATUS
        returnVal = {'state': "OK",
                     'message': "",
                     'version': self.VERSION,
                     'git_url': self.GIT_URL,
                     'git_commit_hash': self.GIT_COMMIT_HASH}
        #END_STATUS
        return [returnVal]
