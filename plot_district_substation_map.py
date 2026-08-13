import json
import pandas as pd
import folium
from folium.plugins import MarkerCluster


# Read data
districts = pd.read_csv("district_locations.csv")
substations = pd.read_csv(
    "ssen_individual_substation_coordinates.csv"
)

# Remove substations without coordinates
substations = substations.dropna(
    subset=["latitude", "longitude"]
).copy()

# Create UK map
uk_map = folium.Map(
    location=[54.5, -3.0],
    zoom_start=6,
    tiles="OpenStreetMap"
)

# District representative points
district_colors = {
    "SEPD": "#0066ff",
    "SHEPD": "#7b2cbf"
}

district_layer = folium.FeatureGroup(
    name="District representative points",
    show=True
)

# We store the JavaScript variable name of each District marker.
district_marker_names = {}

for _, row in districts.iterrows():

    district_id = str(row["district_id"])
    network = str(row["network"])

    color = district_colors.get(
        network,
        "#555555"
    )

    # Use DivIcon to make a diamond-shaped District marker
    marker = folium.Marker(

        location=[
            row["latitude"],
            row["longitude"]
        ],

        icon=folium.DivIcon(

            icon_size=(16, 16),

            icon_anchor=(8, 8),

            html=f"""
            <div style="
                width: 12px;
                height: 12px;
                background-color: {color};
                border: 2px solid white;
                box-shadow: 0 0 0 1px {color};
                transform: rotate(45deg);
            ">
            </div>
            """
        ),

        tooltip=(
            f"District: {district_id} | "
            f"{row['location_source']}"
        ),

        popup=(
            f"<b>District:</b> {district_id}<br>"
            f"<b>Network:</b> {network}<br>"
            f"<b>Location source:</b> "
            f"{row['location_source']}<br>"
            f"<b>Latitude:</b> "
            f"{row['latitude']:.4f}<br>"
            f"<b>Longitude:</b> "
            f"{row['longitude']:.4f}<br>"
            f"<b>Substations:</b> "
            f"{row['substations_in_area']}"
        )
    )

    marker.add_to(district_layer)

    district_marker_names[
        district_id
    ] = marker.get_name()

district_layer.add_to(uk_map)

# Normal Substations
substation_colors = {
    "Pole Mounted Distribution": "green",
    "Ground Mounted Distribution": "orange",
    "Switching Station": "red",
    "Secondary (Pad Mounted)": "purple"
}

substation_layer = folium.FeatureGroup(
    name="Substations",
    show=True
)

cluster = MarkerCluster(
    options={
        "showCoverageOnHover": False
    }
).add_to(substation_layer)


for _, row in substations.iterrows():

    color = substation_colors.get(
        row["type"],
        "gray"
    )

    folium.CircleMarker(

        location=[
            row["latitude"],
            row["longitude"]
        ],

        radius=3,

        color=color,

        fill=True,
        fill_color=color,
        fill_opacity=0.7,

        weight=1,

        popup=(
            f"<b>Substation ID:</b> "
            f"{row['substation_id']}<br>"
            f"<b>Network:</b> "
            f"{row['network']}<br>"
            f"<b>Type:</b> "
            f"{row['type']}<br>"
            f"<b>Class:</b> "
            f"{row['class']}<br>"
            f"<b>Operating area:</b> "
            f"{row['operating_area']}<br>"
            f"<b>Locality:</b> "
            f"{row['locality']}<br>"
            f"<b>Status:</b> "
            f"{row['status']}"
        )
    ).add_to(cluster)
substation_layer.add_to(uk_map)

# Prepare District → Substation relationships
district_substation_coordinates = {}

for _, district in districts.iterrows():

    district_id = str(
        district["district_id"]
    )

    network = str(
        district["network"]
    )

    location_source = str(
        district["location_source"]
    )

    if not location_source.startswith(
        "operating_area:"
    ):
        continue

    operating_area = (
        location_source
        .split(":", 1)[1]
        .strip()
    )

    matching_substations = substations[

        (
            substations["network"]
            .astype(str)
            == network
        )
        &
        (
            substations["operating_area"]
            .astype(str)
            .str.strip()
            .str.casefold()
            == operating_area.casefold()
        )
    ]

    coordinates = [
        [
            float(row["latitude"]),
            float(row["longitude"])
        ]

        for _, row
        in matching_substations.iterrows()
    ]

    district_substation_coordinates[
        district_id
    ] = {
        "operating_area": operating_area,
        "count": len(coordinates),
        "coordinates": coordinates
    }

# District radius layers
radius_3_layer = folium.FeatureGroup(
    name="District radius - 3 km",
    show=False
)

radius_6_layer = folium.FeatureGroup(
    name="District radius - 6 km",
    show=False
)

radius_9_layer = folium.FeatureGroup(
    name="District radius - 9 km",
    show=False
)

for _, row in districts.iterrows():

    location = [
        row["latitude"],
        row["longitude"]
    ]

    folium.Circle(
        location=location,
        radius=3000,
        color="blue",
        fill=False,
        weight=1
    ).add_to(radius_3_layer)

    folium.Circle(
        location=location,
        radius=6000,
        color="green",
        fill=False,
        weight=1
    ).add_to(radius_6_layer)

    folium.Circle(
        location=location,
        radius=9000,
        color="red",
        fill=False,
        weight=1
    ).add_to(radius_9_layer)


radius_3_layer.add_to(uk_map)
radius_6_layer.add_to(uk_map)
radius_9_layer.add_to(uk_map)

# JavaScript interaction
map_name = uk_map.get_name()

district_data_json = json.dumps(
    district_substation_coordinates
)

district_markers_json = json.dumps(
    district_marker_names
)

hover_javascript = f"""
<script>

document.addEventListener(
    "DOMContentLoaded",
    function() {{

        const map = {map_name};

        const districtData =
            {district_data_json};

        const districtMarkers =
            {district_markers_json};


        let activeHighlightLayer = null;

        function clearHighlight() {{

            if (activeHighlightLayer !== null) {{

                map.removeLayer(
                    activeHighlightLayer
                );

                activeHighlightLayer = null;
            }}
        }}

        Object.entries(
            districtMarkers
        ).forEach(

            function(
                [districtId, markerVariableName]
            ) {{

                const marker =
                    window[markerVariableName];

                if (!marker) {{
                    return;
                }}

                marker.on(
                    "mouseover",
                    function() {{

                        clearHighlight();

                        const data =
                            districtData[districtId];

                        if (!data) {{
                            return;
                        }}

                        activeHighlightLayer =
                            L.layerGroup();

                        data.coordinates.forEach(

                            function(coordinate) {{

                                const point =
                                    L.circleMarker(

                                        coordinate,

                                        {{

                                            radius: 5,

                                            color: "#00ffff",

                                            weight: 2,

                                            fillColor:
                                                "#00ffff",

                                            fillOpacity:
                                                0.95

                                        }}

                                    );

                                point.addTo(
                                    activeHighlightLayer
                                );

                            }}

                        );

                        activeHighlightLayer.addTo(
                            map
                        );

                        marker.bindTooltip(

                            "District " +
                            districtId +
                            "<br>" +
                            data.operating_area +
                            "<br>" +
                            data.count +
                            " substations",

                            {{
                                sticky: true
                            }}

                        ).openTooltip();

                    }}
                );

                marker.on(
                    "mouseout",
                    function() {{

                        clearHighlight();

                    }}
                );

            }}

        );

    }}
);

</script>
"""

uk_map.get_root().html.add_child(
    folium.Element(
        hover_javascript
    )
)

# Legend
legend_html = """
<div style="
    position: fixed;
    bottom: 30px;
    left: 30px;
    z-index: 9999;
    background-color: white;
    padding: 10px 14px;
    border: 1px solid #999;
    border-radius: 5px;
    font-size: 13px;
">

<b>Map symbols</b><br><br>

<span style="
    display:inline-block;
    width:10px;
    height:10px;
    background:#0066ff;
    transform:rotate(45deg);
    margin-right:8px;">
</span>
SEPD District
<br>

<span style="
    display:inline-block;
    width:10px;
    height:10px;
    background:#7b2cbf;
    transform:rotate(45deg);
    margin-right:8px;">
</span>
SHEPD District
<br><br>

<span style="
    color:#00bfbf;
    font-size:18px;">
●
</span>
Highlighted District substations

</div>
"""

uk_map.get_root().html.add_child(
    folium.Element(
        legend_html
    )
)

# Layer controls
folium.LayerControl(
    collapsed=False
).add_to(uk_map)

# Save map
uk_map.save("district_substation_map.html")
print("Map saved to district_substation_map.html")