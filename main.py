from pathlib import Path

from sections import find_consolidated_sections


PDF_PATHS = [
    Path("/mnt/data/DFP - 2024.pdf"),
    Path("/mnt/data/ITR 1T25.pdf"),
]


def main() -> None:
    for pdf_path in PDF_PATHS:
        print(pdf_path)
        if not pdf_path.exists():
            print("Arquivo não encontrado.")
            continue

        sections = find_consolidated_sections(str(pdf_path))
        print(sections)


if __name__ == "__main__":
    main()
