# Python / Matplotlib / Seaborn 规范

## 实现

- 优先使用显式的 `fig, ax = plt.subplots(...)` 与对象方法；可复用函数不依赖隐式 `gca()` 或调用顺序。
- 在局部 `matplotlib.rc_context` 或共享样式函数中设置字体和线宽，避免污染同一进程的其他任务。
- 无显示环境使用非交互后端；正式脚本运行结束关闭 Figure。
- 数据验证发生在创建图形之前。Seaborn 的自动聚合、误差条和分类顺序必须显式设置或先自行计算，不能依赖版本默认值。
- 分类顺序、色彩映射、参考线、坐标变换和图层顺序使用显式参数。
- 随机抖动或抽样使用局部随机生成器和记录的种子；不修改全局随机状态来隐藏不确定来源。

建议入口：

```python
def load_data(path): ...
def validate_data(data): ...
def compute_plot_data(data): ...
def draw_figure(plot_data, profile): ...
def export_figure(fig, outputs, profile): ...
def main(): ...
```

## 布局与字体

用英寸换算最终厘米尺寸：`inch = cm / 2.54`。在这个尺寸下完成字号、图例和布局。优先选择一种布局机制；不要在没有核对的情况下混用 `constrained_layout`、`tight_layout()`、`subplots_adjust()` 和 tight cropping。

目标为 IEEE Transactions 或 Elsevier 时，给模板传入对应的 [出版商 profile](publisher-profiles.md)。profile 同时约束 placement 宽度、字体层级、线宽和按图件类型选择的默认 DPI；具体期刊规则优先，不要只换配色就称为出版商适配。

字体使用可用字体列表和明确回退；数学字体与正文字体协调。源代码设置了字号不等于导出后字体正确，仍需检查 PDF 文字对象、字体替换和最终页面。

轴外图例、色条和注释可能让 `bbox_inches="tight"` 改变页面宽度。需要严格物理宽度时，导出后测量 PDF page box，再调整布局或 profile，不能只相信 `figsize`。

## 导出

线图、散点、柱图和文字优先直接导出矢量 PDF；大量点、热图或图像层可局部栅格化，不把整张图转为位图 PDF。按任务需要额外导出 PNG/TIFF；设置 DPI 时同时核对最终像素和物理尺寸。

从同一个 Figure 状态导出各格式，避免格式间数据、图例或范围不同。输出完成后检查：真实格式、页面/像素尺寸、PDF 文本、透明度、裁切、字体和图层一致性。

使用 Seaborn 时固定类别顺序、估计器、误差定义、bootstrap/seed 和 `native_scale` 等会影响结果的参数。库版本变化可能改变默认行为，关键值不得依赖默认。
