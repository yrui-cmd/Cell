"""Run the platform preview and persist its verified outcome for the panel."""
import os
from pathlib import Path
import subprocess
import sys
from tempfile import NamedTemporaryFile, gettempdir

from handoff import sha
from transfer import order_lock, read, write

RESULT = "element-output-result.json"


def result_for(root, state):
    if not state.get("run_id"):
        return None
    try:
        result = read(Path(root) / RESULT)
    except (OSError, ValueError):
        return None
    if (isinstance(result, dict) and result.get("job_id") == state["job_id"]
            and result.get("run_id") == state["run_id"] and result.get("status") in {"completed", "failed"}):
        return result["status"]
    return None


def run_macos(deck, targets):
    worker = Path(__file__).with_name("run_element_playback.applescript")
    with NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as queue:
        queue_path = Path(queue.name)
        for page, items in targets.items():
            for item in items:
                queue.write(f"{int(page)}\t{item['name']}\t{item['left_points']:.6f}\n")
    try:
        lock = Path(gettempdir()) / f"cell-ppt-output-{os.getuid()}.lock"
        with order_lock(lock):
            return subprocess.run(["/usr/bin/osascript", str(worker), str(deck), str(queue_path),
                                   deck.name, deck.stem], check=False).returncode
    finally:
        queue_path.unlink(missing_ok=True)


def run(manifest):
    state = read(manifest)
    status = "failed"
    try:
        deck = Path(state["copy"]).resolve()
        if deck.parent != manifest.parent or deck == Path(state["source"]).resolve() or sha(deck) != state["copy_sha256"]:
            raise ValueError("Invalid PPT preview copy")
        if sys.platform == "win32":
            worker = Path(__file__).with_name("swarm_playback.py")
            with manifest.with_name("element-playback.log").open("ab") as log:
                code = subprocess.run([sys.executable, "-X", "utf8", str(worker), str(manifest)],
                                      check=False, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                      creationflags=subprocess.CREATE_NO_WINDOW).returncode
        elif sys.platform == "darwin":
            code = run_macos(deck, state["targets"])
        else:
            raise ValueError("Unsupported PPT preview platform")
        status = "completed" if code == 0 else "failed"
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        with manifest.with_name("element-playback.log").open("a", encoding="utf-8") as log:
            log.write(f"PPT output failed ({type(error).__name__}): {error}\n")
    finally:
        write(manifest.with_name(RESULT), {"job_id": state["job_id"], "run_id": state["run_id"], "status": status,
                                            "diagnostic_log": "element-playback.log"})
    return 0 if status == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(run(Path(sys.argv[1]).resolve()))
