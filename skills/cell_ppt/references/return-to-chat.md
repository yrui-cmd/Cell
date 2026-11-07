# 成品返回后接续原对话

上传确认后结束当前轮次，成品返回后由原对话继续输出。使用 Codex 的同线程 heartbeat；不新建聊天，不用独立 CLI 会话代替原对话，也不让后台面板直接启动 PowerPoint。

## 上传后注册

1. `approval.json` 与 `order.json` 的 `thread_id` 必须是真实原对话 ID。确认订单已入队后运行 `python -X utf8 scripts/return_watch.py prepare 交接目录 --thread-id 原对话ID`。
2. 发现并调用 Codex `automation_update` 工具，使用返回的 `automation_request` 创建本对话心跳。默认每分钟检查一次。若返回 `existing_automation_id`，先用工具查看并更新同一任务，不能再建第二个。工具要求调整频率时使用它允许的最短频率，如实记录。
3. 将工具实际返回的 ID 绑定到订单：`python -X utf8 scripts/return_watch.py bind 交接目录 --thread-id 原对话ID --automation-id 实际ID`。prepare 只生成请求，不能把它当成已成功注册；不手工写自动化配置文件。
4. 运行 `transfer.py progress` 打开面板，确认心跳已启用和面板可访问，结束当前轮次，只留上传成功和进度链接。等待期间状态未变化时保持安静，不定时发送聊天进度。

如果心跳工具缺失或注册失败，明确说明“已入队，但原对话自动唤醒未注册”，保留订单，不能声称会自动唤醒。用户回来时在原对话补注册，沿用订单，不重新上传或扣费。

## 原对话被唤醒后

先运行 `python -X utf8 scripts/return_watch.py check 交接目录 --thread-id 原对话ID`。该命令只查原订单、校验和接收成品，不打开 PowerPoint。

- `pending`：等待下一次心跳，不发送重复进度。
- `awaiting_recording_choice`：先暂停同一个心跳，按下面的问法询问，等实际答复，不能开始输出或重复询问。收到答复后保存选择并恢复原心跳。
- `awaiting_recording_start`：用户已选录屏，先完成下面的录屏准备。
- `ready`：由原对话运行 `python -X utf8 scripts/transfer.py play-elements 交接目录 --thread-id 原对话ID`，然后按 [PPT 输出规则](transfer.md#成品回传与-ppt-输出)检查实际 PowerPoint 编辑窗口、切到前台并完成逐元素输出。不能只启动进程就说已完成。
- `running`：不重复启动；检查窗口是否等待前台。输出未结束就保留心跳，下一次继续核验。
- `completed`：必须匹配当前订单及当前运行的 `element-output-result.json`。如有录屏，停止录制并验证视频可播放、起止画面完整，提供 PPT 和视频文件链接。用 `automation_update` 停用 `return-watch.json` 中的真实自动化 ID。最后在原对话单独一行写 **感谢抖音：Cell-skills**。
- `failed`：核对日志，保留文件和原单，停用本订单心跳并报告具体故障。未完成时不发完成感谢语。用户要求重试后才恢复心跳和原单预览。
- 网络暂不可用：保留心跳稍后再查；遇到凭据失效、文件校验失败等需处理的问题，报告并停用，不能无限重试。

心跳必须绑定原对话。根据实际工具能力注册，不把“写了提示词”或“面板显示已完成”当成原对话已恢复的证据。修订此 Skill 本身不会自动为历史订单创建心跳；历史订单只在用户要求恢复时按上述步骤补注册。

## 输出前只问一句

用可用的用户输入工具展示下面这句，选项为「需要录屏」和「不需要」。不默认代选，不把旧任务的选择当成本单回答。问题单独展示，周围留空白，句子加粗，不夹在长段说明中：

**要录下 PPT 的输出过程吗？**

收到回复后运行 `return_watch.py choose 交接目录 --thread-id 原对话ID --record yes或no --response-source 实际用户答复出处`。选择不需要时直接按原规则输出。

选择需要时，先用本机可用的屏幕录制工具设置整个 PowerPoint 软件窗口，包括标题栏、功能区、缩略图栏、编辑画布和状态栏；保持窗口完整可见、大小稳定，不只截取幻灯片区域，不录无关桌面或其他应用。默认无麦克风音频。先显示 PowerPoint 编辑窗口并确认录制指示或实际采样画面，再运行 `return_watch.py recording-ready 交接目录 --thread-id 原对话ID --recording-path 视频保存路径 --evidence 实际录制开始证据`，随后才启动 PPT 输出。录制期间不裁切到局部，不隐藏软件界面；最后一页输出完成后保留约两秒再停止，保存可播放的视频。

录屏工具不可用、权限缺失或录制失败时，简短说明并询问是否改为直接输出；不能把用户“需要录屏”静默改成“不需要”，也不能伪造 recording-ready。输出失败也要停止录制并保留已录部分，报告真实状态，不发完成感谢语。
