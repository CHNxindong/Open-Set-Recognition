"""
Version2: includes centroids into model, and shares embedding layers.
"""
import math
import torch
import torch.nn as nn
import torch.nn.functional as F
import backbones.cifar as models
from Distance import Similarity, Distance

class DFPNet(nn.Module):
    def __init__(self, backbone='ResNet18', num_classes=1000, embed_dim=512):
        super(DFPNet, self).__init__()
        self.num_classes = num_classes
        self.backbone_name = backbone

        self.backbone = models.__dict__[backbone](num_classes=num_classes, backbone_fc=False)
        self.feat_dim = self.get_backbone_last_layer_out_channel()  # get the channel number of backbone output
        self.embed_dim = embed_dim

        self.embeddingLayer = nn.Sequential(
            nn.PReLU(),
            nn.Linear(self.feat_dim, self.feat_dim // 16, bias=False),
            nn.PReLU(),
            nn.Linear(self.feat_dim // 16, embed_dim, bias=False)
        )
        self.centroids = nn.Parameter(torch.randn(num_classes, embed_dim))
        nn.init.xavier_uniform_(self.centroids)

    def get_backbone_last_layer_out_channel(self):
        if self.backbone_name.startswith("LeNet"):
            return 128 * 3 * 3
        last_layer = list(self.backbone.children())[-1]
        while (not isinstance(last_layer, nn.Conv2d)) and \
                (not isinstance(last_layer, nn.Linear)) and \
                (not isinstance(last_layer, nn.BatchNorm2d)):

            temp_layer = list(last_layer.children())[-1]
            if isinstance(temp_layer, nn.Sequential) and len(list(temp_layer.children())) == 0:
                temp_layer = list(last_layer.children())[-2]
            last_layer = temp_layer
        if isinstance(last_layer, nn.BatchNorm2d):
            return last_layer.num_features
        else:
            return last_layer.out_channels

    def forward(self, x):
        x = self.backbone(x)
        gap = (F.adaptive_avg_pool2d(x, 1)).view(x.size(0), -1)
        embed_fea = self.embeddingLayer(gap)
        norm_fea = torch.norm(embed_fea, dim=1, p=2,keepdim=True)
        embed_fea_normed = F.normalize(embed_fea, dim=1, p=2)
        centroids = self.centroids
        centroids_normed = F.normalize(centroids, dim=1, p=2)
        SIMI = Similarity()
        # dotproduct: X*W = ||X|| * ||W|| * cos(X,W)  ignoring transposition operation
        dotproduct_fea2cen = getattr(SIMI, "dotproduct")(embed_fea, centroids)
        # cosine: cos(X,W)   ignoring transposition operation
        cosine_fea2cen = getattr(SIMI, "dotproduct")(embed_fea_normed, centroids_normed)
        # normweight: ||X|| * cos(X,W)
        normweight_fea2cen = getattr(SIMI, "dotproduct")(embed_fea, centroids_normed)


        return {
            "gap": gap,  # [n,self.feat_dim] gap extracted by backbone
            "embed_fea": embed_fea,  # [n,embed_dim] embedded features
            "norm_fea": norm_fea, # [n,1]  the norm value of one images features, keepdim for post-processing
            "dotproduct_fea2cen": dotproduct_fea2cen,  # [n,num_classes]
            "cosine_fea2cen": cosine_fea2cen,  # [n,num_classes]
            "normweight_fea2cen": normweight_fea2cen
        }


def demo():
    x = torch.rand([3, 3, 32, 32])
    y = torch.rand([6, 3, 32, 32])
    net = DFPNet('ResNet18', num_classes=10, embed_dim=64)
    output = net(x)
    print(output)

# demo()
