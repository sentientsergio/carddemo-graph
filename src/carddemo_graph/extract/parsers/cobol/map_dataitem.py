"""Map seam (COBOL data layer) — MAPA parse tree → DataItem Observations.

Walks MAPA's `dataDescriptionEntryFormat1` nodes and emits the **existing, unchanged**
RUL-COBOL-021 Observation contract: a DataItem entity_candidate per entry + the
parent/child hierarchy (HAS_FIELD for a record root, CONTAINS_ITEM for a child),
identical in shape to `extract/cobol.py::_scan_data_items`.

The mapping is generic over the COBOL grammar (level / dataName / dataPictureClause /
dataUsageClause / dataOccursClause / dataRedefinesClause) — there is NO CardDemo-specific
handling here. `_suggested_sql_type` is **reused unchanged** from the regex extractor
(PIC→SQL is semantic mapping, not parsing). Reusing it (not reimplementing) is what keeps
the downstream type contract provably identical across the parser swap.
"""

from __future__ import annotations

from carddemo_graph.extract.observation import (
    Observation, ObservationSink, ProvenanceItem,
)
# Reused UNCHANGED — the PIC+USAGE → advisory SQL type table is semantic, not parsing.
from carddemo_graph.extract.cobol import _suggested_sql_type, _normalize_usage

from .normalize import OriginMap


# --- generic parse-tree helpers (rule names are COBOL-grammar, not corpus) ---

def _find_all(node, rule: str, out: list) -> None:
    if isinstance(node, dict):
        if node.get("r") == rule:
            out.append(node)
        for c in node.get("k", []):
            _find_all(c, rule, out)


def _child_rule_nodes(node: dict, rule: str) -> list:
    return [c for c in node.get("k", [])
            if isinstance(c, dict) and c.get("r") == rule]


def _flat(node) -> list[str]:
    if isinstance(node, str):
        return [node]
    out: list[str] = []
    for c in node.get("k", []):
        out += _flat(c)
    return out


def _level_of(item: dict) -> int | None:
    for c in item.get("k", []):
        if isinstance(c, str) and c.strip().isdigit():
            return int(c.strip())
    return None


def _name_of(item: dict) -> str:
    names = _child_rule_nodes(item, "dataName")
    if names:
        return "".join(_flat(names[0])).upper()
    for c in item.get("k", []):
        if isinstance(c, str) and c.strip().upper() == "FILLER":
            return "FILLER"
    return "FILLER"  # an unnamed elementary entry is FILLER padding


def _picture_of(item: dict) -> str | None:
    pcs = _child_rule_nodes(item, "dataPictureClause")
    if not pcs:
        return None
    # Keep every non-blank token: the dataPictureClause never contains the entry
    # terminator (that '. ' is a sibling of the entry), so any '.' here is the
    # picture's own edited decimal point (e.g. -ZZZ,ZZZ,ZZZ.ZZ). Dropping it would
    # corrupt the implied-decimal count.
    toks = [t for t in _flat(pcs[0]) if t.strip()]
    while toks and toks[0].upper() in ("PIC", "PICTURE", "IS"):
        toks.pop(0)
    return "".join(toks) or None


def _usage_of(item: dict) -> str | None:
    ucs = _child_rule_nodes(item, "dataUsageClause")
    if not ucs:
        return None
    txt = "".join(_flat(ucs[0])).upper()
    # longest-match first so COMPUTATIONAL-3 isn't shadowed by COMP
    for u in ("COMPUTATIONAL-3", "PACKED-DECIMAL", "COMPUTATIONAL-4",
              "COMPUTATIONAL-5", "COMP-3", "COMP-4", "COMP-5", "COMPUTATIONAL",
              "COMP", "BINARY", "DISPLAY"):
        if u in txt:
            return _normalize_usage(u)
    return None


def _occurs_of(item: dict) -> int | None:
    ocs = _child_rule_nodes(item, "dataOccursClause")
    if not ocs:
        return None
    for t in _flat(ocs[0]):
        if t.strip().isdigit():
            return int(t.strip())
    return None


def _redefines_of(item: dict) -> str | None:
    rcs = _child_rule_nodes(item, "dataRedefinesClause")
    if not rcs:
        return None
    toks = [t.strip() for t in _flat(rcs[0]) if t.strip()]
    # form: REDEFINES <target>
    for i, t in enumerate(toks):
        if t.upper() == "REDEFINES" and i + 1 < len(toks):
            return toks[i + 1].upper()
    return None


def emit_data_items(
    *,
    tree: dict,
    copybook_stem: str,
    lines: list[str],
    origin: OriginMap,
    source_file_id: str,
    source_hash: str,
    sink: ObservationSink,
) -> None:
    """Emit RUL-COBOL-021 DataItem entity_candidates + hierarchy edges from `tree`.

    Mirrors `cobol.py::_scan_data_items`: level-number stack for parent/child, FILLER
    sequencing, group-vs-elementary, suggested_sql_type from the *raw* usage (the
    DISPLAY default is stored on the entity but not fed to the type rule). Provenance
    lines are mapped through `origin` (identity for a standalone copybook).
    """
    cb = copybook_stem.upper()
    cb_id = f"copybook:{cb}"
    source_path = origin.source_path

    items: list[dict] = []
    _find_all(tree, "dataDescriptionEntryFormat1", items)

    stack: list[tuple[int, str]] = []  # (level, dataitem_id) ancestor chain
    filler_seq = 0

    for it in items:
        level = _level_of(it)
        if level is None or level == 88:
            continue  # 88-level condition names: KU9 stretch seam, not core
        name = _name_of(it)
        while stack and stack[-1][0] >= level:
            stack.pop()
        parent_id = stack[-1][1] if stack else None
        if name == "FILLER":
            filler_seq += 1
            item_id = f"dataitem:{cb}/FILLER#{filler_seq}"
        else:
            item_id = f"dataitem:{cb}/{name}"

        pic = _picture_of(it)
        usage = _usage_of(it)
        occurs = _occurs_of(it)
        redefines = _redefines_of(it)
        is_group = pic is None

        data = {
            "entity_type": "DataItem",
            "name": name,
            "id_candidate": item_id,
            "level": level,
            "picture": pic,
            "usage": usage or (None if is_group else "DISPLAY"),
            "occurs": occurs,
            "redefines": redefines,
            "is_filler": name == "FILLER",
            "is_group": is_group,
            "suggested_sql_type": None if is_group else _suggested_sql_type(pic, usage),
            "parent_item": parent_id,
            "copybook_id": cb_id,
        }

        start_p = int(it.get("ln", 0))
        end_p = int(it.get("le", start_p))
        start_line = origin.source_line(start_p) or start_p
        end_line = origin.source_line(end_p) or start_line

        _emit(sink, kind="entity_candidate", rule_id="RUL-COBOL-021", data=data,
              source_path=source_path, lines=lines,
              start_line=start_line, end_line=end_line,
              source_file_id=source_file_id, source_hash=source_hash,
              role="declaration")
        if parent_id is None:
            edge = {"edge_type": "HAS_FIELD", "from": cb_id, "to_candidate": item_id}
        else:
            edge = {"edge_type": "CONTAINS_ITEM", "from": parent_id,
                    "to_candidate": item_id}
        _emit(sink, kind="edge_candidate", rule_id="RUL-COBOL-021", data=edge,
              source_path=source_path, lines=lines,
              start_line=start_line, end_line=end_line,
              source_file_id=source_file_id, source_hash=source_hash,
              role="use-site")
        stack.append((level, item_id))


def _emit(sink: ObservationSink, *, kind: str, rule_id: str, data: dict,
          source_path: str, lines: list[str], start_line: int, end_line: int,
          source_file_id: str, source_hash: str, role: str) -> None:
    snippet = "\n".join(lines[start_line - 1:end_line])
    prov = [ProvenanceItem(
        source_path=source_path,
        start_line=start_line,
        end_line=end_line,
        snippet=snippet,
        role=role,
        source_file_id=source_file_id,
        source_hash=source_hash,
    )]
    sink.add(Observation(
        id=sink.next_id(),
        kind=kind,
        evidence_kind="deterministic",
        rule_id=rule_id,
        provenance=prov,
        data=data,
    ))
