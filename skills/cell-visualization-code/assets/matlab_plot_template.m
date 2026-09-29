function matlab_plot_template(inputCsv, outputStem, widthCm, heightCm, dpi, ...
    styleProfile, placement, artType)
% Reusable x/y/series plotting scaffold. Adapt labels and calculations to real data.
arguments
    inputCsv (1,1) string
    outputStem (1,1) string
    widthCm (1,1) double {mustBePositive}
    heightCm (1,1) double {mustBePositive}
    dpi (1,1) double {mustBeInteger,mustBeNonnegative} = 0
    styleProfile (1,1) string = ""
    placement (1,1) string = "single_column"
    artType (1,1) string {mustBeMember(artType, ...
        ["color_grayscale", "combination", "line_art"])} = "color_grayscale"
end

[style, recommendedDpi] = loadStyleProfile(styleProfile, placement, widthCm, artType);
if dpi == 0
    dpi = recommendedDpi;
elseif dpi < 72
    error("dpi must be 0 for the profile recommendation or at least 72.");
end

data = readtable(inputCsv, TextType="string");
required = ["x", "y", "series"];
if ~all(ismember(required, string(data.Properties.VariableNames)))
    error("Input must contain x, y, and series columns.");
end
if ~isnumeric(data.x) || ~isnumeric(data.y) || any(~isfinite(data.x)) || any(~isfinite(data.y))
    error("x and y must be finite numeric values.");
end
if any(strlength(strtrim(data.series)) == 0)
    error("series labels must be nonempty.");
end

fig = figure(Color="w", Units="centimeters", Position=[2 2 widthCm heightCm]);
cleanup = onCleanup(@() close(fig));
layout = tiledlayout(fig, 1, 1, TileSpacing="compact", Padding="compact");
ax = nexttile(layout);
hold(ax, "on");
names = unique(data.series, "stable");
lineStyles = ["-", "--", "-.", ":"];
markers = ["o", "s", "^", "d", "v", "+"];
for k = 1:numel(names)
    subset = data(data.series == names(k), :);
    [x, order] = sort(subset.x);
    plot(ax, x, subset.y(order), LineWidth=style.mainPt, ...
        LineStyle=lineStyles(mod(k-1,numel(lineStyles))+1), ...
        Marker=markers(mod(k-1,numel(markers))+1), MarkerSize=style.markerPt, ...
        DisplayName=names(k));
end
xlabel(ax, "Verified x label (unit)", FontSize=style.axisLabelPt);
ylabel(ax, "Verified y label (unit)", FontSize=style.axisLabelPt);
set(ax, FontName=style.fontName, FontSize=style.tickPt, LineWidth=style.axesPt, ...
    TickDir="in", Box="on", Layer="top");
grid(ax, "on");
ax.GridAlpha = 0.3;
ax.GridLineStyle = "--";
legend(ax, Location="best", FontSize=style.legendPt, FontName=style.fontName);
drawnow;

fig.PaperUnits = "centimeters";
fig.PaperSize = [widthCm heightCm];
fig.PaperPosition = [0 0 widthCm heightCm];
fig.PaperPositionMode = "manual";
exportgraphics(fig, outputStem + ".pdf", ContentType="vector", ...
    Width=widthCm, Height=heightCm, Units="centimeters", ...
    Padding="figure", PreserveAspectRatio="off");
exportgraphics(fig, outputStem + ".png", Resolution=dpi, ...
    Width=widthCm, Height=heightCm, Units="centimeters", ...
    Padding="figure", PreserveAspectRatio="off");
savefig(fig, outputStem + ".fig");
end

function [style, recommendedDpi] = loadStyleProfile(path, placement, widthCm, artType)
style = struct(fontName="Times New Roman", axisLabelPt=8.5, tickPt=8, ...
    legendPt=7.5, mainPt=1.25, axesPt=0.8, gridPt=0.5, markerPt=3.5);
recommendedDpi = 600;
if strlength(path) == 0
    return;
end

profile = jsondecode(fileread(path));
if ~isfield(profile, "schema_version") || profile.schema_version ~= 1
    error("Style profile schema_version must be 1.");
end
placementField = char(placement);
if ~isfield(profile.placements, placementField)
    error("Placement '%s' is not defined by the style profile.", placement);
end
expectedWidth = profile.placements.(placementField).width_cm;
if abs(expectedWidth - widthCm) > 0.01
    error(["widthCm must be %g for placement '%s'; copy and document a " ...
        "journal-specific profile before overriding it."], expectedWidth, placement);
end
artField = char(artType);
if ~isfield(profile.raster_dpi, artField)
    error("No raster DPI is defined for art type '%s'.", artType);
end

fonts = string(profile.font_families);
style.fontName = fonts(1);
style.axisLabelPt = profile.typography.axis_label_pt;
style.tickPt = profile.typography.tick_pt;
style.legendPt = profile.typography.legend_pt;
style.mainPt = profile.strokes.main_pt;
style.axesPt = profile.strokes.axes_pt;
style.gridPt = profile.strokes.grid_pt;
style.markerPt = profile.strokes.marker_pt;
recommendedDpi = profile.raster_dpi.(artField);
end
