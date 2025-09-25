"""Command line entry-point for running the Sirius tools."""
from __future__ import annotations

import argparse
import importlib
from importlib import util as importlib_util
import json
from pathlib import Path
from typing import Optional, Sequence

HOST = "127.0.0.1"
PORT = 8000
UI_MESSAGE = (
    "Use a UI em http://127.0.0.1:8000 (drag-and-drop). "
    "Para rodar o fluxo antigo: python main.py --legacy-cli caminho/do.pdf"
)


def _parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Interface de linha de comando para iniciar a UI web ou executar o "
            "fluxo legado baseado em arquivos PDF."
        )
    )
    parser.add_argument(
        "--legacy-cli",
        type=Path,
        help="Caminho para o PDF consolidado a ser processado pelo fluxo legado.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="Diretório opcional para salvar CSVs produzidos pelo extrator legado.",
    )

    args = parser.parse_args(argv)
    if args.out and not args.legacy_cli:
        parser.error("--out só pode ser usado em conjunto com --legacy-cli.")

    return args


def _load_uvicorn():
    spec = importlib_util.find_spec("uvicorn")
    if spec is None or spec.loader is None:
        raise ModuleNotFoundError(
            "uvicorn não está instalado. Instale a dependência para iniciar a UI."
        )

    module = importlib_util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_ui() -> None:
    print(UI_MESSAGE)
    uvicorn = _load_uvicorn()
    uvicorn.run("webapp:app", host=HOST, port=PORT, log_level="info")


def _legacy_cli(pdf_path: Path, output_dir: Optional[Path]) -> None:
    print(UI_MESSAGE)

    if not pdf_path.exists():
        print(f"Arquivo '{pdf_path}' não encontrado.")
        return

    if importlib_util.find_spec("fitz") is None:
        print(
            "Dependência 'PyMuPDF' não encontrada. Instale-a com 'pip install pymupdf' "
            "para usar o fluxo legado."
        )
        return

    sections_module = importlib.import_module("sections")
    find_consolidated_spans = sections_module.find_consolidated_spans

    sections = find_consolidated_spans(str(pdf_path))
    print("Seções consolidadas detectadas (páginas 1-based):")
    print(json.dumps(sections, indent=2, ensure_ascii=False))

    if output_dir is None:
        return

    output_dir.mkdir(parents=True, exist_ok=True)
    print(
        "Exportação de CSV ainda não está disponível. "
        "Os arquivos serão gerados automaticamente quando o extrator estiver integrado."
    )


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = _parse_args(argv)
    if args.legacy_cli:
        _legacy_cli(args.legacy_cli, args.out)
        return

    try:
        _run_ui()
    except ModuleNotFoundError as error:
        print(error)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
