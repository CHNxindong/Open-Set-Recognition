
from __future__ import print_function

import torch
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F
import torch.backends.cudnn as cudnn

import torchvision
import numpy as np
import torchvision.transforms as transforms

import os
import argparse
import sys

#from models import *
sys.path.append("../..")
import backbones.cifar as models
from datasets import CIFAR100
from Utils import adjust_learning_rate, progress_bar, Logger, mkdir_p
from openmax import compute_train_score_and_mavs_and_dists,fit_weibull

model_names = sorted(name for name in models.__dict__
    if not name.startswith("__")
    and callable(models.__dict__[name]))

os.environ["HDF5_USE_FILE_LOCKING"] = "FALSE"
# os.environ["CUDA_VISIBLE_DEVICES"] = "0,1,2,3"
parser = argparse.ArgumentParser(description='PyTorch CIFAR10 Training')
parser.add_argument('--lr', default=0.1, type=float, help='learning rate')
parser.add_argument('--resume', '-r',default=False, action='store_true', help='resume from checkpoint')
parser.add_argument('--arch', default='ResNet18', choices=model_names, type=str, help='choosing network')
parser.add_argument('--bs', default=256, type=int, help='batch size')
parser.add_argument('--es', default=100, type=int, help='epoch size')
parser.add_argument('--cifar', default=100, type=int, help='dataset classes number')
parser.add_argument('--train_class_num', default=50, type=int, help='Classes used in training')
parser.add_argument('--test_class_num', default=70, type=int, help='Classes used in testing')
parser.add_argument('--includes_all_train_class', default=True,  action='store_true',
                    help='If required all known classes included in testing')

args = parser.parse_args()



def main():
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    print(device)
    best_acc = 0  # best test accuracy
    start_epoch = 0  # start from epoch 0 or last checkpoint epoch

    # checkpoint
    args.checkpoint = './checkpoints/cifar/' + args.arch
    if not os.path.isdir(args.checkpoint):
        mkdir_p(args.checkpoint)

    # Data
    print('==> Preparing data..')
    transform_train = transforms.Compose([
        transforms.RandomCrop(32, padding=4),
        transforms.RandomHorizontalFlip(),
        transforms.ToTensor(),
        transforms.Normalize((0.4914, 0.4822, 0.4465), (0.2023, 0.1994, 0.2010)),
    ])

    transform_test = transforms.Compose([
        transforms.ToTensor(),
        transforms.Normalize((0.4914, 0.4822, 0.4465), (0.2023, 0.1994, 0.2010)),
    ])

    trainset = CIFAR100(root='../../data', train=True, download=True, transform=transform_train,
                        train_class_num=args.train_class_num, test_class_num=args.test_class_num,
                        includes_all_train_class=args.includes_all_train_class)
    trainloader = torch.utils.data.DataLoader(trainset, batch_size=args.bs, shuffle=True, num_workers=4)
    testset = CIFAR100(root='../../data', train=False, download=True, transform=transform_test,
                       train_class_num=args.train_class_num, test_class_num=args.test_class_num,
                       includes_all_train_class=args.includes_all_train_class)
    testloader = torch.utils.data.DataLoader(testset, batch_size=args.bs, shuffle=False, num_workers=4)


    # Model
    print('==> Building model..')
    try:
        net = models.__dict__[args.arch](num_classes=100) # CIFAR 100
    except:
        net = models.__dict__[args.arch]()
    net = net.to(device)

    if device == 'cuda':
        net = torch.nn.DataParallel(net)
        cudnn.benchmark = True

    if args.resume:
        # Load checkpoint.
        print('==> Resuming from checkpoint..')
        assert os.path.isdir('checkpoint'), 'Error: no checkpoint directory found!'
        checkpoint_path = os.path.join(args.checkpoint,'last_model.pth')
        checkpoint = torch.load(checkpoint_path)
        net.load_state_dict(checkpoint['net'])
        best_acc = checkpoint['acc']
        print("BEST_ACCURACY: "+str(best_acc))
        start_epoch = checkpoint['epoch']
        logger = Logger(os.path.join(args.checkpoint, 'log.txt'), resume=True)
    else:
        logger = Logger(os.path.join(args.checkpoint, 'log.txt'))
        logger.set_names(['Epoch', 'Learning Rate', 'Train Loss','Train Acc.', 'Test Loss', 'Test Acc.'])

    criterion = nn.CrossEntropyLoss()
    optimizer = optim.SGD(net.parameters(), lr=args.lr, momentum=0.9, weight_decay=5e-4)

    test(0, net, trainloader, testloader, criterion, device)

    for epoch in range(start_epoch, start_epoch + args.es):
        print('\nEpoch: %d   Learning rate: %f' % (epoch+1, optimizer.param_groups[0]['lr']))
        adjust_learning_rate(optimizer, epoch, args.lr)
        train_loss, train_acc = train(net,trainloader,optimizer,criterion,device)
        save_model(net, None, epoch, os.path.join(args.checkpoint,'last_model.pth'))
        test_loss, test_acc = 0, 0
        if epoch>10:
            test(epoch, net,trainloader, testloader, criterion,device)
        logger.append([epoch+1, optimizer.param_groups[0]['lr'], train_loss, train_acc, test_loss, test_acc])

    logger.close()


# Training
def train(net,trainloader,optimizer,criterion,device):
    net.train()
    train_loss = 0
    correct = 0
    total = 0
    for batch_idx, (inputs, targets) in enumerate(trainloader):
        inputs, targets = inputs.to(device), targets.to(device)
        optimizer.zero_grad()
        outputs = net(inputs)
        loss = criterion(outputs, targets)
        loss.backward()
        optimizer.step()

        train_loss += loss.item()
        _, predicted = outputs.max(1)
        total += targets.size(0)
        correct += predicted.eq(targets).sum().item()

        progress_bar(batch_idx, len(trainloader), 'Loss: %.3f | Acc: %.3f%% (%d/%d)'
            % (train_loss/(batch_idx+1), 100.*correct/total, correct, total))
    return train_loss/(batch_idx+1), correct/total


def test(epoch, net,trainloader,  testloader,criterion, device):
    net.eval()
    # _, mavs,dists = compute_train_score_and_mavs_and_dists(args.train_class_num,trainloader,device,net)
    # categories = list(range(0,args.train_class_num))
    # weibull_model = fit_weibull(mavs, dists, categories, 80, "euclidean")

    test_loss = 0
    correct = 0
    total = 0

    scores, labels = None, None
    with torch.no_grad():
        for batch_idx, (inputs, targets) in enumerate(testloader):
            inputs, targets = inputs.to(device), targets.to(device)
            outputs = net(inputs)
            loss = criterion(outputs, targets)

            test_loss += loss.item()
            _, predicted = outputs.max(1)
            print(outputs.shape)
            print(predicted.shape)
            total += targets.size(0)
            correct += predicted.eq(targets).sum().item()

            progress_bar(batch_idx, len(testloader))



def save_model(net, acc, epoch, path):
    print('Saving..')
    state = {
        'net': net.state_dict(),
        'testacc': acc,
        'epoch': epoch,
    }
    torch.save(state, path)

if __name__ == '__main__':
    main()

