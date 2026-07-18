"""输出 Word 简历中的非空段落。"""
import argparse
from pathlib import Path

from docx import Document


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="要读取的 .docx 文件")
    args = parser.parse_args()

    document = Document(args.input)
    for paragraph in document.paragraphs:
        if paragraph.text.strip():
            print(paragraph.text)


if __name__ == "__main__":
    main()
