import torch
import torch.nn as nn
from typing import Tuple
from torch.nn.utils.rnn import pad_sequence

from .utils.MaskMatrices import MaskMatrices
from .utils.model_utils import activation_select


class MLP(nn.Module):
    def __init__(self, in_dim: int, out_dim: int, hidden_dims: list = None, activation: str = 'no',
                 use_cuda=False, bias=True, residual=False):
        super(MLP, self).__init__()
        self.use_cuda = use_cuda
        self.residual = residual

        if not hidden_dims:
            hidden_dims = []
        in_dims = [in_dim] + hidden_dims
        out_dims = hidden_dims + [out_dim]
        self.linears = nn.ModuleList([nn.Linear(i, o, bias=bias) for i, o in zip(in_dims, out_dims)])
        self.layer_act = nn.LeakyReLU()
        self.activate = activation_select(activation)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        for i, linear in enumerate(self.linears):
            x2 = linear(x)
            if i < len(self.linears) - 1:
                x2 = self.layer_act(x2)
            if self.residual:
                x = torch.cat([x, x2])
            else:
                x = x2
        x = self.activate(x)
        return x


class GCN(nn.Module):
    def __init__(self, in_dim: int, out_dim: int, hidden_dims: list = None, activation: str = 'no',
                 use_cuda=False, residual=False):
        super(GCN, self).__init__()
        self.use_cuda = use_cuda
        self.residual = residual

        if not hidden_dims:
            hidden_dims = []
        in_dims = [in_dim] + hidden_dims
        out_dims = hidden_dims + [out_dim]
        self.linears = nn.ModuleList([nn.Linear(i, o, bias=True) for i, o in zip(in_dims, out_dims)])
        self.layer_act = nn.LeakyReLU()
        self.activate = activation_select(activation)

    def forward(self, x: torch.Tensor, a: torch.Tensor) -> torch.Tensor:
        assert x.shape[0] == a.shape[0]
        for i, linear in enumerate(self.linears):
            x2 = a @ linear(x)
            if i < len(self.linears) - 1:
                x2 = self.layer_act(x2)
            if self.residual:
                x = torch.cat([x, x2])
            else:
                x = x2
        x = self.activate(x)
        return x


class LSTMEncoder(nn.Module):
    def __init__(self, in_dim: int, out_dim: int, layers: int = 1):
        super(LSTMEncoder, self).__init__()

        self.rnn = nn.LSTM(in_dim, out_dim, layers)

    def forward(self, hv_neighbor_ftr: torch.Tensor, mask_matrices: MaskMatrices) -> torch.Tensor:
        seqs = [hv_neighbor_ftr[n == 1, :] for n in mask_matrices.mol_vertex_w]
        lengths = [s.shape[0] for s in seqs]
        m = pad_sequence(seqs)
        output, _ = self.rnn(m)
        pq_ftr = torch.cat([output[:lengths[i], i, :] for i in range(len(lengths))])
        return pq_ftr


class NaiveDynMessage(nn.Module):
    def __init__(self, hv_dim: int, he_dim: int, mv_dim: int, me_dim: int, p_dim: int, q_dim: int,
                 use_cuda=False):
        super(NaiveDynMessage, self).__init__()
        self.use_cuda = use_cuda

        self.attend = nn.Linear(hv_dim, mv_dim)
        self.at_act = nn.LeakyReLU()
        self.align = nn.Linear(p_dim + q_dim + he_dim, 1)
        self.al_act = nn.Softmax(dim=-1)
        self.ag_act = nn.ELU()
        self.link = nn.Linear(hv_dim + p_dim + q_dim + hv_dim, me_dim)
        self.l_act = nn.LeakyReLU()

    def forward(self, hv_ftr: torch.Tensor, he_ftr: torch.Tensor, p_ftr: torch.Tensor, q_ftr: torch.Tensor,
                mask_matrices: MaskMatrices
                ) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        naive message passing with dynamic properties
        :param hv_ftr: hidden vertex features with shape [n_vertex, hv_dim]
        :param he_ftr: hidden edge features with shape [n_edge, he_dim]
        :param p_ftr: atom momentum features with shape [n_vertex, p_dim]
        :param q_ftr: atom position features with shape [n_vertex, q_dim]
        :param mask_matrices: mask matrices
        :return: vertex message, edge message
        """
        vew1 = mask_matrices.vertex_edge_w1  # shape [n_vertex, n_edge]
        vew2 = mask_matrices.vertex_edge_w2  # shape [n_vertex, n_edge]
        veb1 = mask_matrices.vertex_edge_b1  # shape [n_vertex, n_edge]
        veb2 = mask_matrices.vertex_edge_b2  # shape [n_vertex, n_edge]
        vew_u = torch.cat([vew1, vew2], dim=1)  # shape [n_vertex, 2 * n_edge]
        vew_v = torch.cat([vew2, vew1], dim=1)  # shape [n_vertex, 2 * n_edge]
        veb_v = torch.cat([veb2, veb1], dim=1)  # shape [n_vertex, 2 * n_edge]
        hv_u_ftr = vew_u.t() @ hv_ftr  # shape [2 * n_edge, hv_dim]
        hv_v_ftr = vew_v.t() @ hv_ftr  # shape [2 * n_edge, hv_dim]
        p_u_ftr = vew_u.t() @ p_ftr  # shape [2 * n_edge, p_dim]
        p_v_ftr = vew_v.t() @ p_ftr  # shape [2 * n_edge, p_dim]
        q_u_ftr = vew_u.t() @ q_ftr  # shape [2 * n_edge, q_dim]
        q_v_ftr = vew_v.t() @ q_ftr  # shape [2 * n_edge, q_dim]
        p_uv_ftr = p_v_ftr - p_u_ftr  # shape [2 * n_edge, p_dim]
        q_uv_ftr = q_v_ftr - q_u_ftr  # shape [2 * n_edge, q_dim]
        he2_ftr = torch.cat([he_ftr, he_ftr])  # shape [2 * n_edge, he_dim]

        attend_ftr = self.attend(hv_v_ftr)  # shape [2 * n_edge, mv_dim]
        attend_ftr = self.at_act(attend_ftr)
        align_ftr = self.align(torch.cat([p_uv_ftr, q_uv_ftr, he2_ftr], dim=1))  # shape [2 * n_edge, 1]
        align_ftr = vew_v @ torch.diag(torch.reshape(align_ftr, [-1])) + veb_v  # shape [n_vertex, 2 * n_edge]
        align_ftr = self.al_act(align_ftr)
        mv_ftr = self.ag_act(align_ftr @ attend_ftr)  # shape [n_vertex, mv_dim]

        me_ftr = self.link(torch.cat([hv_u_ftr, p_uv_ftr, q_uv_ftr, hv_v_ftr], dim=1))  # shape [2 * n_edge, me_dim]
        me_ftr = self.l_act(me_ftr)

        return mv_ftr, me_ftr


class NaiveUnion(nn.Module):
    def __init__(self, h_dim: int, m_dim: int,
                 use_cuda=False, bias=True):
        super(NaiveUnion, self).__init__()
        self.linear = nn.Linear(h_dim + m_dim, h_dim, bias=bias)
        self.activate = nn.LeakyReLU()

    def forward(self, h_ftr: torch.Tensor, m_ftr: torch.Tensor) -> torch.Tensor:
        h_ftr = self.linear(torch.cat([h_ftr, m_ftr]))
        h_ftr = self.activate(h_ftr)
        return h_ftr


class GRUUnion(nn.Module):
    def __init__(self, h_dim: int, m_dim: int,
                 use_cuda=False, bias=True):
        super(GRUUnion, self).__init__()
        self.gru_cell = nn.GRUCell(m_dim, h_dim, bias=bias)

    def forward(self, h_ftr: torch.Tensor, m_ftr: torch.Tensor) -> torch.Tensor:
        h_ftr = self.gru_cell(m_ftr, h_ftr)
        return h_ftr


class GlobalDynReadout(nn.Module):
    def __init__(self, hm_dim: int, hv_dim: int, mm_dim: int, p_dim: int, q_dim: int,
                 use_cuda=False):
        super(GlobalDynReadout, self).__init__()
        self.use_cuda = use_cuda

        self.attend = nn.Linear(p_dim + q_dim + hv_dim, mm_dim)
        self.at_act = nn.LeakyReLU()
        self.align = nn.Linear(hm_dim + hv_dim, 1)
        self.al_act = nn.Softmax(dim=-1)
        self.ag_act = nn.ELU()

    def forward(self, hm_ftr: torch.Tensor, hv_ftr: torch.Tensor, p_ftr: torch.Tensor, q_ftr: torch.Tensor,
                mask_matrices: MaskMatrices
                ) -> torch.Tensor:
        """
        molecule message readout with global attention and dynamic properties
        :param hm_ftr: molecule features with shape [n_mol, hm_dim]
        :param hv_ftr: vertex features with shape [n_vertex, hv_dim]
        :param p_ftr: atom momentum features with shape [n_vertex, p_dim]
        :param q_ftr: atom position features with shape [n_vertex, q_dim]
        :param mask_matrices: mask matrices
        :return: molecule message
        """
        mvw = mask_matrices.mol_vertex_w  # shape [n_mol, n_vertex]
        mvb = mask_matrices.mol_vertex_b  # shape [n_mol, n_vertex]
        hm_v_ftr = mvw.t() @ hm_ftr  # shape [n_vertex, hm_dim]

        attend_ftr = self.attend(torch.cat([p_ftr, q_ftr, hv_ftr], dim=1))  # shape [n_vertex, mm_dim]
        attend_ftr = self.at_act(attend_ftr)
        align_ftr = self.align(torch.cat([hm_v_ftr, hv_ftr], dim=1))  # shape [n_vertex, 1]
        align_ftr = mvw @ torch.diag(torch.reshape(align_ftr, [-1])) + mvb  # shape [n_mol, n_vertex]
        align_ftr = self.al_act(align_ftr)
        mm_ftr = self.ag_act(align_ftr @ attend_ftr)  # shape [n_mol, mm_dim]

        return mm_ftr


