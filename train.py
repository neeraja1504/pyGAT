from __future__ import division
from __future__ import print_function

import os
import glob
import time
import random
import argparse
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torch.autograd import Variable

from utils import load_data, accuracy, print_class_acc, print_class_acc_test
from models import GAT, SpGAT, GCN
import math
from sklearn.model_selection import StratifiedShuffleSplit

import dgl
from dgl.data import CoraGraphDataset, CiteseerGraphDataset, PubmedGraphDataset, CoraFullDataset

import wandb

wandb.init(project="GAT", entity="neerajak")
# DATA
# Training settings
parser = argparse.ArgumentParser()
parser.add_argument('--no-cuda', action='store_true', default=False, help='Disables CUDA training.')
parser.add_argument('--fastmode', action='store_true', default=False, help='Validate during training pass.')
parser.add_argument('--sparse', action='store_true', default=False, help='GAT with sparse version or not.')
parser.add_argument('--seed', type=int, default=72, help='Random seed.')
parser.add_argument('--epochs', type=int, default=10000, help='Number of epochs to train.')
parser.add_argument('--lr', type=float, default=0.005, help='Initial learning rate.')
parser.add_argument('--weight_decay', type=float, default=5e-4, help='Weight decay (L2 loss on parameters).')
parser.add_argument('--hidden', type=int, default=8, help='Number of hidden units.')
parser.add_argument('--nb_heads', type=int, default=8, help='Number of head attentions.')
parser.add_argument('--dropout', type=float, default=0.6, help='Dropout rate (1 - keep probability).')
parser.add_argument('--alpha', type=float, default=0.2, help='Alpha for the leaky_relu.')
parser.add_argument('--patience', type=int, default=100, help='Patience')
parser.add_argument('--GCN', action='store_true', default=False, help='GCN neural network')

wandb.config = {
  "learning_rate": 0.005,
  "epochs": 300,
  "batch_size": 1
}

args = parser.parse_args()
args.cuda = not args.no_cuda and torch.cuda.is_available()

random.seed(args.seed)
np.random.seed(args.seed)
torch.manual_seed(args.seed)
if args.cuda:
    torch.cuda.manual_seed(args.seed)

if(torch.cuda.is_available()):
    gpu=0
    device='cuda:{}'.format(gpu)
else:
  device='cpu'    

#Loading the dataset
dataset = CoraGraphDataset()
graph = dataset[0]   
graph = dgl.add_self_loop(graph)
print(graph)
adj=graph.adj()
print(adj)
adj = torch.FloatTensor(np.array(adj.to_dense()))
print(adj)
print(adj.shape)
n_classes = dataset.num_classes
labels = graph.ndata.pop('label').to(device).long()
feats = graph.ndata.pop('feat').to(device)
n_features = feats.shape[-1]
features=feats
print(n_features)

#Getting train test and val data
train_mask = graph.ndata.pop('train_mask')
val_mask = graph.ndata.pop('val_mask')
test_mask = graph.ndata.pop('test_mask')
print("Train_mask",train_mask)

# idx_train = torch.nonzero(train_mask, as_tuple=False).squeeze().to(device)
# idx_val = torch.nonzero(val_mask, as_tuple=False).squeeze().to(device)
# idx_test = torch.nonzero(test_mask, as_tuple=False).squeeze().to(device)

# idx_train = range(3327)
# idx_val = range(3327)
# idx_test = range(3327)

# idx_train = torch.LongTensor(idx_train)
# idx_val = torch.LongTensor(idx_val)
# idx_test = torch.LongTensor(idx_test)

c_train_num = []
class_sample_num=20
for i in range(labels.max().item() + 1):
    if i==0 or i==5 or i==1 or i==6: #only imbalance the last classes
        c_train_num.append(int(class_sample_num*0.5))

    else:
        c_train_num.append(class_sample_num)
print("Ctrain num",c_train_num)
def split_arti(labels, c_train_num):
    #labels: n-dim Longtensor, each element in [0,...,m-1].
    #cora: m=7
    num_classes = len(set(labels.tolist()))
    c_idxs = [] # class-wise index
    train_idx = []
    val_idx = []
    test_idx = []
    c_num_mat = np.zeros((num_classes,3)).astype(int)
    c_num_mat[:,1] = 25
    c_num_mat[:,2] = 55

    for i in range(num_classes):
        c_idx = (labels==i).nonzero()[:,-1].tolist()
        print('{:d}-th class sample number: {:d}'.format(i,len(c_idx)))
        random.shuffle(c_idx)
        c_idxs.append(c_idx)

        train_idx = train_idx + c_idx[:c_train_num[i]]
        c_num_mat[i,0] = c_train_num[i]

       
        # val_idx = val_idx + c_idx[c_train_num[i]:c_train_num[i]+25]
        # test_idx = test_idx + c_idx[c_train_num[i]+25:c_train_num[i]+80]
        val_idx= range(200,500)
        test_idx=range(500,1500)

    random.shuffle(train_idx)

    #ipdb.set_trace()

    train_idx = torch.LongTensor(train_idx)
    val_idx = torch.LongTensor(val_idx)
    test_idx = torch.LongTensor(test_idx)
    #c_num_mat = torch.LongTensor(c_num_mat)


    return train_idx, val_idx, test_idx, c_num_mat  

idx_train, idx_val, idx_test, c_num_mat=split_arti(labels,c_train_num)
# # Load data
adj, features, labels, idx_train, idx_val, idx_test = load_data()
n_features=features.shape[-1]

# cv = StratifiedShuffleSplit(n_splits=1, random_state=42,test_size=0.2)
# for train_idx, test_idx in cv.split(features.cpu(),labels.cpu()):
#   print(train_idx)
#   print(len(train_idx))
#   print(len(test_idx))

# cv1= StratifiedShuffleSplit(n_splits=1, random_state=42,test_size=0.125)
# for trai_idx, val_idx in cv1.split(features[train_idx].cpu(),labels[train_idx].cpu()):
#   print(train_idx)
#   print(len(trai_idx))
#   print(len(val_idx))  

# idx_train, idx_val,idx_test= trai_idx, val_idx, test_idx 
# idx_train = torch.LongTensor(idx_train)
# idx_val = torch.LongTensor(idx_val)
# idx_test = torch.LongTensor(idx_test) 

majority=[]
minority=[]
for i in range(len(idx_train)):
  if(labels[idx_train[i]]==0):
    minority.append(idx_train[i])
  if(labels[idx_train[i]]==1):
    minority.append(idx_train[i])
  if(labels[idx_train[i]]==6):
    minority.append(idx_train[i])    
    
  if(labels[idx_train[i]]==5):
    minority.append(idx_train[i])
  #   print(labels[idx_train[i]])
    # majority_id.append(i)
  else:
    majority.append(idx_train[i]) 
print("length")    
print(len(idx_train))
print(len(idx_val))
print(len(idx_test))
print(minority)
relist=[]
# Model and optimizer
if args.sparse:
    model = SpGAT(nfeat=n_features, 
                nhid=args.hidden, 
                nclass=int(labels.max()) + 1, 
                dropout=args.dropout, 
                nheads=args.nb_heads, 
                alpha=args.alpha)
if args.GCN:

  model = GCN(nfeat=n_features,
  nhid=args.hidden,
  nclass=int(labels.max()) + 1, 
  dropout=args.dropout)
                
else:
    model = GAT(nfeat=n_features, 
                nhid=args.hidden, 
                nclass=int(labels.max()) + 1, 
                dropout=args.dropout, 
                nheads=args.nb_heads, 
                alpha=args.alpha)
optimizer = optim.Adam(model.parameters(), 
                       lr=args.lr, 
                       weight_decay=args.weight_decay)

if args.cuda:
    model.cuda()
    features = features.cuda()
    adj = adj.cuda()
    labels = labels.cuda()
    idx_train = idx_train.cuda()
    idx_val = idx_val.cuda()
    idx_test = idx_test.cuda()

features, adj, labels = Variable(features), Variable(adj), Variable(labels)


def train(epoch):
    t = time.time()
    model.train()
    optimizer.zero_grad()
    output = model(features, adj)
    weight = features.new((labels.max().item()+1)).fill_(1)
    for i in range(n_classes):
        c_idx = (labels==i).nonzero()[:,-1].tolist()
        weight[i]=1/math.sqrt(len(c_idx))
    reg=0
    # for i in minority:
      
    #   sub=adj[i] - model.attentions[1].weight[i]
      
      
    #   reg=reg+torch.linalg.norm(sub) 
    # print(reg)  
    # t=torch.tensor(adj[minority],dtype=torch.long)
    # sub=F.cross_entropy(model.attentions[1].weight[minority],t)
    # print("Sub is",sub)
    # reg=0
    # kl_loss = nn.KLDivLoss(reduction="batchmean")
    # input = F.log_softmax((model.attentions[1].weight[minority]),dim=-1)
    # target = F.softmax(adj[minority],dim=-1)
    # reg = kl_loss(input, target)
    # print(reg)
    # print(model.attentions[1].weight[minority].shape)
    # reg=0
    reg=0
    # print("out_att",model.out_att.weight.shape)
    for i in minority:
      kl_loss = nn.KLDivLoss(reduction="batchmean")
      input = F.log_softmax((model.attentions[1].weight[i]),dim=-1)
      print(input)
    
      target =adj[i]
      sub = kl_loss(input, target)
      reg=reg+sub
      reg=reg/len(minority)
    print("reg is",reg)
    
  
    relist.append(reg)




    
    


    # alpha=1
    # gamma=2
    # ce_loss_train= F.cross_entropy(output[idx_train], labels[idx_train], weight=weight,reduction='mean') 
    # pt = torch.exp(-ce_loss_train)
    # loss_train = ((alpha * (1-pt)**gamma * ce_loss_train).mean()) 

    
    # labels_onehot = F.one_hot(labels[idx_train], num_classes=n_classes).to(device=output.device,
    #                                                                        dtype=output.dtype)
    # ce_loss= F.cross_entropy(output[idx_train], labels[idx_train], weight=weight,reduction='mean')
    # pt=torch.sum((one_hot.type(torch.float)*(torch.nn.Softmax()(output[idx_train].type(torch.float)))),dim=-1)
    # print("inside poly loss")
    # pt = torch.sum(labels_onehot * F.softmax(output[idx_train], dim=-1), dim=-1)
    # print(ce_loss)
   
    
    # print(one_hot.shape)
    # print((output[idx_train].shape))
    # print(torch.nn.Softmax()(output[idx_train]).shape)
    # loss_train= ce_loss + (0.5)*(1-pt)
    # loss_train=loss_train.mean()

    loss_train = F.cross_entropy(output[idx_train], labels[idx_train],weight=weight) + 0.5*reg
    # print("Reg is",reg)
    # print("Train accuracy is",F.cross_entropy(output[idx_train], labels[idx_train],weight=weight))
    acc_train = accuracy(output[idx_train], labels[idx_train])
    
    loss_train.backward()
    optimizer.step()

    if not args.fastmode:
        # Evaluate validation set performance separately,
        # deactivates dropout during validation run.
        model.eval()
        output = model(features, adj)
    loss_val= F.cross_entropy(output[idx_val], labels[idx_val], weight=weight,reduction='mean') 
    # loss_val = ((alpha * (1-pt)**gamma * ce_loss_val).mean())  
    acc_val = accuracy(output[idx_val], labels[idx_val])
    f1=print_class_acc(output[idx_val], labels[idx_val], 0)
    f2=print_class_acc(output[idx_train], labels[idx_train], 0)
    print('Epoch: {:04d}'.format(epoch+1),
          # 'loss_train: {:.4f}'.format(loss_train.data.item()),
          'acc_train: {:.4f}'.format(acc_train.data.item()),
          'loss_val: {:.4f}'.format(loss_val.data.item()),
          'acc_val: {:.4f}'.format(acc_val.data.item()),
          'time: {:.4f}s'.format(time.time() - t))
    metrics= {
      # "loss_train": loss_train.data.item(),
    "loss_val": loss_val.data.item(),
    "acc_train": acc_train.data.item(),
    "acc_val":acc_val.data.item(),
    "val_f1":f1,
    "train_f1":f2 }          
    wandb.log(metrics)

    return loss_val.data.item()


def compute_test():
    model.eval()
    output = model(features, adj)
    weight = features.new((labels.max().item()+1)).fill_(1)
    for i in range(n_classes):
        c_idx = (labels==i).nonzero()[:,-1].tolist()
        weight[i]=1/math.sqrt(len(c_idx))
    loss_test = F.cross_entropy(output[idx_test], labels[idx_test],weight=weight)  
    acc_test = accuracy(output[idx_test], labels[idx_test])
    f1=print_class_acc_test(output[idx_test], labels[idx_test], 0, pre='test')
    print("Test set results:",
          "loss= {:.4f}".format(loss_test.data.item()),
          "accuracy= {:.4f}".format(acc_test.data.item()))
    # test_metrics={"loss_test": loss_test.data.item(),
    # "acc_test": acc_test.data.item(),
    # "test_f1":f1}
    # wandb.log(test_metrics)
             

# Train model
t_total = time.time()
loss_values = []
bad_counter = 0
best = args.epochs + 1
best_epoch = 0
for epoch in range(args.epochs):
    loss_values.append(train(epoch))
    

    torch.save(model.state_dict(), '{}.pkl'.format(epoch))
    if loss_values[-1] < best:
        best = loss_values[-1]
        best_epoch = epoch
        bad_counter = 0
    else:
        bad_counter += 1

    if bad_counter == args.patience:
        break

    files = glob.glob('*.pkl')
    for file in files:
        epoch_nb = int(file.split('.')[0])
        if epoch_nb < best_epoch:
            os.remove(file)

files = glob.glob('*.pkl')
for file in files:
    epoch_nb = int(file.split('.')[0])
    if epoch_nb > best_epoch:
        os.remove(file)

print("Optimization Finished!")
print("Total time elapsed: {:.4f}s".format(time.time() - t_total))

# Restore best model
print('Loading {}th epoch'.format(best_epoch))
model.load_state_dict(torch.load('{}.pkl'.format(best_epoch)))

# Testing
compute_test()

mainlist=[]
labell=[]

 
# for i in minority:
#   list1=[]
#   list2=[]
#   list3=[]
#   # print("Node id and label",i,labels[i])
#   for j in range(2708):
#     if(model.attentions[0].weight[i][j]>0):
#       list1.append(j)
#       list2.append((model.attentions[0].weight[i][j]).item())
#       list3.append((labels[j]).item())  
#   # print(list1)
#   # print(list3)
#   # print(list2) 
#       mainlist.append(list2)
#       labell.append(list3)

# with open("/content/drive/MyDrive/Neeraja/noreg.txt", 'w') as output:
#        for row in mainlist:
#           output.write(str(row) + '\n')


# with open("/content/drive/MyDrive/Neeraja/label.txt", 'w') as output:
#        for row in labell:
#           output.write(str(row) + '\n') 

for i in relist:
  print(i.item())





    





   
   

      

       
       