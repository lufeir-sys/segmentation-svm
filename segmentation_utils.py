import os
import numpy as np
from scipy import ndimage

from rwsegment import io_analyze
from rwsegment import rwsegment_prior
reload(rwsegment_prior)

import config
reload(config)

from rwsegment import utils_logging
logger = utils_logging.get_logger('segmentation_utils',utils_logging.DEBUG)


def compute_objective(test, y, w):
    im = io_analyze.load(config.dir_reg + test + 'gray.hdr')
    nim = im/np.std(im)
     
    prior,mask = load_or_compute_prior_and_mask(
        test, force_recompute=False)
    seeds = (-1)*mask.astype(int)

    from rwsegment import rwsegment_prior_models as models
    from rwsegment import weight_functions as wflib
    rwparams = {
            'labelset': np.asarray([0,13,14,15,16]),

            # optimization
            'rtol': 1e-6,
            'maxiter': 1e3,
            'per_label':True,
            'optim_solver':'unconstrained',
            }

    weight_functions = {
        'std_b10'     : lambda im: wflib.weight_std(im, beta=10),
        'std_b50'     : lambda im: wflib.weight_std(im, beta=50),
        'std_b100'    : lambda im: wflib.weight_std(im, beta=100),
        'inv_b100o1'  : lambda im: wflib.weight_inv(im, beta=100, offset=1),
        # 'pdiff_r1b10': lambda im: wflib.weight_patch_diff(im, r0=1, beta=10),
        # 'pdiff_r2b10': lambda im: wflib.weight_patch_diff(im, r0=2, beta=10),
        # 'pdiff_r1b50' : lambda im: wflib.weight_patch_diff(im, r0=1, beta=50),
        }

    prior_models = {
        'constant': models.Constant,
        'entropy': models.Entropy_no_D,
        'intensity': models.Intensity,
        }
    
    ## indices of w
    nlaplacian = len(weight_functions)
    nprior = len(prior_models)
    indices_laplacians = np.arange(nlaplacian)
    indices_priors = np.arange(nlaplacian,nlaplacian + nprior)
  
    laplacian_functions = weight_functions.values()
    laplacian_names     = weight_functions.keys()
    prior_functions     = prior_models.values()
    prior_names         = prior_models.keys()
    
    weights_laplacians = np.asarray(w)[indices_laplacians]
    weights_priors = np.asarray(w)[indices_priors]

    def meta_weight_functions(im,_w):
        ''' meta weight function'''
        data = 0
        for iwf,wf in enumerate(laplacian_functions):
            ij,_data = wf(im)
            data += _w[iwf]*_data
        return ij, data
    weight_function = lambda im: meta_weight_functions(im, weights_laplacians)
    
    

    from svm_rw_api import MetaAnchor 
    anchor_api = MetaAnchor(
        prior,
        prior_functions,
        weights_priors,
        image=im,
        )

    from rwsegment import rwsegment
    en_rw = rwsegment.energy_rw(
            nim,
            y
            seeds=seeds,
            weight_function=weight_function,
            **rwparams
            )

    en_anchor = rwsegment.energy_anchor(
            nim,
            y
            anchor_api,
            seeds=seeds,
            **rwparams
            )
    obj = en_rw + en_anchor
    return obj

def load_or_compute_prior_and_mask(test, force_recompute=False):

    labelset = np.asarray(config.labelset)
    outdir = config.dir_work+'/prior/' + test
    if not os.path.isdir(outdir):
        os.makedirs(outdir)
    
    ## load mask and prior
    prior = None
    file_mask  = outdir + 'mask.hdr'
    file_prior = outdir + 'prior.npz'
    file_segprior = outdir + 'segprior.hdr'
    file_entropymap = outdir + 'entropymap.hdr'
   
    if (not force_recompute) and os.path.exists(file_prior):        # logger.info('load prior')
        mask  = io_analyze.load(file_mask)
        prior = np.load(file_prior)
    else:
        generator = rwsegment_prior.PriorGenerator(labelset)
        
        for train in config.vols:
            if test==train: continue
            logger.debug('load training img: {}'.format(train))
            
            ## segmentation
            file_seg = config.dir_reg + test + train + 'regseg.hdr'
            seg = io_analyze.load(file_seg)
            
            ## image (for intensity prior)
            file_im = config.dir_reg + test + train + 'reggray.hdr'
            im = io_analyze.load(file_im)
            
            generator.add_training_data(seg,image=im)
        
        from scipy import ndimage
        mask    = generator.get_mask()
        struct  = np.ones((7,)*mask.ndim)
        mask    = ndimage.binary_dilation(
                mask.astype(bool),
                structure=struct,
                )
        prior = generator.get_prior(mask)
        
        nlabel = len(labelset)
        segprior = np.zeros(mask.shape)
        segprior[mask] = labelset[np.argmax(prior['data'],axis=0)]
            
        entropymap = np.zeros(mask.shape)
        entropymap[mask] = np.sum(
            np.log(prior['data'] + 1e-10)*prior['data'],
            axis=0)
        entropymap = entropymap / np.log(nlabel) * 2**15
            
        np.savez(file_prior,**prior)
        
        io_analyze.save(file_mask, mask.astype(np.int32))
        io_analyze.save(file_segprior, segprior.astype(np.int32))
        io_analyze.save(file_entropymap, entropymap.astype(np.int32))
        
    return prior, mask
    
    
def compute_dice_coef(seg1, seg2, labelset=None):
    if labelset is None:
        lbset = np.union(np.unique(seg1), np.unique(seg2))
    else:
        lbset = np.asarray(labelset, dtype=int)
    
    seg1.flat[~np.in1d(seg1, lbset)] = -1
    seg2.flat[~np.in1d(seg2, lbset)] = -1
    
    dicecoef = {}
    for label in lbset:
        l1 = (seg1==label)
        l2 = (seg2==label)
        d = 2*np.sum(l1&l2)/(1e-9 + np.sum(l1) + np.sum(l2))
        dicecoef[label] = d
    return dicecoef
    
