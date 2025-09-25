"""Extract tables from consolidated statement sections using pdfplumber."""
from __future__ import annotations

import io
import json
import re
import zipfile
import importlib
import tempfile
from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Optional, Sequence, Tuple

import pandas as pd
import pdfplumber

from sections import find_consolidated_spans_from_bytes


GRID_TABLE_SETTINGS = {
    "vertical_strategy": "lines",
    "horizontal_strategy": "lines",
    "keep_blank_chars": False,
}

TEXT_TABLE_SETTINGS = {
    "vertical_strategy": "text",
    "horizontal_strategy": "text",
    "intersection_tolerance": 5,
    "snap_tolerance": 3,
    "join_tolerance": 3,
    "edge_min_length": 3,
}


_EXPECTED_NUMERIC_SECTIONS = {
    "BPA",
    "BPP",
    "DRE",
    "DRA",
    "DFC",
    "DMPL",
    "DVA",
}


@dataclass
class ColumnSummary:
    name: int
    non_empty: int
    numeric_count: int
    string_count: int
    majority: str


@dataclass
class NormalizationSummary:
    column_majority: List[str]
    numeric_columns: List[int]
    first_column_string_ratio: Optional[float]


@dataclass
class TableAnalysis:
    row_count: int = 0
    column_count: int = 0
    empty_cell_ratio: Optional[float] = None
    first_column_string_ratio: Optional[float] = None
    numeric_columns: int = 0
    column_majority: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class TableRecord:
    page: int
    raw_table_index: int
    table_index: Optional[int]
    row_count: int
    column_count: int
    numeric_columns: int
    empty_cell_ratio: Optional[float]
    first_column_string_ratio: Optional[float]
    column_majority: List[str]
    warnings: List[str]
    original_columns: List[str] = field(default_factory=list)
    normalized_columns: List[str] = field(default_factory=list)
    stitched_from: List[int] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {
            "page": self.page,
            "raw_table_index": self.raw_table_index,
            "table_index": self.table_index,
            "row_count": self.row_count,
            "column_count": self.column_count,
            "numeric_columns": self.numeric_columns,
            "empty_cell_ratio": self.empty_cell_ratio,
            "first_column_string_ratio": self.first_column_string_ratio,
            "column_majority": list(self.column_majority),
            "warnings": list(self.warnings),
            "original_columns": list(self.original_columns),
            "normalized_columns": list(self.normalized_columns),
            "stitched_from": list(self.stitched_from),
        }


@dataclass
class ExtractedTable:
    dataframe: pd.DataFrame
    record: TableRecord


@dataclass
class SectionExtraction:
    key: str
    pages: Tuple[int, int]
    tables: List[ExtractedTable] = field(default_factory=list)
    table_details: List[TableRecord] = field(default_factory=list)
    alerts: List[TableRecord] = field(default_factory=list)
    engine_used: str = "pdfplumber"
    stitched: bool = False
    schema_normalized: bool = False


@dataclass
class ExtractionResult:
    pdf_label: str
    spans: Dict[str, Dict[str, int]]
    sections: Dict[str, SectionExtraction] = field(default_factory=dict)
    alerts: List[TableRecord] = field(default_factory=list)
    report: Dict[str, object] = field(default_factory=dict)

    @property
    def tables(self) -> Dict[str, List[pd.DataFrame]]:
        return {
            key: [table.dataframe for table in section.tables]
            for key, section in self.sections.items()
            if section.tables
        }


def extract_consolidated_from_bytes(
    pdf_bytes: bytes,
    *,
    pdf_label: Optional[str] = None,
    sections: Optional[Dict[str, Dict[str, int]]] = None,
    max_pages: int = 40,
    engine: str = "auto",
    stitch_tables: bool = True,
    normalize_schema: bool = True,
) -> ExtractionResult:
    """Extract consolidated tables and metadata directly from PDF bytes."""

    if not pdf_bytes:
        return ExtractionResult(
            pdf_label=pdf_label or "document",
            spans={},
            sections={},
            alerts=[],
            report={"pdf_label": pdf_label or "document", "sections": {}, "alerts": []},
        )

    if sections is None:
        sections = find_consolidated_spans_from_bytes(pdf_bytes, max_pages=max_pages)

    pdf_label = pdf_label or "document"
    spans = dict(sections)
    requested_engine = (engine or "auto").lower()
    if requested_engine not in {"auto", "pdfplumber", "camelot"}:
        raise ValueError(f"Motor de extração não suportado: {engine}")

    camelot_mod = None
    if requested_engine in {"auto", "camelot"}:
        camelot_mod = _load_camelot_module()
        if requested_engine == "camelot" and camelot_mod is None:
            raise RuntimeError(
                "O motor Camelot foi solicitado, mas o pacote 'camelot' não está disponível."
            )

    report_data: Dict[str, object] = {
        "pdf_label": pdf_label,
        "sections": {},
        "alerts": [],
        "options": {
            "engine": requested_engine,
            "stitch_tables": bool(stitch_tables),
            "normalize_schema": bool(normalize_schema),
            "max_pages": max_pages,
        },
    }

    if not spans:
        return ExtractionResult(
            pdf_label=pdf_label,
            spans={},
            sections={},
            alerts=[],
            report=report_data,
        )

    sections_result: Dict[str, SectionExtraction] = {}
    global_alerts: List[TableRecord] = []

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        total_pages = len(pdf.pages)

        for section_key, meta in spans.items():
            start_page = max(1, meta.get("start_page", 1))
            end_page = meta.get("end_page") or start_page
            end_page = min(end_page, total_pages)

            if start_page > end_page:
                continue

            section_tables: List[ExtractedTable] = []
            discarded_records: List[TableRecord] = []

            pdfplumber_tables = list(
                _iter_pdfplumber_tables(pdf, start_page, end_page, total_pages)
            )
            table_sources: List[Tuple[int, Sequence[Sequence[Optional[str]]]]] = (
                pdfplumber_tables
            )
            effective_engine = "pdfplumber"

            if requested_engine == "camelot":
                table_sources = _iter_camelot_tables(
                    pdf_bytes, start_page, end_page, camelot_mod
                )
                effective_engine = "camelot"
            elif requested_engine == "auto":
                if pdfplumber_tables:
                    table_sources = pdfplumber_tables
                    effective_engine = "pdfplumber"
                else:
                    camelot_tables = _iter_camelot_tables(
                        pdf_bytes, start_page, end_page, camelot_mod
                    )
                    if camelot_tables:
                        table_sources = camelot_tables
                        effective_engine = "camelot"
            else:  # pdfplumber
                table_sources = pdfplumber_tables

            table_index = 1
            raw_table_index = 0

            for page_number, table in table_sources:
                raw_table_index += 1
                dataframe, analysis = _table_to_dataframe(table)
                warnings = list(analysis.warnings)

                record = TableRecord(
                    page=page_number,
                    raw_table_index=raw_table_index,
                    table_index=None,
                    row_count=analysis.row_count,
                    column_count=analysis.column_count,
                    numeric_columns=analysis.numeric_columns,
                    empty_cell_ratio=analysis.empty_cell_ratio,
                    first_column_string_ratio=analysis.first_column_string_ratio,
                    column_majority=analysis.column_majority,
                    warnings=warnings,
                )

                if dataframe is None or dataframe.empty:
                    if not warnings:
                        record.warnings.append(
                            "Tabela descartada por ficar vazia após limpeza."
                        )
                    discarded_records.append(record)
                    continue

                if (
                    section_key in _EXPECTED_NUMERIC_SECTIONS
                    and analysis.numeric_columns < 2
                ):
                    record.warnings.append(
                        "Menos de 2 colunas predominantemente numéricas identificadas."
                    )

                record.original_columns = [str(column) for column in dataframe.columns]
                record.normalized_columns = list(record.original_columns)

                if normalize_schema:
                    dataframe, normalized_columns, header_dropped = (
                        _apply_schema_normalization(section_key, dataframe)
                    )
                    if normalized_columns:
                        record.normalized_columns = normalized_columns
                    if header_dropped:
                        record.row_count = max(0, record.row_count - 1)
                    record.column_count = dataframe.shape[1]

                record.table_index = table_index
                section_tables.append(ExtractedTable(dataframe=dataframe, record=record))
                table_index += 1

            stitched_applied = False
            if stitch_tables and section_tables:
                section_tables, stitched_applied = _stitch_section_tables(section_tables)

            for idx, table in enumerate(section_tables, start=1):
                table.record.table_index = idx

            table_details: List[TableRecord] = [
                table.record for table in section_tables
            ] + discarded_records

            section_alerts = [
                table.record for table in section_tables if table.record.warnings
            ] + [record for record in discarded_records if record.warnings]
            global_alerts.extend(section_alerts)

            if section_tables or discarded_records:
                section_meta = SectionExtraction(
                    key=section_key,
                    pages=(start_page, end_page),
                    tables=section_tables,
                    table_details=table_details,
                    alerts=section_alerts,
                    engine_used=effective_engine,
                    stitched=stitched_applied,
                    schema_normalized=normalize_schema,
                )
                sections_result[section_key] = section_meta

                report_data["sections"][section_key] = {
                    "pages": [start_page, end_page],
                    "table_count": len(section_tables),
                    "table_details": [record.to_dict() for record in table_details],
                    "alerts": [record.to_dict() for record in section_alerts],
                    "engine": effective_engine,
                    "stitched": stitched_applied,
                    "schema_normalized": bool(normalize_schema),
                }

    report_data["alerts"] = [record.to_dict() for record in global_alerts]

    return ExtractionResult(
        pdf_label=pdf_label,
        spans=spans,
        sections=sections_result,
        alerts=global_alerts,
        report=report_data,
    )


def build_csv_exports(
    result: ExtractionResult,
    *,
    encoding: str = "utf-8",
    include_report: bool = True,
) -> Dict[str, bytes]:
    """Serialize extracted tables and metadata to in-memory CSV files."""

    exports: Dict[str, bytes] = {}
    slug = _slugify(result.pdf_label)

    for key, section in result.sections.items():
        start_page, end_page = section.pages
        for table in section.tables:
            if table.record.table_index is None:
                continue
            filename = (
                f"{slug}__{key}__p{start_page}-{end_page}__t{table.record.table_index}.csv"
            )
            buffer = io.StringIO()
            table.dataframe.to_csv(buffer, index=False)
            exports[filename] = buffer.getvalue().encode(encoding)

    if include_report:
        report_name = f"{slug}__report.json"
        exports[report_name] = json.dumps(
            result.report, indent=2, ensure_ascii=False
        ).encode("utf-8")

    return exports


def build_parquet_exports(
    result: ExtractionResult,
    *,
    compression: Optional[str] = "snappy",
    engine: Optional[str] = None,
    include_report: bool = True,
) -> Dict[str, bytes]:
    """Serialize extracted tables and metadata to in-memory Parquet files."""

    exports: Dict[str, bytes] = {}
    slug = _slugify(result.pdf_label)

    for key, section in result.sections.items():
        start_page, end_page = section.pages
        for table in section.tables:
            if table.record.table_index is None:
                continue
            filename = (
                f"{slug}__{key}__p{start_page}-{end_page}__t{table.record.table_index}.parquet"
            )
            buffer = io.BytesIO()
            table.dataframe.to_parquet(
                buffer, index=False, compression=compression, engine=engine
            )
            exports[filename] = buffer.getvalue()

    if include_report:
        report_name = f"{slug}__report.json"
        exports[report_name] = json.dumps(
            result.report, indent=2, ensure_ascii=False
        ).encode("utf-8")

    return exports


def package_exports_as_zip(
    exports: Dict[str, bytes], *, compression: int = zipfile.ZIP_DEFLATED
) -> bytes:
    """Pack in-memory exports into a ZIP archive and return the bytes."""

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=compression) as archive:
        for name, data in exports.items():
            archive.writestr(name, data)
    buffer.seek(0)
    return buffer.read()


def _load_camelot_module():
    try:
        return importlib.import_module("camelot")
    except Exception:
        return None


def _iter_pdfplumber_tables(
    pdf: pdfplumber.PDF, start_page: int, end_page: int, total_pages: int
) -> Iterator[Tuple[int, Sequence[Sequence[Optional[str]]]]]:
    for page_number in range(start_page, end_page + 1):
        if page_number > total_pages:
            break
        page = pdf.pages[page_number - 1]
        tables = _extract_tables_from_page(page)
        for table in tables:
            yield page_number, table


def _iter_camelot_tables(
    pdf_bytes: bytes,
    start_page: int,
    end_page: int,
    camelot_module,
) -> List[Tuple[int, Sequence[Sequence[Optional[str]]]]]:
    if camelot_module is None:
        return []

    page_spec = f"{start_page}-{end_page}" if start_page != end_page else str(start_page)

    with tempfile.NamedTemporaryFile(suffix=".pdf") as temp_file:
        temp_file.write(pdf_bytes)
        temp_file.flush()

        tables = []
        try:
            tables = camelot_module.read_pdf(
                temp_file.name, pages=page_spec, flavor="lattice"
            )
        except Exception:
            tables = []

        if not tables:
            try:
                tables = camelot_module.read_pdf(
                    temp_file.name, pages=page_spec, flavor="stream"
                )
            except Exception:
                tables = []

        results: List[Tuple[int, Sequence[Sequence[Optional[str]]]]] = []
        for table in tables or []:
            page_attr = getattr(table, "page", start_page)
            try:
                page_number = int(page_attr)
            except (TypeError, ValueError):
                page_number = start_page

            try:
                df = table.df
            except AttributeError:
                data = getattr(table, "data", None)
                if data is None:
                    continue
                rows = [[cell for cell in row] for row in data]
                results.append((page_number, rows))
                continue

            normalized = df.where(~df.isna(), None)
            rows = normalized.values.tolist()
            results.append((page_number, rows))

    return results


def _stitch_section_tables(
    tables: List[ExtractedTable],
) -> Tuple[List[ExtractedTable], bool]:
    if len(tables) <= 1:
        return tables, False

    stitched: List[ExtractedTable] = []
    current = tables[0]

    for next_table in tables[1:]:
        if _can_stitch_tables(current, next_table):
            merged_record = _merge_table_records(current, next_table)
            merged_dataframe = pd.concat(
                [current.dataframe, next_table.dataframe], ignore_index=True, sort=False
            )
            current = ExtractedTable(dataframe=merged_dataframe, record=merged_record)
        else:
            stitched.append(current)
            current = next_table

    stitched.append(current)

    for index, table in enumerate(stitched, start=1):
        table.record.table_index = index

    return stitched, len(stitched) != len(tables)


def _can_stitch_tables(left: ExtractedTable, right: ExtractedTable) -> bool:
    if left.dataframe.shape[1] != right.dataframe.shape[1]:
        return False

    left_columns = list(map(str, left.dataframe.columns))
    right_columns = list(map(str, right.dataframe.columns))
    if left_columns != right_columns:
        return False

    if right.record.page - left.record.page > 1:
        return False

    return True


def _merge_table_records(
    left: ExtractedTable, right: ExtractedTable
) -> TableRecord:
    left_record = left.record
    right_record = right.record

    stitched_from = list(left_record.stitched_from) or [left_record.raw_table_index]
    stitched_from.extend(right_record.stitched_from or [right_record.raw_table_index])

    cell_weight_left = left_record.row_count * left_record.column_count
    cell_weight_right = right_record.row_count * right_record.column_count

    merged_record = TableRecord(
        page=left_record.page,
        raw_table_index=left_record.raw_table_index,
        table_index=left_record.table_index,
        row_count=left_record.row_count + right_record.row_count,
        column_count=left_record.column_count,
        numeric_columns=min(left_record.numeric_columns, right_record.numeric_columns),
        empty_cell_ratio=_weighted_average(
            left_record.empty_cell_ratio,
            cell_weight_left,
            right_record.empty_cell_ratio,
            cell_weight_right,
        ),
        first_column_string_ratio=_weighted_average(
            left_record.first_column_string_ratio,
            left_record.row_count,
            right_record.first_column_string_ratio,
            right_record.row_count,
        ),
        column_majority=list(left_record.column_majority),
        warnings=list(dict.fromkeys(left_record.warnings + right_record.warnings)),
        original_columns=list(left_record.original_columns),
        normalized_columns=list(left_record.normalized_columns),
        stitched_from=stitched_from,
    )

    return merged_record


def _weighted_average(
    left: Optional[float], left_weight: int, right: Optional[float], right_weight: int
) -> Optional[float]:
    if left is None and right is None:
        return None
    if left is None:
        return right
    if right is None:
        return left

    total = left_weight + right_weight
    if total == 0:
        return None
    return (left * left_weight + right * right_weight) / total


def _apply_schema_normalization(
    section_key: str, dataframe: pd.DataFrame
) -> Tuple[pd.DataFrame, List[str], bool]:
    if dataframe.empty:
        return dataframe.copy(), [str(column) for column in dataframe.columns], False

    working = dataframe.copy()
    header_row: Optional[List[Optional[str]]] = None
    header_dropped = False

    first_row = list(working.iloc[0])
    textual_cells = sum(
        1 for value in first_row if isinstance(value, str) and value.strip()
    )
    if first_row and textual_cells >= max(1, int(len(first_row) * 0.6)):
        header_row = [value if not _is_empty(value) else None for value in first_row]
        working = working.iloc[1:].reset_index(drop=True)
        header_dropped = True

    width = working.shape[1]
    normalized_columns: List[str] = []
    seen: Dict[str, int] = {}

    for index in range(width):
        header_value = None
        if header_row and index < len(header_row):
            header_value = header_row[index]
        name = _render_column_name(section_key, header_value, index)
        normalized_columns.append(_uniquify_name(name, seen))

    working.columns = normalized_columns
    return working, normalized_columns, header_dropped


def _render_column_name(
    section_key: str, source: Optional[object], index: int
) -> str:
    text = None
    if source is not None:
        text = str(source).strip()

    label = ""
    if text:
        cleaned = _slugify(text)
        cleaned = cleaned.replace("_", " ").strip()
        if cleaned:
            label = " ".join(word.capitalize() for word in cleaned.split())

    if not label:
        if index == 0:
            label = "Descrição"
        else:
            label = f"Valor {index:02d}"

    if index > 0 and label.lower().startswith("valor") and section_key:
        label = f"{section_key} {label}"

    return label


def _uniquify_name(name: str, seen: Dict[str, int]) -> str:
    count = seen.get(name, 0)
    seen[name] = count + 1
    if count == 0:
        return name
    return f"{name} ({count + 1})"


def _extract_tables_from_page(
    page: pdfplumber.page.Page,
) -> List[Sequence[Sequence[Optional[str]]]]:
    tables = page.extract_tables(table_settings=GRID_TABLE_SETTINGS) or []
    if tables:
        return tables
    return page.extract_tables(table_settings=TEXT_TABLE_SETTINGS) or []


def _table_to_dataframe(
    table: Sequence[Sequence[Optional[str]]]
) -> tuple[Optional[pd.DataFrame], TableAnalysis]:
    analysis = TableAnalysis()

    rows = [list(row) if row is not None else [] for row in table]
    if not rows:
        analysis.warnings.append("Tabela ignorada por não conter linhas.")
        return None, analysis

    max_width = max((len(row) for row in rows), default=0)
    if max_width <= 1:
        analysis.warnings.append("Tabela com menos de 2 colunas detectadas.")
        return None, analysis

    normalized_rows = [_normalize_row(row, max_width) for row in rows]

    total_cells = len(normalized_rows) * max_width
    empty_cells = sum(
        1
        for row in normalized_rows
        for cell in row
        if _is_empty(cell)
    )
    analysis.empty_cell_ratio = empty_cells / total_cells if total_cells else None

    dataframe = pd.DataFrame(normalized_rows)
    dataframe = _clean_dataframe(dataframe)

    if dataframe.empty or dataframe.shape[1] <= 1:
        analysis.warnings.append("Tabela descartada por ficar vazia após limpeza inicial.")
        return None, analysis

    dataframe, normalization = _normalize_numeric_columns(dataframe)
    if dataframe.empty or dataframe.shape[1] <= 1:
        analysis.warnings.append("Tabela descartada após normalização numérica.")
        return None, analysis

    analysis.row_count = len(dataframe)
    analysis.column_count = dataframe.shape[1]
    analysis.numeric_columns = len(normalization.numeric_columns)
    analysis.column_majority = normalization.column_majority
    analysis.first_column_string_ratio = normalization.first_column_string_ratio

    if analysis.row_count < 2:
        analysis.warnings.append("Tabela com poucas linhas (menos de 2).")

    if analysis.empty_cell_ratio is not None and analysis.empty_cell_ratio > 0.4:
        analysis.warnings.append("Tabela com muitas células vazias (>40%).")

    if (
        analysis.first_column_string_ratio is not None
        and analysis.first_column_string_ratio <= 0.5
    ):
        analysis.warnings.append(
            "Primeira coluna não é majoritariamente textual (>50%)."
        )

    for idx, majority in enumerate(analysis.column_majority[1:], start=1):
        if majority not in {"numeric", "empty"}:
            analysis.warnings.append(
                f"Coluna {idx + 1} não predominante numérica (status: {majority})."
            )

    return dataframe, analysis


def _normalize_row(row: Sequence[Optional[str]], width: int) -> List[Optional[str]]:
    normalized = list(row) + [None] * (width - len(row))
    return [_clean_cell(value) for value in normalized]


def _clean_cell(value: Optional[str]) -> Optional[str | float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return value
    text = str(value).replace("\r", " ").replace("\n", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text if text else None


def _clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    cleaned = df.applymap(_clean_cell)
    cleaned = cleaned.replace({"": None})
    cleaned = cleaned.dropna(how="all")
    cleaned = cleaned.dropna(axis=1, how="all")
    return cleaned


def _normalize_numeric_columns(
    df: pd.DataFrame,
) -> tuple[pd.DataFrame, NormalizationSummary]:
    normalized = df.copy()
    summaries: List[ColumnSummary] = []

    for column in normalized.columns:
        values = list(normalized[column])
        converted: List[Optional[object]] = []
        numeric_count = 0
        string_count = 0
        non_empty_count = 0

        for value in values:
            if value is None:
                converted.append(None)
                continue

            if isinstance(value, (int, float)):
                numeric_count += 1
                non_empty_count += 1
                converted.append(float(value))
                continue

            if isinstance(value, str):
                cleaned = value.strip()
                if not cleaned:
                    converted.append(None)
                    continue

                non_empty_count += 1
                numeric_value = _parse_br_number(cleaned)
                if numeric_value is not None:
                    numeric_count += 1
                    converted.append(numeric_value)
                else:
                    string_count += 1
                    converted.append(cleaned)
            else:
                non_empty_count += 1
                converted.append(value)

        majority: str
        if non_empty_count == 0:
            majority = "empty"
        elif numeric_count >= (non_empty_count / 2):
            majority = "numeric"
        elif string_count >= (non_empty_count / 2):
            majority = "string"
        else:
            majority = "mixed"

        if majority == "numeric":
            normalized[column] = converted
        else:
            normalized[column] = values

        summaries.append(
            ColumnSummary(
                name=column,
                non_empty=non_empty_count,
                numeric_count=numeric_count,
                string_count=string_count,
                majority=majority,
            )
        )

    normalized = normalized.applymap(lambda value: None if _is_empty(value) else value)
    normalized = normalized.dropna(how="all")
    normalized = normalized.dropna(axis=1, how="all")

    retained_names = list(normalized.columns)
    summary_map = {summary.name: summary for summary in summaries}
    column_majority: List[str] = []
    numeric_columns: List[int] = []

    for name in retained_names:
        summary = summary_map.get(name)
        if summary is None:
            continue
        column_majority.append(summary.majority)
        if summary.majority == "numeric" and summary.non_empty > 0:
            try:
                numeric_columns.append(int(name))
            except (TypeError, ValueError):
                pass

    first_ratio: Optional[float] = None
    first_summary = summary_map.get(retained_names[0]) if retained_names else summary_map.get(0)
    if first_summary and first_summary.non_empty:
        first_ratio = first_summary.string_count / first_summary.non_empty

    normalization_summary = NormalizationSummary(
        column_majority=column_majority,
        numeric_columns=numeric_columns,
        first_column_string_ratio=first_ratio,
    )

    return normalized, normalization_summary


def _parse_br_number(value: str) -> Optional[float]:
    text = value.strip()
    if not text:
        return None

    text = text.replace("R$", "")
    text = text.replace("%", "")
    text = text.replace("\u00a0", "")
    text = text.strip()

    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1]

    text = text.replace(" ", "")

    if text.startswith("-"):
        negative = not negative
        text = text[1:]

    if text.endswith("-"):
        negative = not negative
        text = text[:-1]

    if not text:
        return None

    if "," in text:
        text = text.replace(".", "")
        text = text.replace(",", ".")
    else:
        parts = text.split(".")
        if len(parts) > 2:
            text = "".join(parts[:-1]) + "." + parts[-1]

    try:
        number = float(text)
    except ValueError:
        return None

    return -number if negative else number


def _is_empty(value: Optional[object]) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and pd.isna(value):
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_-]+", "_", value)
    normalized = normalized.strip("_")
    return normalized or value
