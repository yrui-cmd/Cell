"""Native PowerPoint swarm preview. Simulated pointers, no system mouse or IME input.

Runs only the isolated, already-hidden copy supplied by play-elements. No API calls,
recording, order creation, timers or modifications to the received source file.
"""

import json
import time
from pathlib import Path
from hashlib import sha256
from contextlib import contextmanager
from pptx import Presentation

COLORS = [
    "0284C7",
    "7C3AED",
    "16A34A",
    "EA580C",
    "DB2777",
    "0891B2",
    "4F46E5",
    "CA8A04",
    "0D9488",
    "BE123C",
]
GRAPHIC_WORKERS = 4
TEXT_WORKERS = 6
FRAME_DELAY = 0.012


BUSY_ERRORS = {-2147418111, -2147417846}


def com_retry(action, timeout=8.0):
    """Retry only explicit RPC busy/rejected calls; other failures stay visible."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            return action()
        except Exception as error:
            if (
                getattr(error, "hresult", None) not in BUSY_ERRORS
                or time.monotonic() >= deadline
            ):
                raise
            time.sleep(0.04)


class ComObject:
    """Bounded busy-call recovery for nested Office objects and methods."""

    def __init__(self, obj):
        object.__setattr__(self, "_obj", obj)

    def __getattr__(self, name):
        value = com_retry(lambda: getattr(self._obj, name))
        if name == "_oleobj_":
            return value
        if hasattr(value, "_oleobj_"):
            return wrap_com(value)
        if callable(value):
            return lambda *a, **kw: wrap_com(com_retry(lambda: value(*a, **kw)))
        return wrap_com(value)

    def __setattr__(self, name, value):
        com_retry(lambda: setattr(self._obj, name, value))

    def __iter__(self):
        for n in range(1, self.Count + 1):
            yield self.Item(n)


def wrap_com(value):
    return ComObject(value) if hasattr(value, "_oleobj_") else value


def rgb(h):
    return int(h[:2], 16) + (int(h[2:4], 16) << 8) + (int(h[4:], 16) << 16)


def character_steps(text):
    from pypinyin import lazy_pinyin

    syllables = lazy_pinyin(text, errors=lambda chars: list(chars))
    if len(syllables) != len(text):
        raise ValueError("Pinyin character mapping is incomplete")
    offset = 1
    for char, syllable in zip(text, syllables):
        units = len(char.encode("utf-16-le")) // 2
        yield offset, units, char, syllable
        offset += units


def advance(streams):
    """Advance every independent cursor once, rather than drain one cursor first."""
    active = []
    for stream in streams:
        try:
            next(stream)
            active.append(stream)
        except StopIteration:
            pass
    return active


def content_signature(path):
    def shape(s):
        result = [
            s.shape_id,
            s.name,
            int(s.shape_type),
            *[round(v / 12700, 2) for v in (s.left, s.top, s.width, s.height)],
            round(s.rotation, 2),
        ]
        if s.has_text_frame:
            result.append(
                [
                    [
                        p.text,
                        [
                            [
                                r.text,
                                r.font.name,
                                r.font.size,
                                r.font.bold,
                                r.font.italic,
                            ]
                            for r in p.runs
                            if r.text
                        ],
                    ]
                    for p in s.text_frame.paragraphs
                ]
            )
        if s.shape_type == 6:
            result.append([shape(child) for child in s.shapes])
        return result

    return [[shape(s) for s in page.shapes] for page in Presentation(path).slides]


def validate_targets(deck, targets):
    slides = {str(s.SlideID): s for s in deck.Slides}
    if not isinstance(targets, dict):
        raise ValueError("Invalid playback targets")
    mapped = {}
    for page, ids in targets.items():
        if page not in slides or len(ids) != len(set(ids)):
            raise ValueError("Invalid playback slide or duplicate element")
        shapes = {s.Id: s for s in slides[page].Shapes}
        if any(type(i) is not int or i not in shapes for i in ids):
            raise ValueError("Preview element is missing")
        if any(shapes[i].Visible for i in ids):
            raise ValueError("Preview content must be hidden before opening")
        mapped[page] = [shapes[i] for i in ids]
    return slides, mapped


@contextmanager
def exclusive_playback():
    import win32event, win32api

    handle = win32event.CreateMutex(None, False, r"Local\CellPptElementPlayback")
    locked = False
    try:
        locked = win32event.WaitForSingleObject(handle, 0) in (0, 128)
        if not locked:
            raise RuntimeError("A PowerPoint playback session is already running")
        yield
    finally:
        if locked:
            win32event.ReleaseMutex(handle)
        win32api.CloseHandle(handle)


def prepare_page(slide, shapes, W, H, helpers):
    """Build helpers while the presentation has no window, never on page entry."""
    # Cache COM properties once. Keep all geometry inside the slide bounds.
    texts, graphics, info, clones = [], [], {}, {}
    paste_assets = set()
    for shape in shapes:
        sid = shape.Id
        x, y, w, h = map(float, (shape.Left, shape.Top, shape.Width, shape.Height))
        text = (
            shape.TextFrame.TextRange.Text
            if shape.HasTextFrame and shape.TextFrame.HasText
            else ""
        )
        info[sid] = (x, y, w, h, shape.ZOrderPosition, text)
        if text.strip():
            texts.append(shape)
            clone = shape.Duplicate().Item(1)
            helpers.append(clone)
            clone.Visible = 0
            clone.Left, clone.Top = x, y
            clone.TextFrame2.TextRange.Font.Fill.Transparency = 1.0
            clones[sid] = clone
        else:
            graphics.append(shape)
            # Pictures, linked pictures, grouped illustrations, charts/tables and SVGs.
            if int(shape.Type) in {3, 6, 11, 13, 19, 28, 29}:
                paste_assets.add(sid)
    pointers, bubbles = [], []
    for i, color in enumerate(COLORS):
        f = slide.Shapes.BuildFreeform(0, 0, 0)
        for a, b in [(0, 17), (4, 13), (8, 21), (12, 19), (8, 11), (16, 11), (0, 0)]:
            f.AddNodes(0, 0, a, b)
        c = f.ConvertToShape()
        c.Visible = 0
        c.Name = f"SwarmPointer{i}"
        c.Fill.ForeColor.RGB = rgb(color)
        c.Line.ForeColor.RGB = rgb("FFFFFF")
        c.Line.Weight = 0.75
        c.Left, c.Top = W * 0.5 + i * 12, H - 24
        pointers.append(c)
        helpers.append(c)
        b = slide.Shapes.AddTextbox(1, 0, 0, 88, 22)
        b.Visible = 0
        b.Name = f"SwarmPinyin{i}"
        b.Fill.Visible = -1
        b.Fill.ForeColor.RGB = rgb("FFFFFF")
        b.Line.Visible = -1
        b.Line.ForeColor.RGB = rgb(color)
        b.TextFrame.TextRange.Font.Size = 13
        b.TextFrame.TextRange.Font.Color.RGB = rgb(color)
        b.TextFrame.MarginTop = 1
        b.TextFrame.MarginBottom = 1
        bubbles.append(b)
        helpers.append(b)
    return texts, graphics, info, clones, paste_assets, pointers, bubbles


def page_stream(prepared, W, H, helpers, metrics):
    import win32com.client

    texts, graphics, info, clones, paste_assets, pointers, bubbles = prepared
    graphics.sort(key=lambda s: info[s.Id][4])
    tq, loads = [[] for _ in range(TEXT_WORKERS)], [0] * TEXT_WORKERS
    for shape in texts:
        lane = min(range(TEXT_WORKERS), key=lambda i: loads[i])
        tq[lane].append(shape)
        loads[lane] += len(info[shape.Id][5])
    gq = [graphics[i::GRAPHIC_WORKERS] for i in range(GRAPHIC_WORKERS)]
    drawn, active_kind = set(), {}
    parallel_text_frames = parallel_frames = 0

    def motion(c, tx, ty, steps=2):
        c.Visible = -1
        x0, y0 = float(c.Left), float(c.Top)
        for n in range(1, steps + 1):
            q = n / steps
            q = q * q * (3 - 2 * q)
            c.Left = x0 + (tx - x0) * q
            c.Top = y0 + (ty - y0) * q
            yield

    def graphic_worker(i, queue):
        c = pointers[i]
        bubble = bubbles[i]
        for s in queue:
            active_kind[i] = "graphic"
            x, y, sw, sh, *_ = info[s.Id]
            yield from motion(c, x, y, steps=1)
            if s.Id in paste_assets:
                bubble.Left = max(0, min(W - 90, x + 18))
                bubble.Top = max(0, min(H - 24, y - 24))
                bubble.TextFrame.TextRange.Text = "Ctrl+V"
                bubble.Visible = -1
                until = time.monotonic() + 0.10
                while time.monotonic() < until:
                    yield
            # Reveal the untouched native graphic once; no resize/duplicate/delete cycle.
            s.Visible = -1
            c.Left = min(W - 16, x + sw)
            c.Top = min(H - 22, y + sh)
            yield
            drawn.add(s.Id)
            if s.Id in paste_assets:
                until = time.monotonic() + 0.12
                while time.monotonic() < until:
                    yield
                bubble.Visible = 0
        active_kind.pop(i, None)
        c.Visible = 0
        bubble.Visible = 0

    def text_worker(i, queue):
        c = pointers[i]
        b = bubbles[i]
        for s in queue:
            # Wait for overlapping background graphics to avoid text appearing on an absent card.
            x, y, sw, sh, z, full = info[s.Id]
            parents = [
                g.Id
                for g in graphics
                if (
                    lambda a: a[2] > 20
                    and a[3] > 15
                    and a[4] < z
                    and a[0] <= x + 2
                    and a[1] <= y + 2
                    and a[0] + a[2] >= x + sw - 2
                    and a[1] + a[3] >= y + sh - 2
                )(info[g.Id])
            ]
            while any(k not in drawn for k in parents):
                active_kind[i] = "waiting"
                yield
            active_kind[i] = "text"
            yield from motion(c, x, y, steps=1)
            clone = clones[s.Id]
            clone.Visible = -1
            source_range = s.TextFrame.TextRange
            r = clone.TextFrame2.TextRange
            ole = r._oleobj_
            characters_id = com_retry(lambda: ole.GetIDsOfNames("Characters"))
            bubble_range = b.TextFrame.TextRange
            # Reveal original characters in place; wrapping, runs, font sizes and colors stay intact.
            for n, units, ch, py in character_steps(full):
                bounds = source_range.Characters(n, units)
                cx = max(
                    0, min(W - 18, float(bounds.BoundLeft) + float(bounds.BoundWidth))
                )
                cy = max(0, min(H - 24, float(bounds.BoundTop)))
                c.Left = cx
                c.Top = cy
                if "\u4e00" <= ch <= "\u9fff":
                    b.Left = max(0, min(W - 90, cx))
                    b.Top = cy + 24 if cy + 48 < H else cy - 24
                    for k in [len(py)]:
                        bubble_range.Text = py[:k]
                        b.Visible = -1
                        yield
                # Resolve the COM properties on the actual returned interface, avoiding
                # pywin32's cached wrapper choosing an unrelated Office collection class.
                char_ole = com_retry(lambda: ole.InvokeTypes(
                    characters_id, 0, 2, (9, 0), ((3, 49), (3, 49)), n, units
                ))
                font_ole = com_retry(lambda: char_ole.InvokeTypes(
                    char_ole.GetIDsOfNames("Font"), 0, 2, (9, 0), ()
                ))
                fill_ole = com_retry(lambda: font_ole.InvokeTypes(
                    font_ole.GetIDsOfNames("Fill"), 0, 2, (9, 0), ()
                ))
                com_retry(lambda: fill_ole.InvokeTypes(
                    fill_ole.GetIDsOfNames("Transparency"), 0, 4, (24, 0), ((4, 1),), 0.0
                ))
                b.Visible = 0
                yield
            s.Visible = -1
            clone.Visible = 0
        active_kind.pop(i, None)
        c.Visible = 0
        b.Visible = 0

    agents = [graphic_worker(i, gq[i]) for i in range(GRAPHIC_WORKERS)] + [
        text_worker(i + GRAPHIC_WORKERS, tq[i]) for i in range(TEXT_WORKERS)
    ]
    while agents:
        agents = advance(agents)
        if sum(v != "waiting" for v in active_kind.values()) > 1:
            parallel_frames += 1
        if sum(v == "text" for v in active_kind.values()) > 1:
            parallel_text_frames += 1
        yield
    # Hide only here. Delete in one final cleanup, never during typing.
    for helper in helpers:
        helper.Visible = 0

    metrics.update(
        parallel_frames=parallel_frames, parallel_text_frames=parallel_text_frames
    )


def run(manifest):
    import win32com.client, win32gui

    # Fail before opening PowerPoint if the optional platform dependency is missing.
    import pypinyin

    manifest = Path(manifest).resolve()
    state = json.loads(manifest.read_text(encoding="utf-8-sig"))
    copy, source = Path(state["copy"]).resolve(), Path(state["source"]).resolve()
    if (
        copy.parent != manifest.parent
        or copy == source
        or sha256(copy.read_bytes()).hexdigest() != state["copy_sha256"]
    ):
        raise ValueError("Invalid isolated preview copy")
    original_hash = sha256(source.read_bytes()).hexdigest()
    expected = content_signature(copy)
    helpers = {}
    metrics = {}
    app = deck = None
    with exclusive_playback():
        try:
            app = wrap_com(win32com.client.Dispatch("PowerPoint.Application"))
            app.Visible = True
            # No visible window while duplicating text or constructing cursor helpers.
            # These COM mutations otherwise repaint and re-fit the active slide repeatedly.
            deck = app.Presentations.Open(str(copy), False, False, False)
            slides, pending = validate_targets(deck, state["targets"])
            pending = {k: v for k, v in pending.items() if v}
            width, height = float(deck.PageSetup.SlideWidth), float(
                deck.PageSetup.SlideHeight
            )
            prepared = {}
            for page in pending:
                helpers[page] = []
                metrics[page] = {}
                prepared[page] = prepare_page(
                    slides[page], pending[page], width, height, helpers[page]
                )
            window = deck.NewWindow()
            window.Activate()
            window.WindowState = 3
            window.ViewType = 1
            window.View.ZoomToFit = True
            # Freeze this fitted scale before page transitions or transient text changes.
            fitted_zoom = window.View.Zoom
            window.View.ZoomToFit = False
            window.View.Zoom = fitted_zoom
            if pending:
                window.View.GotoSlide(min(slides[k].SlideIndex for k in pending))
            import win32process
            from transfer import write
            from window_recording import matches_preview_title
            preview_windows = []
            win32gui.EnumWindows(
                lambda hwnd, _: preview_windows.append(hwnd)
                if matches_preview_title(win32gui.GetWindowText(hwnd), copy) else None,
                None,
            )
            if len(preview_windows) != 1:
                raise RuntimeError("Cannot uniquely identify the PowerPoint preview window")
            preview_hwnd = preview_windows[0]
            write(manifest.parent / "window-ready.json", {
                "job_id": state["job_id"], "run_id": state["run_id"],
                "hwnd": preview_hwnd,
                "pid": win32process.GetWindowThreadProcessId(preview_hwnd)[1],
            })
            print("ELEMENT_PLAYBACK_EDITOR_OPEN", flush=True)
            if state.get("recording_gate"):
                gate = manifest.parent / "recording.started"
                deadline = time.monotonic() + 900
                while not gate.exists():
                    if (manifest.parent / "playback.cancel").exists():
                        raise RuntimeError("Playback cancelled before recording")
                    if time.monotonic() >= deadline:
                        raise RuntimeError(
                            "Recording did not start; playback cancelled"
                        )
                    time.sleep(0.05)
            streams = {}
            started = time.monotonic()
            waiting = False
            last_view_check = 0.0
            slide = window.View.Slide
            active = window
            while pending:
                if (manifest.parent / "playback.cancel").exists():
                    raise RuntimeError("Playback cancelled")
                foreground = win32gui.GetAncestor(win32gui.GetForegroundWindow(), 2)
                if foreground != preview_hwnd or win32gui.IsIconic(preview_hwnd):
                    if not waiting:
                        print("ELEMENT_PLAYBACK_WAITING_FOR_FOREGROUND", flush=True)
                        waiting = True
                    time.sleep(0.1)
                    continue
                if waiting:
                    print("ELEMENT_PLAYBACK_FOREGROUND_READY", flush=True)
                    waiting = False
                if time.monotonic() - last_view_check > 0.25:
                    slide = active.View.Slide
                    last_view_check = time.monotonic()
                page = str(slide.SlideID)
                if page not in pending:
                    time.sleep(0.1)
                    continue
                if page not in streams:
                    streams[page] = page_stream(
                        prepared[page],
                        width,
                        height,
                        helpers[page],
                        metrics[page],
                    )
                    print(
                        f"ELEMENT_PLAYBACK_PAGE_BEGIN|{slide.SlideIndex}|{int((time.monotonic()-started)*1000)}",
                        flush=True,
                    )
                try:
                    next(streams[page])
                except StopIteration:
                    del pending[page]
                    print(
                        f"ELEMENT_PLAYBACK_PAGE_DONE|{slide.SlideIndex}|{int((time.monotonic()-started)*1000)}",
                        flush=True,
                    )
                    # Respect a manual page switch; resume the other page on its next frame.
                    if pending and str(active.View.Slide.SlideID) == page:
                        later = sorted(pending, key=lambda p: slides[p].SlideIndex)
                        next_page = next(
                            (
                                p
                                for p in later
                                if slides[p].SlideIndex > slide.SlideIndex
                            ),
                            later[0],
                        )
                        active.View.GotoSlide(slides[next_page].SlideIndex)
                        slide = slides[next_page]
                        last_view_check = time.monotonic()
                time.sleep(FRAME_DELAY)
            # All helpers are already hidden. One cleanup after every page has finished.
            for page_helpers in helpers.values():
                for helper in page_helpers:
                    helper.Delete()
                page_helpers.clear()
            deck.Save()
            if content_signature(copy) != expected:
                raise RuntimeError("Preview content or geometry changed during output")
            if sha256(source.read_bytes()).hexdigest() != original_hash:
                raise RuntimeError("Received source changed during output")
            restored = Presentation(copy)
            for page in restored.slides:
                ids = state["targets"].get(str(page.slide_id), [])
                for shape in page.shapes:
                    if shape.shape_id in ids and shape._element[0].find(
                        "{http://schemas.openxmlformats.org/presentationml/2006/main}cNvPr"
                    ).get("hidden") in {"1", "true"}:
                        raise RuntimeError("A preview element remains hidden")
            print("ELEMENT_PLAYBACK_SWARM_METRICS|" + json.dumps(metrics), flush=True)
            print("ELEMENT_PLAYBACK_WORKER_FINISHED", flush=True)
        finally:
            # Failed previews stay recoverable; never leave simulated cursors in saved output.
            if deck is not None:
                for page_helpers in helpers.values():
                    for helper in page_helpers:
                        try:
                            helper.Delete()
                        except Exception:
                            pass
                try:
                    for slide in deck.Slides:
                        ids = state["targets"].get(str(slide.SlideID), [])
                        for shape in slide.Shapes:
                            if shape.Id in ids:
                                shape.Visible = -1
                    deck.Save()
                except Exception:
                    pass
    return 0


if __name__ == "__main__":
    import sys

    raise SystemExit(run(sys.argv[1]))
