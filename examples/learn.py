'''
#########################################################
This file trains a deep learning model to predict
disruptions on time series data from plasma discharges.

Dependencies:
conf.py: configuration of model,training,paths, and data
builder.py: logic to construct the ML architecture
data_processing.py: classes to handle data processing

Author: Julian Kates-Harbeck, jkatesharbeck@g.harvard.edu

This work was supported by the DOE CSGF program.
#########################################################
'''

from __future__ import print_function
import datetime,time,random
import sys,os
import dill
from functools import partial

import matplotlib
matplotlib.use('Agg')
import numpy as np
import multiprocessing as old_mp

from plasma.conf import conf
from pprint import pprint
pprint(conf)
from plasma.primitives.shots import Shot, ShotList
from plasma.preprocessor.normalize import Normalizer
from plasma.preprocessor.preprocess import Preprocessor, guarantee_preprocessed
from plasma.models.loader import Loader

if conf['model']['shallow']:
    from plasma.models.shallow_runner import train, make_predictions_and_evaluate_gpu
else:
    from plasma.models.runner import train, make_predictions_and_evaluate_gpu

if conf['data']['normalizer'] == 'minmax':
    from plasma.preprocessor.normalize import MinMaxNormalizer as Normalizer
elif conf['data']['normalizer'] == 'meanvar':
    from plasma.preprocessor.normalize import MeanVarNormalizer as Normalizer 
elif conf['data']['normalizer'] == 'var':
    from plasma.preprocessor.normalize import VarNormalizer as Normalizer #performs !much better than minmaxnormalizer
elif conf['data']['normalizer'] == 'averagevar':
    from plasma.preprocessor.normalize import AveragingVarNormalizer as Normalizer #performs !much better than minmaxnormalizer
else:
    print('unkown normalizer. exiting')
    exit(1)

shot_list_dir = conf['paths']['shot_list_dir']
shot_files = conf['paths']['shot_files']
shot_files_test = conf['paths']['shot_files_test']
train_frac = conf['training']['train_frac']
stateful = conf['model']['stateful']
# if stateful: 
#     batch_size = conf['model']['length']
# else:
#     batch_size = conf['training']['batch_size_large']

np.random.seed(0)
random.seed(0)

only_predict = len(sys.argv) > 1
custom_path = None
if only_predict:
    custom_path = sys.argv[1]
    print("predicting using path {}".format(custom_path))

#####################################################
####################PREPROCESSING####################
#####################################################
shot_list_train,shot_list_validate,shot_list_test = guarantee_preprocessed(conf)

#####################################################
####################Normalization####################
#####################################################

print("normalization",end='')
nn = Normalizer(conf)
nn.train()
loader = Loader(conf,nn)
print("...done")
print('Training on {} shots, testing on {} shots'.format(len(shot_list_train),len(shot_list_test)))


#####################################################
######################TRAINING#######################
#####################################################
#train(conf,shot_list_train,loader)
if not only_predict:
    p = old_mp.Process(target = train,args=(conf,shot_list_train,shot_list_validate,loader))
    p.start()
    p.join()

#####################################################
####################PREDICTING#######################
#####################################################
loader.set_inference_mode(True)

#load last model for testing
print('saving results')
y_prime = []
y_prime_test = []
y_prime_train = []

y_gold = []
y_gold_test = []
y_gold_train = []

disruptive= []
disruptive_train= []
disruptive_test= []

# y_prime_train,y_gold_train,disruptive_train = make_predictions(conf,shot_list_train,loader)
# y_prime_test,y_gold_test,disruptive_test = make_predictions(conf,shot_list_test,loader)

y_prime_train,y_gold_train,disruptive_train,roc_train,loss_train = make_predictions_and_evaluate_gpu(conf,shot_list_train,loader,custom_path)
y_prime_test,y_gold_test,disruptive_test,roc_test,loss_test = make_predictions_and_evaluate_gpu(conf,shot_list_test,loader,custom_path)
print('=========Summary========')
print('Train Loss: {:.3e}'.format(loss_train))
print('Train ROC: {:.4f}'.format(roc_train))
print('Test Loss: {:.3e}'.format(loss_test))
print('Test ROC: {:.4f}'.format(roc_test))



disruptive_train = np.array(disruptive_train)
disruptive_test = np.array(disruptive_test)

y_gold = y_gold_train + y_gold_test
y_prime = y_prime_train + y_prime_test
disruptive = np.concatenate((disruptive_train,disruptive_test))

shot_list_validate.make_light()
shot_list_test.make_light()
shot_list_train.make_light()

save_str = 'results_' + datetime.datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
result_base_path = conf['paths']['results_prepath']
if not os.path.exists(result_base_path):
    os.makedirs(result_base_path)
np.savez(result_base_path+save_str,
    y_gold=y_gold,y_gold_train=y_gold_train,y_gold_test=y_gold_test,
    y_prime=y_prime,y_prime_train=y_prime_train,y_prime_test=y_prime_test,
    disruptive=disruptive,disruptive_train=disruptive_train,disruptive_test=disruptive_test,
    shot_list_validate=shot_list_validate,shot_list_train=shot_list_train,shot_list_test=shot_list_test,
    conf = conf)

print('finished.')
