"""Module 8 endpoints: federated simulation, privacy accounting, epidemiology byproduct."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from backend.app.security import require
from ml_services.federated import dp as dp_mod
from ml_services.federated.fl_server import FederatedSimulator, run_with_flower
from ml_services.federated.noniid_partition import ARCHETYPES, dirichlet_label_matrix

router = APIRouter(prefix="/api/v1/federated", tags=["federated"])


@router.get("/archetypes")
def archetypes(user: dict = Depends(require("federated:read"))):
    """Hospital archetypes used for non-IID simulation (tribal vs metro case mixes)."""
    return {"archetypes": ARCHETYPES}


@router.post("/simulate")
def simulate(rounds: int = Query(default=8, ge=1, le=50),
             n_clients: int = Query(default=6, ge=2, le=20),
             algorithm: str = Query(default="fedprox", pattern="^(fedavg|fedprox)$"),
             partition: str = Query(default="archetype", pattern="^(archetype|disease)$"),
             alpha: float = Query(default=0.5, gt=0, le=10),
             sigma: float = Query(default=0.0, ge=0, le=10),
             secure_aggregation: bool = Query(default=False),
             user: dict = Depends(require("federated:read"))):
    """Run federated training across simulated hospitals; returns the accuracy curve."""
    sim = FederatedSimulator(n_clients=n_clients, partition=partition, alpha=alpha)
    result = sim.train(rounds=rounds, algorithm=algorithm, sigma=sigma, secure_agg=secure_aggregation)
    result["partition_report"] = sim.dataset_report()
    result["epidemiology_map"] = sim.epidemiology_map()
    result["privacy_utility_table"] = dp_mod.privacy_utility_curve([0.4, 0.7, 1.1, 1.6, 2.5])
    result["flower"] = run_with_flower()
    return result


@router.get("/epi-map")
def epidemiology_map(n_clients: int = Query(default=6, ge=2, le=20),
                     partition: str = Query(default="archetype", pattern="^(archetype|disease)$"),
                     user: dict = Depends(require("federated:read"))):
    """Privacy-preserving national map built only from aggregated per-hospital counts."""
    sim = FederatedSimulator(n_clients=n_clients, partition=partition)
    return sim.epidemiology_map()


@router.get("/privacy-curve")
def privacy_curve(user: dict = Depends(require("federated:read"))):
    return {"points": dp_mod.privacy_utility_curve([0.3, 0.4, 0.7, 1.1, 1.6, 2.5, 4.0]),
            "note": "Utility retained is a monotone heuristic; the simulator measures real accuracy "
                    "at each sigma."}
