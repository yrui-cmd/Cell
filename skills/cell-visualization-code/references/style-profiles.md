# 版式策略与示例 Profile

## 两种合法策略

### 原生最终尺寸 `native_final_size`

绘图画布宽度就是文档中的最终显示宽度，字体使用最终可见点数。适合 MATLAB IEEE 单栏流程，也适合希望直接控制物理尺寸的 Python 图。优点是字号直观；图外对象或 tight cropping 仍可能改变实际 PDF 页面框，必须测量。

### 放大源图后缩放 `scaled_source`

源 PDF 画布和字号较大，再由 LaTeX/排版软件缩到最终栏宽。适合已有 Python 项目已经按统一大画布调好的图族。最终可见字号近似：

```text
source_font_pt × display_width / actual_exported_source_width
```

这里的 source width 必须是导出 PDF 的实际页面宽度，不是名义 `figsize`。外置色条、轴外标签和 tight cropping 会改变它。导出、测量、校准、再导出，并在编译页面中确认。

## 来自材料的 MATLAB IEEE 项目 Profile

以下是特定 IEEE/T-ASE 项目经验，不是所有 IEEE 期刊的硬性标准：

- 策略：`native_final_size`；单栏源宽与显示宽均为 8.89 cm。
- 单轴高度约 5.6 cm；两行约 7.0–7.4 cm；三行约 9.4–10.4 cm。
- 刻度 8 pt，轴标签 8.5 pt，子图标题约 8.5 pt，图例 7.5 pt。
- 主曲线约 1.15–1.35 pt，次要曲线约 1.0–1.15 pt，轴框约 0.8 pt。
- PDF 矢量优先；按任务需要另存 PNG/TIFF 600 dpi 和可编辑 FIG。

使用前核验当前模板的真实栏宽和文件要求。示例中的 DoS 配色、某一图的绝对图例坐标和本机路径属于原项目，不进入通用 profile。

## 来自材料的 Python IEEE 项目 Profile

以下是 STDE-CDM 项目的 `scaled_source` 配置，不得与上面的原生最终尺寸字号混合：

- 源图基准实际 tight PDF 宽度 705.05 pt，最终在 LaTeX 中显示为 `\columnwidth`。
- 源字号：标题/轴标签 24 pt，刻度 19 pt，图例 18 pt，注释 15 pt。
- 源线宽：主曲线 3.0 pt，次要/参考线 2.5 pt，场景线 0.8 pt，网格 1.0 pt。
- 其他源图若实际 tight 宽度为 `W`，各源字号按 `W / 705.05` 校准，再编译检查。
- 项目使用共享样式函数、稳定语义颜色、可测量的图例物理间距和一致的热图色标。

这些值只用于延续该项目或用户明确选择的相同 profile。新论文先建立自己的参考图与测量值；不要把 705.05 pt、特定模型名或 Figure 4–8 布局当通用规范。

## 选择原则

新项目优先使用 `native_final_size`，因为最终字号更容易解释。已有项目若已形成经编译确认的 `scaled_source` 图族，则保留其策略并统一校准，不为了形式改写全部图。

目标为 IEEE Transactions 或 Elsevier 时，不从以上项目经验猜测出版规则；使用 [出版商 Profile](publisher-profiles.md) 的已核验通用基线，再应用具体期刊覆盖项。

无论哪种策略，最终依据都是插入目标文档后的实际页面，而不是源图窗口、PNG 预览或代码中的字号数字。
