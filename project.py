#Code Elias Stand 06.06
#Code Lukas Stand 05.05.


import streamlit as st
import random
import requests
import matplotlib.pyplot as plt
import pandas as pd
import json
import os
import io
from PIL import Image
import geopandas as gpd
from shapely.geometry import Point
import folium
from streamlit_folium import st_folium
from geopy.distance import geodesic

# Set Page Configuration
st.set_page_config(page_title="Country Guesser", layout="wide")

# --- Make layout tighter ---
st.markdown("""
    <style>
    /* Reduce top padding */
    .block-container {
        padding-top: 2rem;
        padding-bottom: 0rem;
    }
    /* Remove unnecessary spacing between elements */
    .element-container {
        margin-bottom: 0.5rem;
    }
    /* Tighter buttons */
    div.stButton > button {
        padding: 0.5rem 1rem;
        font-size: 1rem;
    }
    /* Tighter text inputs, selects */
    div.stTextInput, div.stSelectbox {
        margin-bottom: 0.5rem;
    }
    </style>
""", unsafe_allow_html=True)


# ==================== Prepare Geo Data ====================
@st.cache_data
def load_world_geodata():
    shapefile_path = "data/ne_110m_admin_0_countries/ne_110m_admin_0_countries.shp"
    gdf = gpd.read_file(shapefile_path)
    if gdf.crs and gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(epsg=4326)
    gdf['name_lower'] = gdf['NAME'].str.lower()
    gdf_proj = gdf.to_crs(epsg=3857)
    gdf['centroid'] = gdf_proj.geometry.centroid.to_crs(epsg=4326)
    return gdf[['NAME', 'name_lower', 'geometry', 'centroid']]

world_gdf = load_world_geodata()

def get_centroid_coords(country_name):
    row = world_gdf[world_gdf['name_lower'] == country_name.lower()]
    if not row.empty:
        pt = row.iloc[0]['centroid']
        return [pt.y, pt.x]
    return None

# ==================== Fetch Countries By Population ====================
@st.cache_data
def fetch_countries_by_population(difficulty):
    url = "https://restcountries.com/v3.1/all"
    r = requests.get(url, timeout=10)
    data = r.json() if r.status_code == 200 else []
    data = [c for c in data if c.get('population', 0) > 0 and c.get('name', {}).get('common')]
    sorted_countries = sorted(data, key=lambda x: x.get('population', 0), reverse=True)
    if difficulty == "Easy":
        selected = sorted_countries[:30]
    elif difficulty == "Medium":
        selected = sorted_countries[30:60]
    elif difficulty == "Hard":
        selected = sorted_countries[60:90]
    else:
        selected = sorted_countries[:90]
    return selected

# ==================== Leaderboard ====================
def load_leaderboard():
    if os.path.exists("leaderboard.json"):
        return json.load(open("leaderboard.json", "r"))
    return {}

def save_leaderboard(lb):
    json.dump(lb, open("leaderboard.json", "w"), indent=2)

def update_leaderboard_accuracy(players):
    lb = load_leaderboard()
    for p in players:
        name = p.name
        if name not in lb:
            lb[name] = {"total_points": 0, "total_rounds": 0}
        lb[name]["total_points"] += p.score
        lb[name]["total_rounds"] += p.rounds_played
    save_leaderboard(lb)

def display_leaderboard_top5():
    lb = load_leaderboard()
    if not lb:
        st.write("No leaderboard data yet.")
        return

    # Leaderboard title
    st.markdown("## 🏆 Leaderboard - All Countries Mode")

    scores = [(n, d["total_points"]/d["total_rounds"]) for n, d in lb.items() if d["total_rounds"] > 0]
    scores = sorted(scores, key=lambda x: x[1], reverse=True)[:5]

    # Small nice background container
    with st.container():
        for i, (n, avg) in enumerate(scores, 1):
            if i == 1:
                medal = "🥇"
            elif i == 2:
                medal = "🥈"
            elif i == 3:
                medal = "🥉"
            else:
                medal = "⭐"

            st.markdown(f"""
            <div style="background-color: #f0f2f6; padding: 10px; border-radius: 10px; margin-bottom: 10px;">
                <b>{medal} {i}. {n}</b> — {avg:.2f} points/round
            </div>
            """, unsafe_allow_html=True)


# ==================== Interactive Map ====================
def display_interactive_map(country, game):
    if 'guesses' not in st.session_state:
        st.session_state.guesses = []
    if 'current_country' not in st.session_state or st.session_state.current_country != country['name']['common']:
        st.session_state.guesses = []
        st.session_state.current_country = country['name']['common']
    if 'last_click_processed' not in st.session_state:
        st.session_state.last_click_processed = None
    if 'show_help_circle' not in st.session_state:
        st.session_state.show_help_circle = False
    if 'help_button_clicked' not in st.session_state:
        st.session_state.help_button_clicked = False
    if 'help_used_this_round' not in st.session_state:
        st.session_state.help_used_this_round = 0

    # -------------------------
    # Show HELP button after first guess
    # -------------------------
    if len(st.session_state.guesses) >= 1 and not game.round_over and not st.session_state.help_button_clicked:
        st.markdown("""
            <style>
            div.stButton > button {
                width: 100%;
                max-width: 700px;
                background-color: #28a745;
                color: white;
                padding: 12px 20px;
                font-size: 18px;
                border: none;
                border-radius: 10px;
                transition: background-color 0.3s ease, transform 0.2s ease;
                display: block;
            }
            div.stButton > button:hover {
                background-color: #218838;
                transform: scale(1.05);
            }
            </style>
        """, unsafe_allow_html=True)

        if st.button("🎯 Show Help Circle (-1 Point)"):
            st.session_state.show_help_circle = True
            st.session_state.help_button_clicked = True
            st.session_state.help_used_this_round += 1

    # -------------------------
    # Set map tiles
    # -------------------------
    if st.session_state.get("show_labels") == "No":
        tileset = "CartoDB PositronNoLabels"
    else:
        tileset = "CartoDB Positron"

    m = folium.Map(
        location=[20, 0],
        zoom_start=1.7,
        min_zoom=1,
        max_zoom=5,
        max_bounds=True,
        tiles=tileset,
        no_wrap=True
    )

    fg = folium.FeatureGroup(name="Guesses")

    # -------------------------
    # Draw previous guesses
    # -------------------------
    for i, (lat_i, lon_i) in enumerate(st.session_state.guesses):
        popup = f"Attempt {i+1}"
        folium.Marker(
            location=[lat_i, lon_i],
            popup=popup,
            icon=folium.Icon(color='red', icon='question', prefix='fa')
        ).add_to(fg)

    # -------------------------
    # Show correct country if round is over
    # -------------------------
    if game.round_over:
        coords = get_centroid_coords(country['name']['common'])
        if coords:
            folium.CircleMarker(
                location=coords,
                radius=8,
                popup=f"Solution: {country['name']['common']}",
                color='green',
                fill=True,
                fill_opacity=0.7
            ).add_to(fg)

    # -------------------------
    # Draw Help Circle if requested
    # -------------------------
    if st.session_state.show_help_circle and st.session_state.guesses:
        last_guess = st.session_state.guesses[-1]
        correct = get_centroid_coords(country['name']['common'])
        if correct:
            dist = geodesic((last_guess[0], last_guess[1]), tuple(correct)).kilometers
            folium.Circle(
                location=last_guess,
                radius=dist * 1000,  # km → meters
                color='blue',
                fill=True,
                fill_opacity=0,
                weight=2,
                interactive=False
            ).add_to(fg)

    fg.add_to(m)

    # -------------------------
    # Render map
    # -------------------------
    map_key = f'gdp_map_{game.current_player_index}_{len(st.session_state.guesses)}'
    map_data = st_folium(m, height=500, width=700, key=map_key, returned_objects=['last_clicked'])

    # -------------------------
    # Handle new guesses
    # -------------------------
    if map_data and map_data.get('last_clicked') and not game.round_over:
        lat = map_data['last_clicked']['lat']
        lon = map_data['last_clicked']['lng']
        click_data = (lat, lon)
        if click_data != st.session_state.last_click_processed:
            st.session_state.last_click_processed = click_data
            st.session_state.guesses.append(click_data)

            st.session_state.show_help_circle = False
            st.session_state.help_button_clicked = False

            guess_pt = Point(lon, lat)
            row = world_gdf[world_gdf['name_lower'] == country['name']['common'].lower()]
            if not row.empty and row.iloc[0]['geometry'].contains(guess_pt):
                pts = max(5 - (game.hint_index - 1), 1)
                pts = max(pts - st.session_state.help_used_this_round, 0)  # Deduct points for help usage
                game.get_current_player().add_score(pts)
                game.message = f"🎉 Hit! +{pts} points."
                game.round_over = True
            else:
                correct = get_centroid_coords(country['name']['common'])
                if correct:
                    dist = geodesic((lat, lon), tuple(correct)).kilometers
                    if dist <= 250:
                        pts = max(5 - (game.hint_index - 1), 1)
                        pts = max(pts - st.session_state.help_used_this_round, 0)  # Deduct points for help usage
                        game.get_current_player().add_score(pts)
                        game.message = f"🎉 Close hit! Distance: {int(dist)} km → +{pts} points."
                        game.round_over = True
                    else:
                        game.guess_count += 1
                        if game.hint_index < 5:
                            game.hint_index += 1
                        game.message = f"❌ Wrong – {int(dist)} km away."
                        if game.guess_count >= 5:
                            game.get_current_player().add_score(0)
                            game.message += f" Round over. Answer: {country['name']['common']}."
                            game.round_over = True

            # Reset help counter for new round
            st.session_state.help_used_this_round = 0

            st.rerun()


# ==================== Hints ====================
def format_population(n):
    return f"{n:,}" if isinstance(n, int) else "Unknown"

def get_hint(country, i):
    if i == 1:
        return f"Population: {format_population(country.get('population', 0))}"
    if i == 2:
        area = country.get("area")
        return f"Area: {int(area):,} km²" if area else "Area: Unknown"
    if i == 3:
        flag = country.get("flags", {})
        return flag.get("png") or flag.get("svg") or ""
    if i == 4:
        caps = country.get("capital") or []
        return "Capital: " + ", ".join(caps) if caps else "Capital: Unknown"
    if i == 5:
        borders = country.get("borders") or []
        mapping = st.session_state.country_code_mapping
        names = [mapping.get(c, c) for c in borders]
        return "Borders: " + ", ".join(names) if names else "Borders: None"
    return ""

# ==================== Game Logic ====================
class Player:
    def __init__(self, name):
        self.name = name
        self.score = 0
        self.rounds_played = 0

    def add_score(self, pts):
        self.score += pts
        self.rounds_played += 1

class Game:
    def __init__(self, names, target, countries):
        self.players = [Player(n) for n in names]
        self.current_player_index = 0
        self.target_score = target
        self.countries = countries
        self.used_countries = []
        self.new_round()

    def get_current_player(self):
        return self.players[self.current_player_index]

    def new_round(self):
        avail = [c for c in self.countries if c not in self.used_countries]
        if not avail:
            self.used_countries = []
            avail = self.countries.copy()
        self.country = random.choice(avail)
        self.used_countries.append(self.country)
        self.hint_index = 1
        self.guess_count = 0
        self.round_over = False
        self.message = ""

    def process_guess(self, guess):
        corr = self.country["name"]["common"].lower().strip()
        if guess.lower().strip() == corr:
            pts = max(5 - (self.hint_index - 1), 1)
            self.get_current_player().add_score(pts)
            self.message = f"✅ Correct! +{pts} points."
            self.round_over = True
        else:
            self.guess_count += 1
            if self.hint_index < 5:
                self.hint_index += 1
            if self.hint_index > 5 or self.guess_count >= 5:
                self.get_current_player().add_score(0)
                self.message = f"❌ Wrong. Answer: {self.country['name']['common']}."
                self.round_over = True
            else:
                self.message = "❌ Wrong, try again!"

    def next_player(self):
        self.current_player_index = (self.current_player_index + 1) % len(self.players)

    def is_game_over(self):
        hit = any(p.score >= self.target_score for p in self.players)
        same = len({p.rounds_played for p in self.players}) == 1
        return hit and same

    def get_winner(self):
        max_s = max(p.score for p in self.players)
        tops = [p for p in self.players if p.score == max_s]
        return tops if len(tops) > 1 else tops[0]

# ==================== UI ====================
if "game" not in st.session_state:
    st.title("🌍 Country Guesser")

    # Split screen layout
    left_col, right_col = st.columns([1.5, 2], gap="large")

    with left_col:
        with st.form("setup_form"):
            st.subheader("🎮 Game Settings")
            names = st.text_input("Players (comma-separated)", "Alice, Bob")
            target = st.number_input("Target Score", min_value=1, value=20)
            difficulty = st.selectbox("Select Difficulty", ["Easy", "Medium", "Hard", "All Countries"])
            show_labels = st.selectbox("Show Country Names on Map?", ["Yes", "No"])

            if st.form_submit_button("Start Game"):
                pl = [n.strip() for n in names.split(",") if n.strip()]
                cnt = fetch_countries_by_population(difficulty)
                # Mapping für Nachbarn-Hints
                mapping = {c["cca3"]: c["name"]["common"] for c in cnt if c.get("cca3")}
                st.session_state.country_code_mapping = mapping
                st.session_state.difficulty = difficulty
                st.session_state.show_labels = show_labels
                st.session_state.game = Game(pl, target, cnt)
                st.rerun()

    with right_col:
        display_leaderboard_top5()



if "game" in st.session_state:
    game = st.session_state.game

    if game.is_game_over():
        if st.session_state.get("difficulty") == "All Countries":
            update_leaderboard_accuracy(game.players)

        players = sorted(game.players, key=lambda p: p.score, reverse=True)
        data = []
        for i, p in enumerate(players):
            avg = p.score / p.rounds_played if p.rounds_played else 0
            data.append({
                "Rank": i + 1,
                "Player": p.name,
                "Score": p.score,
                "Avg": f"{avg:.2f}"
            })

        # HTML-Tabelle als flacher String ohne Einrückungen
        table_rows = ""
        for row in data:
            table_rows += f"<tr><td style='text-align: right;'>{row['Rank']}</td><td style='text-align: left;'>{row['Player']}</td><td style='text-align: right;'>{row['Score']}</td><td style='text-align: right;'>{row['Avg']}</td></tr>"

        full_html = f"""
        <div style='display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 80vh;'>
            <h1 style='text-align: center;'>🏆 Final Results</h1>
            <table style='border-collapse: collapse; width: 300px;'>
                <thead>
                    <tr>
                        <th style='text-align: right;'>Rank</th>
                        <th style='text-align: left;'>Player</th>
                        <th style='text-align: right;'>Score</th>
                        <th style='text-align: right;'>Avg</th>
                    </tr>
                </thead>
                <tbody>
                    {table_rows}
                </tbody>
            </table>
        </div>
        """

        st.markdown(full_html, unsafe_allow_html=True)

        # Button mittig darunter
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if st.button("🔁 Start New Game"):
                for key in list(st.session_state.keys()):
                    del st.session_state[key]
                st.rerun()

        st.stop()






# ─────────────────────────────────────────────────────────────────────────────

    player = game.get_current_player()


    left_col, right_col = st.columns([2.0, 2.0], gap="large")

    with right_col:
        display_interactive_map(game.country, game)

        if st.button("❌ Exit Game"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()

        # ─── NEU: Next Round Button ───
        if game.round_over and not game.is_game_over():
            if st.button("➡️ Next Round"):
                game.next_player()
                game.new_round()
                # Reset Session-State für neue Runde
                st.session_state.guesses = []
                st.session_state.current_country = None
                st.session_state.last_click_processed = None
                st.session_state.show_help_circle = False
                st.session_state.help_button_clicked = False
                st.session_state.help_used_this_round = 0
                st.rerun()

    with left_col:
        st.subheader(f"Current Turn: {player.name}")
        st.markdown("**Score:** " + ", ".join(f"{p.name}: {p.score}" for p in game.players))

        if game.message:
            if game.round_over:
                if game.message.startswith("❌"):
                    st.error(game.message)
                else:
                    st.success(game.message)
            else:
                st.error(game.message)

        st.write("### Hints:")
        for i in range(1, game.hint_index + 1):
            h = get_hint(game.country, i)
            if i == 3 and h.startswith("http"):
                st.write("**Hint 3: Flag**")
                st.image(h, width=150)
            else:
                st.markdown(f"**Hint {i}:** {h}")

        if st.session_state.guesses:
            st.markdown("### Your previous attempts:")
            correct = get_centroid_coords(game.country['name']['common'])
            row = world_gdf[world_gdf['name_lower'] == game.country['name']['common'].lower()]
            if correct and not row.empty:
                geom = row.iloc[0]['geometry']
                for i, (lat_i, lon_i) in enumerate(st.session_state.guesses):
                    point = Point(lon_i, lat_i)
                    if geom.contains(point):
                        st.write(f"Attempt {i+1}: 🎯 Correct Hit!")
                    else:
                        dist = geodesic((lat_i, lon_i), tuple(correct)).kilometers
                        st.write(f"Attempt {i+1}: {int(dist)} km away")


# to run the code: streamlit run project.py