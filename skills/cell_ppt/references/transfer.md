# 固定 PPT 接口

固定地址 `https://xiaomiao-ai.com/api/ppt/v1`。由 Python 执行 `scripts/transfer.py submit 交接目录` 或 `status 交接目录`。客户端自动读取[已配置的 PPT 密钥](credentials.md)。

- `GET /health` 须明确返回 `ok: true` 且 `job_modes` 含 `planned_deck`；旧接口使用第二份 PPTX 作原稿，必须在没有能力声明时止步。
- `GET /balance` 查可用页额度。 `POST /uploads` 用 multipart `pptx`、`material` 和可选 `pptx2`，头为 `X-PPT-Job-Mode: planned_deck` 与已保存的 `Idempotency-Key`。逐份按 PPTX 实际页数计费，每页 1 个 PPT 页额度。模板也计费，PDF 不计费。
- 核对报价和逐份摘要、每份 PPTX 页数及订单模式。 `GET /jobs/{job_id}` 查询同一单。只对确认且报价相符的 `quoted` 调用 `POST /jobs/{job_id}/confirm`，传 `expected_page_credits`。确认即扣费入队。
- 采用绘图客户端的可恢复方式，在网络调用前落盘幂等键、原聊天、文件摘要及额度。重复运行复用原键或原 job_id。客户端不接受跳转至其他主机。没有订单号时重试原请求；已有订单号时使用同一订单。
- 入队后运行 `python -X utf8 scripts/transfer.py progress 交接目录`，将返回的 `progress_url` 用 Codex 的 `open_in_codex` 打开在聊天右侧。也可用同一命令重开原订单的面板。内部按每页额度 9 分钟 32 秒估算，模板额度计入。面板和聊天只展示预计时间、剩余时间与进度结果。从本地入队时间起算，旧订单以最后写入回执的时间近似。
- 面板由后台本地进程提供，每分钟查询原订单。未完成最多显示 99%，制作完成后显示 100%，并启动成品接收和 PPT 输出。面板独立跟踪 PPT 输出状态，所有元素显示完毕才显示感谢语。

## 成品回传与 PPT 输出

1. 入队后用 `python -X utf8 scripts/transfer.py progress 交接目录` 等待回传。原订单已经完成时可用 `python -X utf8 scripts/transfer.py play-elements 交接目录` 直接接收并启动 PPT 输出。
2. 核对原订单号、版本、结算状态、页数、文件大小和 SHA-256。已结算的成品使用固定 `GET /jobs/{job_id}/result`，校验后交付 `交付/成品ppt.pptx`。在交接目录另建输出预览副本，记录原本可见的顶层对象 ID 和层叠顺序。组合和复杂对象按一个整体处理。
3. 工作进程串行执行，仅控制输出预览副本。Windows 和 macOS 都使用桌面版 Microsoft PowerPoint，编辑窗口切到前台并确认后开始。macOS 首次运行可能要求授予 PowerPoint 和 System Events 的自动化权限。每隔 0.5 秒显示一个元素，当前页的元素全部显示后自动切到下一张待输出页。用户手动换页时跟随其选择，返回时继续该页剩余的元素。
4. 确认当前订单的全部元素输出完成后，面板显示「感谢抖音：Cell-skills」。遇到错误或提前关闭窗口时保留交付文件，报告输出状态。通过实际编辑窗口确认对象显现和换页后再报告桌面验收。

