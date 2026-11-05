"""Build and verify the planning handoff without opening Office."""
import argparse
import hashlib
import json
from pathlib import Path
import textwrap

import fitz
from pptx import Presentation
from pptx.util import Inches, Pt

PLAN = "逐页安排.pptx"
MATERIAL = "问答与原始资料.pdf"
TEMPLATE = "精简参考模板.pptx"
INDEX = "cell-ppt-handoff.json"
MAX_FILE = 64 * 1024**2


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def check(condition, message):
    if not condition:
        raise ValueError(message)


def json_text(data):
    return json.dumps(data, ensure_ascii=False, indent=2)


def slide_count(path):
    count = len(Presentation(path).slides)
    check(1 <= count <= 500, "PPTX 必须有 1–500 页")
    return count


def validate_spec(spec):
    check(spec.get("questions_locked") is True, "先完成问答")
    questions = spec["questions"]
    check(bool(questions), "问答为空")
    for item in questions:
        check(item["state"] in {"confirmed", "delegated"} and item["answer"].strip(),
              "问答尚未锁定")
    timing = spec["timing"]
    total, talk, qa = (timing[key] for key in ("total", "talk", "qa"))
    check(all(type(x) is int and x >= 0 for x in (total, talk, qa)) and talk > 0,
          "时间以整数秒记录，演讲时间必须大于零")
    includes = timing["includes_qa"]
    check(type(includes) is bool and total == talk + (qa if includes else 0),
          "总时长与演讲、现场问答时间不一致")
    for source in spec["sources"]:
        path = Path(source["path"])
        check(path.is_file(), "缺少原始资料文件")
        if source.get("required_paper"):
            check(path.suffix.lower() == ".pdf" and source.get("fulltext_verified") is True,
                  "必用文献先尝试获取全文，缺全文时请客户补发")
    pages = spec["pages"]
    check(1 <= len(pages) <= 500, "规划页数超出限制")
    for page in pages:
        check(all(isinstance(page[key], str) and page[key].strip()
                  for key in ("kind", "title", "story", "evidence", "visual")), "逐页安排缺字段")
        check(type(page["seconds"]) is int and page["seconds"] >= 0, "逐页时长错误")
    check(sum(page["seconds"] for page in pages) == talk, "逐页时长之和不等于演讲时长")


def make_plan(path, pages):
    pres = Presentation()
    pres.slide_width, pres.slide_height = Inches(13.3333), Inches(7.5)
    for number, item in enumerate(pages, 1):
        slide = pres.slides.add_slide(pres.slide_layouts[5])
        slide.shapes.title.text = f"{number:02d} | {item['title']}"
        box = slide.shapes.add_textbox(Inches(.85), Inches(1.8), Inches(11.7), Inches(5))
        frame = box.text_frame
        frame.word_wrap = True
        lines = (("页型 / 时间", f"{item['kind']} / {item['seconds']} 秒"),
                 ("核心内容", item["story"]), ("依据", item["evidence"]),
                 ("配图安排", item["visual"]))
        for i, (label, value) in enumerate(lines):
            para = frame.paragraphs[0] if i == 0 else frame.add_paragraph()
            para.text = f"{label}  {value}"
            para.font.name = "Microsoft YaHei"
            para.font.size = Pt(18)
            para.space_after = Pt(14)
        slide.notes_slide.notes_text_frame.text = json_text({"number": number, **item})
    pres.save(path)


def make_template(output, source, picks):
    pres = Presentation(source)
    indices = [item["page"] for item in picks]
    styles = [item["style"] for item in picks]
    check(indices and len(set(indices)) == len(indices) and len(set(styles)) == len(styles)
          and sum(item["kind"] == "agenda" for item in picks) <= 1,
          "模板代表页重复、未选，或目录多于一页")
    check(all(type(n) is int and 1 <= n <= len(pres.slides) for n in indices),
          "模板源页码无效")
    for item in picks:
        slide = pres.slides[item["page"] - 1]
        check(slide.element.get("show") != "0", "隐藏页不能作为模板代表页")
        slide.notes_slide.notes_text_frame.text = json_text(item)
    ids = pres.slides._sldIdLst
    for index, slide_id in reversed(list(enumerate(ids, 1))):
        if index not in indices:
            pres.part.drop_rel(slide_id.rId)
            ids.remove(slide_id)
    pres.save(output)
    check(slide_count(output) == len(indices), "模板提取页数不符")


def wrap(lines):
    return [piece for line in lines for piece in textwrap.wrap(line, width=46) or [""]]


def make_material(path, spec, plan_hash, template_hash):
    timing = spec["timing"]
    timing_line = (f"总时长 {timing['total']} 秒｜演讲 {timing['talk']} 秒｜现场问答 {timing['qa']} 秒"
                   f"｜总时长{'含' if timing['includes_qa'] else '不含'}现场问答")
    answers = [f"{i}. {q['question']}｜{q['state']}｜{q['answer']}"
               for i, q in enumerate(spec["questions"], 1)]
    lines = wrap(answers)
    groups = [lines[i:i+35] for i in range(0, len(lines), 35)]
    start = len(groups) + 1
    toc = [[1, "客户问答", 1], [1, "原始资料", start]]
    index = {"schema": 1, "material_start": start, "timing": timing, "page_count": len(spec["pages"]),
             "plan_sha256": plan_hash, "template_sha256": template_hash,
             "template_id": spec.get("template_id"), "sources": []}

    def write_page(doc, title, text_lines):
        page = doc.new_page(width=595, height=842)
        for i, line in enumerate([title, "", *text_lines]):
            page.insert_text((38, 55 + i * 18), line, fontname="china-s", fontsize=11)

    with fitz.open() as doc:
        for i, group in enumerate(groups):
            header = wrap([timing_line, f"原始资料从第 {start} 页开始", ""]) if i == 0 else []
            write_page(doc, "客户问答" if i == 0 else "客户问答（续）", header + group)
        for i, source in enumerate(spec["sources"], 1):
            source_path = Path(source["path"])
            title = source["title"]
            first = len(doc) + 1
            attachment = None
            if source_path.suffix.lower() == ".pdf":
                with fitz.open(source_path) as original:
                    check(not original.needs_pass and len(original) > 0, "原始 PDF 无法读取")
                    doc.insert_pdf(original)
            else:
                attachment = f"source-{i:03d}{source_path.suffix}"
                doc.embfile_add(attachment, source_path.read_bytes(), filename=source_path.name)
                readable = source.get("readable_pdf")
                if readable:
                    with fitz.open(readable) as rendered:
                        doc.insert_pdf(rendered)
                else:
                    write_page(doc, "原始资料附件", wrap([title, f"附件：{source_path.name}"]))
            toc.append([2, title, first])
            index["sources"].append({"title": title, "first": first, "last": len(doc),
                                     "sha256": sha(source_path), "attachment": attachment})
        if not index["sources"]:
            write_page(doc, "原始资料", wrap([spec["original_request"]]))
            index["sources"].append({"title": "原始任务说明", "first": start, "last": start})
        doc.set_toc(toc)
        doc.embfile_add(INDEX, json_text(index).encode("utf-8"), filename=INDEX)
        doc.save(path, deflate=True)


def inspect(root):
    paths = {role: root / name for role, name in (("pptx", PLAN), ("material", MATERIAL), ("pptx2", TEMPLATE))}
    if not paths["pptx2"].exists():
        del paths["pptx2"]
    for path in paths.values():
        check(path.is_file() and 0 < path.stat().st_size <= MAX_FILE, f"文件缺失或超出 64 MiB：{path.name}")
    hashes = {role: sha(path) for role, path in paths.items()}
    pages = slide_count(paths["pptx"])
    template_pages = slide_count(paths["pptx2"]) if "pptx2" in paths else 0
    with fitz.open(paths["material"]) as doc:
        index = json.loads(doc.embfile_get(INDEX))
        start = index["material_start"]
        check(index["schema"] == 1 and index["page_count"] == pages
              and index["plan_sha256"] == hashes["pptx"] and index["template_sha256"] == hashes.get("pptx2"),
              "资料 PDF 与规划或模板版本不符")
        check(2 <= start <= len(doc) and [1, "原始资料", start] in doc.get_toc()
              and f"原始资料从第{start}页开始" in "".join(doc[0].get_text().split()),
              "资料首页、书签与分区不一致")
        next_page = start
        for item in index["sources"]:
            check(item["first"] == next_page and next_page <= item["last"] <= len(doc), "原始资料页段不连续")
            if item.get("attachment"):
                actual = hashlib.sha256(doc.embfile_get(item["attachment"])).hexdigest()
                check(actual == item["sha256"], "原始资料附件摘要不符")
            next_page = item["last"] + 1
        check(next_page == len(doc) + 1, "存在未登记的资料页")
    return {"plan_pages": pages, "template_pages": template_pages, "credits": pages + template_pages,
            "sha256": hashes, "index": index}


def build(spec, root):
    validate_spec(spec)
    root.mkdir(parents=True, exist_ok=False)
    make_plan(root / PLAN, spec["pages"])
    if template := spec.get("template"):
        make_template(root / TEMPLATE, template["path"], template["picks"])
    template_hash = sha(root / TEMPLATE) if (root / TEMPLATE).exists() else None
    make_material(root / MATERIAL, spec, sha(root / PLAN), template_hash)
    return inspect(root)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    create = sub.add_parser("build")
    create.add_argument("spec", type=Path)
    create.add_argument("output", type=Path)
    review = sub.add_parser("inspect")
    review.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.action == "build":
        result = build(json.loads(args.spec.read_text(encoding="utf-8-sig")), args.output)
    else:
        result = inspect(args.output)
    print(json_text(result))

