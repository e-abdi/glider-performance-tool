# Glider Performance Tool

Research compendium for comparing how the PAM-equipped gliders of the NOAA Fisheries
Glider Rodeo 2026 performed across mission modes (fast, slow, intermediate, drift):
piloting, navigation, endurance and self-noise.

The tool works only on [OceanGliders OG1.0](https://oceangliderscommunity.github.io/OG-format-user-manual/OG_Format.html)
NetCDF files, so the same analysis runs on every glider type (Slocum, Seaglider,
SeaExplorer, Oceanscout) and on future deployments. The OG1 files are produced by
[glider-og1](https://github.com/NMFS-PAM-Glider/hackathon-shared-repo/tree/ehsan-abdi/glider-og1).

## Link to Final Report
**TODO: link to the project website once GitHub Pages is on**

## How to Cite
**TODO: recommended citation**

## Research Compendium
This repository contains the code, documentation and small derived outputs for the
Glider Performance Tool. It follows the
[Glider Rodeo Hackweek Projects research compendium template](https://github.com/NMFS-PAM-Glider/GliderRodeo-HackweekProjects).

## Contents

-   📁 content: pages for the project website (Quarto)
-   📁 code: scripts and modules that do the analysis
-   📁 data: pointers to the ORIGINAL data (no large files in git)
-   📁 output: modified or intermediate data products made by the code
-   📁 supplement: supplementary files that are not data, code or website pages
-   📄 index.qmd, _quarto.yml: website home page and configuration
-   📄 requirements.txt: Python packages

## Getting started

```bash
git clone https://github.com/e-abdi/glider-performance-tool.git
cd glider-performance-tool
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Input data: OG1 files for the rodeo gliders. Make them with glider-og1 (on the Glider
Rodeo JupyterHub the source data is in `~/shared-public/GliderRodeo`), then point the
tool at the output folder. See [data/ReadMe.md](data/ReadMe.md).

## Collaborators
Ehsan Abdi, Akvaplan-niva, eab@akvaplan.niva.no

## Funding
**TODO: statement of funding**

## Acknowledgements
This project was part of the Glider Rodeo Hackathon, which worked with PAM-Glider data collected
by the NOAA Fisheries Glider Rodeo (2026). The event was hosted by NOAA Fisheries with support
from Openscapes (JupyterHub, support), Oregon State University (Zoom, Box data storage) and
Aquaview (technical support).

## License
Released under CC0 1.0 Universal (see [LICENSE](LICENSE)), as in the template.
