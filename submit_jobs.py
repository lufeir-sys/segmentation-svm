import os
import sys

header = \
'''#!/bin/bash

# shell
#PBS -S /bin/bash

# standard error output
#PBS -j oe

# queueName
#PBS -q iceq
'''

## resources blocs to allocate
## mpiprocs is num. of train img + 1
##PBS -l select=11:ncpus=12:mpiprocs=3:mem=22gb

def icemem48gbq():
    return '''
# Params for icemem48gbq
#PBS -l select=1:ncpus=12:mpiprocs=1:mem=44gb
#PBS -l walltime=23:59:00
NP=1
'''

def icemem72gbq():
    return '''
# Params for icemem72gbq
#PBS -l select=1:ncpus=12:mpiprocs=1:mem=68gb
#PBS -l walltime=23:59:00
NP=1
'''

def icepar156q():
    return '''
## Params for icepar156q
#PBS -l select=8:ncpus=12:mpiprocs=4:mem=24000000kb
#PBS -l walltime=03:59:59
NP=32

export MPI_DSM_VERBOSE=1
export MPI_OPENMP_INTEROP=1
export OMP_NUM_THREADS=12
#export MPI_DSM_CPULIST=0,3,6,9:allhosts
export MPI_BUFS_PER_PROC=32
export MPI_BUFS_PER_HOST=64
'''


def icetestq():
    return '''
## Params for icetestq
#PBS -l select=2:ncpus=12:mpiprocs=4:mem=24000000kb
#PBS -l walltime=00:19:59
NP=8

export MPI_DSM_VERBOSE=1
export MPI_OPENMP_INTEROP=1
export OMP_NUM_THREADS=12
#export MPI_DSM_CPULIST=0,3,6,9:allhosts
export MPI_BUFS_PER_PROC=32
export MPI_BUFS_PER_HOST=64
'''

def set_jobname(name):
    return '''
# name of the job
#PBS -N learnbatch
'''


def output(job_name):
     return '''
# output
#PBS -o log_{}.txt
'''.format(job_name)


def folder():
    return '\ncd {}\n'.format(os.path.dirname(os.path.abspath(__file__)))

def make_job(job_name, command, queue='icepar156q'):
    job_file = job_name + '.sh'

    f = open(job_file, 'w')
    f.write(header)
    f.write(set_jobname(job_name))
    f.write(output(job_name))
    f.write(eval(queue)())
    f.write(folder())
    f.write('\n#command:\n')


    #f.write('\nmodule purge\n')
    #f.write('module load sgi-mpt/2.01\n')
    #f.write('module load intel-compiler/12.1\n')
    #f.write('module load intel-mkl/10.3\n')
    #f.write('module load python/2.7.3\n')
    #f.write('module load git/1.7.5.1\n')

    f.write('type python\n')

    f.write(command)
    f.write(' --folder {}'.format(job_name))
    f.write(' --script {}'.format(job_file))
    f.write('\n')
    f.close()
    
    email = 'pierre-yves.baudin@ecp.fr'
    os.system('qsub -k oe -m ae -M {} {}'.format(email,job_file))

if __name__=='__main__':


    # jobs

    #make_job(
    #    '2012.12.13.test_parallel_duald',
    #    'mpiexec_mpt -n $NP python duald/duald.py ' \
    #        '--parallel ',
    #    queue='icetestq')

    make_job(
        '2012.12.13.test_duald_icepar156q',
        'mpirun -np $NP python learn_svm_batch.py ' \
            '--parallel --crop 2 -t 0 '\
            '--loss none --loss_factor 1000 '\
            '--latent  --duald_niter 10 '\
            '--Cprime 1.0 -C 1.0 ',
        queue='icetestq')


    #C = [1e-1, 1e0, 1e1, 1e2]#, 1e3, 1e4]
    #Cp = [1e-2, 1e0, 1e2, 1e6]
    #for c in C:
    #    make_job(
    #        '2012.12.13.exp_latent_DDACI_crop2_Lsdloss_x1000_C{}'.format(c),
    #        'mpirun -np $NP python learn_svm_batch.py ' \
    #            '--parallel --crop 2 '\
    #            '--loss squareddiff --loss_factor 1000 '\
    #            '--latent --duald_niter 10 '\
    #            '-C {} '.format(c))
    #
    #    for cprime in Cp:
    #        make_job(
    #            '2012.12.13.exp_latent_DDACI_crop2_Lnone_x1000_Cp{}_C{}'.format(cprime, c),
    #            'mpirun -np $NP python learn_svm_batch.py ' \
    #                '--parallel --crop 2 '\
    #                '--loss none --loss_factor 1000 '\
    #                '--latent --duald_niter 10 '\
    #                ' --Cprime {} -C {} '.format(cprime, c))

        #make_job(
        #    '2012.12.06.exp_latent_DACI_crop2_Lsdloss_x1000_C{}'.format(c),
        #    'mpirun -np $NP python learn_svm_batch.py ' \
        #        '--parallel --crop 2 '\
        #        '--loss squareddiff --loss_factor 1000 '\
        #        '--latent --approx_aci '\
        #        '-C {} '.format(c))
    
        #for cprime in Cp:
        #    make_job(
        #        '2012.12.06.exp_latent_DACI_crop2_Lnone_x1000_Cp{}_C{}'.format(cprime, c),
        #        '$mpirun -np NP python learn_svm_batch.py ' \
        #            '--parallel --crop 2 '\
        #            '--loss none --loss_factor 1000 '\
        #            '--latent --approx_aci '\
        #            ' --Cprime {} -C {} '.format(cprime, c))

        #make_job(
        #    '2012.12.06.exp_baseline_crop10_Lsdloss_x1000_C{}'.format(c),
        #    'mpirun -np $NP python learn_svm_batch.py ' \
        #        '--parallel --crop 10 '\
        #        '--loss squareddiff --loss_factor 1000 '\
        #        '-C {} '.format(c))

        #for cprime in Cp:
        #    make_job(
        #        '2012.12.06.exp_baseline_crop10_Lnone_x1000_Cp{}_C{}'.format(cprime, c),
        #        'mpirun -np $NP python learn_svm_batch.py '\
        #            '--parallel --crop 10 '\
        #            '--loss none --loss_factor 1000 '\
        #            '--Cprime {} -C {} '.format(cprime, c))


