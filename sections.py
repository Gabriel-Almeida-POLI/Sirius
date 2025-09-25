"""Module for locating consolidated financial statement sections in PDFs."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

import fitz  # PyMuPDF


@dataclass
class SectionMatch:
    key: str
    start_page: int
    end_page: Optional[int] = None

    def to_dict(self) -> Dict[str, int]:
        end_page = self.end_page if self.end_page is not None else self.start_page
        return {"key": self.key, "start_page": self.start_page, "end_page": end_page}


PATTERN_MAP: Dict[str, List[str]] = {
    "BPA": [r"DFs\s+Consolidadas\s*/\s*Balanço\s+Patrimonial\s+Ativo"],
    "BPP": [r"DFs\s+Consolidadas\s*/\s*Balanço\s+Patrimonial\s+Passivo"],
    "DRE": [r"DFs\s+Consolidadas\s*/\s*Demonstração\s+do\s+Resultado(?!\s+Abrangente)"],
    "DRA": [r"DFs\s+Consolidadas\s*/\s*Demonstração\s+do\s+Resultado\s+Abrangente"],
    "DFC": [r"DFs\s+Consolidadas\s*/\s*Demonstração\s+do\s+Fluxo\s+de\s+Caixa"],
    "DMPL": [
        r"DFs\s+Consolidadas\s*/\s*Demonstraç(?:ão|ões)\s+das\s+Mutações\s+do\s+Patrimônio\s+Líquido",
        r"DFs\s+Consolidadas\s*/\s*DMPL",
    ],
    "DVA": [r"DFs\s+Consolidadas\s*/\s*Demonstração\s+de\s+Valor\s+Adicionado"],
}


def _first_pattern_match(text: str, patterns: Iterable[str]) -> bool:
    for pattern in patterns:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return True
    return False


def _scan_document(doc: fitz.Document, *, max_pages: int) -> Dict[str, Dict[str, int]]:
    total_pages = doc.page_count
    search_limit = min(max_pages, total_pages)
    matches: Dict[str, SectionMatch] = {}

    for page_index in range(search_limit):
        page = doc.load_page(page_index)
        text = page.get_text("text")

        for key, patterns in PATTERN_MAP.items():
            if key in matches:
                continue
            if _first_pattern_match(text, patterns):
                matches[key] = SectionMatch(key=key, start_page=page_index + 1)

    if not matches:
        return {}

    ordered = sorted(matches.values(), key=lambda item: item.start_page)
    for current, nxt in zip(ordered, ordered[1:]):
        current.end_page = max(current.start_page, nxt.start_page - 1)

    ordered[-1].end_page = total_pages

    return {match.key: match.to_dict() for match in ordered}


def find_consolidated_spans_from_bytes(
    pdf_bytes: bytes, *, max_pages: int = 40
) -> Dict[str, Dict[str, int]]:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        return _scan_document(doc, max_pages=max_pages)
    finally:
        doc.close()


def find_consolidated_spans(pdf_path: str, *, max_pages: int = 40) -> Dict[str, Dict[str, int]]:
    with open(pdf_path, "rb") as pdf_file:
        pdf_bytes = pdf_file.read()
    return find_consolidated_spans_from_bytes(pdf_bytes, max_pages=max_pages)
