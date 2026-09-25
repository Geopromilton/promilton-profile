# LithoLog

**Free, open-source borehole logging for geologists, hydrogeologists and geotechnical engineers.**

Fill in one Excel sheet (or point it at a GMS borehole file) → get publication-quality
borehole strip logs, cross-sections, 3D fence diagrams, contour maps and a 3D lithology block
model with volumes and groundwater-storage estimates — as PDF, PNG or SVG.

![Example strip log](docs/BW-01.png)

## Quick start (3 commands)

```bash
pip install -e .                       # from this folder (Python 3.9+)
litholog template my_site.xlsx         # 1. get the input workbook
# ... fill in my_site.xlsx in Excel / LibreOffice ...
litholog striplog my_site.xlsx         # 2. strip logs appear in ./striplogs/
```

Try it on the bundled (synthetic) demo data:

```bash
litholog striplog examples/sample_project.xlsx --title "Demo project"
```

## What goes in the workbook

| Sheet | One row per… | Columns |
|---|---|---|
| **Boreholes** | borehole | Borehole ID, Easting/X, Northing/Y, Elevation (m amsl), Total depth (m). *Any extra column you add (Location, Date, Drilling method, Logged by, Client…) is printed in the log header.* |
| **Lithology** | depth interval | Borehole ID, From (m), To (m), Code, Description |
| **Construction** *(optional)* | pipe / annulus interval | Borehole ID, From, To, Element (`casing`, `screen`, `gravel pack`, `seal`/`grout`, `open hole`), Diameter (mm), Material |
| **WaterLevels** *(optional)* | measurement | Borehole ID, Date, Depth to water (m bgl) |
| **Downhole** *(optional)* | reading | Borehole ID, Depth, Parameter, Value, Unit — e.g. resistivity, gamma, EC, drilling yield (up to 3 curves are plotted) |
| **Legend** *(optional)* | lithology code | Code, Name, Color, Pattern — add your own codes or restyle the built-in ones |

Headers are matched loosely: `BH ID`, `Well`, `Borehole` all work; units in brackets are ignored;
dates can be `2025-03-13` or `13-03-2025`. A folder of CSV files with the same names also works.

## Importing GMS borehole files

LithoLog reads GMS borehole text files (`Name  X  Y  Z  Material`, tab/space/comma separated)
directly. Each row is the top elevation of a contact and the material below it; the last row of a
hole marks its bottom. Elevations become depths below the collar, and material IDs become
lithology codes; give them names, colours and patterns in a small legend file
(see `examples/gms_legend_example.csv`):

```bash
litholog striplog boreholes_gms.txt --legend my_legend.csv      # logs straight from GMS data
litholog convert  boreholes_gms.txt my_site.xlsx --legend my_legend.csv
# → editable workbook: add descriptions, well construction, water levels, then re-run striplog
```

## Cross-sections

```bash
litholog section data.xlsx -b BH-01 BH-04 BH-07 -n "A-A'"         # line runs hole to hole
litholog section data.xlsx --line 778000,943000 808000,925000 --buffer 1000 -n "B-B'"
litholog section data.xlsx -s sections.csv                        # many sections at once
```

`sections.csv` lists `Section, Borehole ID` rows in order along each line (or `Section, X, Y`
vertices, with an optional `Buffer` column); see `examples/sections_example.csv`.
Holes near a `--line` are projected onto it and labelled with their offset.

Layers are joined between neighbouring holes by aligning the two sequences, much like correlating
by hand: the same unit at a similar level is joined, a unit found in only one hole pinches out
half-way, and different units at the same level meet at a vertical boundary half-way between the
holes. Each section has a location plan, legend, ground surface, water table (if measured) and a
vertical exaggeration chosen to fill the page (`--ve 20` to fix it; `--page A4`).
`--datum depth` hangs all holes from a flat ground surface instead of their elevations.

![Cross-section](docs/section_demo.png)

## Fence diagrams (3D)

```bash
litholog fence data.xlsx                              # minimum spanning tree: every hole, no crossings
litholog fence data.xlsx --network delaunay           # denser triangulated network
litholog fence data.xlsx --network sections -s sections.csv
litholog fence data.xlsx --views 4 -o fence.pdf       # four views around the model
```

`--azim` / `--elev` set the viewing direction and `--ve` the vertical exaggeration.

![Fence diagram](docs/fence_demo.png)

## Contour maps

```bash
litholog map data.xlsx -a ground top:KHON thickness:FRAC water -m kriging
```

| Attribute | Map |
|---|---|
| `ground` | ground (collar) elevation |
| `top:CODE`, `base:CODE` | elevation of the top / base of a unit |
| `depth:CODE` | depth below ground to a unit |
| `thickness:CODE` | total thickness of a unit (isopach), with its volume |
| `water`, `dtw` | water-table elevation (with flow arrows) and depth to water |

Gridding by inverse distance (`idw`, default), `linear` (TIN) or ordinary `kriging` with an
automatically fitted spherical variogram. Maps are limited to the area enclosed by the boreholes
(`--no-mask` for the full rectangle). Each map is also saved as an ESRI ASCII grid (`.asc`) that
opens in QGIS, ArcGIS or Surfer, plus a CSV of the borehole values.

![Water-table map](docs/map_demo.png)

## 3D block model, volumes and groundwater storage

```bash
litholog model data.xlsx --sy FRAC=0.015 --only FRAC
```

Builds a voxel model in which each voxel takes the lithology favoured by an inverse-distance vote of
the boreholes, bounded by the ground surface, the base of drilling and the boreholes' outline.

* `--datum depth` (default) compares holes at equal depth below ground, so layers follow the land
  surface — suited to weathered / fractured hard-rock aquifers. `--datum elevation` compares them
  at equal elevation — suited to flat-lying sediments.
* Volumes are summed from the vote *proportions*, not only the winning lithology, so thin units
  are not under-counted; they agree with the isopach (thickness-map) volume.
* `--sy CODE=value` adds groundwater storage = volume × specific yield (your estimate) per unit.

Outputs: cut-away 3D view with a legend/volume table, views of selected units (`--only`),
horizontal slices, `volumes.csv`, and `model.vtk` for ParaView.

![Block model](docs/model_demo.png)

## Study-area boundary (shapefile)

```bash
litholog map   data.xlsx -a thickness:FRAC --boundary study_area.shp
litholog model data.xlsx --sy FRAC=0.015 --boundary study_area.shp
```

Maps and the block model then cover and are clipped to the polygon (multi-part polygons and holes
are supported), volumes and storage are totalled inside it, and the outline is drawn on maps, slices
and 3D views. The share of the study area lying beyond the boreholes (where values are extrapolated)
is reported.

The shapefile's `.prj` is used to reproject the boundary into the boreholes' coordinates. Give the
boreholes' system with `--crs EPSG:32643`; if you don't and the boundary is in a UTM zone that does
not overlap the boreholes, the neighbouring UTM zone that does is used (and reported) — a common
mix-up near zone edges.

## Commands

```
litholog template FILE.xlsx [--empty]        write the input workbook (with example rows)
litholog validate DATA                       check for overlaps, gaps, bad depths, unknown codes
litholog striplog DATA [-o DIR] [-f pdf|png|svg] [-b BH1 BH2] [-m 50] [--title NAME]
litholog section DATA (-b IDS | --line X,Y ... | -s FILE) [--ve N] [--page A3|A4]
litholog fence DATA [--network mst|delaunay|sections] [--views N] [-o fence.pdf]
litholog map DATA -a ATTR ... [-m idw|linear|kriging] [--cell M] [--boundary SHP [--crs EPSG]]
litholog model DATA [--datum depth|elevation] [--sy CODE=SY ...] [--only CODE ...] [--boundary SHP]
litholog convert DATA [OUT.xlsx] [-l LEGEND] turn GMS text / CSV folder into a workbook
litholog legend [DATA] [-o legend.pdf]       list / draw the lithology legend

Add `-l my_legend.csv` to validate / striplog / convert to use your own codes.
```

`-m 50` splits long holes into pages of 50 m each; by default each hole fits on one A4 page.
A combined `all_boreholes.pdf` is written alongside the individual logs.

## Lithology legend

30 built-in codes covering soils, alluvium, the laterite–saprolite weathering profile,
crystalline, volcanic and sedimentary rocks. All patterns are original to LithoLog and
drawn at a fixed printed size, so they look the same at any depth scale. Combine patterns
with `+` (e.g. `crosses+fractures`).

![Legend](docs/legend.png)

## Use from Python

```python
from litholog import load_project, save_striplog, validate

project = load_project("my_site.xlsx")
for issue in validate(project):
    print(issue)
bh = project.borehole("BW-01")
save_striplog(bh, project.legend, "BW-01.pdf")
```

## Roadmap

- [x] **M1** Borehole database (Excel/CSV/GMS), validation, strip logs, custom legends
- [x] **M2** Cross-sections (hole-to-hole or along any line), 3D fence diagrams
- [x] **M3** Contour maps (surfaces, isopachs, water table), 3D block model, volumes, storage
- [ ] **M4** Browser app (no install), 3D viewer, report export, KMZ/VTK/DXF export

## Development

```bash
pip install -e ".[dev]"
pytest
python examples/make_sample.py   # regenerate the demo workbook
```

The demo data in `examples/` is **synthetic** and for illustration only.

## License

MIT, see [LICENSE](LICENSE). Contributions welcome.
