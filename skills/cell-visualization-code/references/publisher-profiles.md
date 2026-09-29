# IEEE Transactions 与 Elsevier 出版商 Profile

这里的 profile 是出版商通用基线，不是某本期刊的审美模板。先确认具体期刊和版面，再用其 Guide for Authors 覆盖通用值；不能仅凭出版商名称宣称已经满足目标期刊全部要求。

## IEEE Transactions 通用基线

使用 [IEEE profile](../assets/styles/ieee-transactions.json)。IEEE Author Center 当前给出的通用图宽为单栏 88.9 mm、双栏 182 mm；矢量图优先，非矢量彩色/灰度图要求高于 300 dpi，黑白线图高于 600 dpi。推荐字体包括 Helvetica、Times New Roman、Arial、Cambria 和 Symbol，最终全尺寸文字约 9–10 pt。

本 profile 选择 Times 系列和 9–10 pt 作为可重复实现，并选择 600/1200 dpi 作为高于最低门槛的工作值。它不强制某一配色；颜色之外仍必须使用线型、标记或直接标签，使灰度打印可辨。

官方依据：

- https://journals.ieeeauthorcenter.ieee.org/create-your-ieee-journal-article/create-graphics-for-your-article/resolution-and-size/
- https://journals.ieeeauthorcenter.ieee.org/create-your-ieee-journal-article/create-graphics-for-your-article/file-formatting/
- https://journals.ieeeauthorcenter.ieee.org/create-your-ieee-journal-article/create-graphics-for-your-article/

## Elsevier 通用基线

使用 [Elsevier profile](../assets/styles/elsevier-general.json)。Elsevier 当前通用图宽为最小 30 mm、单栏 90 mm、1.5 栏 140 mm、双栏 190 mm；最终普通文字通常为 7 pt，上下标不小于 6 pt。位图基线是半色调 300 dpi、组合图 500 dpi、线图 1000 dpi。推荐字体包括 Arial/Helvetica、Courier、Symbol、Times/Times New Roman。

本 profile 选择 Arial/Helvetica，轴标签 8 pt、刻度和图例 7 pt，并保留更大的标题。具体期刊若要求不同栏宽、文件格式或字体，以期刊页面为准；修改 profile 后保留来源和核验日期。

官方依据：

- https://www.elsevier.com/about/policies-and-standards/author/artwork-and-media-instructions/artwork-sizing
- https://www.elsevier.com/about/policies-and-standards/author/artwork-and-media-instructions/artwork-overview

## 两个后端的调用

Python 模板通过同一个 JSON 读取物理宽度、字体、字号、线宽和推荐 DPI：

```bash
python assets/python_plot_template.py \
  --input plot_data.csv --output-stem figure \
  --width-cm 8.89 --height-cm 6 \
  --style-profile assets/styles/ieee-transactions.json \
  --placement single_column --art-type color_grayscale
```

MATLAB 中将 `dpi` 设为 `0` 可使用 profile 对应图件类型的推荐值：

```matlab
matlab_plot_template("plot_data.csv", "figure", 9, 6, 0, ...
    "assets/styles/elsevier-general.json", "single_column", "color_grayscale");
```

传入的 `widthCm` 必须与所选 placement 一致，避免代码声称使用某一版式却实际导出另一宽度。高度由内容决定，不由通用 profile 伪造。完成后仍须测量 PDF 页面框、检查字体嵌入，并把图放入目标模板查看。
