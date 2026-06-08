"""Observation: the unit of Pass 1 output.

Each extractor emits Observations into a shared list. Pass 3 (resolution) reads
observations and writes entities.json + edges.json.

Observation shape mirrors `artifacts/schema.json`'s Observation $def. Observations
NEVER directly become entities or edges; the resolution pass does that, possibly
merging, rejecting, or promoting evidence_kind.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


@dataclass
class ProvenanceItem:
    source_path: str
    start_line: int
    end_line: int
    source_file_id: str
    source_hash: str
    snippet: str | None = None
    role: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = {
            "source_path": self.source_path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "source_file_id": self.source_file_id,
            "source_hash": self.source_hash,
        }
        if self.snippet is not None:
            d["snippet"] = self.snippet
        if self.role is not None:
            d["role"] = self.role
        return d


@dataclass
class Observation:
    """An evidence claim emitted by a Pass 1 rule.

    `kind` ∈ {entity_candidate, edge_candidate, property_observation,
              unresolved_reference, anomaly}.
    `data` is rule-specific payload (entity_type+name+id_candidate for entity
    candidates, edge_type+from+to_candidate for edge candidates, etc.).
    """
    id: str
    kind: str
    evidence_kind: str
    rule_id: str
    provenance: list[ProvenanceItem]
    data: dict[str, Any] = field(default_factory=dict)
    prompt_template_id: str | None = None
    category: str | None = None
    uncertainty_rationale: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = {
            "id": self.id,
            "kind": self.kind,
            "evidence_kind": self.evidence_kind,
            "rule_id": self.rule_id,
            "provenance": [p.to_dict() for p in self.provenance],
        }
        if self.data:
            d["data"] = self.data
        if self.prompt_template_id is not None:
            d["prompt_template_id"] = self.prompt_template_id
        if self.category is not None:
            d["category"] = self.category
        if self.uncertainty_rationale is not None:
            d["uncertainty_rationale"] = self.uncertainty_rationale
        return d


@dataclass
class SourceFileRecord:
    id: str
    path: str
    source_hash: str
    normalized_source_hash: str
    encoding: str
    language: str
    parse_status: str = "ok"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ObservationSink:
    """Accumulates observations across all per-file extractor runs.

    Maintains a stable counter for observation IDs and the source-file table.
    Single-threaded.
    """

    def __init__(self):
        self._counter = 0
        self.observations: list[Observation] = []
        self.source_files: dict[str, SourceFileRecord] = {}

    def next_id(self) -> str:
        self._counter += 1
        return f"obs-{self._counter:06d}"

    def add(self, obs: Observation) -> None:
        self.observations.append(obs)

    def register_source_file(self, sfr: SourceFileRecord) -> None:
        self.source_files[sfr.id] = sfr

    def relativize_paths(self, repo_root: Path) -> None:
        """Rewrite every emitted `source_path` to be repo-root-relative, at generation
        time, so no absolute build path (which contains the OS username) ever leaks into
        the artifacts. Single chokepoint over the whole sink — every ProvenanceItem and
        the source-file table, regardless of which extractor produced them (including any
        future extractor). Called by the generation drivers before serialization; the
        resolution pass then carries the already-relative provenance into entities/edges.
        Paths already relative, or genuinely outside the repo, are left unchanged."""
        root = str(repo_root.resolve()).rstrip("/")

        def _rel(p: str) -> str:
            if not p or not p.startswith("/"):
                return p  # already relative
            try:
                return str(Path(p).resolve().relative_to(root))
            except ValueError:
                # fall back to a literal prefix strip (handles symlink/realpath drift)
                return p[len(root) + 1:] if p.startswith(root + "/") else p

        for sfr in self.source_files.values():
            sfr.path = _rel(sfr.path)
        for obs in self.observations:
            for prov in obs.provenance:
                prov.source_path = _rel(prov.source_path)

    def to_artifact(
        self, *,
        schema_version: str,
        extractor_version: str,
        run_id: str,
        corpus_hash: str,
    ) -> dict[str, Any]:
        return {
            "schema_version": schema_version,
            "extractor_version": extractor_version,
            "run_id": run_id,
            "corpus_hash": corpus_hash,
            "source_files": [sf.to_dict() for sf in self.source_files.values()],
            "observations": [o.to_dict() for o in self.observations],
        }
