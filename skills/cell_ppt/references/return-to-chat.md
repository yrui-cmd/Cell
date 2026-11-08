# 成品返回后接续原对话

上传确认后结束当前轮次，由单个 Python 接收进程检查已入队订单，接收并校验 PPT 后通过桌面连接唤醒原对话一次。禁止创建、恢复或要求用户启用定时任务、heartbeat、cron、Windows 计划任务。进程内部查询不是聊天定时任务；后台不能启动 PowerPoint 或替用户选择录屏。

## 上传后启动

1. `approval.json` 与 `order.json` 的 `thread_id` 必须是真实原对话 ID，订单已经结算入队。运行 `python -X utf8 scripts/receive_and_wake.py start 交接目录 --thread-id 原对话ID`。本流程授权该 Python 接收器仅向绑定的原对话发送一次本订单接续消息。
2. `start` 先核对绑定并探测桌面连接，再启动隐藏的单订单进程。检查 `receive-state.json` 的 worker_pid、started_at 和实际存活状态；`return_watch.py prepare` 只准备绑定，不表示接收进程已启动。重复 start 不重新提交或另起进程。
3. 运行 `transfer.py progress`，确认面板可访问并在聊天右侧打开，然后结束本轮，只留「已上传，[查看进度](实际 progress_url)」。不在聊天中循环等待或定时播报。
4. 接收器只查询、领取原订单，不调用上传或扣费接口。文件摘要、原订单和原聊天匹配后，等待原聊天空闲，再发送一次接续消息并退出。回执不确定时记录 uncertain，不能盲目重发。

桌面连接不可用、进程启动失败或连接失效时如实说明，保留原单和本地状态，不声称自动唤醒成功，不改回定时任务。收到停止指令运行 `receive_and_wake.py stop 交接目录 --thread-id 原对话ID`；仅用户明确恢复时才运行 resume。启动后默认最多等待 24 小时，超时记录 ReceiverTimeout，用户回来时检查状态再恢复。用户关闭电脑或 Codex 会影响接收/唤醒，不保证离线仍工作。

## 迁移旧订单

已绑定旧任务时，先用 automation_update 删除该订单真实 automation_id 指向的任务；仅删除已经核对订单和原对话匹配的任务，不影响其他订单。记录 automation_deleted=true，再启动本订单 Python 接收器。旧 prepare 不再生成自动化请求；旧 bind 命令拒绝绑定。不要取消订单、重新上传或再次收费。

## 原对话被唤醒后

读取 receive-state.json，核对 job_id、thread_id 和消息中的 nonce。运行 `receive_and_wake.py ack 交接目录 --thread-id 原对话ID --nonce 接续标记`。核对 return-ready.json 的绑定及文件 SHA-256；调用 `return_watch.py check 交接目录 --thread-id 原对话ID` 获取输出状态。若接收器为 attention，只检查并报告错误，不假装收到了成品。

- pending：保留单个接收进程，不建立定时任务。
- awaiting_recording_choice：只问下面的一句话，等实际答复，用 choose 保存；接收器已退出，不恢复任何心跳。
- awaiting_recording_start：先录制整个 PowerPoint 软件窗口，验证实际开始后保存 recording-ready。
- ready：原对话运行 `transfer.py play-elements 交接目录 --thread-id 原对话ID`。按从左到右、从上到下，每 0.2 秒一个元素、自动换页的规则输出。
- running：在本次输出轮次检查实际窗口和进程直到完成，不重复启动，不建立定时任务。聊天被中断则用户继续时沿用本次运行。
- completed：必须匹配当前 job_id 和 run_id 的 element-output-result.json。若录屏，停止并验证可播放、起止完整，再提供 PPT 和视频链接。最后单独一行写「感谢抖音：Cell-skills」。
- failed：停止录制，保留原单和文件，报告具体问题，不提前感谢或宣称成功。

## 输出前只问一句

用可用的用户输入工具展示下面这句，选项为「需要录屏」和「不需要」。不默认代选，不把旧任务的选择当成本单回答。问题单独展示，周围留空白，句子加粗，不夹在长段说明中：

**要录下 PPT 的输出过程吗？**

收到回复后运行 `return_watch.py choose 交接目录 --thread-id 原对话ID --record yes或no --response-source 实际用户答复出处`。选择不需要时直接按原规则输出。

选择需要时，先用本机可用的屏幕录制工具设置整个 PowerPoint 软件窗口，包括标题栏、功能区、缩略图栏、编辑画布和状态栏；保持窗口完整可见、大小稳定，不只截取幻灯片区域，不录无关桌面或其他应用。默认无麦克风音频。先显示 PowerPoint 编辑窗口并确认录制指示或实际采样画面，再运行 `return_watch.py recording-ready 交接目录 --thread-id 原对话ID --recording-path 视频保存路径 --evidence 实际录制开始证据`，随后才启动 PPT 输出。录制期间不裁切到局部，不隐藏软件界面；最后一页输出完成后保留约两秒再停止，保存可播放的视频。

录屏工具不可用、权限缺失或录制失败时，简短说明并询问是否改为直接输出；不能把用户“需要录屏”静默改成“不需要”，也不能伪造 recording-ready。输出失败也要停止录制并保留已录部分，报告真实状态，不发完成感谢语。
