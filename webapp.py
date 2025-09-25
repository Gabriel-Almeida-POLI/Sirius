"""FastAPI application providing a drag-and-drop UI for PDF extraction."""
from __future__ import annotations

import io
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import pandas as pd
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from extractor import (
    SectionExtraction,
    build_csv_exports,
    build_parquet_exports,
    extract_consolidated_from_bytes,
    package_exports_as_zip,
)


EXPECTED_SECTIONS = ["BPA", "BPP", "DRE", "DRA", "DFC", "DMPL", "DVA"]


@dataclass
class SectionDownload:
    key: str
    filename: str
    data: bytes
    media_type: str


@dataclass
class StoredResult:
    token: str
    filename: str
    zip_bytes: Optional[bytes]
    section_downloads: Dict[str, SectionDownload] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    format: str = "csv"
    include_report: bool = True


def _build_section_export(
    section: SectionExtraction, pdf_label: str, *, export_format: str = "csv"
) -> Optional[SectionDownload]:
    if not section.tables:
        return None

    frames: List[pd.DataFrame] = []
    for table in section.tables:
        df = table.dataframe.copy()
        df.columns = [str(column) for column in df.columns]
        df.insert(0, "Tabela", table.record.table_index or 0)
        frames.append(df)

    if not frames:
        return None

    combined = pd.concat(frames, ignore_index=True, sort=False)

    if export_format == "parquet":
        buffer_bytes = io.BytesIO()
        try:
            combined.to_parquet(buffer_bytes, index=False)
        except Exception as exc:  # pragma: no cover - depends on optional deps
            raise RuntimeError(
                "Não foi possível gerar Parquet (verifique dependências como pyarrow)."
            ) from exc
        filename = f"{pdf_label}__{section.key}.parquet"
        return SectionDownload(
            key=section.key,
            filename=filename,
            data=buffer_bytes.getvalue(),
            media_type="application/octet-stream",
        )

    buffer = io.StringIO()
    combined.to_csv(buffer, index=False)
    filename = f"{pdf_label}__{section.key}.csv"
    return SectionDownload(
        key=section.key,
        filename=filename,
        data=buffer.getvalue().encode("utf-8"),
        media_type="text/csv",
    )


def _build_preview(section: SectionExtraction) -> Optional[Dict[str, object]]:
    if not section.tables:
        return None

    dataframe = section.tables[0].dataframe.head(5)
    headers = [str(column) for column in dataframe.columns]
    rows: List[List[str]] = []
    for _, row in dataframe.iterrows():
        rows.append(["" if pd.isna(value) else str(value) for value in row])
    return {"headers": headers, "rows": rows}


def _clean_expired_results(
    storage: Dict[str, StoredResult], *, ttl: float = 600.0, max_items: int = 24
) -> None:
    now = time.time()
    expired = [key for key, item in storage.items() if now - item.created_at > ttl]
    for key in expired:
        storage.pop(key, None)

    if len(storage) <= max_items:
        return

    # Remove oldest entries beyond capacity.
    ordered = sorted(storage.items(), key=lambda entry: entry[1].created_at)
    excess = len(storage) - max_items
    for key, _ in ordered[:excess]:
        storage.pop(key, None)


def _parse_bool(value: object, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    return text in {"1", "true", "on", "yes", "sim"}


app = FastAPI(title="Sirius PDF Extractor UI")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")


STORAGE: Dict[str, StoredResult] = {}


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return FileResponse("static/index.html")


@app.post("/api/process")
async def process_file(
    file: UploadFile = File(...),
    engine: str = Form("auto"),
    stitch: str = Form("true"),
    normalize_schema: str = Form("true"),
    download_format: str = Form("csv"),
    include_report: str = Form("true"),
) -> JSONResponse:
    if file.content_type not in {"application/pdf", "application/octet-stream"}:
        raise HTTPException(
            status_code=400,
            detail={"message": "Apenas arquivos PDF são aceitos."},
        )

    start = time.perf_counter()
    pdf_bytes = await file.read()
    label = (file.filename or "document").rsplit(".", 1)[0]

    requested_engine = (engine or "auto").lower()
    stitch_enabled = _parse_bool(stitch, True)
    normalize_enabled = _parse_bool(normalize_schema, True)
    include_report_flag = _parse_bool(include_report, True)
    download_format_value = (download_format or "csv").lower()

    if download_format_value not in {"csv", "parquet"}:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Formato de download inválido.",
                "hint": "Escolha entre CSV ou Parquet.",
            },
        )

    try:
        result = extract_consolidated_from_bytes(
            pdf_bytes,
            pdf_label=label,
            engine=requested_engine,
            stitch_tables=stitch_enabled,
            normalize_schema=normalize_enabled,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "message": str(exc),
                "hint": "Experimente o motor pdfplumber ou ajuste as opções avançadas.",
            },
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"message": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Falha inesperada ao processar o PDF.",
                "hint": "Tente novamente com menos opções ou outro motor de extração.",
            },
        ) from exc

    processing_ms = (time.perf_counter() - start) * 1000

    try:
        if download_format_value == "parquet":
            exports = build_parquet_exports(
                result, include_report=include_report_flag
            )
        else:
            exports = build_csv_exports(result, include_report=include_report_flag)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "message": str(exc),
                "hint": "Prefira CSV ou instale os requisitos de Parquet (ex.: pyarrow).",
            },
        ) from exc

    zip_bytes = package_exports_as_zip(exports) if exports else None

    token = uuid.uuid4().hex

    section_payloads = []
    section_downloads: Dict[str, SectionDownload] = {}
    total_tables = 0

    for key in EXPECTED_SECTIONS:
        section = result.sections.get(key)
        if section is None:
            section_payloads.append(
                {
                    "key": key,
                    "present": False,
                    "pages": None,
                    "table_count": 0,
                    "alerts": [],
                    "preview": None,
                    "download_url": None,
                    "download_name": None,
                    "download_format": download_format_value,
                    "download_media_type": None,
                    "engine": None,
                    "stitched": False,
                    "schema_normalized": False,
                }
            )
            continue

        start_page, end_page = section.pages
        preview = _build_preview(section)

        download: Optional[SectionDownload]
        try:
            download = _build_section_export(
                section, result.pdf_label, export_format=download_format_value
            )
        except RuntimeError as exc:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": str(exc),
                    "hint": "Opte por CSV para baixar esta seção.",
                },
            ) from exc

        if download is not None:
            section_downloads[key] = download
            download_url = f"/api/download/section/{token}/{key}"
            download_name = download.filename
            download_media_type = download.media_type
        else:
            download_url = None
            download_name = None
            download_media_type = None

        section_payloads.append(
            {
                "key": key,
                "present": True,
                "pages": [start_page, end_page],
                "table_count": len(section.tables),
                "alerts": [record.to_dict() for record in section.alerts],
                "preview": preview,
                "download_url": download_url,
                "download_name": download_name,
                "download_format": download_format_value,
                "download_media_type": download_media_type,
                "engine": section.engine_used,
                "stitched": section.stitched,
                "schema_normalized": section.schema_normalized,
            }
        )
        total_tables += len(section.tables)

    STORAGE[token] = StoredResult(
        token=token,
        filename=file.filename or "document.pdf",
        zip_bytes=zip_bytes,
        section_downloads=section_downloads,
        format=download_format_value,
        include_report=include_report_flag,
    )
    _clean_expired_results(STORAGE)

    zip_filename = None
    if zip_bytes:
        base_name = (file.filename or "document.pdf").rsplit(".", 1)[0]
        zip_filename = f"{base_name}__tables_{download_format_value}.zip"

    effective_engines = sorted({section.engine_used for section in result.sections.values()})

    response_payload = {
        "token": token,
        "pdf": {
            "filename": file.filename,
            "label": result.pdf_label,
            "processing_time_ms": round(processing_ms, 2),
            "total_tables": total_tables,
            "spans": result.spans,
            "sections": section_payloads,
        },
        "downloads": {
            "zip": f"/api/download/zip/{token}" if zip_bytes else None,
            "zip_name": zip_filename,
            "format": download_format_value,
            "include_report": include_report_flag,
        },
        "options": {
            "engine": requested_engine,
            "effective_engines": effective_engines,
            "stitch_tables": stitch_enabled,
            "normalize_schema": normalize_enabled,
            "download_format": download_format_value,
            "include_report": include_report_flag,
        },
    }

    return JSONResponse(response_payload)


@app.get("/api/download/zip/{token}")
async def download_zip(token: str) -> StreamingResponse:
    stored = STORAGE.get(token)
    if stored is None or not stored.zip_bytes:
        raise HTTPException(status_code=404, detail="Arquivo não disponível.")

    base_name = stored.filename.rsplit(".", 1)[0]
    format_suffix = stored.format if stored.format else "csv"
    filename = f"{base_name}__tables_{format_suffix}.zip"
    return StreamingResponse(
        io.BytesIO(stored.zip_bytes),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.get("/api/download/section/{token}/{section_key}")
async def download_section(token: str, section_key: str) -> StreamingResponse:
    stored = STORAGE.get(token)
    if stored is None:
        raise HTTPException(status_code=404, detail="Arquivo não disponível.")

    download = stored.section_downloads.get(section_key.upper())
    if download is None:
        raise HTTPException(status_code=404, detail="Seção não disponível para download.")

    return StreamingResponse(
        io.BytesIO(download.data),
        media_type=download.media_type,
        headers={"Content-Disposition": f"attachment; filename={download.filename}"},
    )


@app.on_event("startup")
def on_startup() -> None:
    _clean_expired_results(STORAGE, ttl=0)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("webapp:app", host="0.0.0.0", port=8000, reload=True)
