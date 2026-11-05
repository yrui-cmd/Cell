# 固定 PPT 接口

固定地址 `https://xiaomiao-ai.com/api/ppt/v1`。由 Python 执行 `scripts/transfer.py submit 交接目录` 或 `status 交接目录`。客户端自动读取[已配置的 PPT 密钥](credentials.md)。

- `GET /health` 须返回 `ok: true`、`version: 2`、`job_modes` 含 `planned_deck`，且 `planned_upload` 声明 `files: ["material"]`、`format: "pdf"`、`billing: "declared_ppt_content_pages"`。不支持的契约先止步。
- `GET /balance` 查可用页额度。`POST /uploads` 只传 multipart `material`（交接 PDF），不传 `pptx` 或 `pptx2`。头为 `X-PPT-Job-Mode: planned_deck` 与已保存的 `Idempotency-Key`。服务读取 PDF 内嵌的 `ppt-material-index.json` 的整数 `page_count`，每个最终 PPT 内容页 1 额度；PDF 的模板、问答、资料页及正文续页不增加计费页数。首页页数仅供人阅读，不用 OCR 或字体编码推断计费。
- 核对模式、PDF SHA-256、计费页数和金额。`GET /jobs/{job_id}` 查询同一单。只对当前 PDF 已获用户确认、报价完全相符的 `quoted` 调用 `POST /jobs/{job_id}/confirm`，传 `expected_page_credits`。确认即扣费入队。
- 采用绘图客户端的可恢复方式，在网络调用前落盘幂等键、原聊天、文件摘要及额度。重复运行复用原键或原 job_id。客户端不接受跳转至其他主机。没有订单号时重试原请求；已有订单号时使用同一订单。
- 入队后运行 `python -X utf8 scripts/transfer.py progress 交接目录`，将返回的 `progress_url` 用 Codex 的 `open_in_codex` 打开在聊天右侧。也可用同一命令重开原订单的面板。内部按原订单实际扣除的页额度乘以 9 分钟 32 秒估算，新订单模板预览不另计额度。面板和聊天只展示预计时间、剩余时间与进度结果。从本地入队时间起算，旧订单以最后写入回执的时间近似。
- 面板由后台本地进程提供，每分钟查询原订单。未完成最多显示 99%，制作完成后显示 100%，并启动成品接收和 PPT 输出。面板独立跟踪 PPT 输出状态，所有元素显示完毕才显示感谢语。

## 上传后结束聊天

订单确认入队后，运行一次 `progress`，确认返回的进度面板可访问，并用 `open_in_codex` 打开。随后立即结束本轮聊天，最终回复只留「已上传，[查看进度](实际 progress_url)」。不要在聊天中执行循环查询、sleep/wait、轮询工具、持续等待代理或定时汇报，也不要为等待订单额外建立聊天提醒。进度由后台面板自己刷新，成品接收和 PPT 输出由后台启动。

若上传或确认入队失败，说明实际状态并保留原订单；若仅面板启动失败，简短说明已入队但面板未启动，保留交接目录和原订单供恢复，不要重新提交。用户主动回来查询时可按原订单检查或重开面板。

## 成品回传与 PPT 输出

以下步骤由后台进程执行，不是主代理在聊天结束前等待完成的步骤。

1. 入队后用 `python -X utf8 scripts/transfer.py progress 交接目录` 启动后台接收，然后结束聊天。原订单已经完成时可用 `python -X utf8 scripts/transfer.py play-elements 交接目录` 直接接收并启动 PPT 输出。
2. 核对原订单号、版本、结算状态、页数、文件大小和 SHA-256。已结算的成品使用固定 `GET /jobs/{job_id}/result`，校验后交付 `交付/成品ppt.pptx`。在交接目录另建输出预览副本，记录原本可见的顶层对象 ID 和层叠顺序。组合和复杂对象按一个整体处理。
3. 工作进程串行执行，仅控制输出预览副本。Windows 和 macOS 都使用桌面版 Microsoft PowerPoint，编辑窗口切到前台并确认后开始。macOS 首次运行可能要求授予 PowerPoint 和 System Events 的自动化权限。每隔 0.5 秒显示一个元素，当前页的元素全部显示后自动切到下一张待输出页。用户手动换页时跟随其选择，返回时继续该页剩余的元素。
4. 确认当前订单的全部元素输出完成后，面板显示「感谢抖音：Cell-skills」。遇到错误或提前关闭窗口时保留交付文件，在面板记录输出状态，不主动恢复聊天。只有用户回来要求检查时才核验实际编辑窗口，并据实报告桌面验收。


## 预览失败恢复

成品下载成功但 PowerPoint 预览失败时，先查看交接目录的 `element-playback.log`。手动打开 PowerPoint 本身不会重启失败的工作进程；用 `python -X utf8 scripts/transfer.py play-elements 交接目录` 重试原订单预览，无需再次上传或扣费。客户端保留旧预览，创建新的预览副本；正在运行或已经完成的预览不会重复启动。

生成预览时，仅移除指向缺失或错误关系类型的非可视 custom tags 引用，保留原始回传文件及其摘要。其他无法打开的文件仍如实报告失败，不声称完整修复。错误日志保存 PowerPoint 的实际启动错误。

## 版本与接单端兼容

新建交接包在 PDF 中同时写入 `ppt-material-index.json` 和 `cell-ppt-handoff.json`，内容一致，提交前校验页数、分区和摘要。不要仅修改首页文字来修复页数错误，也不要在用户确认后自动改 PDF 索引。旧包缺新索引时，在新目录重新构建并确认新 PDF 摘要和额度，保留原订单记录。已存在 job_id 的旧多文件订单仍按原文件摘要和原计费规则查询、领取，不转成新订单或再次收费。

健康接口声明单 PDF 不代表接单程序已完成升级。若接单端仍报 `planned_invalid_handoff`、要求独立 PPTX，报告服务端兼容问题，保留原单，不回退上传多个文件或擅自重复扣费。本客户端同步不自动部署接单端。
