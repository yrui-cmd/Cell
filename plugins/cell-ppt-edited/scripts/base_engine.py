"""Independent, single-threaded PowerPoint COM engine. No third-party plugin code."""
from __future__ import annotations

import base64
import hashlib
import json
import math
import os
from pathlib import Path
import re
import time
import uuid
from collections import OrderedDict, defaultdict


class EditError(Exception):
    def __init__(self, message, details=None):
        super().__init__(message)
        self.details = details or {}


def absolute_path(value, suffix=None):
    p = Path(value).expanduser()
    if not p.is_absolute():
        raise EditError("An absolute file path is required.")
    p = p.resolve()
    if suffix and p.suffix.lower() not in suffix:
        raise EditError("Unexpected file extension.")
    return p


def path_key(value):
    return os.path.normcase(str(Path(value).resolve()))


def rgb(value):
    if not isinstance(value, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        raise EditError("Colors must be #RRGGBB.")
    r, g, b = (int(value[i:i+2], 16) for i in (1, 3, 5))
    return r | (g << 8) | (b << 16)


def hex_rgb(value):
    v = int(value)
    return f"#{v & 255:02X}{(v >> 8) & 255:02X}{(v >> 16) & 255:02X}"


GEOMETRY = {"left": "Left", "top": "Top", "width": "Width", "height": "Height", "rotation": "Rotation"}
PROPERTIES = set(GEOMETRY) | {"fill_color", "line_color", "line_width", "text", "font_color", "font_size", "bold"}


def validate_patch(patch):
    if not isinstance(patch, dict) or set(patch) - {"name", "id", "set", "expected"}:
        raise EditError("A patch accepts name or id, set, and optional expected.")
    if ("name" in patch) == ("id" in patch):
        raise EditError("Specify exactly one of name or id.")
    if "name" in patch and (not isinstance(patch["name"], str) or not patch["name"]):
        raise EditError("Shape name must be nonempty.")
    if "id" in patch and (type(patch["id"]) is not int or patch["id"] < 1):
        raise EditError("Shape id must be a positive integer.")
    values = patch.get("set")
    if not isinstance(values, dict) or not values or set(values) - PROPERTIES:
        raise EditError("Unsupported or empty property patch.")
    for key, value in values.items():
        if key.endswith("_color"):
            rgb(value)
        elif key in GEOMETRY or key in {"line_width", "font_size"}:
            if type(value) not in (int, float) or not math.isfinite(value):
                raise EditError("Numeric properties must be finite numbers.")
            if key in {"width", "height", "font_size"} and value <= 0:
                raise EditError(f"{key} must be positive.")
            if key == "line_width" and value < 0:
                raise EditError("line_width cannot be negative.")
        elif key == "bold" and type(value) is not bool:
            raise EditError("bold must be boolean.")
        elif key == "text" and (not isinstance(value, str) or len(value) > 100000):
            raise EditError("text must be a string of at most 100000 characters.")
    expected = patch.get("expected", {})
    if not isinstance(expected, dict) or set(expected) - PROPERTIES:
        raise EditError("Unsupported expected property.")
    return values


class Engine:
    def __init__(self, application=None):
        self.application = application
        self.sessions = {}
        self.receipts = OrderedDict()
        self.started = time.perf_counter()
        self.com_initialized = False

    def app(self, create=False):
        if self.application is None:
            import pythoncom
            from win32com.client import GetActiveObject, DispatchEx
            if not self.com_initialized:
                pythoncom.CoInitialize()
                self.com_initialized = True
            try:
                self.application = GetActiveObject("PowerPoint.Application")
            except Exception as exc:
                if not create:
                    raise EditError("PowerPoint is not running. Bind an existing file to open it.") from exc
                self.application = DispatchEx("PowerPoint.Application")
        return self.application

    def documents(self):
        try:
            app = self.app()
        except EditError:
            return {"documents": [], "running": False, "process_id": os.getpid()}
        result = []
        for i in range(1, app.Presentations.Count + 1):
            p = app.Presentations.Item(i)
            result.append({"name": p.Name, "path": p.FullName, "saved": bool(p.Saved), "slides": p.Slides.Count})
        return {"documents": result, "backend": "independent-pywin32-COM", "process_id": os.getpid()}

    def bind(self, path, mode="copy", output_path=None):
        if mode not in {"copy", "in_place", "read_only"}:
            raise EditError("mode must be copy, in_place, or read_only.")
        source = absolute_path(path, {".pptx", ".pptm", ".ppsx"})
        if not source.is_file():
            raise EditError("Presentation file does not exist.")
        app = self.app(create=True)
        doc = None
        for i in range(1, app.Presentations.Count + 1):
            candidate = app.Presentations.Item(i)
            if path_key(candidate.FullName) == path_key(source):
                doc = candidate
                break
        if doc is None:
            if not source.is_file():
                raise EditError("Presentation file does not exist.")
            doc = app.Presentations.Open(str(source), mode == "read_only", False, True)
        target = source
        if mode == "copy":
            if not output_path:
                raise EditError("copy mode requires an explicit new output_path.")
            target = absolute_path(output_path, {".pptx"})
            if target.exists() or path_key(target) == path_key(source):
                raise EditError("Output copy must be a new path different from the source.")
            if source.suffix.lower() == ".pptm":
                raise EditError("Macro-enabled decks require explicit in_place/read_only mode; conversion is not implicit.")
            target.parent.mkdir(parents=True, exist_ok=True)
            doc.SaveCopyAs(str(target), 24)
            doc = app.Presentations.Open(str(target), False, False, True)
        elif output_path is not None:
            raise EditError("output_path is used only with copy mode.")
        if mode != "read_only" and bool(doc.ReadOnly):
            raise EditError("The selected presentation is read-only.")
        token = uuid.uuid4().hex
        self.sessions[token] = {"doc": doc, "path": str(target), "source": str(source), "mode": mode, "indexes": {}, "selection": None}
        return {"session_id": token, "path": str(target), "source": str(source), "mode": mode,
                "slides": doc.Slides.Count, "slide_width": doc.PageSetup.SlideWidth,
                "slide_height": doc.PageSetup.SlideHeight, "backend": "independent-pywin32-COM", "process_id": os.getpid()}

    def session(self, session_id, write=False):
        if session_id not in self.sessions:
            raise EditError("Unknown session. Bind this document once in this server process.")
        s = self.sessions[session_id]
        try:
            if path_key(s["doc"].FullName) != path_key(s["path"]):
                raise EditError("Bound document identity changed. Rebind explicitly.")
            _ = s["doc"].Slides.Count
        except EditError:
            raise
        except Exception as exc:
            raise EditError("Bound document is no longer open. Rebind explicitly; no active-window fallback.") from exc
        if write and s["mode"] == "read_only":
            raise EditError("This session is read-only.")
        return s

    def slide(self, s, slide_index):
        if type(slide_index) is not int or not 1 <= slide_index <= s["doc"].Slides.Count:
            raise EditError("Invalid one-based slide_index.")
        return s["doc"].Slides.Item(slide_index)

    def resolve(self, s, slide, selector):
        shapes = slide.Shapes
        if "name" in selector:
            # PowerPoint's native lookup avoids a Python/COM full-slide scan.
            try:
                shape = shapes.Item(selector["name"])
                if str(shape.Name) != selector["name"]:
                    raise EditError("Shape name mismatch.")
                return shape
            except Exception as exc:
                raise EditError(f"Shape not found: {selector['name']}") from exc
        count = shapes.Count
        key = int(slide.SlideID)
        index = s["indexes"].get(key)
        if index is None or index["count"] != count:
            names = {}
            for i in range(1, count + 1):
                obj = shapes.Item(i)
                names[int(obj.Id)] = str(obj.Name)
            index = {"count": count, "names": names}
            s["indexes"][key] = index
        name = index["names"].get(selector["id"])
        if name is None:
            raise EditError("Shape id not found. Inspect target names first.")
        try:
            shape = shapes.Item(name)
            if int(shape.Id) == selector["id"]:
                return shape
        except Exception:
            pass
        s["indexes"].pop(key, None)
        raise EditError("Shape index became stale; inspect/retry the exact target.")

    def value(self, shape, prop):
        if prop in GEOMETRY:
            return round(float(getattr(shape, GEOMETRY[prop])), 4)
        if prop == "fill_color":
            if int(shape.Fill.Type) != 1 or not bool(shape.Fill.Visible):
                raise EditError("fill_color patches currently require an existing visible solid fill.")
            return hex_rgb(shape.Fill.ForeColor.RGB)
        if prop == "line_color":
            return hex_rgb(shape.Line.ForeColor.RGB)
        if prop == "line_width":
            return float(shape.Line.Weight) if shape.Line.Visible else 0.0
        if not shape.HasTextFrame:
            raise EditError("Target does not have a native text frame.")
        tr = shape.TextFrame.TextRange
        if prop == "text":
            if tr.Runs().Count > 1:
                raise EditError("Mixed-run text replacement is unsupported; formatting would be ambiguous.")
            return str(tr.Text)
        if prop == "font_color":
            return hex_rgb(tr.Font.Color.RGB)
        if prop == "font_size":
            return float(tr.Font.Size)
        if prop == "bold":
            return bool(tr.Font.Bold)
        raise EditError("Unsupported property.")

    def summary(self, obj, detail=False):
        r = {"id": int(obj.Id), "name": str(obj.Name), "type": int(obj.Type)}
        if detail:
            r.update({key: round(float(getattr(obj, attr)), 4) for key, attr in GEOMETRY.items()})
            if obj.HasTextFrame:
                r["text"] = str(obj.TextFrame.TextRange.Text)
            if int(obj.Fill.Type) == 1 and obj.Fill.Visible:
                r["fill_color"] = hex_rgb(obj.Fill.ForeColor.RGB)
            r["group_count"] = obj.GroupItems.Count if int(obj.Type) == 6 else 0
        return r

    def inspect(self, session_id, slide_index=1, names=None, offset=0, limit=100, detail=False):
        s = self.session(session_id)
        slide = self.slide(s, slide_index)
        count = slide.Shapes.Count
        if names is not None:
            if not isinstance(names, list) or not 1 <= len(names) <= 500 or len(set(names)) != len(names):
                raise EditError("names must contain 1..500 unique shape names.")
            objects = [self.resolve(s, slide, {"name": n}) for n in names]
        else:
            if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 2500:
                raise EditError("Invalid pagination.")
            objects = [slide.Shapes.Item(i) for i in range(offset + 1, min(count, offset + limit) + 1)]
        return {"path": s["path"], "slide_index": slide_index, "shape_count": count,
                "shapes": [self.summary(obj, detail) for obj in objects],
                "next_offset": offset + len(objects) if names is None and offset + len(objects) < count else None}

    def selection(self, session_id):
        s = self.session(session_id)
        # Selection belongs to this bound presentation's own window, not ActiveWindow.
        try:
            window = s["doc"].Windows.Item(1)
            selection = window.Selection
            objects = selection.ShapeRange
            result = [self.summary(objects.Item(i), True) for i in range(1, objects.Count + 1)]
            slide_index = int(window.View.Slide.SlideIndex)
            s["selection"] = {"slide_index": slide_index, "names": [o["name"] for o in result]}
            return {"path": s["path"], "slide_index": slide_index, "shapes": result}
        except Exception as exc:
            raise EditError("No shape selection in the bound presentation window.") from exc

    def _assign(self, shape, prop, value):
        if prop in GEOMETRY:
            if prop in {"width", "height"} and shape.LockAspectRatio:
                lock = shape.LockAspectRatio
                shape.LockAspectRatio = 0
                try:
                    setattr(shape, GEOMETRY[prop], value)
                finally:
                    shape.LockAspectRatio = lock
            else:
                setattr(shape, GEOMETRY[prop], value)
        elif prop == "fill_color":
            shape.Fill.ForeColor.RGB = rgb(value)
        elif prop == "line_color":
            shape.Line.ForeColor.RGB = rgb(value)
        elif prop == "line_width":
            shape.Line.Visible = -1 if value else 0
            if value:
                shape.Line.Weight = value
        elif prop == "text":
            shape.TextFrame.TextRange.Text = value
        else:
            font = shape.TextFrame.TextRange.Font
            if prop == "font_color":
                font.Color.RGB = rgb(value)
            elif prop == "font_size":
                font.Size = value
            elif prop == "bold":
                font.Bold = -1 if value else 0

    def patch(self, session_id, slide_index, patches, request_id, save=False):
        if not isinstance(request_id, str) or not request_id or len(request_id) > 200:
            raise EditError("A stable request_id is required for retry protection.")
        if not isinstance(patches, list) or not 1 <= len(patches) <= 500:
            raise EditError("patches must contain 1..500 entries.")
        for p in patches:
            validate_patch(p)
        signature = hashlib.sha256(json.dumps([session_id, slide_index, patches, save], sort_keys=True).encode()).hexdigest()
        if request_id in self.receipts:
            prior = self.receipts[request_id]
            if prior[0] != signature:
                raise EditError("request_id was already used for a different request.")
            return {**prior[1], "replayed": True}
        s = self.session(session_id, write=True)
        slide = self.slide(s, slide_index)
        count = slide.Shapes.Count
        prepared, seen = [], set()
        for p in patches:
            shape = self.resolve(s, slide, p)
            shape_id = int(shape.Id)
            if shape_id in seen:
                raise EditError("Duplicate target in batch; merge its properties into one patch.")
            seen.add(shape_id)
            before = {k: self.value(shape, k) for k in p["set"]}
            for key, expected in p.get("expected", {}).items():
                actual = before[key] if key in before else self.value(shape, key)
                matches = math.isclose(actual, expected, abs_tol=0.01) if type(actual) in (int, float) and type(expected) in (int, float) else actual == expected
                if not matches:
                    raise EditError("Target changed since inspection.", {"name": shape.Name, "property": key, "actual": actual, "expected": expected})
            prepared.append({"shape": shape, "id": shape_id, "name": str(shape.Name), "set": p["set"], "before": before})
        grouped = defaultdict(list)
        for item in prepared:
            if "fill_color" in item["set"]:
                grouped[item["set"]["fill_color"].upper()].append(item["name"])
        started = time.perf_counter()
        completed, attempted, fill_calls = [], [], 0
        try:
            for color, names in grouped.items():
                attempted.extend(names)
                if len(names) == 1:
                    slide.Shapes.Item(names[0]).Fill.ForeColor.RGB = rgb(color)
                else:
                    import pythoncom
                    from win32com.client import VARIANT
                    arr = VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_VARIANT, tuple(names))
                    slide.Shapes.Range(arr).Fill.ForeColor.RGB = rgb(color)
                fill_calls += 1
            for item in prepared:
                for prop, value in item["set"].items():
                    if prop != "fill_color":
                        attempted.append(item["name"])
                        self._assign(item["shape"], prop, value)
                actual = {k: self.value(item["shape"], k) for k in item["set"]}
                for key, value in item["set"].items():
                    wanted = value.upper() if key.endswith("_color") else value
                    got = actual[key]
                    good = math.isclose(got, wanted, abs_tol=0.02) if type(got) in (float, int) and type(wanted) in (float, int) else got == wanted
                    if not good:
                        raise EditError("PowerPoint readback mismatch.", {"name": item["name"], "property": key, "expected": wanted, "actual": got})
                completed.append({"id": item["id"], "name": item["name"], "before": item["before"], "after": actual})
            if slide.Shapes.Count != count:
                raise EditError("External structural edit occurred during this batch.")
            if save:
                s["doc"].Save()
            result = {"status": "applied", "path": s["path"], "slide_index": slide_index, "objects_updated": len(completed),
                      "fill_write_calls": fill_calls, "shape_count": count, "changes": completed, "saved": bool(save),
                      "apply_ms": round((time.perf_counter() - started) * 1000, 3), "replayed": False}
        except Exception as exc:
            # Native batches are not transactional. Never conceal a partial write or automatically retry it.
            result = {"status": "partial_or_uncertain", "path": s["path"], "error": str(exc), "completed": completed,
                      "attempted_names": sorted(set(attempted)), "saved": False, "requires_inspection": True}
        self.receipts[request_id] = (signature, result)
        while len(self.receipts) > 512:
            self.receipts.popitem(last=False)
        return result

    def save(self, session_id, output_path=None):
        s = self.session(session_id, write=True)
        if output_path:
            p = absolute_path(output_path, {".pptx"})
            if p.exists():
                raise EditError("Refusing to overwrite an existing copy. Omit output_path to save the bound document.")
            if Path(s["path"]).suffix.lower() == ".pptm":
                raise EditError("Implicit macro removal is unsupported.")
            p.parent.mkdir(parents=True, exist_ok=True)
            s["doc"].SaveCopyAs(str(p), 24)
            return {"saved": True, "path": str(p), "bound_path": s["path"]}
        s["doc"].Save()
        return {"saved": True, "path": s["path"]}

    def export(self, session_id, slide_index, output_path, width=1200, overwrite=False, include_image=False):
        s = self.session(session_id)
        slide = self.slide(s, slide_index)
        p = absolute_path(output_path, {".png"})
        if p.exists() and not overwrite:
            raise EditError("Preview file already exists; pass overwrite=true.")
        if type(width) is not int or not 64 <= width <= 4096:
            raise EditError("Preview width must be 64..4096.")
        height = round(width * s["doc"].PageSetup.SlideHeight / s["doc"].PageSetup.SlideWidth)
        p.parent.mkdir(parents=True, exist_ok=True)
        slide.Export(str(p), "PNG", width, height)
        result = {"path": str(p), "width": width, "height": height, "bytes": p.stat().st_size, "renderer": "Microsoft PowerPoint"}
        if include_image:
            result["_image"] = base64.b64encode(p.read_bytes()).decode("ascii")
        return result

    def status(self):
        return {"backend": "independent-pywin32-COM", "process_id": os.getpid(),
                "uptime_seconds": round(time.perf_counter() - self.started, 3),
                "sessions": [{"session_id": key, "path": s["path"], "mode": s["mode"]} for key, s in self.sessions.items()],
                "persistent": True, "active_window_used_for_mutations": False, "receipt_count": len(self.receipts)}

    def shutdown(self):
        # Release our references only. Never close user documents or quit PowerPoint.
        self.sessions.clear()
        self.application = None
        if self.com_initialized:
            import pythoncom
            pythoncom.CoUninitialize()
            self.com_initialized = False
