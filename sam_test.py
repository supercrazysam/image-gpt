# -*- coding: utf-8 -*-
"""TEST Image-GPT_Sample_with_Conditioning.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/11oka1LlDjWItYsz6bYwOPRppZxEirvF7

Image GPT [https://openai.com/blog/image-gpt/](https://openai.com/blog/image-gpt/)

Barebones demo, this just samples 32x32 images. That site shows lovely 64x64 images but the XL sized model isn't available. (Yet?)

(Runtime)->(Run All) will work unless you get really unlucky with the GPU.

Notebook by [https://twitter.com/jonathanfly](https://twitter.com/jonathanfly)

Notebook modified to include conditional input by [Alfredo Peguero](https://twitter.com/alfredompeguero)

# Download Image-GPT
"""

#!nvidia-smi #OpenAI says you need 16GB GPU for the large model, but it may work if you lower n_sub_batch on the others.

#!git clone https://github.com/openai/image-gpt.git
#!pip install tensorflow-gpu==1.15.0

# Commented out IPython magic to ensure Python compatibility.
# %cd /content/image-gpt


import os
##path = os.path.dirname(__file__)
print(__file__)
###os.chdir(path)


model_sizes = ["s", "m", "l"] #small medium large, xl not available
model_sizes = ["s"] #"s" #actually just download one
n_sub_batch = 8 #8 is default, trying lowering if this doesn't work.
n_px = 32 #resolution?
n_gpu = 1




#if already downloaded can skip this

os.system("mkdir -p models")
os.system("mkdir -p clusters")
os.system("mkdir -p datasets")

for model_size in model_sizes:
    os.system("mkdir -p models/"+str(model_size)+"")
    os.system("python download.py --model "+str(model_size)+" --ckpt 1000000 --download_dir models/"+str(model_size)) #models
    os.system("python download.py --clusters --download_dir clusters/"+str(model_size)) #color clusters

model_size = "s"

"""# Setup cropped images for conditioning"""

#numpy implementation of functions in src/utils which convert pixels of image to nearest color cluster. 
def normalize_img(img):
  return img/127.5 - 1

def squared_euclidean_distance_np(a,b):
  b = b.T
  a2 = np.sum(np.square(a),axis=1)
  b2 = np.sum(np.square(b),axis=0)
  ab = np.matmul(a,b)
  d = a2[:,None] - 2*ab + b2[None,:]
  return d

def color_quantize_np(x, clusters):
    x = x.reshape(-1, 3)
    d = squared_euclidean_distance_np(x, clusters)
    return np.argmin(d,axis=1)

#get images
#example image
#os.system("curl https://i.imgur.com/vF56Fsib.jpg > kp.jpg")
#image_paths = ["kp.jpg"]*(n_gpu*n_sub_batch)

os.system("curl https://imgur.com/CT9g3qp.png > kp.png")
#os.system("curl https://imgur.com/7VwPbII.png > kp.png")
#os.system("curl https://imgur.com/y3p2zpq.png > kp.png")
image_paths = ["kp.png"]*(n_gpu*n_sub_batch)


#Resize original images to n_px by n_px
import cv2
import numpy as np
dim=(n_px,n_px)

x = np.zeros((n_gpu*n_sub_batch,n_px,n_px,3),dtype=np.uint8)

for n,image_path in enumerate(image_paths):
  img_np = cv2.imread(image_path)   # reads an image in the BGR format
  img_np = cv2.cvtColor(img_np, cv2.COLOR_BGR2RGB)   # BGR -> RGB
  H,W,C = img_np.shape
  D = min(H,W)
  img_np = img_np[:D,:D,:C] #get square piece of image
  x[n] = cv2.resize(img_np,dim, interpolation = cv2.INTER_AREA) #resize to n_px by n_px

# Commented out IPython magic to ensure Python compatibility.
#visualize resized images
# %matplotlib inline
import pathlib
import matplotlib.pyplot as plt
import matplotlib.image as mpimg

f, axarr = plt.subplots(1,8,dpi=180)

i = 0
for img in x:
    axarr[i].imshow(img)
    i += 1

#use Image-GPT color palette and crop images

color_cluster_path = "clusters/"+str(model_size)+"/kmeans_centers.npy"
clusters = np.load(color_cluster_path) #get color clusters
x_norm = normalize_img(x) #normalize pixels values to -1 to +1

samples = color_quantize_np(x_norm,clusters).reshape(x_norm.shape[:-1]) #map pixels to closest color cluster

n_px_crop = int(n_px/2) #half #8
primers = samples.reshape(-1,n_px*n_px)[:,:n_px_crop*n_px] # crop top n_px_crop rows

# Commented out IPython magic to ensure Python compatibility.

#visualize samples and crops with Image-GPT color palette. Should look similar to original resized images
# %matplotlib inline
import pathlib
import matplotlib.pyplot as plt
import matplotlib.image as mpimg

samples_img = [np.reshape(np.rint(127.5 * (clusters[s] + 1.0)), [n_px, n_px, 3]).astype(np.uint8) for s in samples] # convert color clusters back to pixels
primers_img = [np.reshape(np.rint(127.5 * (clusters[s] + 1.0)), [n_px_crop,n_px, 3]).astype(np.uint8) for s in primers] # convert color clusters back to pixels

f, axarr2 = plt.subplots(1,8,dpi=180)
i = 0
for img in samples_img:
    axarr2[i].imshow(img)
    i += 1

f, axarr = plt.subplots(1,8,dpi=180)
i = 0
for img in primers_img:
    axarr[i].imshow(img)
    i += 1

"""# Functions from run.py

"""

import argparse
import json
import math
import os
import random
import sys
import time
sys.path.append('src')

import numpy as np
import tensorflow as tf

from imageio import imwrite
from scipy.special import softmax
from tensorflow.contrib.training import HParams
from tqdm import tqdm

from model import model
from utils import iter_data, count_parameters


def parse_arguments():
    parser = argparse.ArgumentParser()

    # data and I/O
    parser.add_argument("--data_path", type=str, default="/root/downloads/imagenet")
    parser.add_argument("--ckpt_path", type=str, default="/root/downloads/model.ckpt-1000000")
    parser.add_argument("--color_cluster_path", type=str, default="/root/downloads/kmeans_centers.npy")
    parser.add_argument("--save_dir", type=str, default="/root/save/")

    # model
    parser.add_argument("--n_embd", type=int, default=512)
    parser.add_argument("--n_head", type=int, default=8)
    parser.add_argument("--n_layer", type=int, default=24)
    parser.add_argument("--n_px", type=int, default=32, help="image height or width in pixels")
    parser.add_argument("--n_vocab", type=int, default=512, help="possible values for each pixel")

    parser.add_argument("--bert", action="store_true", help="use the bert objective (defaut: autoregressive)")
    parser.add_argument("--bert_mask_prob", type=float, default=0.15)
    parser.add_argument("--clf", action="store_true", help="add a learnable classification head")

    # parallelism
    parser.add_argument("--n_sub_batch", type=int, default=8, help="per-gpu batch size")
    parser.add_argument("--n_gpu", type=int, default=8, help="number of gpus to distribute training across")

    # mode
    parser.add_argument("--eval", action="store_true", help="evaluates the model, requires a checkpoint and dataset")
    parser.add_argument("--sample", action="store_true", help="samples from the model, requires a checkpoint and clusters")

    # reproducibility
    parser.add_argument("--seed", type=int, default=42, help="seed for random, np, tf")

    args = parser.parse_args()
    print("input args:\n", json.dumps(vars(args), indent=4, separators=(",", ":")))
    return args


def set_seed(seed):
    random.seed(seed)
    np.random.seed(seed)
    tf.set_random_seed(seed)


def load_data(data_path):
    trX = np.load(f'{data_path}_trX.npy')
    trY = np.load(f'{data_path}_trY.npy')
    vaX = np.load(f'{data_path}_vaX.npy')
    vaY = np.load(f'{data_path}_vaY.npy')
    teX = np.load(f'{data_path}_teX.npy')
    teY = np.load(f'{data_path}_teY.npy')
    return (trX, trY), (vaX, vaY), (teX, teY)


def set_hparams(args):
    return HParams(
        n_ctx=args.n_px*args.n_px,
        n_embd=args.n_embd,
        n_head=args.n_head,
        n_layer=args.n_layer,
        n_vocab=args.n_vocab,
        bert=args.bert,
        bert_mask_prob=args.bert_mask_prob,
        clf=args.clf,
    )


def create_model(x, y, n_gpu, hparams):
    gen_logits = []
    gen_loss = []
    clf_loss = []
    tot_loss = []
    accuracy = []

    trainable_params = None
    for i in range(n_gpu):
        with tf.device("/gpu:%d" % i):
            results = model(hparams, x[i], y[i], reuse=(i != 0))

            gen_logits.append(results["gen_logits"])
            gen_loss.append(results["gen_loss"])
            clf_loss.append(results["clf_loss"])

            if hparams.clf:
                tot_loss.append(results["gen_loss"] + results["clf_loss"])
            else:
                tot_loss.append(results["gen_loss"])

            accuracy.append(results["accuracy"])

            if i == 0:
                trainable_params = tf.trainable_variables()
                print("trainable parameters:", count_parameters())

    return trainable_params, gen_logits, gen_loss, clf_loss, tot_loss, accuracy


def reduce_mean(gen_loss, clf_loss, tot_loss, accuracy, n_gpu):
    with tf.device("/gpu:0"):
        for i in range(1, n_gpu):
            gen_loss[0] += gen_loss[i]
            clf_loss[0] += clf_loss[i]
            tot_loss[0] += tot_loss[i]
            accuracy[0] += accuracy[i]
        gen_loss[0] /= n_gpu
        clf_loss[0] /= n_gpu
        tot_loss[0] /= n_gpu
        accuracy[0] /= n_gpu


def evaluate(sess, evX, evY, X, Y, gen_loss, clf_loss, accuracy, n_batch, desc, permute=False):
    metrics = []
    for xmb, ymb in iter_data(evX, evY, n_batch=n_batch, truncate=True, verbose=True):
        metrics.append(sess.run([gen_loss[0], clf_loss[0], accuracy[0]], {X: xmb, Y: ymb}))
    eval_gen_loss, eval_clf_loss, eval_accuracy = [np.mean(m) for m in zip(*metrics)]
    print(f"{desc} gen: {eval_gen_loss:.4f} clf: {eval_clf_loss:.4f} acc: {eval_accuracy:.2f}")


# naive sampler without caching
def sample(sess, X, gen_logits, n_sub_batch, n_gpu, n_px, n_vocab, clusters, save_dir,primers=None):
  
    samples = np.zeros([n_gpu * n_sub_batch, n_px * n_px], dtype=np.int32)

    if primers is None:
      N_cond_px = 0
    else:
      N_cond_px = primers.shape[1]
      samples[:,:N_cond_px] = primers
      

    print('Conditioning on %d out of %d pixels'%(N_cond_px,n_px*n_px))
    for i in tqdm(range(N_cond_px,n_px * n_px), ncols=80, leave=False):
        np_gen_logits = sess.run(gen_logits, {X: samples})
        for j in range(n_gpu):
            p = softmax(np_gen_logits[j][:, i, :], axis=-1)  # logits to probas
            for k in range(n_sub_batch):
                c = np.random.choice(n_vocab, p=p[k])  # choose based on probas
                samples[j * n_sub_batch + k, i] = c
    
    # dequantize
    samples = [np.reshape(np.rint(127.5 * (clusters[s] + 1.0)), [32, 32, 3]).astype(np.uint8) for s in samples]

    # write to png
    for i in range(n_gpu * n_sub_batch):
        imwrite(f"{args.save_dir}/seed_{args.seed}_sample_{i}.png", samples[i])


def main(args,primers=None):
    tf.reset_default_graph()
    set_seed(args.seed)

    n_batch = args.n_sub_batch * args.n_gpu

    if args.sample:
        n_class = 1000
        print("Skipping dataset requirement for sampling.")
    else:
        if args.data_path.endswith("cifar10"):
            n_class = 10
        elif args.data_path.endswith("imagenet"):
            n_class = 1000
        else:
            raise ValueError("Dataset not supported.")

    X = tf.placeholder(tf.int32, [n_batch, args.n_px * args.n_px])
    Y = tf.placeholder(tf.float32, [n_batch, n_class])

    x = tf.split(X, args.n_gpu, 0)
    y = tf.split(Y, args.n_gpu, 0)

    hparams = set_hparams(args)
    trainable_params, gen_logits, gen_loss, clf_loss, tot_loss, accuracy = create_model(x, y, args.n_gpu, hparams)
    reduce_mean(gen_loss, clf_loss, tot_loss, accuracy, args.n_gpu)

    saver = tf.train.Saver(var_list=[tp for tp in trainable_params if not 'clf' in tp.name])
    with tf.Session(config=tf.ConfigProto(allow_soft_placement=True, log_device_placement=False)) as sess:
        sess.run(tf.global_variables_initializer())

        saver.restore(sess, args.ckpt_path)

        if args.eval:
            (trX, trY), (vaX, vaY), (teX, teY) = load_data(args.data_path)
            evaluate(sess, trX[:len(vaX)], trY[:len(vaY)], X, Y, gen_loss, clf_loss, accuracy, n_batch, "train")
            evaluate(sess, vaX, vaY, X, Y, gen_loss, clf_loss, accuracy, n_batch, "valid")
            evaluate(sess, teX, teY, X, Y, gen_loss, clf_loss, accuracy, n_batch, "test")

        if args.sample:
            if not os.path.exists(args.save_dir):
                os.makedirs(args.save_dir)
            clusters = np.load(args.color_cluster_path)
            sample(sess, X, gen_logits, args.n_sub_batch, args.n_gpu, args.n_px, args.n_vocab, clusters, args.save_dir,primers=primers)

"""# Sample"""

#set model hyperparameters
MODELS={"l":(1536,16,48),"m":(1024,8,36),"s":(512,8,24) }
n_embd,n_head,n_layer=MODELS[model_size]

sys.argv="""src/run.py  --sample --n_embd %d --n_head %d --n_layer %d
--ckpt_path models/%s/model.ckpt-1000000 --color_cluster_path clusters/%s/kmeans_centers.npy 
--data_path datasets/s/imagenet_notused --save_dir output 
--n_gpu %d --n_px %d --n_sub_batch %d --seed 42"""%(n_embd,n_head,n_layer,model_size,model_size,n_gpu,n_px,n_sub_batch)

sys.argv=sys.argv.split()

args = parse_arguments()

main(args,primers=primers) #conditional generation
#main(args) #unconditional generation

# Commented out IPython magic to ensure Python compatibility.
#visualize output samples
# %matplotlib inline
import pathlib
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
import glob

samples = pathlib.Path('output').glob('*.png')

f, axarr = plt.subplots(1,len(glob.glob('output/*.png')),dpi=180)

i = 0
for image in samples:
    axarr[i].imshow(mpimg.imread(image))
    i += 1
