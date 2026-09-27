# 本地验收协议

本文件的 JSON、比较图和日志仅用于本次临时工作；不得复制进最终交付目录。
脚本所在路径以宿主实际安装位置解析，以下 `<SKILL>` / `<WORK>` 是占位符，不是需要新建的目录名。
Python 依赖：`python -m pip install pillow numpy pymupdf matplotlib`。数据分析另按实际需求安装。
优先复用已有兼容环境，不自动升级用户项目依赖、不修改其全局环境。

## 1. 比较实际参考与代码生成图

先执行真实的参考绘图脚本，再调用：

```bash
python "<SKILL>/scripts/figure_tools.py" compare --reference "<WORK>/reference.png" --render "<WORK>/reference_render.png" --code "<WORK>/reference_plot.py" --data "<WORK>/reference_data.csv" --work "<WORK>/compare_01"
```

`--data` 支持多个实际输入文件。输入可以是位图或 PDF；PDF 页码使用 `--reference-page 1` / `--render-page 1`，从 1 开始。
先锁定真实面板裁切，保持对应参考和复现画布一致；不要在比较时自动裁掉误差。
每次迭代使用新的 compare 目录，不覆盖已审核证据。

脚本生成并排图（左参考、右复现）、50% 叠加图、差异图及 comparison.json。
缩放仅等比例；长宽比不一致时补白并报告误差，不拉伸形状掩盖问题。
像素/边缘差异只作定位参考，不自行得出 PASS。纯白背景和抗锯齿会影响数值；不要把百分比当主观“复现度”。

宿主必须实际打开参考、复现图、并排图、叠加图，必要时查看原分辨率局部。
六项检查：

| 字段 | 核验范围 |
|---|---|
| layout | 画布比例、面板数量/位置/大小、留白、间距 |
| axes | 数据变换、轴类型、方向、范围、刻度、基线 |
| marks | 点形、线型、线宽、柱宽、颜色、透明度、误差条 |
| typography | 字体外观、字号层级、标签/图例位置、符号、裁切 |
| data_geometry | 点位、曲线、分布、热图值/排序与参考数值对应关系 |
| annotations | 图例映射、面板标签、样本量、区间含义、统计标记 |

默认长宽比相对偏差超过 1% 时 gate 拒绝；这是本 Skill 的布局检查阈值，不是公认期刊标准。
任一重要关系、方向、尺度、标签、数据、统计标注错误，一律未通过。
源图压缩/抗锯齿差别可在具体观察中说明，但不能豁免丢面板、文字错位或关键数值无法复现。
近似提取的局限写清楚；不能用“只是近似”掩盖明显数据几何不一致。

## 2. 填写真实的参考复现检查记录

在实际核验后创建 `reference_review.json`。以下是**未通过的空白结构**，不能原样使用，更不能批量替换 true 而不核验：

```json
{
  "kind": "reference_visual_review",
  "comparison_sha256": "替换为本次 comparison.json 的真实 SHA-256",
  "target_figures": ["figure"],
  "reference": {
    "title": "实际论文标题或用户提供的参考图",
    "journal": "有依据时填入，未知留空",
    "year": "有依据时填入，未知留空",
    "doi": "已核实的 DOI，未知留空",
    "figure": "实际图号和面板，或用户参考图的选定范围",
    "locator": "真实来源定位信息或已读取的用户文件位置",
    "accessed": "实际访问日期"
  },
  "data_origin": "author_source",
  "data_limitations": "实际来源局限；无局限也不得凭空承诺",
  "execution_command": "实际成功执行的参考绘图命令",
  "execution_exit_code": null,
  "code_executed": false,
  "actual_images_inspected": false,
  "data_driven_render": false,
  "source_verified": false,
  "no_material_mismatch": false,
  "checks": {
    "layout": {"passed": false, "observation": ""},
    "axes": {"passed": false, "observation": ""},
    "marks": {"passed": false, "observation": ""},
    "typography": {"passed": false, "observation": ""},
    "data_geometry": {"passed": false, "observation": ""},
    "annotations": {"passed": false, "observation": ""}
  },
  "unresolved": ["尚未实际检查"]
}
```

`data_origin` 仅允许 author_source、reported_values、digitized_approximate 通过；演示随机数据不能通过。
`source_verified` 指如实核实当前来源层级；用户截图没有 DOI 时不能编造 DOI，但可核实其确实是用户提供的目标。
`observation` 写具体可核查的观察，不写“已检查”“完全一致”代替实际内容；未解决项真实保留。

```bash
python "<SKILL>/scripts/figure_tools.py" gate --comparison "<WORK>/compare_01/comparison.json" --review "<WORK>/reference_review.json" --output "<WORK>/reference_gate.json"
python "<SKILL>/scripts/figure_tools.py" check-gate --gate "<WORK>/reference_gate.json"
```

门槛绑定参考图、复现图、代码、数据、比较材料和 review 的真实文件哈希。
任何绑定文件变化都必须重新 compare/review/gate。不得手改旧 gate 中的哈希。
这能防止意外使用过期证据，不能从技术上证明模型确实看了图、也不能证明统计正确；宿主仍对真实核验负责。

## 3. 使用三格式导出函数

从 assets/export_triplet.py 复制所需函数进最终 plot.py，替换所有路径依赖。
调用前完成字号、布局、尺寸和数据绘制：

```python
export_triplet(fig, output_directory / "figure", dpi=600)
```

不要传带扩展名的 stem。组件从同一 Figure 导出三种格式，TIFF/JPEG 共用同一次内存栅格渲染。
PDF 从同一 Figure 直接生成，非从 JPG 转换；源图没有的图层不能擅自追加。
组件不会把内存 PNG 保存到最终目录。它不负责画图设计，也不自动防止所有标签碰撞；仍须读图检查。
颜色、字体等均由已核验实现设置；组件只统一导出规则。

## 4. 孤立目录重跑与正式文件审核

复制最终 plot.py 与必要 plot_data* 到全新的临时目录，实际重跑；不带参考图、Skill 文件、门槛记录或旧运行输出。
最终代码不得导入 assets/export_triplet.py、scripts/figure_tools.py 或其他未交付本地模块。
支持时禁网重跑。验证样本数、分组、单位、误差和统计标记；看全部三格式，不仅看文件存在。
比较 TIF 像素、JPG 渲染和 PDF 渲染；记录真实运行命令与版本。PDF 元数据变化不等于内容变化。
重跑若产生 README、PNG、缓存等额外输出，修改最终代码，而不是仅在交付前藏掉这些副产品。

```bash
python "<SKILL>/scripts/figure_tools.py" audit --stage "<WORK>/staging" --data plot_data.csv --figures figure --dpi 600
```

输出只到 stdout。可保存到工作区，但不要保存到 staging 或 final。结果包含真实 artifacts 哈希集合。
`audit` 检查精确文件集合、Python 语法、CSV 基本结构、图像实际编码/RGB/分辨率/dpi、无损 TIFF 和 PDF 页数/物理尺寸/路径/文本对象。
它不自动运行 plot.py，不自动选择统计方法，也不能仅凭 PDF 存在路径对象就排除一切贴图作弊；宿主必须检查数据图层和 PDF 实际渲染。

根据实际检查建立 `final_review.json`：

```json
{
  "kind": "final_delivery_review",
  "artifacts": {},
  "actual_formats_inspected": [],
  "checks": {
    "data_integrity": {"passed": false, "observation": ""},
    "statistics": {"passed": false, "observation": ""},
    "visual_layout": {"passed": false, "observation": ""},
    "format_consistency": {"passed": false, "observation": ""},
    "vector_pdf": {"passed": false, "observation": ""},
    "clean_rerun": {"passed": false, "observation": ""}
  },
  "rerun": {
    "isolated_code_and_data_only": false,
    "command": "实际重跑命令",
    "exit_code": null,
    "outputs_match": false
  },
  "unresolved": ["尚未实际检查"]
}
```

artifacts 必须等于最新 audit 返回的完整映射；不得自行编造哈希。
全部实际检查后 actual_formats_inspected 为 `["tif", "jpg", "pdf"]`。
没有推断统计时 statistics 可记录“仅描述性，无推断检验或显著性标注”，不需要为了填字段强行做检验。

## 5. 发布仅三类最终产物

```bash
python "<SKILL>/scripts/figure_tools.py" publish --stage "<WORK>/staging" --data plot_data.csv --figures figure --dpi 600 --gate "<WORK>/reference_gate.json" --review "<WORK>/final_review.json" --destination "<PROJECT>/final"
```

多图：`--figures figure_01 figure_02`；多数据：`--data plot_data_01.csv plot_data_02.csv`；多参考门槛重复 `--gate`。
所有输出图名都必须被某个真实通过的门槛 target_figures 覆盖。相同参考图族可共用已核验门槛，但不同参考不得冒用。
目标目录必须尚不存在；已存在时使用新任务目录，不能删除或覆盖用户已有交付。
工具先验证门槛、最终哈希和真实文件格式，再复制并检查，之后发布。失败不会删除用户文件。
发布完成后，宿主只清理自身临时工作区；final 不保留 gate、review、比较图、参考脚本或包内运行组件。

## 维护依据

技能目录/前置元数据依据 Agent Skills 格式，Codex 本地目录与显式调用依据其官方文档。
导出组件所用格式参数依据 Matplotlib Figure.savefig 和 Pillow 的 TIFF/JPEG 文档。
链接用于维护者核验，不需要另外生成参考清单交付给绘图用户：

```text
https://agentskills.io/specification
https://developers.openai.com/codex/skills/
https://matplotlib.org/stable/api/_as_gen/matplotlib.figure.Figure.savefig.html
https://pillow.readthedocs.io/en/stable/handbook/image-file-formats.html
```
