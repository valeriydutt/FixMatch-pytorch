import logging
import math
import os
import csv

import numpy as np
from PIL import Image, ImageFile
ImageFile.LOAD_TRUNCATED_IMAGES = Truefrom torchvision import datasets
from torchvision import transforms

from .randaugment import RandAugmentMC

logger = logging.getLogger(__name__)

# Change this to the correct directory of drd dataset
# Training images should be in the folder train_images
# and test images should be in the folder test_images
# Train labels should be in the file train_labels.csv
# There should be a file name test_images.csv
# All these files/folders should be in drd_dir
# drd_dir = 'data/drd/'
drd_dir = '/content/gdrive/MyDrive/'

drd_mean = ([0.4560, 0.3106, 0.2178])
drd_std = ([0.2766, 0.2001, 0.1654])
cifar10_mean = (0.4914, 0.4822, 0.4465)
cifar10_std = (0.2471, 0.2435, 0.2616)
cifar100_mean = (0.5071, 0.4867, 0.4408)
cifar100_std = (0.2675, 0.2565, 0.2761)
normal_mean = (0.5, 0.5, 0.5)
normal_std = (0.5, 0.5, 0.5)

# Resize Image
w = 100
h = 100

def get_drd(args, root):
    transform_labeled = transforms.Compose([
        transforms.RandomHorizontalFlip(),
        transforms.RandomCrop(size=(h, w),
                              padding=int(64*0.125),
                              padding_mode='reflect'),
        transforms.ToTensor(),
        transforms.Normalize(mean=drd_mean, std=drd_std)
    ])
    transform_val = transforms.Compose([
        transforms.ToTensor(),
        transforms.Normalize(mean=drd_mean, std=drd_std)
    ])

    # Read the drd training data
    train_data = []
    train_labels = []
    
    with open(os.path.join(drd_dir, 'train_labels.csv')) as csv_file:
        reader = csv.DictReader(csv_file, delimiter=',')

        for row in reader:
            img_id = row.get('id_code')
            train_folder = os.path.join(drd_dir, 'train')
            img = Image.open(os.path.join(train_folder, img_id + '.jpeg'))
            img_arr = np.asarray(img.resize((w, h)))
            train_data.append(img_arr)
            train_labels.append(int(row.get('diagnosis')))

    # Copy last 500 images of training data as test data
    test_data = train_data[-500:]
    test_labels = train_labels[-500:]

    # Update train data accordingly
    train_data = train_data[:-500]
    train_labels = train_labels[:-500]           

    print('Training data is successfully loaded!')

    train_labeled_idxs, train_unlabeled_idxs = x_u_split(args, train_labels)

    train_labeled_dataset = DRD_SSL(train_data, train_labels, train_labeled_idxs,  transform=transform_labeled)

    train_unlabeled_dataset = DRD_SSL(train_data, train_labels, train_unlabeled_idxs, 
        transform=TransformFixMatch2(mean=drd_mean, std=drd_std))

 

    test_dataset = DRD_SSL(test_data, test_labels, None, transform=transform_val)

    return train_labeled_dataset, train_unlabeled_dataset, test_dataset


def get_cifar10(args, root):
    transform_labeled = transforms.Compose([
        transforms.RandomHorizontalFlip(),
        transforms.RandomCrop(size=32,
                              padding=int(32*0.125),
                              padding_mode='reflect'),
        transforms.ToTensor(),
        transforms.Normalize(mean=cifar10_mean, std=cifar10_std)
    ])
    transform_val = transforms.Compose([
        transforms.ToTensor(),
        transforms.Normalize(mean=cifar10_mean, std=cifar10_std)
    ])
    base_dataset = datasets.CIFAR10(root, train=True, download=True)

    train_labeled_idxs, train_unlabeled_idxs = x_u_split(
        args, base_dataset.targets)

    train_labeled_dataset = CIFAR10SSL(
        root, train_labeled_idxs, train=True,
        transform=transform_labeled)

    train_unlabeled_dataset = CIFAR10SSL(
        root, train_unlabeled_idxs, train=True,
        transform=TransformFixMatch(mean=cifar10_mean, std=cifar10_std))

    test_dataset = datasets.CIFAR10(
        root, train=False, transform=transform_val, download=False)

    return train_labeled_dataset, train_unlabeled_dataset, test_dataset


def get_cifar100(args, root):

    transform_labeled = transforms.Compose([
        transforms.RandomHorizontalFlip(),
        transforms.RandomCrop(size=32,
                              padding=int(32*0.125),
                              padding_mode='reflect'),
        transforms.ToTensor(),
        transforms.Normalize(mean=cifar100_mean, std=cifar100_std)])

    transform_val = transforms.Compose([
        transforms.ToTensor(),
        transforms.Normalize(mean=cifar100_mean, std=cifar100_std)])

    base_dataset = datasets.CIFAR100(
        root, train=True, download=True)

    train_labeled_idxs, train_unlabeled_idxs = x_u_split(
        args, base_dataset.targets)

    train_labeled_dataset = CIFAR100SSL(
        root, train_labeled_idxs, train=True,
        transform=transform_labeled)

    train_unlabeled_dataset = CIFAR100SSL(
        root, train_unlabeled_idxs, train=True,
        transform=TransformFixMatch(mean=cifar100_mean, std=cifar100_std))

    test_dataset = datasets.CIFAR100(
        root, train=False, transform=transform_val, download=False)

    return train_labeled_dataset, train_unlabeled_dataset, test_dataset


def x_u_split(args, labels):
    label_per_class = args.num_labeled // args.num_classes
    labels = np.array(labels)
    labeled_idx = []
    # unlabeled data: all data (https://github.com/kekmodel/FixMatch-pytorch/issues/10)
    unlabeled_idx = np.array(range(len(labels)))
    for i in range(args.num_classes):
        idx = np.where(labels == i)[0]
        idx = np.random.choice(idx, label_per_class, False)
        labeled_idx.extend(idx)
    labeled_idx = np.array(labeled_idx)
    assert len(labeled_idx) == args.num_labeled

    if args.expand_labels or args.num_labeled < args.batch_size:
        num_expand_x = math.ceil(
            args.batch_size * args.eval_step / args.num_labeled)
        labeled_idx = np.hstack([labeled_idx for _ in range(num_expand_x)])
    np.random.shuffle(labeled_idx)
    return labeled_idx, unlabeled_idx


class TransformFixMatch(object):
    def __init__(self, mean, std):
        self.weak = transforms.Compose([
            transforms.RandomHorizontalFlip(),
            transforms.RandomCrop(size=32,
                                  padding=int(32*0.125),
                                  padding_mode='reflect')])
        self.strong = transforms.Compose([
            transforms.RandomHorizontalFlip(),
            transforms.RandomCrop(size=32,
                                  padding=int(32*0.125),
                                  padding_mode='reflect'),
            RandAugmentMC(n=2, m=10)])
        self.normalize = transforms.Compose([
            transforms.ToTensor(),
            transforms.Normalize(mean=mean, std=std)])

    def __call__(self, x):
        weak = self.weak(x)
        strong = self.strong(x)
        return self.normalize(weak), self.normalize(strong)


class CIFAR10SSL(datasets.CIFAR10):
    def __init__(self, root, indexs, train=True,
                 transform=None, target_transform=None,
                 download=False):
        super().__init__(root, train=train,
                         transform=transform,
                         target_transform=target_transform,
                         download=download)
        if indexs is not None:
            self.data = self.data[indexs]
            self.targets = np.array(self.targets)[indexs]

    def __getitem__(self, index):
        img, target = self.data[index], self.targets[index]
        img = Image.fromarray(img)

        if self.transform is not None:
            img = self.transform(img)

        if self.target_transform is not None:
            target = self.target_transform(target)

        return img, target


class CIFAR100SSL(datasets.CIFAR100):
    def __init__(self, root, indexs, train=True,
                 transform=None, target_transform=None,
                 download=False):
        super().__init__(root, train=train,
                         transform=transform,
                         target_transform=target_transform,
                         download=download)
        if indexs is not None:
            self.data = self.data[indexs]
            self.targets = np.array(self.targets)[indexs]

    def __getitem__(self, index):
        img, target = self.data[index], self.targets[index]
        img = Image.fromarray(img)

        if self.transform is not None:
            img = self.transform(img)

        if self.target_transform is not None:
            target = self.target_transform(target)

        return img, target


DATASET_GETTERS = {'cifar10': get_cifar10,
                   'cifar100': get_cifar100,
                   'drd': get_drd}
