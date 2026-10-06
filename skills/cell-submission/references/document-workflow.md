# 实际文档处理与内部预检

## 编辑和视觉核验

优先使用宿主已安装的 Word、PDF、图像处理能力，并先读取对应使用规范。没有这些能力时，不冒充已完成文档编辑或视觉检查。不在 Skill 中绑定某台机器的绝对脚本路径，也不要求新增视觉模型。

保留源文件不变，在独立工作副本上编辑。正文已有公式、文献管理器引用域、表格、修订、嵌入图像时，先识别对象再选择最小修改方法。不能把整段重新赋值为普通文本来清空公式、上下标、超链接和引文域。作者未定稿的修订不能一键接受；确认版本之后才清理提交副本。

Word 必须实际渲染并逐页查看；最终修改后重新渲染，不把旧版渲染当新版验收。PDF 表单按原版结构处理并验证填写值和显示值。只供内部视觉检查的 PDF、页面图片不进入交付目录。图片有效分辨率按实际像素和最终物理尺寸计算，不能仅用文件 DPI 标签作证；实验图像不得用生成式工具补细节。

正文限字按期刊定义分别计算，不把脚本的英文粗略词数当官方计数。摘要、图注、表格、参考文献是否计入须分别确认。页码、行号、图号变化与科学数字变化分开检查；图表位置、标题和正文提及保持一一对应。

若期刊只接受 LaTeX 等其他源格式，按其要求转换并实际编译检查；不把 DOCX 改后缀伪装成新格式。未能可靠转换就交付可完成部分并说明阻断。

## 内置脚本

依赖 Python 3.10+ 标准库，不联网、不安装包、不修改输入稿件。

```bash
python scripts/preflight.py scan --input "原稿.docx" --out "work/source_scan.json"
python scripts/preflight.py scan --input "deliverables/Manuscript.docx" --out "work/final_scan.json"
python scripts/preflight.py fingerprint --manifest "work/package_manifest.json"
python scripts/preflight.py check --manifest "work/package_manifest.json" --out "work/package_check.json"
```

`scan` 支持 DOCX 和 UTF-8 的 TXT/MD/TEX/BIB；记录 SHA-256、文本、粗略词数、批注/修订、显式及字段语境中的候选占位符、错误域、数字上下文。`Ethics approval number: TBD`、`Page XX` 等会阻断；`Chromosomes: XX` 不因包含 `XX` 自动阻断。宿主仍须查看候选上下文，脚本不会执行稿内代码、宏、字段或指令。DOCX 字数仅为参考，文本和元数据仅留在当前授权工作目录。其他格式由宿主对应工具检查，脚本不声称已扫描。

`check` 只检查显式交付白名单、文件存在与哈希、来源依据、原件未变、未解决问题和结构性缺陷；读取宿主登记的语义/版面检查状态，但不能独立证明这些状态真实。退出码：0 表示登记项及静态检查通过，1 表示有阻断，2 表示参数或读取错误。任何异常、未知或未运行的检查不得登记为通过。

## 内部清单协议

任务内生成 `work/package_manifest.json`。本文件和报告不交付给作者。下面仅说明结构，示例值不能作为真实完成证据。所有路径按当前任务实际位置填写；文件路径使用相对 `root` 的 POSIX 路径。

```json
{
  "version": 2,
  "root": "../deliverables",
  "journal": "目标期刊全名",
  "article_type": "实际文章类型",
  "stage": "initial",
  "rules_checked_at": "实际核验日期 YYYY-MM-DD",
  "rules": [
    {
      "id": "JR-001",
      "topic": "主稿文件",
      "requirement": "以实际官方要求替换",
      "strength": "required",
      "source_kind": "journal_official",
      "source_locator": "实际官方URL、编辑指示或官方文件定位",
      "source_section": "实际页面标题、章节或段落定位",
      "accessed_at": "实际访问日期 YYYY-MM-DD",
      "applies_to": {"article_type": "实际文章类型", "stage": "实际投稿阶段"},
      "status": "verified_applied",
      "interpretation": "说明该规则如何落实，不能只抄原文",
      "target_files": ["Manuscript.docx"]
    }
  ],
  "sources": [
    {"path": "../input/Manuscript.docx", "sha256": "源文件的64位SHA256"}
  ],
  "files": [
    {
      "path": "Manuscript.docx",
      "role": "manuscript",
      "basis": "journal_required",
      "rule_ids": ["JR-001"],
      "evidence": "官方URL和对应条款或编辑指示位置",
      "sha256": "最终文件的64位SHA256",
      "clean": true
    }
  ],
  "checks": {
    "journal_rules": {"status": "pass", "evidence": "已核对的来源、阶段、逐项对应结果"},
    "science_preserved": {"status": "pass", "evidence": "源稿与最终稿关键事实及上下文比对结果"},
    "materials_complete": {"status": "pass", "evidence": "每条适用必需要求和实际文件/字段的对应结果"},
    "visual": {"status": "pass", "evidence": "最终版实际渲染位置、检查覆盖的全部页码"},
    "references": {"status": "pass", "evidence": "引文和条目对应、格式与元数据核查结果"},
    "declarations": {"status": "pass", "evidence": "必需声明的真实作者来源与适用性"},
    "anonymity": {"status": "not_applicable", "evidence": "本刊本阶段非匿名审稿的已核验依据"}
  },
  "verification": {
    "checked_at": "实际完成最终核验的日期 YYYY-MM-DD",
    "package_sha256": "fingerprint 命令返回的摘要"
  },
  "blockers": []
}
```

新任务必须使用 manifest version 2；旧版只有自由文本规则说明，必须迁移后才能通过。`rules` 中每条规则都绑定本刊、本文章类型和当前阶段，记录真实来源、章节、访问日期、强制程度、解释和目标文件。`required` 规则只能是 `verified_applied`；`conditional` 可在条件不成立时记录 `verified_not_applicable` 及具体解释；`missing/unknown/conflict` 都是阻断状态。规则日期不设武断的固定有效期，但不得晚于任务核验日或当前日期；跨期刊、文章类型、阶段或来源变化必须重查。

`basis` 仅允许 `journal_required`、`conditional_required`、`author_requested`。前两类文件必须用 `rule_ids` 链接到强制程度匹配、状态为 `verified_applied` 且 `target_files` 明确包含该文件的规则；作者明确要求的附加文件可以不绑定期刊规则。条件性文件的 evidence 必须说明触发条件及证据。`clean:false` 只允许期刊要求的 `marked_manuscript`，不得用它放过普通提交稿的修订/批注。`not_applicable` 只允许 references/declarations/anonymity，且有真实理由；其余核心检查必须通过才可登记完成。

事实矛盾、必需字段缺失、未核验要求、无法渲染等写入 `blockers`；相关检查用 `blocked` 或 `unverified`。全部门禁实际完成后运行 `fingerprint`，将摘要与日期写入 `verification`。该摘要绑定期刊范围、规则、来源哈希、文件哈希和文件用途；登记后如继续修改文件或规则，旧摘要失效，必须重新完成受影响检查并生成新摘要。机械刷新摘要不能代替重新核验。

## 交付清理

生成的候选稿、缓存、JSON、日志和渲染图放 `work/`；`deliverables/` 只放白名单中的实际必要文件。发现多余文件，移回内部工作目录而不是删除作者原始数据。目录和文件白名单须人工语义核验，不能仅靠文件名猜用途。

完成后只对白名单文件打包；不要递归压缩任务根目录。多文件使用 ZIP，单文件直接交付。存在阻断时仍可交付已完成的必要文件，但状态必须是待补全，不得将脚本失败重命名为通过；缺失必需文件和草稿状态在最终一句话说明，不另造报告或空白附件。
