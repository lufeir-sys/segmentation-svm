import os
import numpy as np
from scipy import ndimage

from rwsegment import io_analyze
from rwsegment import rwsegment
from rwsegment import weight_functions as wflib
from rwsegment import rwsegment_prior_models as prior_models
from rwsegment import loss_functions
from rwsegment.rwsegment import  BaseAnchorAPI
from svm_rw_api import MetaAnchor
reload(rwsegment)
reload(loss_functions)
reload(prior_models)


import segmentation_utils 
reload(segmentation_utils)

from segmentation_utils import load_or_compute_prior_and_mask
from segmentation_utils import compute_dice_coef
    
import config
reload(config)

from rwsegment import utils_logging
logger = utils_logging.get_logger('segmentation_batch',utils_logging.INFO)

class SegmentationBatch(object):
    
    def __init__(self, prior_weights=[1.,0,0], name='constant1'):
        self.labelset  = np.asarray(config.labelset)
        self.model_name = name
        self.force_recompute_prior = False
        
        self.params  = {
            'beta'             : 50,     # contrast parameter
            'return_arguments' :['image','y'],
            # optimization parameter
            'per_label': True,
            'optim_solver':'unconstrained',
            'rtol'      : 1e-6,
            'maxiter'   : 2e3,
            }
        
        laplacian_type = 'std_b50'
        logger.info('laplacian type is: {}'.format(laplacian_type))
        
        self.weight_functions = {
            'std_b10'     : lambda im: wflib.weight_std(im, beta=10),
            'std_b50'     : lambda im: wflib.weight_std(im, beta=50),
            'std_b100'    : lambda im: wflib.weight_std(im, beta=100),
            'inv_b100o1'  : lambda im: wflib.weight_inv(im, beta=100, offset=1),
            'pdiff_r1b10': lambda im: wflib.weight_patch_diff(im, r0=1, beta=10),
            'pdiff_r2b10': lambda im: wflib.weight_patch_diff(im, r0=2, beta=10),
            'pdiff_r1b50' : lambda im: wflib.weight_patch_diff(im, r0=1, beta=50),
            }
        self.weight_function = self.weight_functions[laplacian_type]
       
        self.prior_models = [
            prior_models.Constant,
            prior_models.Entropy_no_D,
            prior_models.Intensity,
            prior_models.Variance_no_D,
            prior_models.Variance_no_D_Cmap,
            ]
        self.prior_weights = prior_weights

        logger.info('Model name = {}, using prior weights={}'\
            .format(self.model_name, self.prior_weights))
    
    def process_sample(self,test,fold=None):

        ## get prior
        prior, mask = load_or_compute_prior_and_mask(
            test,
            fold=fold,
            force_recompute=self.force_recompute_prior)
        seeds   = (-1)*mask
        
        ## load image
        file_name = config.dir_reg + test + 'gray.hdr'        
        logger.info('segmenting data: {}'.format(file_name))
        im      = io_analyze.load(file_name)
        file_gt = config.dir_reg + test + 'seg.hdr'
        seg     = io_analyze.load(file_gt)
        seg.flat[~np.in1d(seg, self.labelset)] = self.labelset[0]
        
           
        ## normalize image
        nim = im/np.std(im)
            
        ## init anchor_api
        anchor_api = MetaAnchor(
            prior=prior,
            prior_models=self.prior_models,
            prior_weights=self.prior_weights,
            image=nim,
            )
           
        ## start segmenting
        #import ipdb; ipdb.set_trace()
        sol,y = rwsegment.segment(
            nim, 
            anchor_api,
            seeds=seeds, 
            labelset=self.labelset, 
            weight_function=self.weight_function,
            **self.params
            )

        ## compute losses
        z = seg.ravel()==np.c_[self.labelset]
        flatmask = mask.ravel()*np.ones((len(self.labelset),1))
        
        ## loss 0 : 1 - Dice(y,z)
        loss0 = loss_functions.ideal_loss(z,y,mask=flatmask)
        logger.info('Tloss = {}'.format(loss0))
        
        ## loss2: squared difference with ztilde
        loss1 = loss_functions.anchor_loss(z,y,mask=flatmask)
        logger.info('SDloss = {}'.format(loss1))
        
        ## loss3: laplacian loss
        loss2 = loss_functions.laplacian_loss(z,y,mask=flatmask)
        logger.info('LAPloss = {}'.format(loss2))
 
        ## loss4: linear loss
        loss3 = loss_functions.linear_loss(z,y,mask=flatmask)
        logger.info('LINloss = {}'.format(loss3))
        
        ## compute Dice coefficient per label
        dice    = compute_dice_coef(sol, seg,labelset=self.labelset)
        logger.info('Dice: {}'.format(dice))
        
        if not config.debug:
            if fold is not None:
                test_name = 'f{}_{}'.format(fold[0][:2], test)
            else:
                test_name = test
            outdir = config.dir_seg + \
                '/{}/{}'.format(self.model_name,test_name)
            logger.info('saving data in: {}'.format(outdir))
            if not os.path.isdir(outdir):
                os.makedirs(outdir)
        
            f = open(outdir + 'losses.txt', 'w')
            f.write('ideal_loss\t{}\n'.format(loss0))
            f.write('anchor_loss\t{}\n'.format(loss1))
            f.write('laplacian_loss\t{}\n'.format(loss2))
            f.close()
            
            io_analyze.save(outdir + 'sol.hdr', sol.astype(np.int32)) 
            np.savetxt(
                outdir + 'dice.txt', np.c_[dice.keys(),dice.values()],fmt='%d %.8f')
        
    def compute_mean_segmentation(self, list):
        for test in list:
            file_gt = config.dir_reg + test + 'seg.hdr'
            seg     = io_analyze.load(file_gt)
            seg.flat[~np.in1d(seg, self.labelset)] = self.labelset[0]
           

            ## get prior
            prior, mask = load_or_compute_prior_and_mask(
                test,force_recompute=self.force_recompute_prior)
            mask = mask.astype(bool)            
           

            y = np.zeros((len(self.labelset),seg.size))
            y[:,0] = 1
            y.flat[prior['imask']] = prior['data']
 
            sol = np.zeros(seg.shape,dtype=np.int32)
            sol[mask] = self.labelset[np.argmax(prior['data'],axis=0)]

            ## compute losses
            z = seg.ravel()==np.c_[self.labelset]
            flatmask = mask.ravel()*np.ones((len(self.labelset),1))
 
            ## loss 0 : 1 - Dice(y,z)
            loss0 = loss_functions.ideal_loss(z,y,mask=flatmask)
            logger.info('Tloss = {}'.format(loss0))
            
            ## loss2: squared difference with ztilde
            #loss1 = loss_functions.anchor_loss(z,y,mask=flatmask)
            #logger.info('SDloss = {}'.format(loss1))
            
            ## loss3: laplacian loss
            #loss2 = loss_functions.laplacian_loss(z,y,mask=flatmask)
            #logger.info('LAPloss = {}'.format(loss2))
 
            ## loss4: linear loss
            #loss3 = loss_functions.linear_loss(z,y,mask=flatmask)
            #logger.info('LINloss = {}'.format(loss3))
            
            ## compute Dice coefficient per label
            dice    = compute_dice_coef(sol, seg,labelset=self.labelset)
            logger.info('Dice: {}'.format(dice))
            
            if not config.debug:
                outdir = config.dir_seg + \
                    '/{}/{}'.format('mean',test)
                logger.info('saving data in: {}'.format(outdir))
                if not os.path.isdir(outdir):
                    os.makedirs(outdir)
            
                #f = open(outdir + 'losses.txt', 'w')
                #f.write('ideal_loss\t{}\n'.format(loss0))
                #f.write('anchor_loss\t{}\n'.format(loss1))
                #f.write('laplacian_loss\t{}\n'.format(loss2))
                #f.close()
                
                io_analyze.save(outdir + 'sol.hdr', sol.astype(np.int32)) 

                np.savetxt(
                    outdir + 'dice.txt', np.c_[dice.keys(),dice.values()],fmt='%d %.8f')
 

    def process_all_samples(self,sample_list, fold=None):
        for test in sample_list:
            self.process_sample(test, fold=fold)
            
            
if __name__=='__main__':
    ''' start script '''
    import sys
    if not '-s' in sys.argv:
        sys.exit()

    #sample_list = ['01/']
    #sample_list = ['02/']
    #sample_list = config.vols

    ## registration
    segmenter = SegmentationBatch()
    segmenter.compute_mean_segmentation(config.vols)
      
 
    # entropy
    #segmenter = SegmentationBatch(prior_weights=[0, 1e-2, 0, 0, 0], name='entropy1e-2')
    #for fold in config.folds:
    #    segmenter.process_all_samples(fold, fold=fold)

    ## constant prior
    #segmenter = SegmentationBatch(prior_weights=[1e-2, 0, 0, 0,0], name='constant1e-2')
    #segmenter.process_all_samples(['01/'])
    #
    ## entropy prior
    #segmenter = SegmentationBatch(prior_weights=[0, 1e-2, 0,0,0], name='entropy1e-2')
    #segmenter.process_all_samples(['01/'])
    #
    ## entropy prior
    #segmenter = SegmentationBatch(prior_weights=[0, 1e-3, 0,0,0], name='entropy1e-3') 
    #segmenter.process_all_samples(['01/'])

    ## intensity prior
    ##segmenter = SegmentationBatch(anchor_weight=1.0,    model_type='intensity')
    ##segmenter.process_all_samples(sample_list)
    #

    ## combine entropy / intensity
    #segmenter = SegmentationBatch(prior_weights=[0, 1e-2, 1e-2], name='entropy1e-2_intensity1e-2')
    #segmenter.process_all_samples(sample_list)
    #
    ## combine entropy / intensity
    #segmenter = SegmentationBatch(prior_weights=[0, 1e-3, 1e-2], name='entropy1e-3_intensity1e-2')
    ##segmenter.process_all_samples(sample_list)
    
    
    # variance+cmap
    #segmenter = SegmentationBatch(prior_weights=[0, 0, 0, 0, 1e-1], name='variancecmap1e-1')
    ##segmenter.compute_mean_segmentation(sample_list)
    #segmenter.process_all_samples(sample_list)
 
    ## variance
    #segmenter = SegmentationBatch(prior_weights=[0, 0, 0, 1e-1, 0], name='variance1e-1')
    #segmenter.process_all_samples(sample_list)
    #
    ## variance+cmap
    #segmenter = SegmentationBatch(prior_weights=[0, 0, 0, 0, 1e-0], name='variancecmap1e-0')
    #segmenter.process_all_samples(sample_list)
    #
    ## variance
    #segmenter = SegmentationBatch(prior_weights=[0, 0, 0,  1e-0, 0], name='variance1e-0')
    #segmenter.process_all_samples(sample_list)
    #
    # # variance+cmap
    #segmenter = SegmentationBatch(prior_weights=[0, 0, 0, 0, 1e-2], name='variancecmap1e-2')
    #segmenter.process_all_samples(sample_list)
    #
    ## variance
    #segmenter = SegmentationBatch(prior_weights=[0, 0, 0,  1e-2, 0], name='variance1e-2')
    #segmenter.process_all_samples(sample_list)
    
    
