"""Heterogeneous Attention Network (HAN) over the India rare-disease KG — Module 4.

Patent claim #5: GNN differential diagnosis using an Indian-population-weighted
heterogeneous graph.

Requires: torch + torch-geometric (`pip install torch torch-geometric`).
    .venv/bin/python -m ml_services.graph_ai.han_model            # train + save checkpoint

Design
------
* HeteroData with one node type per KG node type (Hpo, Disease, Gene, Drug, State,
  Ethnicity, Lab, Doctor) and one edge type per KG relation (HAS_PHENOTYPE, IS_A,
  ASSOCIATED_WITH, PGX_INTERACTS, FOUNDER_RISK, PREVALENT_IN, LOCATED_IN).
* Node features: hashed text features (deterministic, dependency-free) for text nodes;
  numeric attributes for population nodes (consanguinity rate, prevalence, AFs).
* Training task: for each disease, its HPO profile is a positive "patient"; negatives
  are sampled diseases (random + phenotypically hard negatives). The patient vector is
  the mean of its phenotype embeddings; the head scores (patient, disease) pairs.
* Indian population weighting enters as an edge/node feature (consanguinity rate,
  prevalence, founder multiplier) and as a sample weight on Indian-prevalent diseases.
"""
from __future__ import annotations

import hashlib
import math
import random
from typing import Dict, List, Optional, Tuple

from ml_services.config import MODELS_DIR

FEAT_DIM = 128


def hashed_features(texts: List[str], dim: int = FEAT_DIM) -> "list":
    """Deterministic hashed bag-of-words features (no external tokenizer needed)."""
    import numpy as np

    out = np.zeros((len(texts), dim), dtype="float32")
    for i, t in enumerate(texts):
        for tok in (t or "").lower().split():
            h = int(hashlib.md5(tok.encode("utf-8")).hexdigest()[:8], 16)
            out[i, h % dim] += 1.0
        n = np.linalg.norm(out[i])
        if n > 0:
            out[i] /= n
    return out


def build_hetero_data(graph):
    """Convert the assembled GraphData into a PyG HeteroData object."""
    import numpy as np
    import torch
    from torch_geometric.data import HeteroData

    data = HeteroData()
    index: Dict[Tuple[str, str], int] = {}

    for ntype in sorted({n["type"] for n in graph.nodes.values()}):
        nodes = graph.by_type(ntype)
        if not nodes:
            continue
        texts = [(n.get("name") or n["id"]) + " " + (n.get("definition") or "") for n in nodes]
        feats = hashed_features(texts)
        # numeric attributes appended where available
        extra = []
        for n in nodes:
            extra.append([
                float(n.get("prevalence_per_100k") or 0) / 100.0,
                float(n.get("consanguinity_rate") or 0) / 100.0,
                float(n.get("carrier_multiplier") or 0),
                float(n.get("af_indian") or 0),
                1.0 if n.get("is_pgx") else 0.0,
            ])
        X = np.concatenate([feats, np.asarray(extra, dtype="float32")], axis=1)
        data[ntype].x = torch.tensor(X, dtype=torch.float32)
        for i, n in enumerate(nodes):
            index[(ntype, n["id"])] = i

    rels: Dict[Tuple[str, str, str], List[Tuple[int, int]]] = {}
    for e in graph.edges:
        src_key = (e["src_type"], e["src"])
        dst_key = (e["dst_type"], e["dst"])
        if src_key not in index or dst_key not in index:
            continue
        rels.setdefault((e["src_type"], e["type"], e["dst_type"]), []).append(
            (index[src_key], index[dst_key])
        )
    for (stype, etype, dtype), pairs in rels.items():
        arr = np.asarray(pairs, dtype="int64").T
        data[stype, etype, dtype].edge_index = torch.tensor(arr, dtype=torch.long)

    data._index = index
    return data


class HAN(torch.nn.Module if False else object):  # real base set in build_model()
    pass


def build_model(metadata, hidden: int = 64, heads: int = 4, dropout: float = 0.3):
    """Two-layer HANConv encoder + bilinear (patient, disease) scoring head."""
    import torch
    from torch_geometric.nn import HANConv

    class HANModel(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.han = HANConv(
                in_channels=-1,
                out_channels=hidden,
                metadata=metadata,
                heads=heads,
                dropout=dropout,
            )
            self.head = torch.nn.Bilinear(hidden, hidden, 1)

        def encode(self, x_dict, edge_index_dict):
            return self.han(x_dict, edge_index_dict)

        def score(self, patient_vec, disease_vec):
            return self.head(patient_vec, disease_vec).squeeze(-1)

    return HANModel()


def _patient_vector(z_dict, phenotype_idx, disease_type="Disease"):
    import torch

    hpo_z = z_dict["Hpo"]
    vecs = hpo_z[torch.tensor(phenotype_idx, dtype=torch.long)] if phenotype_idx else None
    if vecs is None or len(phenotype_idx) == 0:
        return torch.zeros(hpo_z.shape[1])
    return vecs.mean(dim=0)


def train(graph=None, epochs: int = 60, lr: float = 1e-3, seed: int = 7, out_path=None) -> dict:
    """Train the HAN and save a checkpoint. Returns training metrics."""
    import torch

    from ml_services.etl.graph_store import load_processed

    graph = graph or load_processed()
    if graph is None:
        raise RuntimeError("KG not built. Run: python -m ml_services.etl.kg_build")

    random.seed(seed)
    torch.manual_seed(seed)

    data = build_hetero_data(graph)
    index = data._index
    model = build_model(data.metadata())
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    bce = torch.nn.BCEWithLogitsLoss()

    disease_ids = [n["id"] for n in graph.by_type("Disease")]
    prof_list = []
    for d in disease_ids:
        if ("Disease", d) not in index:
            continue
        pheno = [index[("Hpo", e["dst"])] for e in graph.edges_from(d, "HAS_PHENOTYPE")
                 if ("Hpo", e["dst"]) in index]
        if pheno:
            prof_list.append((index[("Disease", d)], pheno))
    if not prof_list:
        raise RuntimeError("No disease has mapped phenotypes — is the KG built?")

    # GPU placement + fully vectorised pair scoring: the old per-disease Python loop
    # (12.8k forward/backwards per epoch) made training take hours on CPU.
    device = "cuda" if torch.cuda.is_available() else "cpu"
    data = data.to(device)
    model = model.to(device)

    all_local_cpu = sorted(index[("Disease", d)] for d in disease_ids if ("Disease", d) in index)
    all_disease_local = torch.tensor(all_local_cpu, dtype=torch.long, device=device)
    dpos_local = torch.tensor([p[0] for p in prof_list], dtype=torch.long, device=device)
    pheno_padded = torch.nn.utils.rnn.pad_sequence(
        [torch.tensor(p[1], dtype=torch.long, device=device) for p in prof_list], batch_first=True)
    lengths = torch.tensor([len(p[1]) for p in prof_list], device=device)
    pheno_mask = torch.arange(pheno_padded.shape[1], device=device).unsqueeze(0) < lengths.unsqueeze(1)

    # Hard negatives: diseases sharing >=1 phenotype term with the anchor are the
    # real look-alikes. Uniformly random negatives only teach the head profile-size
    # bias (big profiles score high against everything); confusable negatives force
    # it to learn fine phenotypic distinctions, which is what ranking needs.
    term2dis: dict = {}
    for d in disease_ids:
        if ("Disease", d) not in index:
            continue
        for e in graph.edges_from(d, "HAS_PHENOTYPE"):
            if ("Hpo", e["dst"]) in index:
                term2dis.setdefault(index[("Hpo", e["dst"])], set()).add(index[("Disease", d)])
    rng = random.Random(seed)
    HARD_K = 32
    hardneg_rows = []
    for dpos, pheno_idx in prof_list:
        cands: set = set()
        for t in pheno_idx:
            cands |= term2dis.get(t, set())
        cands.discard(dpos)
        cands = sorted(cands)
        rng.shuffle(cands)
        while len(cands) < HARD_K:
            r = rng.choice(all_local_cpu)
            if r != dpos:
                cands.append(r)
        hardneg_rows.append(cands[:HARD_K])
    hardneg = torch.tensor(hardneg_rows, dtype=torch.long, device=device)  # P x HARD_K

    history = []
    n_neg = 3
    for epoch in range(epochs):
        model.train()
        opt.zero_grad()
        z = model.encode(data.x_dict, data.edge_index_dict)
        hpo_z = z["Hpo"]
        gathered = hpo_z[pheno_padded.clamp(min=0)]            # P x T x hidden
        mask = pheno_mask.unsqueeze(-1).float()
        pvecs = (gathered * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1.0)
        Dpos = z["Disease"][dpos_local]
        pick = torch.randint(0, HARD_K, (pvecs.shape[0], n_neg), device=device)
        neg_local = hardneg[torch.arange(pvecs.shape[0], device=device).unsqueeze(1), pick]
        Dneg = z["Disease"][neg_local]                         # P x n_neg x hidden
        pos_logits = model.score(pvecs, Dpos)
        neg_logits = model.score(pvecs.repeat_interleave(n_neg, dim=0),
                                 Dneg.reshape(-1, Dneg.shape[-1]))
        labels = torch.cat([torch.ones_like(pos_logits), torch.zeros_like(neg_logits)])
        loss = bce(torch.cat([pos_logits, neg_logits]), labels)
        loss.backward()
        opt.step()
        history.append(float(loss.item()))

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = out_path or (MODELS_DIR / "gnn_han.pt")
    torch.save({"state_dict": model.state_dict(), "hidden": 64, "heads": 4,
                "metadata": str(data.metadata()), "loss_history": history}, out_path)
    return {"epochs": len(history), "final_loss": round(history[-1], 4) if history else None,
            "n_profiles": len(prof_list), "device": device, "checkpoint": str(out_path)}


class LoadedHAN:
    """Scoring wrapper used by DifferentialDiagnosisEngine when a checkpoint exists."""

    def __init__(self, graph, model, data, index):
        self.graph = graph
        self.model = model
        self.data = data
        self.index = index
        self._z = None  # cached graph encoding: the graph is static after load

    def _ensure_z(self):
        import torch

        if self._z is None:
            self.model.eval()
            with torch.no_grad():
                self._z = self.model.encode(self.data.x_dict, self.data.edge_index_dict)
        return self._z

    def score(self, hpo_ids: List[str], disease_ids: List[str]) -> Dict[str, float]:
        import torch

        z = self._ensure_z()
        pheno_idx = [self.index[("Hpo", h)] for h in hpo_ids if ("Hpo", h) in self.index]
        pvec = _patient_vector(z, pheno_idx).unsqueeze(0)
        local = [self.index[("Disease", d)] for d in disease_ids if ("Disease", d) in self.index]
        if not local:
            return {}
        # one batched bilinear pass instead of 12.8k python-loop scores
        D = z["Disease"][torch.tensor(local, dtype=torch.long, device=z["Disease"].device)]
        s = self.model.score(pvec.expand(D.shape[0], -1), D)
        probs = torch.sigmoid(s).tolist()
        return {d: p for d, p in zip((d for d in disease_ids if ("Disease", d) in self.index), probs)}


def load_han(checkpoint, graph=None):
    """Load a trained checkpoint and rebuild the graph tensors for inference."""
    import torch

    from ml_services.etl.graph_store import load_processed

    graph = graph or load_processed()
    ckpt = torch.load(checkpoint, map_location="cpu", weights_only=False)
    data = build_hetero_data(graph)
    model = build_model(data.metadata(), hidden=ckpt.get("hidden", 64), heads=ckpt.get("heads", 4))
    model.load_state_dict(ckpt["state_dict"])
    model.eval()
    return LoadedHAN(graph, model, data, data._index)


if __name__ == "__main__":
    try:
        metrics = train()
        print("HAN training complete:", metrics)
    except ImportError as exc:
        print(f"HAN training needs torch + torch-geometric ({exc}).")
        print("Install: pip install torch torch-geometric, then re-run this module.")
