# CONFIG FORMAT
The config format is fairly simple
It specifies how the bot should read your svg
It is a .json file (see the two examples), which contains various named values that can be set

## NAME & FILE
The `name` element is the name of your variant.
The `file` element is the relative path of your svg

## GAME OPTIONS
- `build_options`
- `victory_conditions`
- `victory_count`
- `convoyable_islands`

## SVG CONFIG
DiploGM will automatically pick up the necessary layers from the SVG, as long as they are named correctly.
See LAYER_DICTIONARY in DiploGM/map_parser/vector/utils.py for the full list.
`["island_borders", "island_fill_layer", "island_ring_layer", "background", "other_fills", "season", "power_banners", "symbol_templates"]` are all optional

Each layer can also be specified by internal ID (not the layer name) in this section by `"land_layer": "layer1"` for example, and you can see/edit the internal ID in inkscape with the xml editor (ctrl+shift+x)


- `detect_starting_units`
- `unit_type_labeled`
- `unit_labels`
- `province_labels`
- `center_labels`
- `default_sea_colour`
- `border_margin_hint`
- `map_width`
- `unit_radius`
- `order_stroke_width`
- `neutral`
- `neutral_sc`
- `loc_x_offset`
- `loc_y_offset`
- `delete_layer` -> more complicated
- `scoreboard` -> more complicated
- `season_format`

need to explain/figure out colours (just colour vs list of themes)

The SVG config is still a work in progress.
The "layer" that it is referring to is the internal id of the layer object.
You can find the it in the SVG file. If you are using Inkscape, you will likely find id="..." next to
inkscape:groupmode="layer" and inkscape:label="...", the latter of which may describe which of the following (if any)
the group represents. You are looking for the text in the id="..."

Individual explanations of the layers coming at some point in the future


## ABBREVIATIONS

## OVERRIDES
The overrides are used to manually set aspects of the svg that the bot can't read correctly (i. e. multiple coasts)

## PLAYERS
