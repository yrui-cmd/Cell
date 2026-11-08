# 固定 PPT 接口

固定地址 `https://xiaomiao-ai.com/api/ppt/v1`。由 Python 执行 `scripts/transfer.py submit 交接目录` 或 `status 交接目录`。客户端自动读取[已配置的 PPT 密钥](credentials.md)。

- `GET /health` 须返回 `ok: true`、`version: 2`、`job_modes` 含 `planned_deck`，且 `planned_upload` 声明 `files: ["material"]`、`format: "pdf"`、`billing: "declared_ppt_content_pages"`。不支持的契约先止步。
- `GET /balance` 查可用页额度。`POST /uploads` 只传 multipart `material`（交接 PDF），不传 `pptx` 或 `pptx2`。头为 `X-PPT-Job-Mode: planned_deck` 与已保存的 `Idempotency-Key`。客户端与接单程序读取 PDF 第一行 `PPT 总页数：N 页`；服务以该声明的目标 PPT 页数作为报价依据，每个目标 PPT 页 1 额度；PDF 的模板、问答、资料页及正文续页不增加计费页数。内嵌 `ppt-material-index.json` 用于兼容和定位，存在时其整数 `page_count` 须与首页一致；缺少索引的普通 PDF 由服务器按首页明确声明处理。网站沿用原报价、客户确认和扣费逻辑。
- 核对模式、PDF SHA-256、计费页数和金额。`GET /jobs/{job_id}` 查询同一单。只对当前 PDF 已获用户确认、报价完全相符的 `quoted` 调用 `POST /jobs/{job_id}/confirm`，传 `expected_page_credits`。确认即扣费入队。
- 采用绘图客户端的可恢复方式，在网络调用前落盘幂等键、原聊天、文件摘要及额度。重复运行复用原键或原 job_id。客户端不接受跳转至其他主机。没有订单号时重试原请求；已有订单号时使用同一订单。
- 入队后运行 `python -X utf8 scripts/transfer.py progress 交接目录`，将返回的 `progress_url` 用 Codex 的 `open_in_codex` 打开在聊天右侧。也可用同一命令重开原订单的面板。内部按原订单实际扣除的页额度乘以 9 分钟 32 秒估算，新订单模板预览不另计额度。面板和聊天只展示预计时间、剩余时间与进度结果。从本地入队时间起算，旧订单以最后写入回执的时间近似。
- 面板由后台本地进程提供，每分钟查询原订单。制作完成后只接收、校验并保存成品，不启动 PowerPoint。绑定的 Python 接收进程在校验成品后一次性唤醒原聊天，询问是否录屏后再输出；感谢语只在原聊天完成输出时发送。暂时下载失败仍重试同一单。

## 上传后结束聊天

订单确认入队后，按[返回原对话](return-to-chat.md)启动绑定本订单和原对话的 `receive_and_wake.py start`，禁止创建或恢复定时任务。运行一次 `progress`，确认面板可访问并打开，随后结束本轮，只留「已上传，[查看进度](实际 progress_url)」。不在当前轮次循环等待。等待期间无变化不播报，成品返回或需要处理时才接续原对话。接收进程或桌面唤醒连接失败须如实说明，保留原单，不回退到定时任务。

## 成品回传与 PPT 输出

1. 后台仅接收和验证成品，Python 校验接收结果后一次性唤醒原对话。先问 **要录下 PPT 的输出过程吗？**，选项「需要录屏」「不需要」。问题单独展示并留白，必须等答复，不提前启动输出。按 [录屏及返回规则](return-to-chat.md)保存选择；需要录屏时先录制整个 PowerPoint 软件窗口并核验已开始。
2. 原对话运行 `python -X utf8 scripts/transfer.py play-elements 交接目录 --thread-id 原对话ID`。原订单号、结算状态、文件大小、SHA-256 和成品实际页数须与回执一致，单 PDF 不按报价页数拦截成品；旧单仍核对规划页数。保留回传原件，另建输出预览副本，不重复下载有效成品或再次收费。
3. 工作进程串行执行，仅控制输出预览副本。Windows 和 macOS 使用桌面版 Microsoft PowerPoint，编辑窗口切到前台并核验后开始。同一行从左到右、各行从上到下，每隔 0.2 秒显示一个元素，当前页全部显示后自动切到下一张；用户手动换页时跟随选择，返回时继续剩余元素。原对话检查实际窗口，不能只启动进程便称已完成。
4. 匹配本订单和本次运行的 `element-output-result.json` 明确 completed 后，若选录屏，保留末页约两秒、停止录制并验证视频。确认接收进程已退出，在原聊天提供 PPT、可选视频链接，最后单独一行写「感谢抖音：Cell-skills」。失败则停止录制、保留文件并如实说明，不发完成感谢语。


## 预览失败恢复

客户回来查询时，若日志显示预览仍在等待前台，先把当前 PowerPoint 预览窗口切到前台，并核验元素已开始输出。

成品下载成功但 PowerPoint 预览失败时，先查看交接目录的 `element-playback.log`。手动打开 PowerPoint 本身不会重启失败的工作进程；用 `python -X utf8 scripts/transfer.py play-elements 交接目录` 重试原订单预览，无需再次上传或扣费。客户端保留旧预览，创建新的预览副本；正在运行或已经完成的预览不会重复启动。

生成预览时，仅移除指向缺失或错误关系类型的非可视 custom tags 引用，保留原始回传文件及其摘要。其他无法打开的文件仍如实报告失败，不声称完整修复。错误日志保存 PowerPoint 的实际启动错误。

## 版本与接单端兼容

本客户端新建交接包仍在 PDF 中同时写入 `ppt-material-index.json` 和 `cell-ppt-handoff.json`，用于兼容和定位；两者内容一致，且页数须与首页明确声明一致。提交前核对页数、分区和摘要。不要仅修改首页文字来修复页数错误，也不要在用户确认后自动改 PDF 索引。旧包缺新索引时，在新目录重新构建并确认新 PDF 摘要和额度，保留原订单记录。已存在 job_id 的旧多文件订单仍按原文件摘要和原计费规则查询、领取，不转成新订单或再次收费。

本地派单仅接收这一份 PDF，不要求独立规划 PPTX 或模板 PPTX；参考模板应放在 PDF 内。若远端仍报旧输入兼容错误，保留原单，不回退上传多个文件或擅自重复扣费。
