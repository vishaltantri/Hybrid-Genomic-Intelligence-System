"""Service registry: one place that decides whether the API talks to trained models or
the deterministic fallbacks, and that caches expensive objects across requests."""
from __future__ import annotations

import threading
from typing import Optional

from ml_services.config import MODELS_DIR
from ml_services.etl.graph_store import GraphData, load_processed
from ml_services.graph_ai.gnn_diagnosis import DifferentialDiagnosisEngine
from ml_services.learning_pipeline.active_learning import ActiveLearningQueue
from ml_services.learning_pipeline.kg_update import KGUpdateManager
from ml_services.learning_pipeline.triple_extraction import TripleExtractor
from ml_services.nlp.clinical_ner import get_ner
from ml_services.nlp.hpo_mapper import HPOMapper
from ml_services.pharmacogenomics.pgx_engine import PGxEngine
from ml_services.reproductive.carrier_counselor import CarrierCounselor
from ml_services.xai.explainability import ExplainabilityLayer


class ServiceRegistry:
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._graph: Optional[GraphData] = None
        self._ner = None
        self._hpo_mapper: Optional[HPOMapper] = None
        self._diagnosis: Optional[DifferentialDiagnosisEngine] = None
        self._xai: Optional[ExplainabilityLayer] = None
        self._pgx: Optional[PGxEngine] = None
        self._counselor: Optional[CarrierCounselor] = None
        self._active_learning: Optional[ActiveLearningQueue] = None
        self._triples: Optional[TripleExtractor] = None
        self._kg_update: Optional[KGUpdateManager] = None
        self._triage = None

    # ------------------------------ graphs ------------------------------

    @property
    def graph(self) -> GraphData:
        if self._graph is None:
            with self._lock:
                if self._graph is None:
                    self._graph = load_processed()
                    if self._graph is None:
                        from ml_services.etl.graph_store import build_graph

                        self._graph = build_graph()
        return self._graph

    def reload_graph(self) -> GraphData:
        self._graph = None
        return self.graph

    # ------------------------------ models ------------------------------

    @property
    def ner(self):
        if self._ner is None:
            self._ner = get_ner()
        return self._ner

    @property
    def hpo_mapper(self) -> HPOMapper:
        if self._hpo_mapper is None:
            self._hpo_mapper = HPOMapper(self.graph)
        return self._hpo_mapper

    @property
    def diagnosis(self) -> DifferentialDiagnosisEngine:
        if self._diagnosis is None:
            self._diagnosis = DifferentialDiagnosisEngine(self.graph)
        return self._diagnosis

    @property
    def xai(self) -> ExplainabilityLayer:
        if self._xai is None:
            self._xai = ExplainabilityLayer(self.diagnosis)
        return self._xai

    @property
    def pgx(self) -> PGxEngine:
        if self._pgx is None:
            self._pgx = PGxEngine()
        return self._pgx

    @property
    def counselor(self) -> CarrierCounselor:
        if self._counselor is None:
            self._counselor = CarrierCounselor()
        return self._counselor

    @property
    def triage(self):
        if self._triage is None:
            from ml_services.asha.triage_engine import TriageEngine

            self._triage = TriageEngine(ner=self.ner, mapper=self.hpo_mapper)
        return self._triage

    # ------------------------- learning pipeline -------------------------

    @property
    def active_learning(self) -> ActiveLearningQueue:
        if self._active_learning is None:
            self._active_learning = ActiveLearningQueue()
        return self._active_learning

    @property
    def triple_extractor(self) -> TripleExtractor:
        if self._triples is None:
            self._triples = TripleExtractor()
        return self._triples

    @property
    def kg_update(self) -> KGUpdateManager:
        if self._kg_update is None:
            self._kg_update = KGUpdateManager(self.graph)
        return self._kg_update

    # ------------------------------ status ------------------------------

    def status(self) -> dict:
        graph = self.graph
        return {
            "graph_nodes": len(graph.nodes),
            "graph_edges": len(graph.edges),
            "ner_backend": type(self.ner).__name__,
            "hpo_embedding_rerank": bool(getattr(self.hpo_mapper, "_embedder", None)),
            "trained_checkpoints": {
                "clinical_ner_muril": (MODELS_DIR / "clinical_ner_muril" / "config.json").exists(),
                "gnn_han": (MODELS_DIR / "gnn_han.pt").exists(),
                "hpo_mapper": (MODELS_DIR / "hpo_mapper").exists(),
                "whisper_hi": (MODELS_DIR / "whisper-small-hi").exists(),
            },
            "modules": [f"M{i}" for i in range(1, 12)],
        }


registry = ServiceRegistry()
