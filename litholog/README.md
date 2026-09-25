# LithoLog

**Free, open-source borehole logging for geologists, hydrogeologists and geotechnical engineers.**

Fill in one Excel sheet → get publication-quality borehole strip logs as PDF, PNG or SVG.
Cross-sections, fence diagrams and 3D aquifer models are next on the roadmap.

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

## Commands

```
litholog template FILE.xlsx [--empty]        write the input workbook (with example rows)
litholog validate DATA                       check for overlaps, gaps, bad depths, unknown codes
litholog striplog DATA [-o DIR] [-f pdf|png|svg] [-b BH1 BH2] [-m 50] [--title NAME]
litholog legend [DATA] [-o legend.pdf]       list / draw the lithology legend
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

- [x] **M1** Borehole database (Excel/CSV), validation, strip logs, custom legends
- [ ] **M2** Cross-sections along any line, 2D/3D fence diagrams
- [ ] **M3** Layer-surface models, isopach and water-table maps, 3D lithology block models, volumes
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
