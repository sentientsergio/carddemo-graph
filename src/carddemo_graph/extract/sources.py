"""Read source files into a normalized form for per-language extractors.

Responsibilities:
- compute source_hash + normalized_source_hash
- detect language from extension + path
- expose a uniform `SourceFile(path, lines, language, source_file_id)` view
- treat columns 73-80 (COBOL identification area) as ignorable for COBOL/copybook
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from carddemo_graph.extract.observation import SourceFileRecord


COBOL_EXTS = {".cbl", ".CBL", ".cpy", ".CPY"}
JCL_EXTS = {".jcl", ".JCL"}
PROC_EXTS = {".prc", ".proc", ".PRC"}
BMS_EXTS = {".bms"}
CSD_EXTS = {".csd", ".CSD"}
ASM_EXTS = {".asm"}
MAC_EXTS = {".mac"}
CTL_EXTS = {".ctl"}


def detect_language(path: Path) -> str:
    suf = path.suffix
    if suf in COBOL_EXTS:
        return "COBOL"
    if suf in JCL_EXTS:
        return "JCL"
    if suf in PROC_EXTS:
        return "JCL_PROC"
    if suf in BMS_EXTS:
        return "BMS"
    if suf in CSD_EXTS:
        return "CSD"
    if suf in ASM_EXTS:
        return "ASSEMBLER"
    if suf in MAC_EXTS:
        return "ASSEMBLER_MACRO"
    if suf in CTL_EXTS:
        return "IDCAMS_CTL"
    return "TEXT"


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class SourceFile:
    path: Path
    text: str
    lines: list[str]                # 1-indexed lookup: lines[i-1] is line i
    language: str
    record: SourceFileRecord

    @property
    def id(self) -> str:
        return self.record.id

    def line(self, n: int) -> str:
        """Return the 1-indexed line, or '' if out of range."""
        if 1 <= n <= len(self.lines):
            return self.lines[n - 1]
        return ""


def read_source_file(path: Path, sfid: str) -> SourceFile:
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    language = detect_language(path)
    src_hash = hash_text(text)
    # Normalized hash strips columns 73+ for COBOL fixed-format (the strip pipeline
    # preserves them byte-for-byte; for content hashing we normalize them away).
    norm_text = _normalize_for_hash(text, language)
    norm_hash = hash_text(norm_text)
    record = SourceFileRecord(
        id=sfid,
        path=str(path),
        source_hash=src_hash,
        normalized_source_hash=norm_hash,
        encoding="utf-8",
        language=language,
        parse_status="ok",
    )
    return SourceFile(path=path, text=text, lines=lines,
                      language=language, record=record)


def _normalize_for_hash(text: str, language: str) -> str:
    if language not in ("COBOL",):
        return text
    out = []
    for ln in text.splitlines():
        if len(ln) > 72:
            out.append(ln[:72].rstrip())
        else:
            out.append(ln.rstrip())
    return "\n".join(out)


def strip_cobol_columns(line: str) -> str:
    """Strip column 73+ from a COBOL line; return the columns-1..72 view."""
    if len(line) > 72:
        return line[:72]
    return line


def cobol_code_text(line: str) -> str:
    """For COBOL lines: return cols 8..72 (the code area), stripped of trailing
    whitespace. Cols 1-6 are sequence; col 7 is the indicator (stripped already);
    col 73+ is identification."""
    code = strip_cobol_columns(line)
    if len(code) >= 7:
        return code[7:].rstrip()
    return code.rstrip()
