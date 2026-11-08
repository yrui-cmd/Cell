"""Create an isolated edit-mode copy and a manifest of objects to reveal."""
from hashlib import file_digest
from copy import copy
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


def reading_order(slide_xml, slide=None):
    """Order top-level elements by rows without altering their drawing/z order."""
    geometry = {str(s.shape_id): s for s in slide.shapes} if slide is not None else {}
    tree = slide_xml.find(f"{p('cSld')}/{p('spTree')}")
    positioned = []
    for index, element in enumerate(tree):
        if not isinstance(element.tag, str):
            continue
        name = etree.QName(element)
        if name.namespace != NS or name.localname not in SHAPES:
            continue
        info = element[0].find(p('cNvPr'))
        if info is None or not info.get('id') or info.get('hidden') in {'1', 'true'}:
            continue
        shape = geometry.get(info.get('id'))
        if shape is not None:
            left, top = shape.left, shape.top
        else:
            off = element.find(f"{p('spPr')}/{{{DRAWING}}}xfrm/{{{DRAWING}}}off")
            if off is None:
                off = element.find(f"{p('grpSpPr')}/{{{DRAWING}}}xfrm/{{{DRAWING}}}off")
            if off is None:
                off = element.find(f"{p('xfrm')}/{{{DRAWING}}}off")
            left, top = (int(off.get('x', 0)), int(off.get('y', 0))) if off is not None else (None, None)
        positioned.append((float('inf') if top is None else top,
                           float('inf') if left is None else left, index, element))
    remaining = sorted(positioned, key=lambda item: item[:3])
    result = []
    while remaining:
        row_top = remaining[0][0]
        row, later = [], []
        for item in remaining:
            # Small alignment differences still belong to the same visual row.
            (row if item[0] <= row_top + 6 * 12700 else later).append(item)
        result.extend(item[3] for item in sorted(row, key=lambda item: (item[1], item[0], item[2])))
        remaining = later
    return result


def hide_for_playback(slide, geometry=None):
    if slide.get("show") in {"0", "false"}:
        return []
    ids = []
    for shape in reading_order(slide, geometry):
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
    original = {str(shape.shape_id): shape for shape in slide.shapes}
    targets = []
    for element in reading_order(slide_xml, slide):
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


def remove_invalid_tags(slide, relationships):
    """Drop only nonvisual tags pointing to a missing or wrong relationship type."""
    rel_ns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    valid = {node.get("Id") for node in relationships
             if node.get("Type") == rel_ns + "/tags"}
    removed = 0
    for tag in list(slide.iter(p("tags"))):
        if tag.get("{" + rel_ns + "}id") not in valid:
            parent = tag.getparent()
            parent.remove(tag)
            if parent.tag == p("custDataLst") and len(parent) == 0:
                parent.getparent().remove(parent)
            removed += 1
    return removed


def worker_alive(pid):
    if type(pid) is not int or pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        try:
            code = wintypes.DWORD()
            return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


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
                    part = Path(member.filename)
                    rel_name = str(part.parent / "_rels" / (part.name + ".rels")).replace("\\", "/")
                    relationships = (etree.fromstring(original.read(rel_name), parser)
                                     if rel_name in original.namelist() else [])
                    repaired = remove_invalid_tags(xml, relationships)
                    items = stage_for_macos(xml, slide) if macos else hide_for_playback(xml, slide)
                    if items:
                        targets[str(index if macos else slide.slide_id)] = items
                    if items or repaired:
                        payload = etree.tostring(xml, encoding="UTF-8", xml_declaration=True)
                # writestr mutates header_offset; preserve the source archive's index
                # because slide relationships may be read again later in the loop.
                deck.writestr(copy(member), payload)
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
