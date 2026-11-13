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

COLORS = ["0284C7", "7C3AED", "16A34A", "EA580C", "DB2777", "0891B2", "4F46E5"]
FRAME_DELAY = 0.012


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


def page_stream(slide, shapes, W, H, helpers, metrics):
    import win32com.client

    pointers = []
    bubbles = []
    for i, color in enumerate(COLORS):
        f = slide.Shapes.BuildFreeform(0, -200, -200)
        for a, b in [(0, 17), (4, 13), (8, 21), (12, 19), (8, 11), (16, 11), (0, 0)]:
            f.AddNodes(0, 0, a - 200, b - 200)
        c = f.ConvertToShape()
        c.Visible = 0
        c.Name = f"SwarmPointer{i}"
        c.Fill.ForeColor.RGB = rgb(color)
        c.Line.ForeColor.RGB = rgb("FFFFFF")
        c.Line.Weight = 0.75
        c.Left = W * 0.5 + i * 18
        c.Top = H - 24
        pointers.append(c)
        helpers.append(c)
        b = slide.Shapes.AddTextbox(1, -200, -200, 88, 22)
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
        b.Visible = 0
        bubbles.append(b)
        helpers.append(b)
    # Four independent typography workers and three graphic workers.
    texts = []
    graphics = []
    for s in shapes:
        if (
            s.HasTextFrame
            and s.TextFrame.HasText
            and s.TextFrame.TextRange.Text.strip()
        ):
            texts.append(s)
        else:
            graphics.append(s)
    graphics.sort(key=lambda s: (s.ZOrderPosition,))
    tq = [[] for _ in range(4)]
    loads = [0] * 4
    for s in texts:
        lane = min(range(4), key=lambda i: loads[i])
        tq[lane].append(s)
        loads[lane] += len(s.TextFrame.TextRange.Text)
    gq = [graphics[i::3] for i in range(3)]
    drawn = set()
    active_kind = {}
    parallel_text_frames = 0
    parallel_frames = 0

    def motion(c, tx, ty, steps=2):
        c.Visible = -1
        x0, y0 = float(c.Left), float(c.Top)
        for n in range(1, steps + 1):
            q = n / steps
            q = q * q * (3 - 2 * q)
            c.Left = x0 + (tx - x0) * q
            c.Top = y0 + (ty - y0) * q
            c.ZOrder(0)
            yield

    def graphic_worker(i, queue):
        c = pointers[i]
        for s in queue:
            active_kind[i] = "graphic"
            x, y, sw, sh = map(float, (s.Left, s.Top, s.Width, s.Height))
            yield from motion(c, x, y)
            # Preview through a copy; the original is never resized or reordered.
            clone = s.Duplicate().Item(1)
            helpers.append(clone)
            clone.Visible = -1
            clone.LockAspectRatio = 0
            for n in range(1, 5):
                q = n / 4
                clone.Width = max(0.5, sw * q)
                clone.Height = max(0.5, sh * q)
                clone.Left = x
                clone.Top = y
                c.Left = min(W - 16, x + sw * q)
                c.Top = min(H - 22, y + sh * q)
                c.ZOrder(0)
                yield
            s.Visible = -1
            clone.Delete()
            helpers.remove(clone)
            drawn.add(s.Id)
        active_kind.pop(i, None)
        c.Visible = 0

    def text_worker(i, queue):
        c = pointers[i]
        b = bubbles[i]
        for s in queue:
            # Wait for overlapping background graphics to avoid text appearing on an absent card.
            parents = [
                g.Id
                for g in graphics
                if g.Width > 20
                and g.Height > 15
                and g.ZOrderPosition < s.ZOrderPosition
                and g.Left <= s.Left + 2
                and g.Top <= s.Top + 2
                and g.Left + g.Width >= s.Left + s.Width - 2
                and g.Top + g.Height >= s.Top + s.Height - 2
            ]
            while any(k not in drawn for k in parents):
                active_kind[i] = "waiting"
                yield
            active_kind[i] = "text"
            x, y = float(s.Left), float(s.Top)
            yield from motion(c, x, y)
            clone = s.Duplicate().Item(1)
            helpers.append(clone)
            clone.Visible = 0
            clone.Left = x
            clone.Top = y
            full = s.TextFrame.TextRange.Text
            clone.TextFrame2.TextRange.Font.Fill.Transparency = 1.0
            clone.Visible = -1
            # Reveal original characters in place; wrapping, runs, font sizes and colors stay intact.
            for n, units, ch, py in character_steps(full):
                bounds = s.TextFrame.TextRange.Characters(n, units)
                cx = max(
                    0, min(W - 18, float(bounds.BoundLeft) + float(bounds.BoundWidth))
                )
                cy = max(0, min(H - 24, float(bounds.BoundTop)))
                c.Left = cx
                c.Top = cy
                c.ZOrder(0)
                if "\u4e00" <= ch <= "\u9fff":
                    b.Left = max(0, min(W - 90, cx))
                    b.Top = cy + 24 if cy + 48 < H else cy - 24
                    for k in [len(py)]:
                        b.TextFrame.TextRange.Text = py[:k]
                        b.Visible = -1
                        b.ZOrder(0)
                        yield
                r = clone.TextFrame2.TextRange
                char_range = win32com.client.Dispatch(
                    r._oleobj_.InvokeTypes(
                        r._oleobj_.GetIDsOfNames("Characters"),
                        0,
                        2,
                        (9, 0),
                        ((3, 49), (3, 49)),
                        n,
                        units,
                    )
                )
                char_range.Font.Fill.Transparency = 0.0
                b.Visible = 0
                yield
            s.Visible = -1
            clone.Delete()
            helpers.remove(clone)
        active_kind.pop(i, None)
        c.Visible = 0
        b.Visible = 0

    agents = [graphic_worker(i, gq[i]) for i in range(3)] + [
        text_worker(i + 3, tq[i]) for i in range(4)
    ]
    while agents:
        agents = advance(agents)
        if sum(v != "waiting" for v in active_kind.values()) > 1:
            parallel_frames += 1
        if sum(v == "text" for v in active_kind.values()) > 1:
            parallel_text_frames += 1
        yield
    for helper in list(helpers):
        helper.Delete()
    helpers.clear()

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
            app = win32com.client.Dispatch("PowerPoint.Application")
            app.Visible = True
            deck = app.Presentations.Open(str(copy), False, False, True)
            window = deck.Windows.Item(1)
            window.Activate()
            window.ViewType = 1
            slides, pending = validate_targets(deck, state["targets"])
            pending = {k: v for k, v in pending.items() if v}
            width, height = float(deck.PageSetup.SlideWidth), float(
                deck.PageSetup.SlideHeight
            )
            if pending:
                window.View.GotoSlide(min(slides[k].SlideIndex for k in pending))
            print("ELEMENT_PLAYBACK_EDITOR_OPEN", flush=True)
            streams = {}
            started = time.monotonic()
            waiting = False
            while pending:
                if not deck.Windows.Count:
                    raise RuntimeError(
                        "The preview window closed before output finished"
                    )
                foreground = win32gui.GetWindowText(win32gui.GetForegroundWindow())
                active = app.ActiveWindow
                if (
                    not any(
                        foreground.startswith(name + " - ")
                        for name in (copy.name, copy.stem)
                    )
                    or not active
                    or Path(active.Presentation.FullName).resolve() != copy
                ):
                    if not waiting:
                        print("ELEMENT_PLAYBACK_WAITING_FOR_FOREGROUND", flush=True)
                        waiting = True
                    time.sleep(0.1)
                    continue
                if waiting:
                    print("ELEMENT_PLAYBACK_FOREGROUND_READY", flush=True)
                    waiting = False
                slide = active.View.Slide
                page = str(slide.SlideID)
                if page not in pending:
                    time.sleep(0.1)
                    continue
                if page not in streams:
                    helpers[page] = []
                    metrics[page] = {}
                    streams[page] = page_stream(
                        slide,
                        pending[page],
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
                time.sleep(FRAME_DELAY)
            # Native originals alone remain; temporary text never changes their formatting.
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
