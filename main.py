"""Legacy CLI wrapper kept only for backwards compatibility.

The main application surface for Sirius is the drag-and-drop web UI that
processes PDFs inteiramente em memória.  Este módulo permanece apenas como
um utilitário opcional para quem ainda deseja executar o fluxo antigo via
linha de comando.  Para evitar confusão, o comportamento legado fica atrás
da flag ``--legacy-cli``.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable, Tuple

from extractor import build_csv_exports, extract_consolidated_from_bytes


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Interface legada baseada em caminhos. A interface recomendada é a "
            "UI web (`iniciar.sh`)."
        )
    )
    parser.add_argument(
        "--legacy-cli",
        action="store_true",
        help=(
            "Processa um PDF a partir do disco. Sem esta flag o script apenas "
            "informa como iniciar a UI web."
        ),
    )
    parser.add_argument(
        "pdf",
        nargs="?",
        type=Path,
        help="Caminho para o PDF de demonstrações financeiras.",
    )
    parser.add_argument(
        "--out",
        dest="output_dir",
        type=Path,
        help=(
            "Diretório de saída (opcional). Caso informado, os CSVs e o relatório "
            "gerados em memória serão materializados nele."
        ),
    )
    return parser


def parse_args(
    argv: Iterable[str] | None = None,
) -> Tuple[argparse.ArgumentParser, argparse.Namespace]:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    return parser, args


def main(argv: Iterable[str] | None = None) -> int:
    parser, args = parse_args(argv)

    if not args.legacy_cli:
        print(
            "A CLI baseada em caminhos foi descontinuada. Execute `./iniciar.sh` "
            "ou `uvicorn webapp:app --host 0.0.0.0 --port 8000` para abrir a UI "
            "drag-and-drop. Para executar o fluxo antigo, utilize --legacy-cli."
        )
        return 0

    if args.pdf is None:
        parser.error("Informe o PDF após habilitar --legacy-cli.")

    pdf_path: Path = args.pdf
    output_dir: Path | None = args.output_dir

    if not pdf_path.exists():
        print(f"Arquivo não encontrado: {pdf_path}")
        return 1

    pdf_bytes = pdf_path.read_bytes()
    result = extract_consolidated_from_bytes(pdf_bytes, pdf_label=pdf_path.stem)

    if not result.spans:
        print("Nenhuma seção consolidada localizada nas primeiras páginas.")
        return 0

    for key, section in result.sections.items():
        start_page, end_page = section.pages
        print(f"[{key}] (p{start_page}-{end_page}) -> {len(section.tables)} table(s)")

    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        exports = build_csv_exports(result)
        for name, data in exports.items():
            (output_dir / name).write_bytes(data)
        print(f"Arquivos exportados para: {output_dir.resolve()}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
