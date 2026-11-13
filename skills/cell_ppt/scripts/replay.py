"""One-command local replay; no API request, upload, fee or scheduled task."""

import argparse
import json
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

from handoff import sha
from playback import prepare, launch, worker_alive
from output_worker import result_for
from transfer import read, write


def resolve_source(source, order_root, thread_id):
    if order_root:
        order_root = Path(order_root).resolve()
        order = read(order_root / "order.json")
        receipt = read(order_root / "return-ready.json")
        if (
            not thread_id
            or order.get("thread_id") != thread_id
            or receipt.get("thread_id") != thread_id
            or order.get("job_id") != receipt.get("job_id")
            or order.get("billing") != "settled"
        ):
            raise ValueError("Original order/chat binding does not match")
        path = Path(receipt["path"]).resolve()
        if sha(path) != receipt["sha256"]:
            raise ValueError("Saved PPT does not match its received checksum")
        return path, order["job_id"], order_root
    path = Path(source).resolve()
    if not path.is_file() or path.suffix.lower() != ".pptx":
        raise ValueError("Provide an existing PPTX")
    return path, "local-replay-" + uuid.uuid4().hex, path.parent


def run(args):
    if sys.platform != "win32":
        raise ValueError("This local multi-pointer replay requires Windows PowerPoint")
    source, job, parent = resolve_source(args.source, args.order_root, args.thread_id)
    ffmpeg = shutil.which("ffmpeg") if args.record == "yes" else None
    if args.record == "yes" and not ffmpeg:
        raise ValueError("FFmpeg is required for the requested recording")
    import pypinyin  # Validate before starting Office.
    import win32com.client
    import win32gui

    root = (
        Path(args.output_dir).resolve()
        if args.output_dir
        else parent
        / ("replay_" + time.strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:4])
    )
    root.mkdir(parents=True, exist_ok=False)
    copy = root / ("PPT-replay-" + uuid.uuid4().hex[:8] + ".pptx")
    targets = prepare(source, copy)
    manifest = root / "element-playback-state.json"
    state = {
        "job_id": job,
        "run_id": uuid.uuid4().hex,
        "thread_id": args.thread_id,
        "source": str(source),
        "source_sha256": sha(source),
        "copy": str(copy),
        "copy_sha256": sha(copy),
        "targets": targets,
        "replay": True,
        "recording_gate": args.record == "yes",
    }
    write(manifest, state)
    write(
        root / "recording-choice.json",
        {"record": args.record == "yes", "response_source": args.response_source},
    )
    state["worker_pid"] = launch(manifest)
    write(manifest, state)
    print(json.dumps({"replay_dir": str(root)}, ensure_ascii=False), flush=True)
    recorder = log = None
    recording_started = False
    status = None
    try:
        deadline = time.monotonic() + 900
        last_page = ""
        focus_prompted = False
        while time.monotonic() < deadline:
            path = root / "element-playback.log"
            content = (
                path.read_text(encoding="utf-8", errors="replace")
                if path.exists()
                else ""
            )
            if (
                args.record == "yes"
                and not recorder
                and "ELEMENT_PLAYBACK_EDITOR_OPEN" in content
            ):
                if not win32gui.GetWindowText(
                    win32gui.GetForegroundWindow()
                ).startswith(copy.name + " - "):
                    if not focus_prompted:
                        print(
                            "请切到 PPT-replay 的 PowerPoint 窗口，录屏和展示将自动开始。",
                            flush=True,
                        )
                        focus_prompted = True
                    if result_for(root, state):
                        status = result_for(root, state)
                        break
                    time.sleep(0.2)
                    continue
                log = (root / "recording.log").open("wb")
                command = [
                    ffmpeg,
                    "-hide_banner",
                    "-nostats",
                    "-f",
                    "gdigrab",
                    "-framerate",
                    "20",
                    "-draw_mouse",
                    "0",
                    "-i",
                    "title=" + copy.name + " - PowerPoint",
                    "-an",
                    "-vf",
                    "pad=ceil(iw/2)*2:ceil(ih/2)*2",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "ultrafast",
                    "-crf",
                    "23",
                    "-pix_fmt",
                    "yuv420p",
                    "-movflags",
                    "+frag_keyframe+empty_moov",
                    "-g",
                    "40",
                    "-progress",
                    str(root / "recording-progress.txt"),
                    str(root / "PPT-output.mp4"),
                ]
                recorder = subprocess.Popen(
                    command,
                    stdin=subprocess.PIPE,
                    stdout=log,
                    stderr=log,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            if recorder:
                if recorder.poll() is not None:
                    raise RuntimeError(
                        "Recording stopped unexpectedly; see recording.log"
                    )
                progress = root / "recording-progress.txt"
                if not recording_started and progress.exists():
                    fields = dict(
                        line.split("=", 1)
                        for line in progress.read_text().splitlines()
                        if "=" in line
                    )
                    if int(fields.get("frame", "0")) > 0:
                        write(root / "recording.started", {"frames_verified": True})
                        recording_started = True
            pages = [line for line in content.splitlines() if "PAGE_DONE|" in line]
            if pages and pages[-1] != last_page:
                last_page = pages[-1]
                print(last_page, flush=True)
            status = result_for(root, state)
            if status:
                if status == "completed" and recorder:
                    time.sleep(2)
                break
            if not worker_alive(state["worker_pid"]):
                raise RuntimeError(
                    "Playback exited without a matching completion record"
                )
            time.sleep(0.2)
        else:
            raise RuntimeError("Playback timed out; retain files and inspect the log")
    finally:
        if status is None:
            (root / "playback.cancel").touch()
        if recorder:
            if recorder.poll() is None:
                recorder.communicate(b"q\n", timeout=30)
            write(
                root / "recording-result.json",
                {
                    "job_id": job,
                    "run_id": state["run_id"],
                    "returncode": recorder.returncode,
                    "path": str(root / "PPT-output.mp4"),
                    "scope": "entire_powerpoint_window",
                },
            )
        if log:
            log.close()
    if status != "completed":
        raise RuntimeError(f"Playback failed; see {root / 'element-playback.log'}")
    if recorder and recorder.returncode:
        raise RuntimeError("PPT finished but recording failed")
    print(
        json.dumps(
            {
                "status": status,
                "pptx": str(copy),
                "video": str(root / "PPT-output.mp4") if recorder else None,
            },
            ensure_ascii=False,
        )
    )
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--source", type=Path)
    group.add_argument("--order-root", type=Path)
    parser.add_argument("--thread-id")
    parser.add_argument("--record", choices=["yes", "no"], required=True)
    parser.add_argument(
        "--response-source", required=True, help="Actual recording-choice answer"
    )
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    if not args.response_source.strip():
        parser.error("Record the actual user answer")
    try:
        return run(args)
    except Exception as error:
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
