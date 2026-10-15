# Glider Performance Tool

Tools for choosing the right PAM-equipped ocean glider for a study and planning its mission:
what each platform can carry, how the platforms compare, how long a glider will last, and
where and how it can fly.

**Website: <https://e-abdi.github.io/glider-performance-tool/>**

The project started at the NOAA Fisheries Glider Rodeo 2026 hackathon as a comparison of how
the rodeo's gliders performed across mission modes. It has since grown into a general glider
comparison and mission planning tool. The Glider Performance page still holds the rodeo
results; the other pages go beyond the rodeo.

## The pages

| Page | What it does |
|---|---|
| [Glider Selection Dashboard](https://e-abdi.github.io/glider-performance-tool/content/glider-selection.html) | Enter what the mission needs (depth, duration, time of year, sensors, PAM recorder) and see which gliders match. |
| [Direct Comparison](https://e-abdi.github.io/glider-performance-tool/content/direct-comparison.html) | Slocum and Seaglider side by side, factor by factor, from pilots' experience. |
| [Study Design Tool](https://e-abdi.github.io/glider-performance-tool/content/study-design.html) | Draw a study area at sea, lay out a lawnmower, parallel or butterfly survey, see the historical depth-averaged currents for the deployment months, and get a survey estimate (distance, duration, dive cycles) that accounts for them. Also a 3D view over real bathymetry and Slocum / Seaglider waypoint files. |
| Endurance: [Slocum](https://e-abdi.github.io/glider-performance-tool/content/slocum-endurance.html) | How long a Slocum mission lasts, using Teledyne's own endurance-workbook formulas plus extra sensors. |
| Endurance: [Seaglider](https://e-abdi.github.io/glider-performance-tool/content/seaglider-endurance.html) | How long a Seaglider mission lasts, from a model fitted to our own Seaglider's dive logs. |
| [Glider Performance](https://e-abdi.github.io/glider-performance-tool/content/performance.html) | What every rodeo glider actually did, split by mission mode: power, speed, pumping, data volume. |

Every page runs entirely in the browser. The Study Design Tool fetches its outside data live:
bathymetry from [GMRT](https://www.gmrt.org/), currents from the
[Copernicus Marine](https://marine.copernicus.eu/) GLORYS12 reanalysis, and the coastline from
[Natural Earth](https://www.naturalearthdata.com/).

## Repository layout

| Path | Contents |
|---|---|
| `index.qmd`, `content/*.qmd` | The website's pages ([Quarto](https://quarto.org/)). Most are hand-written HTML and JavaScript inside the qmd. |
| `content/data/` | Data the pages use, committed: CSVs you can edit, and JSON produced by the scripts. |
| `content/images/` | Glider photos and logos. |
| `code/` | Scripts that build the pages' data, and the checks CI runs on it. |
| `output/` | Source spreadsheets and intermediate products. Gitignored except its ReadMe; see [CONTRIBUTING.md](CONTRIBUTING.md#where-each-pages-data-comes-from). |
| `data/` | Pointers to the raw Glider Rodeo data (nothing committed). |
| `_quarto.yml`, `theme*.scss` | Site configuration, sidebar and theme. |
| `.github/workflows/` | Renders and publishes the site on every push to `main`. |

## Running it locally

You need [Quarto](https://quarto.org/docs/get-started/) to preview the site:

```bash
git clone https://github.com/e-abdi/glider-performance-tool.git
cd glider-performance-tool
quarto preview
```

The build scripts in `code/` need Python 3 (`pip install -r requirements.txt`) and Node.js.
You only need them if you change data that a script generates; see
[CONTRIBUTING.md](CONTRIBUTING.md).

Publishing is automatic: a push to `main` runs the checks, renders the site and publishes it to
the `gh-pages` branch. Do not run `quarto publish` yourself.

## Contributing

Corrections, new gliders and sensors, and new pages are all welcome. See
[CONTRIBUTING.md](CONTRIBUTING.md) for how to report a problem, where each page's data lives,
and how to make and check a change.

## Team

- Ehsan Abdi, Akvaplan-niva ([eab\@akvaplan.niva.no](mailto:eab@akvaplan.niva.no))
- Héloïse Frouin-Mouy, University of Miami, NOAA Southeast Fisheries Science Center ([heloise.frouin-mouy\@miami.edu](mailto:heloise.frouin-mouy@miami.edu))
- Kasey Castello, Scripps Institution of Oceanography, University of California San Diego ([kcastello\@ucsd.edu](mailto:kcastello@ucsd.edu))
- Anne Simonis, Estuary and Ocean Science Center, San Francisco State University ([asimonis\@sfsu.edu](mailto:asimonis@sfsu.edu))

## Acknowledgements

This project began at the Glider Rodeo Hackathon, which worked with PAM-glider data collected
by the NOAA Fisheries Glider Rodeo (2026). The event was hosted by NOAA Fisheries with support
from Openscapes (JupyterHub, support), Oregon State University (Zoom, Box data storage) and
Aquaview (technical support).

## License

CC0 1.0 Universal; see [LICENSE](LICENSE). Data fetched by the pages keep their own terms,
credited on the pages that use them.
