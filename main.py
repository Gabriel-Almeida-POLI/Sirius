from pathlib import Path

from sections import find_consolidated_spans


PDF_PATHS = [
    Path("DFP - 2024.pdf"),
    Path("ITR 1T25.pdf"),
]


def main() -> None:
    for pdf_path in PDF_PATHS:
        print(pdf_path)
        if not pdf_path.exists():
            print("Arquivo não encontrado.")
            continue

        sections = find_consolidated_spans(str(pdf_path))
        print(sections)


if __name__ == "__main__":
    main()
