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
TRANSPORT_INDEX = "ppt-material-index.json"
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


REQUIRED_QUESTIONS = {"audience", "duration", "focus", "outcome", "scope", "materials",
                      "style", "page_count", "language", "aspect_ratio", "template"}


def validate_spec(spec):
    check(spec.get("questions_locked") is True, "先完成问答")
    questions = spec.get("questions")
    check(isinstance(questions, list) and bool(questions), "必问问题必须实际询问并收到答复")
    fields = set()
    for item in questions:
        check(isinstance(item, dict), "问答记录格式错误")
        field = item.get("field")
        check(isinstance(field, str) and field in REQUIRED_QUESTIONS and field not in fields,
              "关键问答字段缺失、未知或重复")
        fields.add(field)
        check(item.get("asked") is True, "必须向用户实际提问，不能静默采用已有答案")
        check(item.get("state") in {"confirmed", "delegated"}, "问答尚未确认")
        for key in ("question", "answer", "response_source"):
            check(isinstance(item.get(key), str) and bool(item[key].strip()),
                  "必须保留实际问题、用户答复及答复出处")
    check(fields == REQUIRED_QUESTIONS, "必问问题尚未全部完成，先继续逐项提问")
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
                  for key in ("kind", "title", "story", "evidence", "visual", "content", "layout", "notes")), "逐页安排缺字段")
        check(type(page["seconds"]) is int and page["seconds"] >= 0, "逐页时长错误")
    check(sum(page["seconds"] for page in pages) == talk, "逐页时长之和不等于演讲时长")

    design = spec.get("design", {})
    for key in ("style", "language", "aspect_ratio", "palette"):
        check(isinstance(design.get(key), str) and design[key].strip(), "缺少风格、语言、比例或统一配色")
    check(type(design.get("page_count")) is int and design["page_count"] == len(pages), "确认页数与实际 PPT 内容页数不符")
    ratio = design["aspect_ratio"].split(":")
    check(len(ratio) == 2, "比例须为宽:高，例如 16:9")
    width, height = map(float, ratio)
    check(width > 0 and height > 0 and .25 <= width / height <= 4, "页面比例无效")
    check(isinstance(spec.get("template_notes"), str) and spec["template_notes"].strip(), "必须说明模板选择；不用时写无模板")
    if template := spec.get("template"):
        source = Path(template["path"])
        check(template.get("rendered_from_sha256") == sha(source), "模板预览必须对应当前模板源文件摘要")
        with fitz.open(template["readable_pdf"]) as rendered:
            check(not rendered.needs_pass and len(rendered) == slide_count(source), "模板 PDF 须完整渲染当前模板源文件，页数一致")


def make_plan(path, pages, design):
    pres = Presentation()
    width, height = map(float, design["aspect_ratio"].split(":"))
    pres.slide_width, pres.slide_height = Inches(7.5 * width / height), Inches(7.5)
    for number, item in enumerate(pages, 1):
        slide = pres.slides.add_slide(pres.slide_layouts[5])
        slide.shapes.title.text = f"# 第 {number} 页 | {item['title'][:50]}"
        box = slide.shapes.add_textbox(Inches(.85), Inches(1.8), pres.slide_width - Inches(1.7), Inches(5))
        frame = box.text_frame
        frame.word_wrap = True
        lines = (("页型 / 时间", f"{item['kind']} / {item['seconds']} 秒"),
                 ("核心内容", item["story"]), ("依据", item["evidence"]),
                 ("配图安排", item["visual"]))
        for i, (label, value) in enumerate(lines):
            para = frame.paragraphs[0] if i == 0 else frame.add_paragraph()
            summary = value if len(value) <= 120 else value[:120] + "…（完整内容见 PDF）"
            para.text = f"{label}  {summary}"
            para.font.name = "Microsoft YaHei"
            para.font.size = Pt(16)
            para.space_after = Pt(10)
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
    return [piece for line in lines for raw in str(line).split("\n")
            for piece in textwrap.wrap(raw, width=44) or [""]]


def make_material(path, spec, plan_hash, template_hash):
    timing = spec["timing"]
    design = spec["design"]
    total = len(spec["pages"])
    template_label = spec["template_notes"]
    index = {"schema": 2, "timing": timing, "page_count": total,
             "plan_sha256": plan_hash, "template_sha256": template_hash,
             "template_id": spec.get("template_id"), "sources": [],
             "sections": [], "content_pages": []}
    toc = []

    def write_text(doc, title, lines):
        lines = wrap(lines)
        offset = 0
        while offset < max(1, len(lines)):
            page = doc.new_page(width=595, height=842)
            heading = wrap([title if offset == 0 else title + "（续）"])
            check(len(heading) <= 8, "页标题过长，请精简标题")
            for i, line in enumerate(heading):
                page.insert_text((38, 48 + i * 20), line, fontname="china-s", fontsize=11)
            body_y = 62 + len(heading) * 20
            capacity = int((780 - body_y) // 19) + 1
            for i, line in enumerate(lines[offset:offset + capacity]):
                page.insert_text((38, body_y + i * 19), line, fontname="china-s", fontsize=11)
            page.insert_text((38, 815), str(len(doc)), fontsize=9)
            offset += capacity

    def section(doc, name):
        first = len(doc) + 1
        toc.append([1, name, first])
        index["sections"].append({"name": name, "first": first})
        return first

    with fitz.open() as doc:
        section(doc, "问答")
        answers = [f"模板：{template_label}", "", "问答",
                   f"风格：{design['style']}｜语言：{design['language']}｜比例：{design['aspect_ratio']}",
                   f"统一配色：{design['palette']}",
                   f"演讲 {timing['talk']} 秒；现场问答 {timing['qa']} 秒；总时长 {timing['total']} 秒", ""]
        for i, q in enumerate(spec["questions"], 1):
            answers += [f"{i}. {q['question']}", f"答：{q['answer']}", f"答复出处：{q['response_source']}", ""]
        write_text(doc, f"PPT内容共 {total} 页", answers)
        section(doc, "模板")
        write_text(doc, "模板", [f"模板：{template_label}", f"模板编号：{spec.get('template_id') or '无'}",
                   "以下模板预览仅用于风格参考，不计入 PPT 内容总页数。",
                   f"风格：{design['style']}", f"配色：{design['palette']}"])
        if template := spec.get("template"):
            with fitz.open(template["readable_pdf"]) as rendered:
                for pick in sorted(template["picks"], key=lambda x: x["page"]):
                    toc.append([2, f"模板源第 {pick['page']} 页：{pick['style']}", len(doc) + 1])
                    doc.insert_pdf(rendered, from_page=pick["page"]-1, to_page=pick["page"]-1)
        start = section(doc, "资料")
        index["material_start"] = start
        for i, source in enumerate(spec["sources"], 1):
            source_path = Path(source["path"])
            first = len(doc) + 1
            attachment = None
            if source_path.suffix.lower() == ".pdf":
                with fitz.open(source_path) as original:
                    check(not original.needs_pass and len(original) > 0, "原始 PDF 无法读取")
                    doc.insert_pdf(original)
            else:
                attachment = f"source-{i:03d}{source_path.suffix}"
                doc.embfile_add(attachment, source_path.read_bytes(), filename=source_path.name)
                if readable := source.get("readable_pdf"):
                    with fitz.open(readable) as rendered:
                        check(not rendered.needs_pass and len(rendered) > 0, "资料预览 PDF 无法读取")
                        doc.insert_pdf(rendered)
                else:
                    write_text(doc, "原始资料附件", [source["title"], f"附件：{source_path.name}"])
            toc.append([2, source["title"], first])
            index["sources"].append({"title": source["title"], "first": first, "last": len(doc),
                                     "sha256": sha(source_path), "attachment": attachment})
        if not index["sources"]:
            write_text(doc, "资料", [spec["original_request"]])
            index["sources"].append({"title": "原始任务说明", "first": start, "last": len(doc)})
        index["content_start"] = section(doc, "PPT内容")
        for number, item in enumerate(spec["pages"], 1):
            first = len(doc) + 1
            heading = f"# 第 {number} 页：{item['title']}"
            toc.append([2, heading, first])
            write_text(doc, heading, [f"页型：{item['kind']}｜讲解：{item['seconds']} 秒",
                       "核心目的：" + item["story"], "", "PPT内容：", item["content"], "",
                       "排版：", item["layout"], "配图/图表安排：" + item["visual"],
                       "依据：" + item["evidence"], "", "注释（供制作参考，不直接上屏）：", item["notes"]])
            index["content_pages"].append({"number": number, "first": first, "last": len(doc), "heading": heading})
        for i, item in enumerate(index["sections"]):
            item["last"] = index["sections"][i+1]["first"] - 1 if i+1 < len(index["sections"]) else len(doc)
        doc.set_toc(toc)
        payload = json_text(index).encode("utf-8")
        doc.embfile_add(INDEX, payload, filename=INDEX)
        doc.embfile_add(TRANSPORT_INDEX, payload, filename=TRANSPORT_INDEX)
        doc.save(path, deflate=True)


def inspect(root, *, legacy=False):
    root = Path(root)
    pdf = root / MATERIAL
    check(pdf.is_file() and 0 < pdf.stat().st_size <= MAX_FILE, "交接 PDF 缺失或超出 64 MiB")
    with fitz.open(pdf) as doc:
        check(not doc.needs_pass and len(doc) > 0, "交接 PDF 无法读取")
        names = doc.embfile_names()
        single_pdf = TRANSPORT_INDEX in names and not legacy
        index = json.loads(doc.embfile_get(TRANSPORT_INDEX if single_pdf else INDEX))
        check(isinstance(index, dict), "PDF 内嵌索引无效")
        if TRANSPORT_INDEX in names and INDEX in names:
            check(json.loads(doc.embfile_get(INDEX)) == json.loads(doc.embfile_get(TRANSPORT_INDEX)),
                  "PDF 两份内嵌索引不一致，请重新生成并确认")
        pages = index.get("page_count")
        check(type(pages) is int and 1 <= pages <= 500, "内嵌索引 page_count 必须是 1–500 的整数")
        check(index.get("schema") == 2 if single_pdf else index.get("schema") in {1, 2}, "不支持的 PDF 索引格式")
        hashes = {"material": sha(pdf)}
        template_pages = 0
        for role, filename, hash_key in (("pptx", PLAN, "plan_sha256"), ("pptx2", TEMPLATE, "template_sha256")):
            local = root / filename
            if not local.exists():
                check(single_pdf or role == "pptx2", "旧订单缺少规划 PPTX")
                continue
            check(0 < local.stat().st_size <= MAX_FILE, "本地参考 PPTX 超出大小限制")
            check(sha(local) == index.get(hash_key), "本地规划或模板与 PDF 版本不符")
            count = slide_count(local)
            if role == "pptx":
                check(count == pages, "规划 PPTX 与 PDF 声明页数不符")
            else:
                template_pages = count
            if not single_pdf:
                hashes[role] = sha(local)
        if not single_pdf:
            check(index.get("template_sha256") == hashes.get("pptx2"), "旧订单缺少对应模板 PPTX")
        start = index["material_start"]
        if index["schema"] == 1:
            check(2 <= start <= len(doc) and [1, "原始资料", start] in doc.get_toc()
                  and f"原始资料从第{start}页开始" in "".join(doc[0].get_text().split()),
                  "资料首页、书签与分区不一致")
            material_end = len(doc)
        else:
            sections = index["sections"]
            check([x["name"] for x in sections] == ["问答", "模板", "资料", "PPT内容"], "PDF 分区顺序错误")
            cursor = 1
            for item in sections:
                check(item["first"] == cursor and item["first"] <= item["last"] <= len(doc)
                      and [1, item["name"], item["first"]] in doc.get_toc(), "PDF 分区或书签不连续")
                cursor = item["last"] + 1
            check(cursor == len(doc)+1 and start == sections[2]["first"]
                  and index["content_start"] == sections[3]["first"], "资料与 PPT 内容起始页错误")
            first_text = "".join(doc[0].get_text().split())
            check(f"PPT内容共{pages}页" in first_text and "模板：" in first_text, "首页缺少 PPT 总页数或模板")
            records = index["content_pages"]
            check(len(records) == pages, "PDF 的 PPT 内容页数错误")
            cursor = index["content_start"]
            for number, item in enumerate(records, 1):
                check(item["number"] == number and item["first"] == cursor
                      and cursor <= item["last"] <= len(doc), "逐页内容顺序错误")
                text = "".join(doc[item["first"]-1].get_text().split())
                check(f"#第{number}页：" in text, "PPT 每页内容必须以 # 开头")
                cursor = item["last"] + 1
            check(cursor == len(doc)+1, "PPT 内容页段不完整")
            material_end = sections[2]["last"]
        next_page = start
        for item in index["sources"]:
            check(item["first"] == next_page and next_page <= item["last"] <= material_end, "原始资料页段不连续")
            if item.get("attachment"):
                actual = hashlib.sha256(doc.embfile_get(item["attachment"])).hexdigest()
                check(actual == item["sha256"], "原始资料附件摘要不符")
            next_page = item["last"] + 1
        check(next_page == material_end + 1, "存在未登记的资料页")
    return {"plan_pages": pages, "template_pages": template_pages,
            "credits": pages if single_pdf else pages + template_pages,
            "upload_format": "single_pdf" if single_pdf else "legacy_pptx_pdf",
            "sha256": hashes, "index": index}


def build(spec, root):
    validate_spec(spec)
    root.mkdir(parents=True, exist_ok=False)
    make_plan(root / PLAN, spec["pages"], spec["design"])
    (root / "outline.json").write_text(json_text(spec), encoding="utf-8")
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

