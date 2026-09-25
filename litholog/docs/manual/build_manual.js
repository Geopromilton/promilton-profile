// LithoLog Studio user manual (Word). Run from the manual folder: node build_manual.js
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, ImageRun, HeadingLevel, AlignmentType, Table, TableRow, TableCell,
  WidthType, ShadingType, BorderStyle, TableOfContents, Header, Footer, PageNumber, PageBreak, LevelFormat,
  TabStopType, TabStopPosition,
} = require("docx");

const SIZES = JSON.parse(fs.readFileSync("sizes.json", "utf8"));
const NAVY = "1F3A5F", AMBER = "D9861C", GREY = "5F6B7A", LIGHT = "EEF2F7", AMBER_BG = "FDF3E4";
const FONT = "Calibri";
const PAGE_W = 11906, MARGIN = 1134;           // A4, 2 cm margins
const TEXT_W = PAGE_W - 2 * MARGIN;             // 9638 DXA ≈ 6.69 in
const MAX_IN = TEXT_W / 1440;

let fig = 0, tab = 0;
const body = [];

// ------------------------------------------------------------------ helpers
function runs(text, base = {}) {
  // **bold**, *italic*, `code`
  const out = [];
  const re = /(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/g;
  let last = 0, m;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) out.push(new TextRun({ text: text.slice(last, m.index), ...base }));
    const t = m[0];
    if (t.startsWith("**")) out.push(new TextRun({ text: t.slice(2, -2), bold: true, ...base }));
    else if (t.startsWith("`")) out.push(new TextRun({ text: t.slice(1, -1), font: "Consolas", size: 19, color: "7A3E00", ...base }));
    else out.push(new TextRun({ text: t.slice(1, -1), italics: true, ...base }));
    last = m.index + t.length;
  }
  if (last < text.length) out.push(new TextRun({ text: text.slice(last), ...base }));
  return out;
}
const P = (t, o = {}) => body.push(new Paragraph({ children: runs(t), spacing: { after: 120, line: 276 }, ...o }));
const H1 = (t) => body.push(new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(t)], pageBreakBefore: true }));
const H2 = (t) => body.push(new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(t)] }));
const H3 = (t) => body.push(new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun(t)] }));
const B = (items, level = 0) => items.forEach((t) => body.push(new Paragraph({ numbering: { reference: "bullets", level },
  children: runs(t), spacing: { after: 60, line: 264 } })));
let listNo = 0;
const N = (items) => { listNo += 1; items.forEach((t) => body.push(new Paragraph({ numbering: { reference: "steps", level: 0, instance: listNo },
  children: runs(t), spacing: { after: 60, line: 264 } }))); };

function box(kind, text) {
  const color = kind === "Tip" ? "2E7D32" : kind === "Note" ? NAVY : "B45309";
  const fill = kind === "Tip" ? "EAF5EA" : kind === "Note" ? LIGHT : AMBER_BG;
  body.push(new Table({ width: { size: TEXT_W, type: WidthType.DXA }, columnWidths: [TEXT_W],
    rows: [new TableRow({ children: [new TableCell({ width: { size: TEXT_W, type: WidthType.DXA },
      shading: { fill, type: ShadingType.CLEAR, color: "auto" },
      borders: { left: { style: BorderStyle.SINGLE, size: 24, color }, top: { style: BorderStyle.NONE, size: 0, color: "FFFFFF" },
        bottom: { style: BorderStyle.NONE, size: 0, color: "FFFFFF" }, right: { style: BorderStyle.NONE, size: 0, color: "FFFFFF" } },
      margins: { top: 100, bottom: 100, left: 180, right: 180 },
      children: [new Paragraph({ children: [new TextRun({ text: kind + ": ", bold: true, color }), ...runs(text)] })] })] })] }));
  body.push(new Paragraph({ spacing: { after: 80 }, children: [] }));
}
const TIP = (t) => box("Tip", t), NOTE = (t) => box("Note", t), WARN = (t) => box("Important", t);

function FIG(file, caption, widthIn = MAX_IN) {
  const sz = SIZES[file];
  if (!sz) throw new Error("missing image " + file);
  const w = Math.min(widthIn, MAX_IN), h = w * sz[1] / sz[0];
  const maxH = 8.2, ww = h > maxH ? w * maxH / h : w, hh = Math.min(h, maxH);
  fig += 1;
  body.push(new Paragraph({ alignment: AlignmentType.CENTER, keepNext: true, spacing: { before: 120, after: 60 },
    children: [new ImageRun({ type: "png", data: fs.readFileSync(file), transformation: { width: Math.round(ww * 96), height: Math.round(hh * 96) },
      altText: { title: caption, description: caption, name: path.basename(file) } })] }));
  body.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 200 },
    children: [new TextRun({ text: `Figure ${fig}. `, bold: true, color: NAVY, size: 18 }), ...runs(caption, { size: 18, color: GREY })] }));
}

function TABLE(head, rows, widths, caption) {
  const total = widths.reduce((a, b) => a + b, 0);
  const cw = widths.map((w) => Math.round(w * TEXT_W / total));
  cw[cw.length - 1] += TEXT_W - cw.reduce((a, b) => a + b, 0);
  const border = { style: BorderStyle.SINGLE, size: 4, color: "C9D1DC" };
  const cell = (t, i, header) => new TableCell({ width: { size: cw[i], type: WidthType.DXA },
    shading: header ? { fill: NAVY, type: ShadingType.CLEAR, color: "auto" } : undefined,
    borders: { top: border, bottom: border, left: border, right: border },
    margins: { top: 60, bottom: 60, left: 100, right: 100 },
    children: [new Paragraph({ children: header ? [new TextRun({ text: t, bold: true, color: "FFFFFF", size: 19 })] : runs(t, { size: 19 }) })] });
  if (caption) {
    tab += 1;
    body.push(new Paragraph({ keepNext: true, spacing: { before: 120, after: 60 },
      children: [new TextRun({ text: `Table ${tab}. `, bold: true, color: NAVY, size: 18 }), new TextRun({ text: caption, size: 18, color: GREY })] }));
  }
  body.push(new Table({ width: { size: TEXT_W, type: WidthType.DXA }, columnWidths: cw,
    rows: [new TableRow({ tableHeader: true, children: head.map((h, i) => cell(h, i, true)) }),
      ...rows.map((r) => new TableRow({ children: r.map((c, i) => cell(String(c), i, false)) }))] }));
  body.push(new Paragraph({ spacing: { after: 120 }, children: [] }));
}
const CODE = (lines) => lines.forEach((l, i) => body.push(new Paragraph({ shading: { fill: "F4F6F9", type: ShadingType.CLEAR, color: "auto" },
  spacing: { after: i === lines.length - 1 ? 160 : 0 }, indent: { left: 200 },
  children: [new TextRun({ text: l, font: "Consolas", size: 18, color: "1E2530" })] })));

const I = (n) => `img/${n}.png`, F = (n) => `fig/${n}`;

// ================================================================== CONTENT
// ---------------------------------------------------------------- 1 Introduction
H1("1  Introduction");
P("**LithoLog** is free, open-source software for geologists, hydrogeologists and groundwater engineers. It turns borehole data into the outputs a groundwater or geological study needs: strip logs, cross-sections, fence diagrams, contour maps, three-dimensional geological models with volumes, water-table maps, groundwater-storage and recharge estimates, hydrochemical diagrams and fracture analyses. **LithoLog Studio** is its Windows desktop application; the same engine also runs as a web app in the browser and from the command line.");
H2("1.1  What LithoLog Studio does");
TABLE(["Area", "What you can do"], [
  ["Borehole data", "Read an Excel workbook, CSV files or GMS borehole files; check the data for gaps, overlaps and unknown codes; keep a project with all settings."],
  ["Logs and sections", "Strip logs with lithology patterns, descriptions, well construction, fractures and downhole curves; cross-sections through boreholes with correlated layers and pinch-outs; log sections; 3D fence diagrams."],
  ["Maps", "Contour maps of ground, top, base, depth and thickness of any unit, water table and depth to water, with inverse distance, kriging or TIN, clipped to the study area; grids for GIS."],
  ["3D model", "Horizon model that traces every layer between boreholes (like GMS Horizons → Solids) or voxel model; borehole-influence settings with variograms; constraints drawn in Google Earth; DEM as ground surface; volumes by layer and horizon."],
  ["Visualisation", "Lit 3D solids with textures, borehole tubes, labels, boundary and terrain; tick boxes and properties for every item; standard views; cut plane; dark and light themes; print images at up to 1200 dpi."],
  ["Groundwater", "Water table from observation wells for each season, fluctuation, saturated volume and storage of every unit, recharge by the water-table-fluctuation method (GEC-2015), 3D models of downhole properties."],
  ["Hydrochemistry", "Piper, Durov, Stiff, USSL, Wilcox and Gibbs diagrams; water type, ionic balance and irrigation indices."],
  ["Structure", "Fracture rose diagram, stereonet with pole density, fracture frequency with depth, water strikes."],
  ["Quality", "Leave-one-out cross-validation of the model with a one-page report, method comparison and volume uncertainty."],
], [1.3, 4.7], "LithoLog Studio at a glance");
H2("1.2  How this manual is organised");
P("Chapters 2 and 3 install the software and explain the window. Chapter 4 describes the input files — read it before preparing your own data. Chapters 5 to 14 follow a typical project from borehole logs to the 3D model, groundwater analysis and validation. Chapter 15 covers the command line and web app, chapter 16 the methods behind the results and their limits, and chapter 17 common questions. The appendices list the built-in lithology codes, patterns and file formats.");
H2("1.3  The tutorial data");
P("Every screenshot in this manual was made with the **tutorial project** that is installed with LithoLog Studio. Open it with **Home ▸ Tutorial project** and follow along. The tutorial is a **synthetic** hard-rock site (it is not a real place): 24 boreholes through top soil, weathered gneiss and gneiss with two water-bearing fracture zones, the lower of which pinches out towards the north-east.");
TABLE(["File", "Contents"], [
  ["tutorial_boreholes.xlsx", "24 boreholes with lithology, well construction, water level, resistivity log, fractures and legend (UTM zone 43N)."],
  ["tutorial_boundary.geojson", "Study-area polygon in latitude/longitude (16.4 km²)."],
  ["tutorial_water_levels.csv", "30 observation wells with pre- and post-monsoon depth to water."],
  ["tutorial_chemistry.csv", "18 groundwater samples with major ions, EC and pH."],
  ["tutorial_constraints.csv", "An area where the fracture zones are absent (an interpretation)."],
], [2, 4], "Tutorial files (folder litholog\\data\\tutorial inside the installation)");

// ---------------------------------------------------------------- 2 Installation
H1("2  Installation and first start");
H2("2.1  System requirements");
TABLE(["Item", "Requirement"], [
  ["Operating system", "Windows 10 or 11, 64-bit"],
  ["Memory", "8 GB RAM (16 GB for very large models or 1000-dpi exports)"],
  ["Graphics", "Any graphics card or integrated graphics with OpenGL 3.2 (all PCs from the last ten years)"],
  ["Disk", "About 1.5 GB for the program"],
  ["Internet", "Only needed to download a DEM (Home ▸ DEM ▸ Download)"],
], [1.5, 4.5], "System requirements");
H2("2.2  Installing");
N(["Download **LithoLogStudio-Windows** (a .zip file) from the project's GitHub page (Actions ▸ latest successful “LithoLog Studio (Windows build)” ▸ Artifacts).",
  "Unzip it. It contains **LithoLogStudio-Setup.exe** and a portable .zip.",
  "Run **LithoLogStudio-Setup.exe** and follow the steps. Windows may show “Windows protected your PC” because the installer is not code-signed; click **More info ▸ Run anyway**.",
  "Start **LithoLog Studio** from the Start menu or the desktop shortcut."]);
TIP("The portable .zip needs no installation: unzip it anywhere (for example a USB drive) and run LithoLogStudio.exe.");
H2("2.3  First start");
P("A splash screen appears while the 3D engine loads, then the main window opens with an empty 3D view (Figure 1). Open the tutorial with **Home ▸ Tutorial project**: the data are read, checked and a 3D model is built automatically (Figure 2).");
FIG(I("00_start"), "LithoLog Studio when it starts: empty 3D view, ribbon at the top, panels at the sides.");
FIG(I("01_main_3d"), "The tutorial project opened: 3D horizon model with the south-west quarter cut away, the Project tree (left), Properties (right), legend bar and Messages (bottom).");

// ---------------------------------------------------------------- 3 Window
H1("3  The LithoLog Studio window");
P("The window has six areas. They can be rearranged: drag a panel by its title bar to another side or float it; double-click a title bar to dock it again.");
TABLE(["Area", "Purpose"], [
  ["Ribbon (top)", "All commands, grouped in tabs: Home, Boreholes, Sections, Maps, 3D Model, Analysis and View."],
  ["Project tree (left)", "Everything in the project: boreholes, legend, study area, DEM, 3D model units, horizons and 3D scene items, each with tick boxes and a right-click menu."],
  ["Documents (centre)", "Tabs for the 3D Model, Strip Log, Cross-Section, Fence, Map, Chemistry, Fractures and Validation."],
  ["Legend bar", "Under the 3D view: colour, name and volume of each layer; click to edit."],
  ["Properties (right)", "Model settings, display settings, and the volume and storage tables."],
  ["Messages (bottom)", "A log of everything done, with results and warnings. The status bar repeats the latest message."],
], [1.5, 4.5], "Areas of the window");
H2("3.1  The ribbon");
P("Each ribbon tab groups related commands. Buttons with a coloured frame are switched on (for example the dark theme or the legend bar).");
FIG(I("02_ribbon_home"), "Home: open and save project files, open borehole data, legend, study-area boundary and DEM, the tutorial project, and save images or pages.");
FIG(I("02_ribbon_boreholes"), "Boreholes: strip log of the selected borehole, all logs as one PDF, and the data check.");
FIG(I("02_ribbon_sections"), "Sections: new cross-section, and the fence diagram.");
FIG(I("02_ribbon_maps"), "Maps: new contour map and export of the grid (.asc).");
FIG(I("02_ribbon_3dmodel"), "3D Model: build, layer properties, borehole influence and constraints, standard views, cut plane, and model exports.");
FIG(I("02_ribbon_analysis"), "Analysis: aquifer and storage, recharge, property model, stratigraphic model, hydrochemistry, fractures and cross-validation.");
FIG(I("02_ribbon_view"), "View: dark or light theme, 3D background, legend bar, axes grid and terrain, standard views, rendering options and layer properties.");
H2("3.2  The Project tree");
P("The tree lists everything in the project. **Tick boxes** show or hide an item in the 3D view; a group's tick box (for example *Boreholes* or *Horizons*) switches all its members. **Double-click** a borehole to open its strip log, or a layer to open its properties. **Right-click** any item for more: Layer properties, Strip log, Properties (colour, opacity, line width), *Show only this* and *Show all*.");
FIG(I("03_project_tree"), "The Project tree: every borehole has a tick box for the 3D view.", 3.2);
FIG(I("40_scene_tree"), "Lower part of the tree: lithology legend, study area, 3D model units, the 11 traced horizons and the 3D scene items (borehole names, water table, constraints, axes grid, N/E/Up marker, legend bar).", 3.2);
FIG(I("41_scene_properties"), "Right-click ▸ Properties on the study area: colour, opacity and line width.", 3);
H2("3.3  The Properties panel");
FIG(I("04_properties"), "The Properties panel: Model and Display groups (the Volumes & storage tables follow below).", 3.4);
TABLE(["Setting", "Meaning"], [
  ["Method", "Horizons – correlated layers (recommended for layered and weathered profiles) or Voxel – indicator interpolation (for irregular bodies and lenses). See chapter 9."],
  ["Interpolation", "How horizon thickness is interpolated between boreholes: inverse distance, kriging, linear TIN or smooth TIN."],
  ["Influence… / Constraints…", "Borehole-influence settings with variogram (9.3) and interpretation lines and areas (9.4)."],
  ["Correlate at", "Voxel method only: compare boreholes at equal depth below ground (hard rock) or equal elevation (flat-lying sediments)."],
  ["Cell (XY), Cell (Z)", "Model cell size; Auto chooses about 120 cells across the area."],
  ["Smoothing", "Voxel method only: smoothing of the solids."],
  ["Clip to study area", "Limit the model to the boundary polygon."],
  ["Use DEM as ground surface", "Top of the model follows the DEM (when a DEM is loaded)."],
  ["Replace collar elevations with DEM", "Use DEM elevations for boreholes and wells (see 4.6)."],
  ["Vertical exaggeration", "Stretch of the vertical scale; Auto makes the model about one third as high as wide."],
  ["Opacity", "Transparency of all solids."],
  ["Cut-away", "Remove one quarter of the model to see inside."],
  ["Borehole name size, Axis text size", "Size of the labels and axis numbers in the 3D view (and, proportionally, in exports)."],
  ["Boreholes, Labels, Boundary", "Show borehole tubes, their names and the study-area outline."],
], [1.8, 4.2], "Properties panel settings");
H2("3.4  Legend bar and messages");
FIG(I("05_legend_bar"), "The legend bar under the 3D view: each layer with its colour and volume. Click a layer to edit it; right-click to hide, show or isolate it; double-click the title to rename the legend.");
FIG(I("06_messages"), "Messages: what was done and the results (here the model build and the traced horizons).");
H2("3.5  Themes");
P("**View ▸ Dark / Light** switches the colour theme; LithoLog remembers your choice. **View ▸ 3D background** sets the background of the 3D view independently (theme, white, sky or black) — white is useful for reports.");
FIG(I("42_light_theme"), "The light theme.");
H2("3.6  Keyboard shortcuts and mouse");
TABLE(["Action", "How"], [
  ["Save project", "Ctrl+S"], ["Save project as", "Ctrl+Shift+S"], ["Open project", "Ctrl+O"],
  ["Rotate the 3D view", "Drag with the left mouse button"], ["Pan", "Shift + drag, or drag with the middle button"],
  ["Zoom", "Mouse wheel, or drag with the right button"], ["Spin around the view axis", "Ctrl + drag"],
  ["Zoom a page (logs, sections, maps)", "The −, + and Fit buttons above the page; the magnifier of the page toolbar"],
], [2.5, 3.5], "Shortcuts");

// ---------------------------------------------------------------- 4 Data
H1("4  Preparing your data");
P("LithoLog reads plain tables. The easiest start is the Excel template: on the command line run `litholog template my_site.xlsx`, or copy the tutorial workbook and replace its rows. Column names are recognised flexibly (for example *Borehole ID*, *BH*, *Well no*), units in brackets are ignored, and sheets may be in any order.");
H2("4.1  The borehole workbook");
TABLE(["Sheet", "Columns", "Notes"], [
  ["Boreholes", "Borehole ID, X (Easting), Y (Northing), Elevation (m amsl), Total depth (m)", "One row per borehole. Coordinates in metres (e.g. UTM)."],
  ["Lithology", "Borehole ID, From (m), To (m), Code, Description", "Depths below ground; intervals must not overlap or leave gaps."],
  ["Construction", "Borehole ID, From, To, Element, Diameter (mm), Material", "Casing, screen, gravel pack, seal… (optional)."],
  ["WaterLevels", "Borehole ID, Date, Depth to water (m bgl)", "Optional; used for water-table maps and the aquifer tools."],
  ["Downhole", "Borehole ID, Depth (m), Parameter, Value, Unit", "Logs such as resistivity, EC, gamma (optional)."],
  ["Fractures", "Borehole ID, Depth, Dip, Dip direction, Aperture, Yield, Remarks", "Structural and water-strike data (optional)."],
  ["Legend", "Code, Name, Color, Pattern, Group", "Your own lithology codes (optional; see 4.3)."],
], [1.1, 2.9, 2], "Sheets of the borehole workbook");
NOTE("Depths are always metres below ground level (m bgl), measured from the collar. The *Total depth* is optional; the deepest *To* is used when it is missing.");
H2("4.2  GMS borehole files");
P("Files exported from GMS (columns *Name, X, Y, Z, Material*, one row per contact, text or Excel) are read directly by **Home ▸ Open data**. The Z values are converted to depths below the first (collar) elevation and each material ID becomes a lithology code; give names and colours with a legend file. `litholog convert file.txt workbook.xlsx` turns such a file into a LithoLog workbook that you can then complete with descriptions, construction and water levels.");
H2("4.3  Lithology codes, legend and patterns");
P("Each interval has a **code**. Thirty codes are built in (Appendix A) with names, colours and patterns drawn at a fixed printed size. Use your own codes with a **legend** table (CSV or Excel, or the Legend sheet): columns *Code, Name, Color* (hex, e.g. #9FCBEA), *Pattern* and optionally *Group*. Patterns can be combined with “+”, for example `waves+fractures` (Appendix B). Colours and names can also be changed at any time in **Layer properties** (9.8) and saved as a legend file.");
H2("4.4  Coordinates");
P("Borehole coordinates must be in a projected system in metres, such as UTM. Boundaries, DEMs and well files in latitude/longitude are converted automatically to the UTM zone of your boreholes; when LithoLog needs the coordinate system (for example to download a DEM) it proposes one and lets you correct it (e.g. EPSG:32643 for WGS 84 / UTM zone 43N).");
H2("4.5  Study-area boundary");
P("**Home ▸ Boundary** accepts a shapefile (.shp with its .prj, or zipped), a Google Earth **KML/KMZ** or **GeoJSON**. Multi-part polygons and holes are supported. Maps and the model are then clipped to the polygon, and volumes are totalled inside it. If a UTM shapefile is in a neighbouring zone, LithoLog detects it and moves it to the zone of the boreholes, and reports what it did in Messages.");
H2("4.6  Digital elevation model (DEM)");
P("**Home ▸ DEM** opens a GeoTIFF, an SRTM tile (.hgt, .hgt.gz or .zip) or an ESRI ASCII grid, in any coordinate system. **Download (Copernicus 30 m)** fetches the free Copernicus GLO-30 DEM for the project area from the internet and saves it in a folder you choose.");
FIG(I("44_dem_dialog"), "Home ▸ DEM: open a DEM file or download one.", 4.5);
P("When a DEM is loaded, LithoLog compares the borehole collar and well elevations with it and reports the mean difference in Messages. Tick **Use DEM as ground surface** so the model top follows the terrain, and **Replace collar elevations with DEM** to use DEM elevations for boreholes and wells.");
WARN("A difference that is nearly the same for every borehole (for example +19.5 m ± 1.8 m) usually means the elevations were measured against a different height reference (handheld GPS heights, a local benchmark). Relative results — thickness, gradient, fluctuation, volume — are not affected; absolute “m amsl” values are. Decide which reference to report before replacing elevations.");
H2("4.7  Observation-well (water-level) file");
P("A CSV or Excel table with one row per well: a name, coordinates and one column per reading, for example *Well, Easting, Northing, Elevation, Pre-monsoon, Post-monsoon*. Alternatively one row per reading with a *Date* and a *Depth to water* column. Coordinates may be metres or degrees; degrees are recognised even when written under X/Y, in either order. A serial-number column is ignored, village names are used as well IDs, and two wells with the same name are kept apart (“Nanguneri (1)”, “Nanguneri (2)”).");
H2("4.8  Water-quality file");
P("One row per sample with *Sample*, an optional *Group*, the major ions **Ca, Mg, Na, K, HCO3, Cl, SO4** (mg/L, or meq/L when the column name says so), and optionally *CO3, NO3, F, EC, TDS, pH*. Values such as “<0.5” are read as 0.5.");
H2("4.9  Constraints file");
P("Constraints add your interpretation to the boreholes (9.4). In a table: *Horizon, Type, X, Y, Value, Feature*, where Type is **pinchout** (a line where the layer thins to zero), **absent** (an area without the layer) or **thickness** (a point of known thickness), and rows with the same Feature form one line or polygon. In Google Earth or QGIS draw the line, polygon or point and name it like `H4 pinchout`, `code FGN absent` or `H7 thickness 6`, then save as KML/KMZ or GeoJSON.");
H2("4.10  Checking the data");
P("**Boreholes ▸ Validate data** (also run automatically when data are opened) reports overlapping or missing intervals, depths beyond the total depth, unknown codes, missing coordinates and similar problems in Messages. Fix errors in your workbook and open it again.");

// ---------------------------------------------------------------- 5 Projects
H1("5  Working with projects");
P("A **project file** (.llproj) remembers everything about your work: the data, legend and boundary files, the DEM and constraints, model and display settings, layer colours and visibility, specific yields, view settings and text sizes. It stores the file names relative to its own folder, so a project folder can be copied to another computer.");
TABLE(["Command", "What it does"], [
  ["Home ▸ Open data", "Start a new project from a borehole workbook, CSV folder or GMS file."],
  ["Home ▸ Open project (Ctrl+O)", "Open a saved .llproj and rebuild everything as it was."],
  ["Home ▸ Save project (Ctrl+S)", "Save to the current project file (asks for a name the first time)."],
  ["Home ▸ Save as… (Ctrl+Shift+S)", "Save under a new name."],
], [2.3, 3.7], "Project commands");
H2("5.1  Closing with unsaved changes");
P("If you close LithoLog Studio after changing anything since the last save, it asks whether to save. **Save** writes the project file, **Don't save** closes without saving, and **Cancel** returns to your work.");
FIG(I("43_save_prompt"), "The prompt shown when closing with unsaved changes.", 4.2);

// ---------------------------------------------------------------- 6 Logs
H1("6  Borehole strip logs");
P("Select a borehole in the Project tree and click **Boreholes ▸ Strip log**, or double-click the borehole. The log opens in the Strip Log tab as a true-proportion page. **Boreholes ▸ All logs (PDF)** writes every log to one PDF.");
FIG(I("10_striplog"), "A strip log in the Strip Log tab.");
FIG(F("logs/TB-08.png"), "The strip log of TB-08 as printed: depth and elevation scales, lithology column with patterns, descriptions, well construction, fracture tadpoles and the resistivity curve.", 5.2);
TABLE(["Track", "Content"], [
  ["Depth / Elevation", "Metres below ground and metres above sea level."],
  ["Lithology", "Colour and pattern of each interval (patterns print at the same size at any scale)."],
  ["Description", "Your description text, wrapped to fit."],
  ["Well", "Casing, screen, gravel pack and seals (hidden when there are no construction data)."],
  ["Fractures", "Tadpoles: the dot at the depth and dip, the tail pointing in the dip direction; water strikes marked."],
  ["Curves", "Up to three downhole parameters (e.g. resistivity) on their own scales."],
], [1.5, 4.5], "Tracks of a strip log");
TIP("Long holes are split into pages automatically on the command line with `-m 50` (50 m per page). Save the page as PDF or SVG with **Home ▸ Save page** for editing in a drawing program.");

// ---------------------------------------------------------------- 7 Sections
H1("7  Cross-sections and fence diagrams");
H2("7.1  Cross-sections");
N(["Click **Sections ▸ New section**.",
  "Give the section a name, choose the vertical exaggeration (Fit page is automatic) and how boreholes are hung (by elevation or depth below ground).",
  "Choose the section style: a geological section, or a **log section** with strip logs along the line and optionally a curve beside each log.",
  "Add boreholes to the section with **Add ▸** in the order they should appear, then **OK**."]);
FIG(I("11_section_dialog"), "The New section dialog.", 4.4);
P("LithoLog correlates the layers between neighbouring boreholes by matching their sequences (the same method as the horizon model), draws each layer as a continuous band, and ends layers that are missing in the next hole half-way between the holes (pinch-out).");
FIG(F("section.png"), "Cross-section A–A' through TB-01, TB-08, TB-15 and TB-22: correlated layers, both fracture zones and pinch-outs.");
FIG(I("13_section_logs"), "The log-section style: strip logs along the line with the resistivity curve.");
H2("7.2  Fence diagrams");
P("**Sections ▸ Fence diagram** connects the boreholes with a network of panels (minimum spanning tree) and draws them in a 3D perspective, a quick overview of the whole site.");
FIG(F("fence.png"), "Fence diagram of the tutorial site.");

// ---------------------------------------------------------------- 8 Maps
H1("8  Contour maps");
N(["Click **Maps ▸ New map**.", "Choose what to map and, for unit-related maps, the unit.",
  "Choose the gridding method and cell size, and whether to clip to the study area, then **OK**."]);
FIG(I("15_map_dialog"), "The New map dialog.", 3.4);
TABLE(["Map", "Value at each borehole"], [
  ["Ground elevation", "Collar elevation (m amsl)"], ["Top / Base of unit", "Elevation of the top or base of the chosen unit"],
  ["Depth to unit", "Depth below ground of the unit's top"], ["Thickness (isopach)", "Total thickness of the unit; the map also reports its volume"],
  ["Water-table elevation", "Ground minus depth to water, with arrows showing the groundwater flow direction"],
  ["Depth to water", "From the WaterLevels sheet"], ["Drilled depth", "Total depth of each borehole"],
], [2, 4], "Map types");
FIG(F("map/thickness_WGN.png"), "Isopach (thickness) map of the weathered gneiss, kriged and clipped to the study area. The side panel lists the data used, range, method, cell size and the share of the area beyond the boreholes.");
P("**Maps ▸ Grid (.asc)** saves the grid for QGIS, ArcGIS or Surfer. Gridding methods are explained in 16.2.");

// ---------------------------------------------------------------- 9 3D model
H1("9  The 3D geological model");
P("The model is built automatically when data are opened; rebuild it with **3D Model ▸ Build model** (or the orange button in Properties) after changing settings.");
H2("9.1  Horizon method and voxel method");
TABLE(["", "Horizons – correlated layers", "Voxel – indicator interpolation"], [
  ["How it works", "Traces every layer from hole to hole, interpolates the thickness of each, and stacks them from the ground down.", "Each cell takes the unit most boreholes have at that depth, weighted by distance."],
  ["Best for", "Layered sequences, weathering profiles, repeated thin layers such as fracture zones.", "Irregular bodies and lenses that do not continue between holes."],
  ["Thin layers", "Stay continuous where the data support it.", "Tend to break into isolated patches."],
  ["Volumes", "Exact from the thickness grids; also per horizon.", "From the vote shares, so thin units are not under-counted."],
], [1.2, 2.4, 2.4], "The two modelling methods");
P("With the horizon method, a unit that occurs more than once in the boreholes becomes several **horizons**, numbered from the top, for example *Fractured gneiss · zone 1* and *zone 2*. The Messages panel lists them and the Project tree shows each with its volume. If most horizons occur in only one borehole, LithoLog notes that the voxel method may suit the data better.");
H2("9.2  Showing and hiding layers and horizons");
P("Untick a unit under **3D model units** to hide it (with all its horizons), or untick single horizons under **Horizons**. Right-click a horizon ▸ *Show only this* isolates it.");
FIG(I("23_horizons_only_fractures"), "Only the two fracture-zone horizons ticked: both are continuous sheets; the lower one is cut out in the north-east by the constraint.");
H2("9.3  Borehole influence");
P("**3D Model ▸ Borehole influence** (or *Influence…* in Properties) controls how strongly and how far each borehole influences the interpolated layers — the options GMS calls interpolation settings.");
FIG(I("21_influence"), "The Borehole influence dialog with the experimental variogram of fracture zone 1 (dots) and the fitted spherical model (line).");
TABLE(["Setting", "Effect"], [
  ["Method", "Inverse distance (IDW), kriging, linear TIN or smooth (Clough-Tocher) TIN."],
  ["IDW power", "Higher (3–5): each borehole's influence stays local, giving “bull's-eyes”. Lower (1–2): smoother, influence spreads further. Default 2."],
  ["Nearest boreholes", "Use only the N closest boreholes for each point (All = every borehole)."],
  ["Search radius", "Boreholes farther away have no influence (the nearest one is always used)."],
  ["Variogram", "Kriging model: spherical, exponential or gaussian."],
  ["Range, sill, nugget", "Fitted automatically to the data, or your own values: the range is the distance over which values are related; the nugget is variation at shorter distances than the borehole spacing."],
  ["Show for", "Which horizon's variogram to display."],
], [1.5, 4.5], "Borehole-influence settings");
TIP("A large nugget (a big jump of the model curve at zero distance) means that much of the variation happens between boreholes and cannot be predicted from them. Check your choices with **Analysis ▸ Cross-validation** (chapter 14), which scores “your settings” against the defaults.");
H2("9.4  Constraints — adding your interpretation");
P("**3D Model ▸ Constraints ▸ Load file…** reads pinch-out lines, absent areas and thickness points (format in 4.9). A constraint applies to one horizon (H4 = horizon 4 as numbered in the Project tree) or to all horizons of a unit (code FGN). Constraints are drawn on the model (orange lines, magenta areas, white points) and saved with the project. **Remove constraints** in the same dialog goes back to the boreholes alone.");
FIG(I("22_constraints"), "The tutorial constraint (magenta outline, north-east): the fracture zones are absent inside it.");
WARN("Horizon numbers come from the automatic correlation. After adding or changing boreholes, check the numbering in the Project tree before reusing a constraints file, or use unit codes (code FGN) instead.");
H2("9.5  Views and navigation");
P("Rotate, pan and zoom with the mouse (3.6). The standard views are on the 3D Model and View tabs: **Oblique** (from south-west), **Oblique NE**, **Top** (plan), **Front** (from the south), **Back**, **Left side** (from the west) and **Right side**. Front, side and top views are orthographic (without perspective) so that distances can be read.");
FIG(I("24_view_front"), "Front view (looking north), exported at 150 dpi: the fracture zones and their depth variation are clear.");
FIG(I("26_view_left"), "Left-side view (looking east).");
FIG(I("25_view_top"), "Top view (plan) with the study-area boundary and the constraint area.");
H2("9.6  Cut-away and cut plane");
P("**Cut-away** in Properties removes one quarter of the model. **3D Model ▸ Cut plane** adds an amber plane that cuts every solid: drag the plane to move it, drag its arrow to tilt it; click Cut plane again to remove it.");
FIG(I("29_cut_plane"), "The interactive cut plane.");
H2("9.7  Layer properties and the legend bar");
P("**3D Model ▸ Layer properties**, a click on a layer in the legend bar, or a double-click on a layer in the tree opens Layer properties. Choose a layer on the left, then change its name, colour (colour picker), pattern for logs and sections (with preview), group, 3D opacity and visibility. **Apply** shows the change at once in the 3D view, logs, sections and maps; **Save legend…** writes the legend as CSV for other projects, **Load legend…** reads one.");
FIG(I("20_layer_properties"), "Layer properties: name, colour, pattern with preview, group, opacity and volume.");
H2("9.8  3D scene items");
P("Everything drawn in the 3D view has a tick box in the Project tree: each borehole, the borehole names, study area, DEM terrain, water table, constraints, axes grid, N/E/Up marker and the legend bar. Right-click ▸ **Properties** changes colour, opacity and line width (and the thickness of the borehole tubes). These settings are kept when the model is rebuilt, in exported images and in the project file.");
H2("9.9  Rendering options");
P("**View ▸ Rendering** improves the look of the model: **Rock texture** (a subtle grain in each layer's colour), **Pattern texture** (the log pattern on the solids), **Vivid colour** (livelier versions of pale legend colours), **Contact lines** (thin dark lines along layer edges) and **Ambient occlusion** (soft shadows in corners; needs a capable graphics card).");
FIG(I("27_pattern_texture"), "Pattern texture: the lithology patterns of the logs drawn on the solids.");
H2("9.10  Volumes and storage");
P("The **Volumes & storage** table in Properties lists the volume of each unit (MCM = million m³) inside the study area and its share. Type a **specific yield** for a unit to see its groundwater storage (volume × specific yield). The **By horizon** tab lists every horizon with the boreholes where it is found, its mean thickness, the share of the area where it exists and its volume.");
H2("9.11  Exporting the model");
TABLE(["Export (3D Model tab)", "Result"], [
  ["3D web page", "An interactive HTML page that opens in any browser (rotate, zoom, hide layers)."],
  ["Solids (OBJ/STL)", "One OBJ, STL and VTP file per unit, in real coordinates, for CAD, 3D printing or other software."],
  ["ParaView", "The whole model as a VTK file."],
  ["Volumes", "The volume table as CSV."],
], [2, 4], "Model exports");

// ---------------------------------------------------------------- 10 Images
H1("10  Images and pages for reports");
P("**Home ▸ Save image** saves the current document — the 3D view, a log, section, map or diagram — as a print-quality image.");
FIG(I("28_export_dialog"), "The Save image dialog.", 3.6);
TABLE(["Option", "Meaning"], [
  ["View (3D)", "The current view, one standard view, or all standard views at once (one image each)."],
  ["Size / Width", "Printed width: journal column 90 mm, page width 180 mm, A4 or A3, or your own."],
  ["Resolution", "300, 600, 1000 (default) or 1200 dpi. 180 mm at 1000 dpi is 7,087 pixels."],
  ["Text size", "Printed size of labels and axis text in points (1 pt = 1/72 inch); 7–9 pt suits journal figures. Auto keeps the on-screen proportions."],
  ["Format", "PNG (lossless), TIFF (LZW, for printers and journals) or JPEG. The DPI is written into the file."],
], [1.4, 4.6], "Image export options");
P("For 3D images the scene is drawn again at the full output size, not enlarged from the screen, so lines and text stay sharp; the legend bar is added below. **Home ▸ Save page** saves logs, sections and maps as PDF or SVG (vector: sharp at any zoom and editable in Inkscape or Illustrator).");
TIP("Rendering a 1000-dpi 3D image takes a few seconds on a normal graphics card. If memory is short, choose a smaller width or 600 dpi, or save pages as PDF.");

// ---------------------------------------------------------------- 11 Groundwater
H1("11  Groundwater analysis");
H2("11.1  Aquifer and storage");
N(["Click **Analysis ▸ Aquifer & storage**.", "Choose the observation-well file (4.7), or Cancel to use the WaterLevels sheet of the borehole workbook.",
  "Choose the reading (season) when the file has several.",
  "The water table is drawn in the 3D model (the solids become translucent) and as a map with flow arrows; Messages lists the saturated volume of each unit and, where you have typed specific yields, its storage."]);
FIG(I("30_aquifer_3d"), "Pre-monsoon water table (blue surface) in the 3D model.");
FIG(I("31_water_table_map"), "Water-table map with groundwater flow arrows.");
P("By default the depth to water is interpolated between the wells and hung below the ground surface, so the water table follows the topography. The command line also offers contouring of water-table elevations from the wells (`--surface elevation`).");
H2("11.2  Recharge (water-table fluctuation method)");
P("**Analysis ▸ Recharge (WTF)** estimates recharge between a pre- and a post-season reading, following the water-table-fluctuation method of GEC-2015:");
B(["storage change ΔS = Σ (volume of each unit between the two water tables × its specific yield);",
  "total recharge = ΔS + gross groundwater draft during the season;",
  "recharge from rainfall = total recharge − recharge from other sources (tanks, canals, return flow);",
  "with the rainfall of the season: recharge as a percentage of rainfall, and the rainfall-infiltration-factor (RIF) estimate for comparison."]);
FIG(I("32_recharge_dialog"), "The Recharge dialog: readings, rainfall, draft, other sources, RIF, water-table method and specific yield of each unit.", 4.4);
WARN("Specific yield, draft, other sources and the RIF are your inputs (for example from GEC-2015 norms and field data); LithoLog does not assume them. Units without a specific yield are counted as zero and listed in Messages.");
H2("11.3  Property model");
P("**Analysis ▸ Property model** interpolates a downhole parameter (resistivity, EC, yield…) through the model with anisotropic inverse distance (vertical distances are stretched because properties change faster with depth). Choose the parameter and optionally a value range: the voxels within the range are shown with a colour bar, and Messages reports their volume — for example the volume of low-resistivity (fractured, water-bearing) rock.");
FIG(I("33_property_model"), "Resistivity model showing only values below 500 Ω·m: the fracture zones and the weathered zone.");
H2("11.4  Stratigraphic model");
P("**Analysis ▸ Stratigraphy model** builds a layer-cake model from formations in a known order (top to bottom): tick the formations and drag them into order. Each formation's top is gridded and forced into order, so surfaces never cross. Use it for sedimentary sequences where each formation occurs once.");
FIG(I("34_strat_dialog"), "The Stratigraphy model dialog.", 3.4);

// ---------------------------------------------------------------- 12 Chemistry
H1("12  Hydrochemistry");
P("**Analysis ▸ Hydrochemistry** reads a water-quality file (4.8), computes the analysis and opens the Chemistry tab with a diagram selector and the results table.");
FIG(I("35_chemistry"), "The Chemistry tab with the Piper diagram.");
FIG(F("chem/piper.png"), "Piper diagram of the 18 tutorial samples by group.", 5);
TABLE(["Diagram / result", "Use"], [
  ["Piper", "Water type from the relative major cations and anions."], ["Durov", "Water type with TDS and pH."],
  ["Stiff", "Shape of each sample's composition, for comparing samples."],
  ["USSL (Richards, 1954)", "Irrigation classes from salinity (EC) and sodium hazard (SAR)."],
  ["Wilcox (1955)", "Irrigation suitability from %Na and EC."], ["Gibbs", "Controls on chemistry: rainfall, rock weathering or evaporation (indicative)."],
  ["Results table", "Ions in meq/L, ionic balance (flagged outside ±5 %), water type, SAR, %Na, RSC, Kelly's ratio, permeability index, magnesium hazard and irrigation classes."],
], [1.8, 4.2], "Hydrochemical diagrams and indices");
FIG(F("chem/ussl.png"), "USSL (Richards) diagram.", 4.6);

// ---------------------------------------------------------------- 13 Fractures
H1("13  Fracture analysis");
P("**Analysis ▸ Fractures** uses the Fractures sheet: a strike rose diagram (bidirectional, right-hand rule), an equal-area (Schmidt) lower-hemisphere stereonet with poles, great circles and pole density, and fracture frequency with depth with water strikes marked.");
FIG(F("fractures.png"), "Fracture analysis page of the tutorial site.");

// ---------------------------------------------------------------- 14 Validation
H1("14  Model validation (cross-validation)");
P("A 3D model is an estimate between boreholes. **Analysis ▸ Cross-validation** measures how good that estimate is: each borehole is hidden in turn, its log is predicted from the others, and the prediction is compared with the real log. Choose a folder for the report and the unit to report in detail.");
FIG(I("37_validation"), "The Validation tab with the one-page report.");
TABLE(["Result", "Meaning"], [
  ["Depth logged correctly (%)", "Share of the drilled depth where the predicted unit equals the logged unit, as the mean over all boreholes and for the worst 10 %."],
  ["Occurrences detected (%)", "For the chosen unit: share of its occurrences in the hidden boreholes that the prediction also shows there."],
  ["False alarms", "Predicted occurrences that the borehole does not have."],
  ["Top depth error (m)", "Mean difference in the depth of the top, where the occurrence was found."],
  ["Nearest-borehole baseline", "Simply copying the nearest borehole. A useful model must do better than this."],
  ["Accuracy map", "The score at each borehole — shows where the model is weak."],
  ["Distance to nearest borehole", "Data support: far from boreholes the model is extrapolated and cannot be checked."],
  ["Volume range", "The volume of each unit from every method: a practical uncertainty range to quote in reports."],
], [2, 4], "Cross-validation results");
P("The report compares the horizon model (inverse distance and kriging), the voxel model, the nearest-borehole baseline and — when you have changed the borehole influence or loaded constraints — **your settings**. Tables of every borehole and unit are saved as CSV beside the PDF.");
TIP("Quote volumes as the range across methods, and describe where the model is supported by boreholes. Thin units that change quickly between holes (such as fracture zones in hard rock) usually score low: geophysics between the boreholes is the way to improve them.");

// ---------------------------------------------------------------- 15 CLI
H1("15  Command line and web app");
P("The same engine runs from a command window (after `pip install litholog`), which is useful for batch work and scripts. Every command has `--help`.");
TABLE(["Command", "Purpose"], [
  ["litholog template FILE.xlsx", "Write the input workbook to fill in."], ["litholog validate DATA", "Check the data."],
  ["litholog convert GMS.txt OUT.xlsx", "Convert GMS or CSV input to a workbook."], ["litholog striplog DATA", "Strip logs of all or selected boreholes."],
  ["litholog section DATA -b A B C", "Cross-section through boreholes (or --line X,Y …)."], ["litholog fence DATA", "Fence diagram."],
  ["litholog map DATA -a thickness:CODE", "Contour maps and grids."], ["litholog model DATA", "3D model, views, volumes (options: --method, --power, --constraints, --dem …)."],
  ["litholog aquifer DATA -w WELLS", "Water table, fluctuation, storage and recharge."], ["litholog property DATA -p Resistivity", "3D property model."],
  ["litholog strat DATA --order A B C", "Stratigraphic model."], ["litholog chem CHEM.csv", "Hydrochemistry diagrams and indices."],
  ["litholog fractures DATA", "Fracture analysis."], ["litholog crossval DATA -u CODE", "Cross-validation report."],
  ["litholog studio / litholog app", "Open LithoLog Studio / the browser app."],
], [2.6, 3.4], "Commands");
P("Examples with the tutorial data:");
CODE(["litholog model tutorial_boreholes.xlsx --boundary tutorial_boundary.geojson --sy WGN=0.015 FGN=0.01",
  "litholog model tutorial_boreholes.xlsx --grid-method kriging --variogram exponential --constraints tutorial_constraints.csv",
  "litholog aquifer tutorial_boreholes.xlsx -w tutorial_water_levels.csv --sy WGN=0.015 FGN=0.01 --rainfall 900 --draft 1.2",
  "litholog crossval tutorial_boreholes.xlsx -u FGN --power 4 -o validation"]);
P("The **web app** (`litholog app`, or a hosted copy) offers strip logs, sections, fence diagrams, maps and the 3D model in a browser: upload the workbook, and optionally a boundary and DEM, and download the results.");

// ---------------------------------------------------------------- 16 Methods
H1("16  Methods and limitations");
H2("16.1  Correlation of layers");
P("Borehole logs are compared as sequences of units. A sequence-alignment method (as used for DNA sequences) matches units of the same code at similar depths, allowing for units that are missing in one hole. For the horizon model all boreholes are aligned progressively into one master sequence of horizons; horizons of the same unit that never occur together in a hole and can be merged without breaking any hole's order are merged.");
H2("16.2  Interpolation");
B(["**Inverse distance (IDW)**: a weighted average of the boreholes, weights 1/distance^power; honours the boreholes exactly.",
  "**Kriging**: ordinary kriging with a variogram fitted to the data (or given by you); a statistically best linear estimate.",
  "**Linear TIN / smooth TIN**: triangulation between boreholes (the nearest borehole beyond the outer boreholes).",
  "Horizon thickness is interpolated with zeros where a horizon is absent; a presence indicator decides where the layer exists so layers pinch out between holes rather than spreading thinly everywhere.",
  "Volumes are integrated from the thickness grids (horizon model) or from the vote shares (voxel model), and agree with isopach volumes."]);
H2("16.3  What the results can and cannot tell you");
B(["Values at boreholes are data; values between them are estimates, and far from boreholes (see the distance map in the validation report) they are extrapolations.",
  "Automatic correlation can pair the wrong zones where logs are ambiguous. Review the horizons in the Project tree and add constraints where your geological judgement differs.",
  "Storage and recharge depend directly on the specific yield and draft you enter.",
  "Elevations: check boreholes and wells against a DEM (4.6) before reporting absolute levels.",
  "Hydrochemical classes follow the published diagrams (Richards 1954, Wilcox 1955, Gibbs 1970); the Gibbs diagram is indicative only."]);

// ---------------------------------------------------------------- 17 FAQ
H1("17  Troubleshooting and questions");
TABLE(["Problem", "What to do"], [
  ["The boundary does not overlap the boreholes", "The boundary and the boreholes are in different coordinate systems. Save the boundary with a .prj file, or use KML/GeoJSON; LithoLog reprojects them to the boreholes' UTM zone."],
  ["A thin layer breaks into patches", "Use Method: Horizons. If it still breaks, check the horizons in the tree and add constraints."],
  ["Bull's-eyes around boreholes", "Lower the IDW power, or use kriging (9.3)."],
  ["Too many horizons, most in one borehole", "The layers do not continue between holes; the voxel method may represent the data better."],
  ["Collar elevations differ from the DEM by a constant amount", "Different height reference; see 4.6."],
  ["The 3D view is black or empty", "Update the graphics driver. On remote desktops enable hardware graphics, or use the portable version on the local PC."],
  ["Exporting a 1000-dpi image fails", "Use a smaller width or 600 dpi, or save the page as PDF/SVG."],
  ["Windows warns about the installer", "The installer is not code-signed; choose More info ▸ Run anyway."],
  ["Water-level file reads wrong positions", "Coordinates in degrees are recognised automatically; check the Messages note (for example “X was latitude, Y longitude: swapped”)."],
], [2.2, 3.8], "Common problems");

// ---------------------------------------------------------------- Appendices
H1("Appendix A  Built-in lithology codes");
TABLE(["Code", "Name", "Code", "Name"], [
  ["TOP", "Topsoil", "GRA", "Granite (massive)"], ["RSOIL", "Red soil", "WGN", "Weathered gneiss"],
  ["BCS", "Black cotton soil", "FGN", "Fractured gneiss"], ["FILL", "Fill / made ground", "GN", "Gneiss"],
  ["CLAY", "Clay", "SCH", "Schist"], ["SCLAY", "Sandy clay", "PHY", "Phyllite"], ["SILT", "Silt", "QTZ", "Quartzite"],
  ["SAND", "Sand", "BIF", "Banded iron formation"], ["GRAV", "Gravel", "DOL", "Dolerite dyke"],
  ["KANK", "Kankar / calcrete", "BAS", "Basalt (massive)"], ["LAT", "Laterite", "VBAS", "Vesicular basalt"],
  ["LITHO", "Lithomarge", "SST", "Sandstone"], ["SAPR", "Saprolite / weathered zone", "SHL", "Shale"],
  ["WGRA", "Weathered granite", "LST", "Limestone"], ["FGRA", "Fractured granite", "NOREC", "No recovery / not logged"],
], [1, 2, 1, 2], "Built-in codes (names, colours and patterns can be changed in Layer properties)");
H2("Appendix B  Patterns");
P("Pattern names for the legend (combine with “+”): `blank`, `dots`, `fine_dots`, `dashes`, `circles`, `blobs`, `hlines`, `diag`, `backdiag`, `fractures`, `crosses`, `xmarks`, `vees`, `waves`, `schist`, `brick`, `bands`, `roots`.");
H2("Appendix C  File formats");
TABLE(["Data", "Formats"], [
  ["Boreholes", "Excel (.xlsx), CSV folder, GMS text (.txt, .dat, .tsv)"], ["Legend", "CSV, Excel"],
  ["Boundary", "Shapefile (.shp + .prj, or zipped), KML, KMZ, GeoJSON"], ["DEM", "GeoTIFF, SRTM .hgt / .hgt.gz / .zip, ESRI ASCII (.asc)"],
  ["Wells, chemistry, constraints", "CSV, Excel (constraints also KML/KMZ/GeoJSON)"], ["Project", "LithoLog project (.llproj, JSON)"],
  ["Images and pages", "PNG, TIFF, JPEG; PDF, SVG"], ["Grids", "ESRI ASCII grid (.asc)"],
  ["3D", "HTML (interactive), OBJ, STL, VTP, VTK (ParaView)"], ["Tables", "CSV"],
], [1.8, 4.2], "Supported formats");
H2("Appendix D  Licence and credits");
P("LithoLog is open-source software (MIT licence). It uses Python, NumPy, SciPy, pandas, Matplotlib, PyVista/VTK, Qt (PySide6), pyproj/PROJ, scikit-image and Plotly. The user interface uses the Inter typeface (SIL Open Font License) and Material Design icons. The Copernicus GLO-30 DEM is provided by the European Space Agency under the Copernicus licence. The tutorial data are synthetic.");

// ================================================================== DOCUMENT
const cover = [
  new Paragraph({ spacing: { before: 1800 }, alignment: AlignmentType.CENTER,
    children: [new ImageRun({ type: "png", data: fs.readFileSync(F("litholog_wordmark_light.png")),
      transformation: { width: 520, height: Math.round(520 * SIZES[F("litholog_wordmark_light.png")][1] / SIZES[F("litholog_wordmark_light.png")][0]) },
      altText: { title: "LithoLog", description: "LithoLog logo", name: "logo" } })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 600, after: 200 },
    children: [new TextRun({ text: "LithoLog Studio", bold: true, size: 64, color: NAVY, font: FONT })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 400 },
    children: [new TextRun({ text: "User Manual", size: 44, color: AMBER, font: FONT })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 120 },
    children: [new TextRun({ text: "Borehole logs · cross-sections · maps · 3D geological models · groundwater analysis", size: 24, color: GREY })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 2400, after: 80 },
    children: [new TextRun({ text: "Version 0.1 · September 2026", size: 22, color: GREY })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: "Open-source software for geology and hydrogeology (MIT licence)", size: 20, color: GREY })] }),
  new Paragraph({ children: [new PageBreak()] }),
  new Paragraph({ children: [new TextRun({ text: "Contents", bold: true, size: 36, color: NAVY })], spacing: { after: 240 } }),
  new TableOfContents("Contents", { hyperlink: true, headingStyleRange: "1-2" }),
];

const doc = new Document({
  features: { updateFields: true },
  creator: "LithoLog", title: "LithoLog Studio – User Manual", description: "User manual for LithoLog Studio",
  styles: {
    default: { document: { run: { font: FONT, size: 21 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 36, bold: true, color: NAVY, font: FONT }, paragraph: { spacing: { before: 0, after: 240 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 27, bold: true, color: NAVY, font: FONT }, paragraph: { spacing: { before: 300, after: 120 }, outlineLevel: 1, keepNext: true } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 23, bold: true, color: AMBER, font: FONT }, paragraph: { spacing: { before: 200, after: 80 }, outlineLevel: 2, keepNext: true } },
    ],
  },
  numbering: { config: [
    { reference: "bullets", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
      style: { paragraph: { indent: { left: 540, hanging: 270 } } } }, { level: 1, format: LevelFormat.BULLET, text: "–",
      alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 1000, hanging: 270 } } } }] },
    { reference: "steps", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
      style: { paragraph: { indent: { left: 540, hanging: 320 } } } }] },
  ] },
  sections: [
    { properties: { page: { size: { width: PAGE_W, height: 16838 }, margin: { top: MARGIN, bottom: MARGIN, left: MARGIN, right: MARGIN } } },
      children: cover },
    { properties: { page: { size: { width: PAGE_W, height: 16838 }, margin: { top: MARGIN, bottom: MARGIN, left: MARGIN, right: MARGIN },
        pageNumbers: { start: 1 } } },
      headers: { default: new Header({ children: [new Paragraph({ border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: "C9D1DC", space: 4 } },
        tabStops: [{ type: TabStopType.RIGHT, position: TabStopPosition.MAX }],
        children: [new TextRun({ text: "LithoLog Studio", bold: true, color: NAVY, size: 18 }),
          new TextRun({ text: "\tUser Manual", color: GREY, size: 18 })] })] }) },
      footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER,
        children: [new TextRun({ children: ["Page ", PageNumber.CURRENT, " of ", PageNumber.TOTAL_PAGES], color: GREY, size: 18 })] })] }) },
      children: body },
  ],
});

Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync("LithoLog_Studio_User_Manual.docx", buf);
  console.log(`written: ${fig} figures, ${tab} tables`);
});
