from .components import *
from .dynamics.newton import NewtonianDerivation
from .dynamics.hamiltion import DissipativeHamiltonianDerivation
from .utils.model_utils import normalize_adj_r


class Initializer(nn.Module):
    H_DIMS = []
    OUT_DIM = 32

    def __init__(self, atom_dim: int, bond_dim: int, hv_dim: int, he_dim: int, p_dim: int, q_dim: int,
                 use_cuda=False):
        super(Initializer, self).__init__()
        self.use_cuda = use_cuda
        self.p_dim = p_dim

        self.v_linear = nn.Linear(atom_dim, hv_dim, bias=True)
        self.v_act = nn.Tanh()
        self.e_linear = nn.Linear(bond_dim, he_dim, bias=True)
        self.e_act = nn.Tanh()
        self.a_linear = nn.Linear(he_dim, 1, bias=True)
        self.a_act = nn.Sigmoid()
        self.gcn = GCN(hv_dim, self.OUT_DIM, self.H_DIMS, use_cuda=use_cuda, residual=True)
        self.lstm_encoder = LSTMEncoder(hv_dim + sum(self.H_DIMS) + self.OUT_DIM, p_dim + q_dim)

    def forward(self, atom_ftr: torch.Tensor, bond_ftr: torch.Tensor,
                mask_matrices: MaskMatrices
                ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
        vew1 = mask_matrices.vertex_edge_w1
        vew2 = mask_matrices.vertex_edge_w2

        hv_ftr = self.v_act(self.v_linear(atom_ftr))
        he_ftr = self.e_act(self.e_linear(bond_ftr))
        a = self.a_act(self.a_linear(he_ftr))
        adj_d = vew1 @ torch.diag(torch.reshape(a, [-1])) @ vew2.t()
        adj = adj_d + adj_d.t()
        norm_adj = normalize_adj_r(adj)
        hv_neighbor_ftr = self.gcn(hv_ftr, norm_adj)
        pq_ftr = self.lstm_encoder(hv_neighbor_ftr, mask_matrices)
        p_ftr, q_ftr = pq_ftr[:, :self.p_dim], pq_ftr[:, self.p_dim:]

        return hv_ftr, he_ftr, p_ftr, q_ftr


class ConfAwareMPNNKernel(nn.Module):
    def __init__(self, hv_dim: int, he_dim: int, mv_dim: int, me_dim: int, p_dim: int, q_dim: int, hops: int,
                 use_cuda=False, dropout=0.0,
                 message_type='naive', union_type='gru'):
        super(ConfAwareMPNNKernel, self).__init__()
        self.use_cuda = use_cuda
        self.message_type = message_type
        self.union_type = union_type
        self.hops = hops

        if message_type == 'naive':
            self.messages = nn.ModuleList([
                NaiveDynMessage(hv_dim, he_dim, mv_dim, me_dim, p_dim, q_dim, use_cuda, dropout)
                for _ in range(hops)
            ])
        elif message_type == 'norm_naive':
            self.messages = nn.ModuleList([
                NormalizedNaiveDynMessage(hv_dim, he_dim, mv_dim, me_dim, p_dim, q_dim, use_cuda, dropout)
                for _ in range(hops)
            ])
        else:
            assert False, 'Undefined message type {} in net.layers.ConfAwareMPNNKernel'.format(message_type)

        if union_type == 'naive':
            self.unions_v = nn.ModuleList([NaiveUnion(hv_dim, mv_dim, use_cuda) for _ in range(hops)])
            self.unions_e = nn.ModuleList([NaiveUnion(he_dim, me_dim, use_cuda) for _ in range(hops)])
        elif union_type == 'gru':
            self.unions_v = nn.ModuleList([GRUUnion(hv_dim, mv_dim, use_cuda) for _ in range(hops)])
            self.unions_e = nn.ModuleList([GRUUnion(he_dim, me_dim, use_cuda) for _ in range(hops)])
        else:
            assert False, 'Undefined union type {} in net.layers.ConfAwareMPNNKernel'.format(union_type)

    def forward(self, hv_ftr: torch.Tensor, he_ftr: torch.Tensor, p_ftr: torch.Tensor, q_ftr: torch.Tensor,
                mask_matrices: MaskMatrices
                ) -> Tuple[torch.Tensor, torch.Tensor]:
        for i in range(self.hops):
            mv_ftr, me_ftr = self.messages[i](hv_ftr, he_ftr, p_ftr, q_ftr, mask_matrices)
            hv_ftr = self.unions_v[i](hv_ftr, mv_ftr)
            he_ftr = self.unions_e[i](he_ftr, me_ftr)
        return hv_ftr, he_ftr


class InformedDerivationKernel(nn.Module):
    def __init__(self, hv_dim: int, he_dim: int, p_dim: int, q_dim: int, tau: float,
                 use_cuda=False, dropout=0.0,
                 derivation_type='newton'):
        super(InformedDerivationKernel, self).__init__()
        self.tau = tau
        self.use_cuda = use_cuda

        if derivation_type == 'newton':
            self.derivation = NewtonianDerivation(hv_dim, he_dim, p_dim, q_dim,
                                                  use_cuda=use_cuda, dropout=dropout)
        elif derivation_type == 'hamilton':
            self.derivation = DissipativeHamiltonianDerivation(hv_dim, he_dim, p_dim, q_dim,
                                                               use_cuda=use_cuda, dropout=dropout)
        else:
            assert False, 'Undefined derivation type {} in net.layers.InformedDerivationKernel'.format(derivation_type)

    def forward(self, hv_ftr: torch.Tensor, he_ftr: torch.Tensor,
                massive: torch.Tensor, p_ftr: torch.Tensor, q_ftr: torch.Tensor, mask_matrices: MaskMatrices
                ) -> Tuple[torch.Tensor, torch.Tensor]:
        dp, dq = self.derivation(hv_ftr, he_ftr, massive, p_ftr, q_ftr, mask_matrices)
        p_ftr = p_ftr + dp * self.tau
        q_ftr = q_ftr + dq * self.tau
        return p_ftr, q_ftr


class ConfAwareFingerprintGenerator(nn.Module):
    def __init__(self, hm_dim: int, hv_dim: int, mm_dim: int, p_dim: int, q_dim: int, iteration: int,
                 use_cuda=False, dropout=0.0):
        super(ConfAwareFingerprintGenerator, self).__init__()
        self.use_cuda = use_cuda

        self.vertex2mol = nn.Linear(hv_dim, hm_dim, bias=True)
        self.vm_act = nn.LeakyReLU()
        self.readout = GlobalDynReadout(hm_dim, hv_dim, mm_dim, p_dim, q_dim, use_cuda, dropout)
        self.union = GRUUnion(hm_dim, mm_dim, use_cuda)
        self.iteration = iteration

    def forward(self, hv_ftr: torch.Tensor, p_ftr: torch.Tensor, q_ftr: torch.Tensor,
                mask_matrices: MaskMatrices
                ) -> torch.Tensor:
        # initialize molecule features with mean of vertex features
        mvw = mask_matrices.mol_vertex_w
        norm_mvw = mvw / torch.sum(mvw, dim=-1, keepdim=True)
        hm_ftr = norm_mvw @ self.vm_act(self.vertex2mol(hv_ftr))

        # iterate
        for i in range(self.iteration):
            mm_ftr = self.readout(hm_ftr, hv_ftr, p_ftr, q_ftr, mask_matrices)
            hm_ftr = self.union(hm_ftr, mm_ftr)

        return hm_ftr


class ConformationGenerator(nn.Module):
    def __init__(self, q_dim: int, h_dims: list,
                 dropout=0.0):
        super(ConformationGenerator, self).__init__()
        self.mlp = MLP(q_dim, 3, h_dims)
        self.dropout = nn.Dropout(p=dropout)

    def forward(self, q_ftr: torch.Tensor) -> torch.Tensor:
        conf3d = self.dropout(self.mlp(q_ftr))
        return conf3d
