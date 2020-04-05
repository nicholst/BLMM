import warnings as w
# These warnings are caused by numpy updates and should not be
# output.
w.simplefilter(action = 'ignore', category = FutureWarning)
import numpy as np
import sys
import os
import yaml
from lib.fileio import loadFile, str2vec

# ------------------------------------------------------------------------------------
#
# This file is the first stage of the BLMM pipeline. It reads in the inputs file and
# reformats it where necessary, then works out how many batches should be used for 
# computation. The number of batches is output into the file `nb.txt` which informs 
# the rest of the blmm pipeline how many batches are required for computation. 
#
# ------------------------------------------------------------------------------------
#
# Author: Tom Maullin (Last edited: 04/04/2020)
#
# ------------------------------------------------------------------------------------
#
# The code takes the following inputs:
#
#  - input path (optional): If specified, the first argument will be assumed to be a
#                           path to an `inputs` yml file, following the same 
#                           formatting guidelines as `blmm_config.yml`. If not 
#                           specified, the default file `blmm_config.yml` will be 
#                           assumed to contain the inputs.
#
# ------------------------------------------------------------------------------------
def main(*args):

    # Change to blmm directory
    pwd = os.getcwd()
    os.chdir(os.path.dirname(os.path.realpath(__file__)))

    # Check the inputs
    if len(args)==0 or (not args[0]):
        # Load in inputs
        ipath = os.path.abspath(os.path.join('..','blmm_config.yml'))
        with open(ipath, 'r') as stream:
            inputs = yaml.load(stream,Loader=yaml.FullLoader)
    else:
        if os.path.isabs(args[0]):
            ipath = args[0]
        else:
            ipath = os.path.abspath(os.path.join(pwd, args[0]))
        # In this case inputs file is first argument
        with open(ipath, 'r') as stream:
            inputs = yaml.load(stream,Loader=yaml.FullLoader)

    # Save absolute filepaths in place of relative filepaths
    if ipath: 

        # Y files
        if not os.path.isabs(inputs['Y_files']):

            # Change Y in inputs
            inputs['Y_files'] = os.path.join(pwd, inputs['Y_files'])

        # If mask files are specified
        if 'data_mask_files' in inputs:

            # M_files
            if not os.path.isabs(inputs['data_mask_files']):

                # Change M in inputs
                inputs['data_mask_files'] = os.path.join(pwd, inputs['data_mask_files'])

        # If analysis mask file specified,        
        if 'analysis_mask' in inputs:

            # M_files
            if not os.path.isabs(inputs['analysis_mask']):

                # Change M in inputs
                inputs['analysis_mask'] = os.path.join(pwd, inputs['analysis_mask'])

        # If X is specified
        if not os.path.isabs(inputs['X']):

            # Change X in inputs
            inputs['X'] = os.path.join(pwd, inputs['X'])

        # If the output directory is not an absolute, assume its the relative
        # to the present working directory 
        if not os.path.isabs(inputs['outdir']):

            # Change output directory in inputs
            inputs['outdir'] = os.path.join(pwd, inputs['outdir'])

        # Change each random effects factor
        nf = len(inputs['Z'])
        for i in range(0,nf):

            inputs['Z'][i]['f' + str(i+1)]['factor'] = os.path.join(pwd, inputs['Z'][i]['f' + str(i+1)]['factor'])
            inputs['Z'][i]['f' + str(i+1)]['design'] = os.path.join(pwd, inputs['Z'][i]['f' + str(i+1)]['design'])

        # Update inputs
        with open(ipath, 'w') as outfile:
            yaml.dump(inputs, outfile, default_flow_style=False)

    # Check if the maximum memory is saved.    
    if 'MAXMEM' in inputs:
        MAXMEM = eval(inputs['MAXMEM'])
    else:
        MAXMEM = 2**32

    # Output directory
    OutDir = inputs['outdir']

    # Get number of parameters
    c1 = blmm_eval(inputs['contrasts'][0]['c' + str(1)]['vector'])
    c1 = np.array(c1)
    n_p = c1.shape[0]
    del c1

    # Make output directory and tmp
    if not os.path.isdir(OutDir):
        os.mkdir(OutDir)
    if not os.path.isdir(os.path.join(OutDir, "tmp")):
        os.mkdir(os.path.join(OutDir, "tmp"))

    # Read in the Y_files (make sure to remove new line characters)
    with open(inputs['Y_files']) as a:

        Y_files = []
        i = 0
        for line in a.readlines():

            Y_files.append(line.replace('\n', ''))

    # Load in one nifti to check NIFTI size
    try:
        Y0 = loadFile(Y_files[0])
    except Exception as error:
        raise ValueError('The NIFTI "' + Y_files[0] + '"does not exist')

    # Get an estimate of the maximum memory a NIFTI could take in storage.
    NIFTImem = sys.getsizeof(np.zeros(Y0.shape,dtype='uint64'))

    if NIFTImem > MAXMEM:
        raise ValueError('The NIFTI "' + Y_files[0] + '"is too large')

    # Similar to blksize in SwE, we divide by 8 times the size of a nifti
    # to work out how many blocks we use. We also divide though everything
    # by the number of parameters in the analysis.
    blksize = np.floor(MAXMEM/8/NIFTImem/n_p)
    if blksize == 0:
        raise ValueError('Blocksize too small.')

    # Check F contrast ranks 
    n_c = len(inputs['contrasts'])
    for i in range(0,n_c):

        # Read in contrast vector
        cvec = blmm_eval(inputs['contrasts'][i]['c' + str(i+1)]['vector'])
        cvec = np.array(cvec)

        if cvec.ndim>1:

            # Check the F contrast has appropriate rank
            if np.linalg.matrix_rank(cvec)<cvec.shape[0]:
                raise ValueError('F contrast: \n' + str(cvec) + '\n is not of correct rank.')

    # Output number of batches to a text file
    with open(os.path.join(OutDir, "nb.txt"), 'w') as f:
        print(int(np.ceil(len(Y_files)/int(blksize))), file=f)

    # Reset warnings
    w.resetwarnings()

if __name__ == "__main__":
    main()