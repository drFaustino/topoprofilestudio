# TopoProfile Studio

**Professional Topographic and Elevation Profiles for QGIS**

TopoProfile Studio is a QGIS plugin for creating professional topographic and elevation profiles directly from a map. It combines terrain sampling, interactive visualization, geological and structural annotations, profile management, and technical export in a modern, independent interface.

The plugin is designed for geological, geomorphological, topographic, environmental, engineering, and geotechnical workflows where elevation profiles need to be created, interpreted, saved, and exported efficiently.

---

## Features

### Profile creation

TopoProfile Studio allows users to create elevation profiles by manually drawing a profile path directly on the QGIS map.

The profile path defines the section to be analyzed and is used to calculate progressive distances and corresponding elevation values.

### Elevation sources

Profiles can be generated from:

* Raster DEM/DTM layers
* Contour-line vector layers with elevation attributes

#### Raster DEM/DTM

When using a raster elevation source, the plugin samples elevation values along the profile path to generate the elevation section.

#### Contour lines

When using contour lines, the plugin directly intersects the profile path with the contour features and reads the elevation from the selected attribute.

The resulting intersection points are ordered along the profile and intermediate elevation values are interpolated between them.

This allows profiles to be generated from contour datasets without requiring a raster DEM.

---

## Interactive Profile Chart

The generated profile is displayed in a modern interactive chart.

The chart provides:

* Segment distances
* Progressive/cumulative distance
* Elevation values
* Profile direction labels
* Geological and structural markers
* Optional profile smoothing
* Interactive mouse tracking

The chart is designed to provide a clear representation of the terrain section while maintaining a direct connection with its geographic position in QGIS.

---

## Synchronized Map Indicator

TopoProfile Studio links the profile chart directly to the QGIS map.

When the mouse moves over the profile, a synchronized indicator shows the corresponding position along the original profile path on the map.

This makes it possible to move between the graphical section and the geographic location intuitively.

**Profile chart → progressive distance → map position**

---

## Direction Labels

The beginning and end of the profile can be identified using customizable direction labels.

For example:

* `A` → `A'`
* `NW` → `SE`
* `Start` → `End`

This makes exported profiles easier to interpret and document.

---

## Geological and Structural Markers

Identification points can be added directly along the profile.

Markers can be used to identify geological, structural, geotechnical, or other relevant features.

Supported categories include:

* Lithological changes
* Faults
* Thrusts
* Folds
* Boundaries
* Boreholes
* Tests
* Piezometers
* Levels
* Other features

Each marker can have:

* A custom label
* A category
* A position along the profile
* An associated elevation

Markers are displayed on the profile using category-specific colors.

---

## Profile Smoothing

TopoProfile Studio provides three levels of optional profile smoothing:

* **Light**
* **Medium**
* **Strong**

Smoothing can be enabled or disabled from the interface and allows the user to obtain a visually smoother representation of the profile when appropriate.

---

## Profile Management

Multiple profiles can be managed within the same QGIS project.

Profiles can be:

* Created
* Named
* Saved
* Loaded
* Replaced
* Managed independently

This makes it possible to maintain several geological or topographic sections within a single QGIS project.

---

## Project Storage

Profile information can be stored directly inside the QGIS project.

This allows the profiles to remain associated with the project and be restored when the project is reopened.

The project can therefore contain both the geographic data and the associated profile information.

---

## JSON Profile Files

Profiles can also be stored as independent JSON files.

This provides an alternative workflow for:

* Backup
* Data exchange
* Profile sharing
* Archiving
* Moving profiles between projects

Profile information can be loaded either from the current QGIS project or from an external JSON file.

---

## Export

TopoProfile Studio supports both image and CAD-oriented export.

### Image formats

Profiles can be exported as:

* **PNG**
* **SVG**
* **JPG**
* **PDF**

These formats are suitable for:

* Technical reports
* Geological sections
* Presentations
* Documentation
* Publications
* Map layouts

### DXF formats

The plugin supports:

* **2D DXF**
* **3D DXF**

The DXF export is intended for further processing in CAD and technical drawing software.

---

## 2D DXF Export

The 2D DXF export produces a dedicated profile drawing containing:

* Profile geometry
* Horizontal and vertical axes
* Distance ticks
* Elevation ticks
* Axis labels
* Profile direction labels
* Geological/structural markers
* Marker labels

The exported drawing is organized into dedicated CAD layers to facilitate further editing.

### Main layers

* `PROFILO`
* `MARKER`
* `TESTO`
* `ASSI`

### Marker category layers

* `MARK_LITOLOGICO`
* `MARK_FAGLIA`
* `MARK_SOVRASCORRIMENTO`
* `MARK_PIEGA`
* `MARK_LIMITE`
* `MARK_SONDAGGIO`
* `MARK_PROVA`
* `MARK_PIEZOMETRO`
* `MARK_LIVELLO`
* `MARK_ALTRO`

Marker layers use category-specific colors corresponding to their representation in the profile chart.

---

## 3D DXF Export

The 3D DXF export preserves the spatial position and elevation of the profile.

The profile is exported using:

* X coordinate
* Y coordinate
* Z/elevation

This makes the resulting DXF suitable for workflows requiring a spatially positioned 3D profile.

Geological and structural markers are also exported with their corresponding category and color.

---

## Modern Independent Interface

TopoProfile Studio uses a modern interface designed specifically for profile analysis.

The main panel is:

* Independent from the QGIS main window
* Always floating
* **Never dockable**
* Resizable
* Dedicated to the plugin
* Styled using the plugin's own visual design

The interface includes dedicated dialogs for marker editing and export configuration.

---

## Typical Workflow

A typical workflow with TopoProfile Studio is:

1. Open **TopoProfile Studio** from QGIS.
2. Select a DEM/DTM raster or a contour-line layer.
3. Configure the elevation source.
4. Draw the profile path on the map.
5. Generate the elevation profile.
6. Inspect distances and elevations in the interactive chart.
7. Move the mouse over the chart to locate positions on the map.
8. Add geological or structural identification points.
9. Customize the profile direction labels.
10. Enable optional profile smoothing if required.
11. Save the profile inside the QGIS project or as a JSON file.
12. Reload profiles when needed.
13. Export the final section as PNG, SVG, JPG, PDF, or DXF.

---

## Supported Marker Categories

| Category            | Typical use                               |
| ------------------- | ----------------------------------------- |
| Lithological change | Change between geological units           |
| Fault               | Fault or fracture                         |
| Thrust              | Thrust or overthrust structure            |
| Fold                | Fold structure                            |
| Boundary            | Geological or structural boundary         |
| Borehole            | Borehole or drilling point                |
| Test                | Field or geotechnical test                |
| Piezometer          | Piezometric monitoring point              |
| Level               | Identified geological or structural level |
| Other               | Custom identification point               |

---

## Use Cases

TopoProfile Studio can be used for a wide range of GIS and earth-science applications, including:

* Geological cross-sections
* Structural geology
* Engineering geology
* Geomorphology
* Topographic analysis
* Terrain interpretation
* Environmental studies
* Geotechnical investigations
* Preliminary engineering analysis
* Geological fieldwork
* Technical reporting
* CAD-based section preparation

---

## Data Requirements

### DEM/DTM

For raster-based profiles, the selected raster layer should contain valid elevation values.

The quality of the resulting profile depends on the resolution, accuracy, and vertical quality of the source raster.

### Contour Lines

For contour-based profiles, the selected vector layer should contain contour geometries with a numeric elevation attribute.

The quality of the resulting profile depends on:

* Contour spacing
* Geometry accuracy
* Elevation attribute quality
* Profile path
* Interpolation between contour intersections

---

## Profile Data

A profile can contain information such as:

* Profile name
* Profile path
* Start and end labels
* Elevation source
* Source layer
* Coordinate reference system
* Sampled distances
* Elevation values
* Smoothing settings
* Profile colors
* Background color
* Geological/structural markers
* Marker categories
* Marker labels

Profile information can be stored within the QGIS project or in an independent JSON file.

---

## Requirements

TopoProfile Studio is designed for modern QGIS environments and uses:

* QGIS Python API
* PyQt
* Matplotlib
* `ezdxf` for DXF generation

DXF export requires `ezdxf` to be available in the Python environment used by QGIS.

---

## Installation

### QGIS Plugin Manager

If TopoProfile Studio is distributed through a QGIS plugin repository:

1. Open QGIS.
2. Go to **Plugins → Manage and Install Plugins**.
3. Search for **TopoProfile Studio**.
4. Select **Install**.
5. Open the plugin from the QGIS toolbar or Plugins menu.

### Manual installation

For development or local installation:

1. Copy the `topoprofilestudio` plugin folder into the QGIS Python plugins directory.
2. Restart QGIS or reload the plugin.
3. Open **Plugins → Manage and Install Plugins**.
4. Enable **TopoProfile Studio**.
5. Launch the plugin from the toolbar or Plugins menu.

---

## DXF and CAD Compatibility

TopoProfile Studio exports profiles in DXF format rather than native DWG.

DXF files can be opened and edited using compatible CAD applications and can also be converted to other CAD formats when required.

The 2D export is intended primarily for technical profile drawings, while the 3D export preserves the spatial X/Y/Z geometry of the profile.

---

## Data Quality and Interpretation

TopoProfile Studio is a profile-generation and visualization tool.

The accuracy of the resulting profile depends on the source data and processing parameters.

Particular attention should be paid to:

* Raster resolution
* Contour interval
* Elevation accuracy
* Coordinate reference system
* Profile geometry
* Interpolation between contour intersections
* Smoothing settings

Smoothed profiles should be considered a visualization or generalized representation of the sampled terrain and should not automatically be interpreted as additional measured elevation information.

Always verify critical results against the original source data.

---

## Project Persistence

Profiles stored in the QGIS project are associated with that project.

When a project is reopened, TopoProfile Studio can restore the stored profile information.

Independent JSON files provide an additional way to preserve and exchange profile information outside the QGIS project.

---

## License

Add the project's applicable license here.

If TopoProfile Studio is distributed as open-source software, the appropriate `LICENSE` file should be included with the project.

---

## Credits

**TopoProfile Studio**

A QGIS plugin for professional topographic and elevation profile creation, terrain sampling, geological and structural annotation, profile management, and technical export.

Built with:

* QGIS
* Python
* PyQt
* Matplotlib
* ezdxf

---

## Disclaimer

TopoProfile Studio is intended to assist with GIS-based terrain profile generation, visualization, interpretation, and technical documentation.

The plugin does not replace professional surveying, geological, engineering, or geotechnical analysis.

Users are responsible for validating generated profiles against the original datasets and the requirements of their specific project.
