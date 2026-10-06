# MATLAB 绘图代码规范

## 实现

- 可复用函数显式接收 figure/axes 或返回句柄；不要依赖未知的 `gcf`、`gca` 和基础工作区残留变量。
- 数据用 `readtable`、`readmatrix`、MAT 文件或显式函数参数读取，并在绘图前检查字段、尺寸、有限值和单位。
- 使用 `tiledlayout`/`nexttile` 管理常规多面板；需要绝对位置时只在最终物理尺寸确定后设置，并记录原因。
- 通过共享函数集中应用字体、线宽、刻度、图例和色条样式；单图函数只保留数据映射与必要几何。
- 所有对象使用显式句柄设置属性。绘制阴影、图像或补丁后复核轴范围与层级，不让辅助对象改变科学尺度。
- 随机抽样、抖动和模拟明确设置并保存随机流；绘图脚本不重新运行主仿真或优化来生成正式结果。

## 最终尺寸

在导出前设置最终物理尺寸：

```matlab
fig.Units = 'centimeters';
fig.Position = [2 2 widthCm heightCm];
fig.PaperUnits = 'centimeters';
fig.PaperSize = [widthCm heightCm];
fig.PaperPosition = [0 0 widthCm heightCm];
fig.PaperPositionMode = 'manual';
drawnow;
```

栏宽来自目标模板或用户确认；`8.89 cm` 只可作为已核实 IEEE 单栏 profile 的值。不要先做大图再缩小，也不要最大化图窗后把临时位置当最终布局。

目标为 IEEE Transactions 或 Elsevier 时，给模板传入对应的 [出版商 profile](publisher-profiles.md)。`dpi=0` 表示按 profile 和 `artType` 选推荐值；仍需用具体期刊 Guide for Authors 覆盖通用宽度或文件要求。

共用横轴时减少重复标签；相同比较使用相同范围与刻度。图例 `Location='best'` 只作初始位置，最终必须看图。人工拖动后把 `Legend.Position` 的绝对厘米坐标回写脚本；坐标只适用于当前图窗尺寸，不能复制到其他图。

## 样式与导出

颜色以外同时使用线型、标记或标签。密集事件优先使用细 stem、累计曲线或局部放大，不选择性删除事件。阴影和 patch 位于主数据下方，并检查透明度是否导致矢量导出栅格化。

优先：

```matlab
exportgraphics(fig, pdfPath, 'ContentType', 'vector', ...
    'Width', widthCm, 'Height', heightCm, 'Units', 'centimeters', ...
    'Padding', 'figure', 'PreserveAspectRatio', 'off');
exportgraphics(fig, pngPath, 'Resolution', dpi, ...
    'Width', widthCm, 'Height', heightCm, 'Units', 'centimeters', ...
    'Padding', 'figure', 'PreserveAspectRatio', 'off');
```

`exportgraphics` 默认 tight padding 可能让实际 PDF 页面小于代码声明的 Figure 尺寸；需要固定版面宽度时显式设置 `Width`、`Height`、`Units` 和 `Padding='figure'`，并测量导出后的 PDF page box。旧 MATLAB 不支持这些参数时使用其可用的等价导出方法并同样测量，不能静默忽略。

需要继续手动编辑时额外 `savefig`；`.fig` 是编辑副本，不代替可重跑 `.m` 代码。`Renderer='painters'` 可用于兼容的二维矢量图，但不能只因设置了该属性就宣称 PDF 全矢量；实际检查导出文件。

路径由函数参数或 `fullfile` 构造，不保留某台 Windows/Linux 机器的绝对路径。导出后重新运行脚本并检查所有文件；若嵌入 LaTeX，再编译并查看最终页面。
