# Optional Pro step before path recognition

This is the only provider change from `cell_su7`. Run it after text removal and visual checking, before path recognition. Approved vector inputs skip this image step.

## Reuse the image-specific choice

If the user already accepted or declined this treatment for the current image, retain that decision. Otherwise ask once: “是否使用 Pro 接口进行去 AI 水印处理？选择‘是’额外消耗 3 个额度；选择‘否’则直接进行路径识别。” Keep the recognition cost separate and reuse any explicit approval already given for the full quoted workflow.

New Pro submissions require approval covering the current 3-credit price. An earlier 1-credit or 5-credit Pro approval does not cover a new 3-credit job. An already-submitted job retains its original frozen price; resume that job without another POST, a new reservation or a 3-credit balance precheck.

The Pro API processes the submitted image and returns a PNG. Verify the returned dimensions, layout, shapes, colors and connections before continuing. Receiving a PNG does not establish removal of every hidden watermark. Do not promise complete removal or unchanged pixels.

## Yes

1. Read [no-ai-pro-api.md](no-ai-pro-api.md). Reuse the securely stored customer Xiaomiao API key. Only the customer `/api/no-ai-pro-jobs` API belongs here; no worker/admin credential, internal claim endpoint or browser is needed.
2. Before a new submission, query the live balance with `python scripts/no_ai_pro.py balance`. Display the actual available balance and additional 3-credit cost. A failed/invalid balance or less than 3 prevents a new upload. Do not infer credit availability from an upload response.
3. With current approval, submit the verified text-free image once and receive it in the same foreground workflow:

   ```text
   python scripts/no_ai_pro.py process --image cleaned.png --job-dir output/pro-image --approved-three-credits
   ```

   The client repeats the live balance check immediately before POST. Save each image stage separately; the original reference and text manifest remain unchanged. Stdout gives the actual job/result information; progress and balance notices use stderr.
4. On an interrupted wait or download, resume the original job:

   ```text
   python scripts/no_ai_pro.py resume --job-dir output/pro-image
   ```

   Do not create another job directory to retry a submitted or uncertain upload. If the POST identity is unknown, preserve its submission barrier and report the concrete uncertainty. A failed later vector step never authorizes resending this Pro image.
5. The client verifies actual PNG decoding, its SHA against status, and the source-visible dimensions. Actually view the full returned PNG and compare its layout, contours, colors, arrows and empty text regions with the original and cleaned image. Retain the original text coordinate frame. Material drift must be resolved before recognition; technical checks cannot prove label alignment.
6. Use the downloaded `result.png` directly as recognition input. Keep the original `source_canvas` and text manifest; continue the same vectorization, editable-text merge and selected PPT/Illustrator backend. Do not insert another enhancement or resize stage. If `recognition_compatible` is false because the PNG exceeds the unchanged recognition uploader's 10 MiB limit, preserve the result and report that blocker.

## No

Do not call or charge Pro. Submit the already-verified cleaned image directly for recognition and continue the original text-restoration/drawing workflow.

## Fixed order

Yes: text-free image → actual Pro returned PNG → path-return SVG → editable text restoration → selected backend.

No: text-free image → path-return SVG → editable text restoration → selected backend.

The Pro client is included in `cell_su8`; it does not run the old `cell_no_ai` workflow or update that sibling skill.
