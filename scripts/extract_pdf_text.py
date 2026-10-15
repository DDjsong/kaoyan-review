"""
从可复制 PDF 提取文字，输出 txt
用法: python scripts/extract_pdf_text.py <pdf路径>
"""
import os
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import fitz


def main():
    if len(sys.argv) < 2:
        print("用法: python scripts/extract_pdf_text.py <pdf路径>")
        sys.exit(1)

    pdf_path = sys.argv[1]
    if not os.path.exists(pdf_path):
        print(f"❌ 文件不存在: {pdf_path}")
        sys.exit(1)

    print(f"📄 读取: {pdf_path}")
    doc = fitz.open(pdf_path)

    pages_text = []
    for i, page in enumerate(doc):
        text = page.get_text()
        pages_text.append(text)
        print(f"  第 {i+1}/{len(doc)} 页: {len(text)} 字符")

    doc.close()

    full_text = "\n".join(pages_text)
    out_path = os.path.splitext(pdf_path)[0] + ".txt"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(full_text)

    print(f"\n✅ 完成！输出: {out_path}")
    print(f"📊 总字符数: {len(full_text)}")


if __name__ == "__main__":
    main()