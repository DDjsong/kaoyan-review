"""
扫描版 PDF → txt
用法:
  python scripts/ocr_pdf.py <pdf路径>            # 全部页
  python scripts/ocr_pdf.py <pdf路径> 3          # 只处理前 3 页（测试用）
"""
import os
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import fitz  # PyMuPDF
from rapidocr import RapidOCR


def pdf_to_images(pdf_path, dpi=200, max_pages=None):
    doc = fitz.open(pdf_path)
    total = len(doc)
    if max_pages:
        total = min(total, max_pages)

    base_dir = os.path.dirname(pdf_path)
    base_name = os.path.splitext(os.path.basename(pdf_path))[0]
    img_dir = os.path.join(base_dir, f"_img_{base_name}")
    os.makedirs(img_dir, exist_ok=True)

    img_paths = []
    for page_num in range(total):
        page = doc[page_num]
        pix = page.get_pixmap(dpi=dpi)
        img_path = os.path.join(img_dir, f"page_{page_num + 1:03d}.png")
        pix.save(img_path)
        img_paths.append(img_path)
        print(f"  📄 第 {page_num + 1} 页 -> {os.path.basename(img_path)}")

    doc.close()
    return img_paths


def _merge_lines(items, y_threshold=12):
    """
    items: [(y_center, x_left, text), ...]
    返回: 合并后每行的文本列表（按 y 从上到下，x 从左到右）
    """
    if not items:
        return []

    items.sort(key=lambda t: t[0])  # 先按 y 排

    # 按 y 差合并成行
    lines = []
    current = [items[0]]
    for item in items[1:]:
        if abs(item[0] - current[-1][0]) <= y_threshold:
            current.append(item)
        else:
            lines.append(current)
            current = [item]
    if current:
        lines.append(current)

    # 每行内按 x 排序后拼接
    result = []
    for line in lines:
        line.sort(key=lambda t: t[1])
        text = " ".join(t[2] for t in line)
        result.append(text)
    return result


def ocr_one_page(ocr, img_path):
    result = ocr(img_path)

    items = []  # [(y_center, x_left, text), ...]

    # 新版 rapidocr 3.x
    if hasattr(result, "txts"):
        txts = result.txts or []
        boxes = result.boxes
        if boxes is None or len(boxes) == 0:
            return []
        for i, txt in enumerate(txts):
            try:
                box = boxes[i]
                x_left = float(min(p[0] for p in box))
                y_top = float(min(p[1] for p in box))
                y_bottom = float(max(p[1] for p in box))
                y_center = (y_top + y_bottom) / 2
                items.append((y_center, x_left, txt))
            except Exception:
                continue

    # 旧版 rapidocr_onnxruntime
    elif isinstance(result, tuple):
        data, _ = result
        if not data:
            return []
        for item in data:
            box, txt = item[0], item[1]
            x_left = float(min(p[0] for p in box))
            y_top = float(min(p[1] for p in box))
            y_bottom = float(max(p[1] for p in box))
            y_center = (y_top + y_bottom) / 2
            items.append((y_center, x_left, txt))

    return _merge_lines(items)


def ocr_images(img_paths):
    print("🔍 初始化 OCR 引擎（首次运行会下载模型）...")
    ocr = RapidOCR()

    pages_text = []
    for i, img_path in enumerate(img_paths):
        print(f"  🔎 OCR 第 {i + 1}/{len(img_paths)} 页...")
        lines = ocr_one_page(ocr, img_path)
        pages_text.append("\n".join(lines))
    return pages_text


def main():
    if len(sys.argv) < 2:
        print("用法: python scripts/ocr_pdf.py <pdf路径> [最多页数]")
        sys.exit(1)

    pdf_path = sys.argv[1]
    max_pages = int(sys.argv[2]) if len(sys.argv) >= 3 else None

    if not os.path.exists(pdf_path):
        print(f"❌ 文件不存在: {pdf_path}")
        sys.exit(1)

    doc = fitz.open(pdf_path)
    total_pages = len(doc)
    doc.close()

    print(f"📄 处理: {pdf_path}")
    print(f"📐 总页数: {total_pages}", end="")
    if max_pages:
        print(f"（本次只处理前 {max_pages} 页）")
    else:
        print()

    print("\n[1/2] PDF 转图片...")
    img_paths = pdf_to_images(pdf_path, max_pages=max_pages)

    print(f"\n[2/2] OCR 识别 {len(img_paths)} 页...")
    pages_text = ocr_images(img_paths)

    full_text = "\n\n".join(
        f"===== Page {i + 1} =====\n{text}"
        for i, text in enumerate(pages_text)
    )

    if max_pages:
        out_path = os.path.splitext(pdf_path)[0] + f"_test{max_pages}p.txt"
    else:
        out_path = os.path.splitext(pdf_path)[0] + ".txt"

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(full_text)

    print(f"\n✅ 完成！输出: {out_path}")
    print(f"📊 总字符数: {len(full_text)}")


if __name__ == "__main__":
    main()