#!/bin/bash
python3 cifar10.py --train_class_num 7 --test_class_num 10
python3 cifar10.py --train_class_num 5 --test_class_num 10
python3 cifar100.py --train_class_num 50 --test_class_num 100
python3 cifar100.py --train_class_num 80 --test_class_num 100

