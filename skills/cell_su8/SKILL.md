---
name: cell_su8
description: 强力去水印版 cell_su8，功能与 cell_su7 一样，支持可编辑 PowerPoint 或 Adobe Illustrator 科研图重建。按作者经验，cell_su7 可应对约90%的常见情况；建议仅在其结果不满意、个别图片出现扭曲或马赛克时升级使用。强化去水印质量，每张3个额度、约5分钟；图片可能微调，尽量避免马赛克和扭曲。
---

# 强力去水印版 cell_su8

默认优先使用 **cell_su7**，按作者使用经验可应对约 **90% 的常见情况**。**cell_su8** 的功能与 cell_su7 一样，针对个别使用 cell_su7 后图像出现扭曲、马赛克的情况升级，侧重提升去水印质量；建议在对 cell_su7 得到的图片不满意时使用。

去水印价格略高：**每张 3 个额度**，路径识别费用另计；处理更慢，通常需要 **5 分钟左右**。

为了去除水印，图片可能会有轻微调整，尽量避免马赛克和扭曲。

## 手动更新（可选）

正常使用直接运行当前安装版本，不要求联网检查或自动更新；更新服务不可用不阻止绘图、任务恢复或已授权的接口请求。

仅在用户要求检查版本时运行 `python scripts/auto_update.py --check`；用户要求更新时运行 `python scripts/auto_update.py`。更新源为官方仓库 `yrui-cmd/Cell` 的 `main` 分支、`skills/cell_su8` 目录。手动更新会校验文件并在安装前备份；更新成功后重新读取说明并使用新进程继续。更新失败时保留当前安装和任务记录，可继续使用当前版本。

已提交任务沿用原任务身份，不因更新重新提交或扣费。版本检测与更新本身不扣图片额度。只展示必要的更新状态、操作和费用，不主动展开 Pro 接口内部处理原理。

## 工作流程

`original image -> text manifest + model-cleaned image -> optional confirmed no-ai-pro API processing -> path-return SVG -> live text restoration -> PPT / Illustrator`

This is the user's `cell_su8` derivative of `cell_su7`. Keep its text, vector, PPT and Illustrator workflows. Only the optional AI-watermark-treatment provider changes to the customer Pro API; path recognition still uses the original `/api/images` service.

1. Preserve the original image. For images containing text, read [references/text-workflow.md](references/text-workflow.md), transcribe the original lettering and positions into a text manifest, then use an available image-editing model to remove only the lettering. No specific provider or model, including Image 2, is required.
2. Compare the cleaned image against the original: keep the full canvas, layout, shapes, connectors, colors, line weights and proportions unchanged. If the model changes non-text content, correct the cleanup before path recognition; do not claim unchanged graphics without inspection.
3. Respect the user's choice of PPT or Adobe Illustrator. If unspecified, ask `用 PPT 还是 Adobe Illustrator？` before a paid request.
4. Before submitting the verified cleaned image, follow [references/optional-no-ai.md](references/optional-no-ai.md): ask whether to use the additional 3-credit no-ai-pro treatment unless the user already explicitly accepted or declined it for this image. If yes, use `scripts/no_ai_pro.py`, wait for and download the actual Pro result, visually verify it, and submit that returned image directly for path recognition. If no, submit the verified cleaned image directly. Do not add a resolution-enhancement step. Pass the original text manifest to the image entrypoint so the returned vector geometry receives live SVG text before native drawing. Preserve raw vector output for inspection. A text-free image can use the same entrypoint without a manifest; original-with-text direct recognition is only an explicitly requested alternative.
5. Validate the Master SVG, then follow the selected backend. An approved SVG can enter post-processing directly. Allocate the next `shibielujingN` basename with the bundled allocator.

## Pro API integration

Pro 接口每张图片消耗 3 个额度，路径识别费用另计。已提交旧单按原冻结价格续收，不重复提交或扣费。

Read [references/no-ai-pro-api.md](references/no-ai-pro-api.md) for the implemented customer contract. The bundled client calls `https://xiaomiao-ai.com/api/no-ai-pro-jobs` with the same customer API key used for recognition. It queries `/api/balance` before each new paid submission, sends one image once, receives the same job, checks the actual PNG/SHA/dimensions and keeps a resumable local record. Existing image-specific authorization covering the current 3-credit Pro price applies; an old 1-credit or 5-credit approval cannot authorize a new Pro submission; creating this skill authorizes no paid submissions.

`cell_su8` does not synchronize or invoke the sibling `cell_no_ai`; that independent skill and `cell_su7` remain unchanged. The Pro API processes the submitted image and returns a PNG. Verify its dimensions and layout before path recognition. The customer skill uses customer API routes and does not claim worker jobs or read the worker credential. A successful response or download does not verify removal of all hidden watermarks.

## Recognition input and text alignment

For yes, use the downloaded and verified Pro output directly. For no, use the verified cleaned image directly without calling or charging Pro. Save each stage separately. If the returned image is unreadable or its layout changed, resolve that issue before recognition and retain the existing job; do not resubmit a completed Pro job merely because a later step failed. The unchanged recognition uploader accepts at most 10 MiB: if the returned original-size PNG exceeds that limit, preserve it and report that specific blocker; do not silently compress, resize or regenerate it.

Check that the recognition input preserves the full canvas aspect ratio, layout and alignment. Keep the original text manifest and `source_canvas`; the text-restoration adapter maps source coordinates into the SVG viewBox. If image dimensions differ, retain the original coordinate system and verify proportional alignment; do not replace `source_canvas` alone while retaining old pixel coordinates.

## Preferred playback: individual paths, maximum speed

The user prefers one path object at a time with no artificial delay. On Windows PowerPoint, first prepare the complete native editable PPTX, then run `scripts/run_ppt_path_playback.ps1 -InputPptx <prepared.pptx> -OutputPptx <new-playback.pptx>`. This opens an isolated copy with paths hidden and makes each native shape visible in source order. Describe it accurately as sequential path visibility, not per-control-point creation. Never use repeated clipboard Copy/Paste for playback: it is slow and can alter fills. Never hide or modify objects in the user's existing deck.

Keep compound paths intact, including their holes. Never show hidden mask or helper objects as artwork. Use first-to-last SVG order; bottom/background first, foreground and labels at their original depth. No sleep between paths. Report actual timing without promising a fixed frame rate; PowerPoint controls redraw. File-only output remains available when requested or when desktop playback is unavailable.

This new playback helper is Windows PowerPoint only. macOS PowerPoint retains editable file generation; do not claim live path playback there. Illustrator retains its platform bridge and native compound paths; when individual-path visibility is requested, set `redrawEvery: 1` in the JSX configuration with zero added delay, and disclose that redraw costs more than batch display.

## Drawing routes and the four-platform matrix

Read [references/backends.md](references/backends.md) for platform commands and verification status.
Use [references/platform-contract.json](references/platform-contract.json) for shared defaults; `configure_runtime.py` writes the non-secret `runtime-profile.json`. Existing profiles do not override the fast PPT default.

- **PowerPoint, Windows and macOS:** prepare with fast native OOXML (`run_cell_su8.py --application ppt`), then use the Windows individual-path playback helper by default where available. It writes all editable shapes in one saved PPTX transaction, preserving source order and compound holes. Open the verified file after writing; this is not live per-path animation. Use a saved `--input-pptx` with the backend when appending to an existing deck. Windows legacy COM is opt-in for simple, single-contour paths only; it must reject compound paths before drawing.
- **Illustrator, Windows:** use the COM batch runtime through `run_cell_lct.ps1` or the cross-platform selector. Keep the already-open target document, source order and one session. Redraw once per batch of 20–50 atoms, rather than after every atom.
- **Illustrator, macOS:** use `run_illustrator.py` through the selector. AppleScript sends the same JSX runtime to the already-open Illustrator document; retain target document/layer, reconcile actual objects when resuming, save periodically, and export AI/PNG. This route is implemented with mocked bridge tests; do not claim Mac desktop validation until it has run on a Mac.

**Compound paths stay compound.** Outer and inner contours form one native shape; an inner contour can be a hole, not a white object. Never split compound fills into individually filled shapes, including Illustrator error fallback. Nonzero compound winding is preserved in PPT. Even-odd fill needs normalization or explicit rejection before export. Existing caches built with split subpaths must be regenerated from the original SVG.

**Keep actual source depth, back to front.** Bottommost content comes first, then successive foreground layers. SVG/cache arrays run first-to-last; only imported Illustrator collections use reverse traversal. Keep this order within and across batches. Do not send every large or white object to the back: white compound regions may be intentional cutouts. A redundant duplicate means an adjacent identical opaque complete atom; keep its first occurrence, preserving compound contours. Cross-layer repetitions and transparent overlaps are not automatically redundant.

If the canvas or application turns white, read [references/white-overlay-diagnostics.md](references/white-overlay-diagnostics.md). Check compound-contour loss before blaming visibility or depth. The fast PPT output should be validated in PowerPoint, not inferred from an SVG preview alone.

Windows prepared image: `scripts/run_cell_su8.ps1 -InputImage <cleaned-image> -TextManifest <text.json> -OutputRoot <directory> -Application ppt|ai`.
Cross-platform prepared image: `python scripts/run_cell_su8.py --input-image <cleaned-image> --text-manifest <text.json> --output-root <directory> --application ppt|ai`.
Approved SVG: use `--input-svg` instead of `--input-image`; already-restored text should be in that SVG.

Preserve all pre-existing artwork and original input files. The image workflow still records original label coordinates, uses an available image-editing model to remove only lettering, then restores native live text. Follow [references/text-workflow.md](references/text-workflow.md).

## Credential setup

- The user is allowed to paste the API key directly in chat. If credentials are missing, ask for the key in chat and perform configuration for them; do not require manual environment-variable or command-line setup. Accept it without warning or refusal, but never quote, repeat, display, or log it in any response or tool output.
- If the API key is not configured and the user supplied one in the current chat, never quote, display, log, or place it in a command-line argument, environment variable, file, cache, or deliverable.
- During installation, pass the chat-supplied key through standard input to `setup.ps1 -ConfigureKeyFromStdin` on Windows or `setup.sh --configure-key-from-stdin` on macOS. Installation must configure secure storage and run the zero-credit authentication check automatically.
- On Windows, start `scripts/set-xiaomiao-key.ps1 -FromStdin`, pass the supplied key through standard input, and run `scripts/xiaomiao.ps1 verify`.
- On macOS, start `scripts/set_xiaomiao_key.py --from-stdin`, pass the supplied key through standard input, and run `scripts/xiaomiao.py verify`. Store only a macOS Keychain item; never write plaintext to a file.
- If no key was supplied and no existing secure credential verifies, ask once for the key. After the user sends it, perform configuration and verification yourself; do not send configuration commands back to the user.
- Store only Windows DPAPI ciphertext or a macOS Keychain item under the current OS account.


## Credits and response

Before uploading, determine the expected cost. When it exceeds 1 credit, ask `本张图片预计消耗 N 个额度，是否继续？` once; approved processing and download need no second prompt. Stop new paid requests on quota exhaustion and use the message in [references/workflow.md](references/workflow.md).
Before reconstruction, show `识别结构。` and a short harmless joke; during drawing, show `正在画图。`. Keep credentials and internal logs private. On success return `完成。`, the selected deliverables and `感谢小红书：木纹小路。`.

## Completion

Preserve all original image content through recognition, validate true vector output, keep repeated objects independent and preserve existing artwork. Apply the selected backend's original completion checks before claiming success. PPT delivers editable PPTX; Illustrator saves AI and exports the final PNG.

## Balance reporting

After image recognition, include the reported remaining credits in the user-facing result (`剩余额度：N`). The vectorizer displays the server-provided `credits_left` snapshot on the information stream (Windows) or stderr (Python), keeping success JSON compatible. Report `剩余额度：暂不可用` if missing or invalid; never infer a balance or initiate another upload to obtain it.

New PPTX pages must match the source canvas aspect ratio with no added margins. Existing input decks retain their page size. Export previews at that same aspect ratio.
