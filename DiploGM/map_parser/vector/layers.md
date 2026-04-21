Layers of the SVG:

* Region Colors (aka Region Fills, land_layer): Contains all the land provinces. The Parser assigns initial ownership based on the colors of the SVG. If a province does not match any defined player color or the neutral player color, then it will create a new non-player-controlled country named after a province it owns.
* Island Fills (aka island_fill_layer): Similar to Region Colors, but for island provinces instead of land provinces.
* Island Rongs (aka island_ring_layer): Contains the rings around island provinces that get colored in based on ownership. Necessary for small islands where it's hard to see how they're filled in.
* Sea Adjacencies (aka sea_borders): Contains all the sea provinces. Since seas don't have "owners", this is mainly for adjacency purposes. The bot can color them as impassable provinces if they are so, but typically these will remain the standard sea color.
* Island Adjacencies (aka island_borders): This layer is used to determine the bounds of island provinces for the sake of adjacency calculations. For each island province, this path should encompass the entirety of the land and water of the province, up to and including the island ring.
* Titles (aka Region Names, labels): The name of each province. Currently has limited bot functionality, but might be used to help detect regions in the future, or potentially to support dynamic names.
* Supply Centers (aka SC Markers, supply_center_icons): This layer is used to determine which provinces are supply centers and which ones are home supply centers for each power. In addition, if there is a group labelled "Capital Marker", that can be copied over to create capitals. 
* Army/Fleet Locations (aka army/fleet): Indicates where army and fleets should be placed for each province. The color of the units do not matter -- only the label and location. If a province doesn't have a unit location on this location, it will default to placing units at its centroid.
* Army/Fleet Locations (Retreats) (aka Army/Fleet Retreat Locations, retreat_army/fleet): Indicates where dislodged units should be. If one is not found, the mapper will default to using the normal unit locations but shifted slightly up and left.
    "starting_units": {"Units"},
    "unit_output": {"Unit Output Layer"},
    "arrow_output": {"Orders Output Layer"},
    "background": {"Background"},
    "other_fills": {"Other Fills", "OTHER FILLS (High Seas)", "OTHER FILLS (Impassables and High Seas)"},
    "season": {"Season Title"},
    "power_banners": {"Power Banners"},