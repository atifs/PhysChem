import torch
import torch.nn as nn
import torch.nn.functional as F

from net.utils.MaskMatrices import MaskMatrices
from net.utils.model_utils import normalize_adj_rc


def multi_mse_loss(source: torch.Tensor, target: torch.Tensor, explicit=False) -> torch.Tensor:
    se = (source - target) ** 2
    mse = torch.mean(se, dim=0)
    if explicit:
        return mse
    else:
        return torch.sum(mse)


def multi_mae_loss(source: torch.Tensor, target: torch.Tensor, explicit=False) -> torch.Tensor:
    ae = torch.abs(source - target)
    if explicit:
        return torch.mean(ae, dim=0)
    else:
        return torch.mean(ae)


def mse_loss(source: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    return F.mse_loss(source, target)


def rmse_loss(source: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    return F.mse_loss(source, target).sqrt()


def mae_loss(source: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    return torch.mean(torch.abs(source - target))


def distance_among(positions: torch.Tensor) -> torch.Tensor:
    p1 = torch.unsqueeze(positions, 0)
    p2 = torch.unsqueeze(positions, 1)
    distance = torch.norm(p1 - p2, dim=2)
    return distance


def adj3_loss(source: torch.Tensor, target: torch.Tensor, mask_matrices: MaskMatrices,
              use_cuda=False) -> torch.Tensor:
    vew1 = mask_matrices.vertex_edge_w1
    vew2 = mask_matrices.vertex_edge_w2
    adj_d = vew1 @ vew2.t()
    i = torch.eye(adj_d.shape[0])
    if use_cuda:
        i = i.cuda()
    adj = adj_d + adj_d.t() + i
    norm_adj = normalize_adj_rc(adj)
    norm_adj_2 = norm_adj @ norm_adj
    norm_adj_3 = norm_adj @ norm_adj
    mean_adj_3 = (norm_adj + norm_adj_2 + norm_adj_3) / 3

    ds = distance_among(source)
    dt = distance_among(target)
    distance_2 = (ds - dt) ** 2
    loss = distance_2 * mean_adj_3
    return loss