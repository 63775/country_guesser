# ========================================
# COUNTRY GUESSER 3D GLOBE VERSION (Prototype)
# ========================================

import streamlit as st
import pydeck as pdk
import random

# Streamlit Page Setup
st.set_page_config(page_title="🌍 Country Guesser 3D", layout="wide")

# --- Country Data (Simplified) ---
countries = [
    {"name": "United States", "lat": 38.0, "lon": -97.0},
    {"name": "Germany", "lat": 51.0, "lon": 10.0},
    {"name": "Brazil", "lat": -14.0, "lon": -51.0},
    {"name": "Australia", "lat": -25.0, "lon": 133.0},
    {"name": "India", "lat": 21.0, "lon": 78.0},
]

# Select a random target country
if "target_country" not in st.session_state:
    st.session_state.target_country = random.choice(countries)

target = st.session_state.target_country

# --- Sidebar: Guess Form ---
with st.sidebar:
    st.title("🌍 Country Guesser 3D")
    guess = st.text_input("Your guess for the country name:")
    if st.button("Submit Guess"):
        if guess.lower().strip() == target["name"].lower():
            st.success(f"✅ Correct! It was {target['name']} 🎉")
            # Reset for new round
            st.session_state.target_country = random.choice(countries)
        else:
            st.error(f"❌ Wrong! Try again!")

    st.write("---")
    st.write(f"Hint: It is located around latitude {target['lat']}°, longitude {target['lon']}°.")

# --- Main Area: 3D Globe Map ---

# Create a layer for all country "centroids"
layer = pdk.Layer(
    "ScatterplotLayer",
    data=countries,
    get_position="[lon, lat]",
    get_color="[200, 30, 0, 160]",
    get_radius=500000,
    pickable=True,
)

# View settings
view_state = pdk.ViewState(
    latitude=0,
    longitude=0,
    zoom=0.5,
    min_zoom=0,
    max_zoom=5,
    pitch=30,
    bearing=0
)

# Create 3D Deck
deck = pdk.Deck(
    layers=[layer],
    initial_view_state=view_state,
    tooltip={"text": "{name}"},
    map_style=None,
    globe=True,  # Enable 3D Globe 🌍
)

st.pydeck_chart(deck)

# Instruction
st.info("🎲 Rotate and zoom the globe. Try guessing the target country based on hints!")
