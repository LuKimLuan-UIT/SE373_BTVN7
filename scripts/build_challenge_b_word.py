"""Create a basic Challenge B Word report from the retained group template.

Uses package-level edits so the original cover, styles, images, headers and
footers remain intact. Requires python-docx/lxml from the document runtime.
"""
import argparse
from copy import deepcopy
import hashlib
from pathlib import Path
import re
from zipfile import ZipFile, ZIP_DEFLATED

from lxml import etree

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W}
ROOT = Path(__file__).resolve().parents[1]


def node(tag, **attrs):
    element = etree.Element("{" + W + "}" + tag)
    for key, value in attrs.items():
        element.set("{" + W + "}" + key, str(value))
    return element


def plain(text):
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", text)
    return text.replace("**", "").replace("`", "")


def build(template, output):
    original = Path(template).read_bytes()
    with ZipFile(template) as source:
        parts = {info.filename: source.read(info.filename) for info in source.infolist()}
    document = etree.fromstring(parts["word/document.xml"])
    body = document.find("w:body", NS)
    paragraphs = body.findall("w:p", NS)
    normal = deepcopy(paragraphs[28].find("w:pPr", NS))
    heading1 = deepcopy(paragraphs[27].find("w:pPr", NS))
    heading2 = deepcopy(paragraphs[48].find("w:pPr", NS))
    first_table = body.find("w:tbl", NS)
    table_props = deepcopy(first_table.find("w:tblPr", NS))
    # Cover editable slots: exercise title and month; retain all drawing runs.
    for text in paragraphs[13].findall(".//w:t", NS):
        text.text = (text.text or "").replace(" - Challenge A", " CHALLENGE B")
    pstyle = paragraphs[13].find("w:pPr/w:pStyle", NS)
    if pstyle is not None:
        pstyle.set("{" + W + "}val", "Title")
    for text in paragraphs[20].findall(".//w:t", NS):
        if text.text == "09":
            text.text = "10"
    # Remove only old TOC/body nodes; the original section stays unchanged.
    cut = list(body).index(paragraphs[21])
    for child in list(body)[cut:]:
        if child.tag != "{" + W + "}sectPr":
            body.remove(child)
    section = body.find("w:sectPr", NS)

    def paragraph(text, role="normal", *, bold=False, size=None):
        p = node("p")
        prop = deepcopy(heading1 if role == "h1" else heading2 if role == "h2" else normal)
        if prop is None:
            prop = node("pPr")
        for old in prop.findall("w:rPr", NS):
            prop.remove(old)
        p.append(prop)
        if role == "code":
            for tag in ("spacing", "jc", "keepNext"):
                for old in prop.findall("w:" + tag, NS):
                    prop.remove(old)
            prop.append(node("spacing", before=0, after=40, line=240, lineRule="auto"))
            prop.append(node("jc", val="left"))
        r = node("r")
        rp = node("rPr")
        rp.append(node("rFonts", ascii="Consolas" if role == "code" else "Times New Roman", hAnsi="Consolas" if role == "code" else "Times New Roman", eastAsia="Times New Roman"))
        rp.append(node("color", val="000000"))
        if size or role == "code":
            rp.append(node("sz", val=round((size or 10) * 2)))
        if bold:
            rp.append(node("b"))
        r.append(rp)
        t = node("t")
        t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        t.text = plain(text)
        r.append(t)
        p.append(r)
        return p

    def add(element):
        body.insert(list(body).index(section), element)

    body_title = paragraph("NỘI DUNG BÀI LÀM CHALLENGE B", "h1")
    body_title.find("w:pPr", NS).append(node("pageBreakBefore"))
    add(body_title)
    add(paragraph("Kho mã nguồn: https://github.com/LuKimLuan-UIT/SE373_BTVN7"))
    lines = (ROOT / "CHALLENGE_B_REPORT.md").read_text(encoding="utf-8").splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("Không tạo lại project hay thay memory"):
            line = "Challenge B tái sử dụng agent của Challenge A, giữ nguyên persistent memory và bản nộp Challenge A."
        if line.startswith("Người dùng đã cho phép chạy provider thật"):
            line = "Các lượt kiểm chứng dùng history và log giả lập qua provider đã cấu hình. " + line[line.index("Các lượt kiểm chứng thành công"):]
        if not line.strip() or line.startswith("# "):
            i += 1; continue
        if line.startswith("```"):
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                add(paragraph(lines[i], "code"))
                i += 1
        elif line.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                cells = [x.strip() for x in lines[i].strip("|").split("|")]
                if not all(re.fullmatch(r"[:\- ]+", x) for x in cells):
                    rows.append(cells)
                i += 1
            table = node("tbl"); props = deepcopy(table_props)
            width = props.find("w:tblW", NS)
            width.set("{" + W + "}type", "dxa"); width.set("{" + W + "}w", "9026")
            borders = node("tblBorders")
            for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
                borders.append(node(side, val="single", sz=4, color="D9D9D9"))
            props.append(borders)
            margins = node("tblCellMar")
            for side in ("top", "bottom", "left", "right"):
                margins.append(node(side, w=90, type="dxa"))
            props.append(margins); table.append(props)
            count = len(rows[0]); ratios = {2:[.30,.70],3:[.25,.30,.45],4:[.34,.16,.25,.25]}.get(count,[1/count]*count)
            grid = node("tblGrid")
            for ratio in ratios: grid.append(node("gridCol", w=round(9026*ratio)))
            table.append(grid)
            for index, row in enumerate(rows):
                tr = node("tr"); trp = node("trPr"); trp.append(node("cantSplit"))
                if index == 0: trp.append(node("tblHeader"))
                tr.append(trp)
                for j, text in enumerate(row):
                    tc = node("tc"); tcp = node("tcPr"); tcp.append(node("tcW", w=round(9026*ratios[j]), type="dxa")); tcp.append(node("vAlign", val="center"))
                    if index == 0: tcp.append(node("shd", fill="F0F0F0"))
                    tc.append(tcp); p = paragraph(text, bold=index==0, size=11.5)
                    pp = p.find("w:pPr", NS)
                    for tag in ("spacing", "jc", "keepNext"):
                        for old in pp.findall("w:"+tag, NS): pp.remove(old)
                    pp.append(node("spacing", before=40, after=40, line=276, lineRule="auto")); pp.append(node("jc", val="left"))
                    if len(rows) <= 4 and index < len(rows)-1:
                        pp.append(node("keepNext"))
                    tc.append(p); tr.append(tc)
                table.append(tr)
            add(table); add(paragraph(""))
            continue
        elif line.startswith("### "):
            add(paragraph(line[4:], "h2"))
        elif line.startswith("## "):
            add(paragraph(line[3:], "h1"))
        else:
            add(paragraph(line))
        i += 1

    parts["word/document.xml"] = etree.tostring(document, xml_declaration=True, encoding="UTF-8", standalone=True)
    styles = etree.fromstring(parts["word/styles.xml"])
    if not styles.xpath("w:style[@w:styleId='Title']", namespaces=NS):
        style = node("style", type="paragraph", styleId="Title")
        style.append(node("name", val="Title")); style.append(node("basedOn", val="Default"))
        styles.append(style)
    parts["word/styles.xml"] = etree.tostring(styles, xml_declaration=True, encoding="UTF-8", standalone=True)
    settings = etree.fromstring(parts["word/settings.xml"])
    update = settings.find("w:updateFields", NS)
    if update is None: update = node("updateFields"); settings.append(update)
    update.set("{" + W + "}val", "true")
    parts["word/settings.xml"] = etree.tostring(settings, xml_declaration=True, encoding="UTF-8", standalone=True)
    core = etree.fromstring(parts["docProps/core.xml"])
    for element in core:
        if etree.QName(element).localname in {"creator", "lastModifiedBy"}:
            element.text = "LuKimLuan-UIT"
        elif etree.QName(element).localname == "title":
            element.text = "BTVN7 Challenge B Context Management"
    parts["docProps/core.xml"] = etree.tostring(core, xml_declaration=True, encoding="UTF-8", standalone=True)
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", ZIP_DEFLATED) as target:
        for name, data in parts.items(): target.writestr(name, data)
    assert Path(template).read_bytes() == original, "Template must remain unchanged"
    print(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    build(args.template, args.output)
