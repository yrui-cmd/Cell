"""Create an isolated edit-mode copy and a manifest of objects to reveal."""
from hashlib import file_digest
import os
from pathlib import Path
import subprocess
import sys
from tempfile import NamedTemporaryFile
from zipfile import ZipFile

from lxml import etree
from pptx import Presentation

NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
DRAWING = "http://schemas.openxmlformats.org/drawingml/2006/main"
SHAPES = {"sp", "pic", "graphicFrame", "grpSp", "cxnSp"}


def p(name):
    return f"{{{NS}}}{name}"


def hide_for_playback(slide):
    if slide.get("show") in {"0", "false"}:
        return []
    ids = []
    tree = slide.find(f"{p('cSld')}/{p('spTree')}")
    for shape in tree:
        if not isinstance(shape.tag, str):
            continue
        name = etree.QName(shape)
        if name.namespace != NS or name.localname not in SHAPES:
            continue
        info = shape[0].find(p("cNvPr"))
        if info is not None and info.get("id") and info.get("hidden") not in {"1", "true"}:
            ids.append(int(info.get("id")))
            info.set("hidden", "1")
    return ids


def stage_for_macos(slide_xml, slide):
    if slide_xml.get("show") in {"0", "false"}:
        return []
    tree = slide_xml.find(f"{p('cSld')}/{p('spTree')}")
    original = {str(shape.shape_id): shape for shape in slide.shapes}
    targets = []
    for element in tree:
        if not isinstance(element.tag, str):
            continue
        name = etree.QName(element)
        if name.namespace != NS or name.localname not in SHAPES:
            continue
        info = element[0].find(p("cNvPr"))
        if info is None or info.get("hidden") in {"1", "true"}:
            continue
        shape_id = info.get("id")
        shape = original[shape_id]
        if name.localname == "graphicFrame":
            container, transform_tag = element, p("xfrm")
        else:
            properties = "grpSpPr" if name.localname == "grpSp" else "spPr"
            container = element.find(p(properties))
            transform_tag = f"{{{DRAWING}}}xfrm"
        transform = container.find(transform_tag)
        if transform is None:
            transform = etree.Element(transform_tag)
            container.insert(0, transform)
        off = transform.find(f"{{{DRAWING}}}off")
        if off is None:
            off = etree.Element(f"{{{DRAWING}}}off", x=str(shape.left), y=str(shape.top))
            transform.insert(0, off)
        if transform.find(f"{{{DRAWING}}}ext") is None:
            size = etree.Element(f"{{{DRAWING}}}ext", cx=str(shape.width), cy=str(shape.height))
            transform.insert(1, size)
        left = int(off.get("x"))
        preview_name = f"CellPptPreview_{slide.slide_id}_{shape_id}"
        info.set("name", preview_name)
        off.set("x", str(10000 * 12700))
        targets.append({"name": preview_name, "left_points": left / 12700})
    return targets


def prepare(source, destination, *, macos=False):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if source == destination or destination.exists():
        raise ValueError("输出预览副本需要新的 PPTX 路径")
    with source.open("rb") as stream:
        original_hash = file_digest(stream, "sha256").hexdigest()
    slides = Presentation(source).slides
    parts = {str(slide.part.partname).lstrip("/"): (index, slide)
             for index, slide in enumerate(slides, 1)}
    targets = {}
    parser = etree.XMLParser(resolve_entities=False, no_network=True)
    with NamedTemporaryFile(dir=destination.parent, suffix=".pptx", delete=False) as temporary:
        staged = Path(temporary.name)
    try:
        with ZipFile(source) as original, ZipFile(staged, "w") as deck:
            for member in original.infolist():
                payload = original.read(member)
                if member.filename in parts:
                    index, slide = parts[member.filename]
                    xml = etree.fromstring(payload, parser)
                    items = stage_for_macos(xml, slide) if macos else hide_for_playback(xml)
                    if items:
                        targets[str(index if macos else slide.slide_id)] = items
                        payload = etree.tostring(xml, encoding="UTF-8", xml_declaration=True)
                deck.writestr(member, payload)
        if len(Presentation(staged).slides) != len(slides):
            raise ValueError("输出预览副本页数与回传成品不一致")
        with source.open("rb") as stream:
            if file_digest(stream, "sha256").hexdigest() != original_hash:
                raise ValueError("回传成品在处理期间已改变")
        staged.rename(destination)
    finally:
        staged.unlink(missing_ok=True)
    return targets


def launch(manifest):
    if sys.platform not in {"win32", "darwin"}:
        raise ValueError("PPT 输出预览需要 Windows 或 macOS 版 Microsoft PowerPoint")
    worker = Path(__file__).with_name("output_worker.py")
    exe = Path(sys.executable)
    options = {"start_new_session": True}
    if os.name == "nt":
        if exe.with_name("pythonw.exe").is_file():
            exe = exe.with_name("pythonw.exe")
        options = {"creationflags": subprocess.CREATE_NO_WINDOW}
    log_path = Path(manifest).with_name("element-playback.log")
    with log_path.open("ab") as log:
        environment = {name: value for name, value in os.environ.items() if name != "CELL_PPT_API_KEY"}
        process = subprocess.Popen([str(exe), "-X", "utf8", str(worker), str(Path(manifest).resolve())],
                                   stdin=subprocess.DEVNULL, stdout=log, stderr=log, env=environment,
                                   **options)
    return process.pid
