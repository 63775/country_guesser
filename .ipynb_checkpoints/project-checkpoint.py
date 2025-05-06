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

# Set Page Configuration (muss ganz oben stehen)
st.set_page_config(page_title="Country Guesser", layout="wide")  # Changed to "wide" for greater width

# ==================== Geo-Daten vorbereiten ====================
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

# ==================== Länder-Liste (Top GDP) ====================
@st.cache_data
def fetch_top_gdp_countries():
    top_countries = {
        "United States", "China", "Japan", "Germany", "India", "United Kingdom",
        "France", "Italy", "Canada", "Russia", "South Korea", "Australia",
        "Spain", "Mexico", "Indonesia", "Brazil", "Saudi Arabia", "Turkey",
        "Netherlands", "Switzerland", "Argentina", "Sweden", "Poland",
        "Belgium", "Thailand", "Iran", "Austria", "Norway", "Ireland", "Israel"
    }
    url = "https://restcountries.com/v3.1/all"
    r = requests.get(url, timeout=10)
    data = r.json() if r.status_code == 200 else []
    filtered = [c for c in data if c.get("name", {}).get("common") in top_countries]
    return random.sample(filtered, k=min(10, len(filtered)))

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
    st.write("## Leaderboard (Avg. Points/Round)")
    scores = [
        (n, d["total_points"]/d["total_rounds"]) for n, d in lb.items() if d["total_rounds"]>0
    ]
    scores.sort(key=lambda x: x[1], reverse=True)
    for i, (n, avg) in enumerate(scores[:5], 1):
        st.write(f"{i}. **{n}** – {avg:.2f}")

# ==================== Interaktive Karte ====================
def display_interactive_map(country, game):
    # Initialisiere die Sitzungsvariablen für die Karte
    if 'guesses' not in st.session_state:
        st.session_state.guesses = []
    if 'current_country' not in st.session_state or st.session_state.current_country != country['name']['common']:
        st.session_state.guesses = []
        st.session_state.current_country = country['name']['common']
    if 'last_click_processed' not in st.session_state:
        st.session_state.last_click_processed = None
        
    # Erstelle eine statische Basiskarte
    m = folium.Map(location=[20, 0], zoom_start=2)
    
    # Feature Group für alle Marker
    fg = folium.FeatureGroup(name="Guesses")
    
    # Bisherige Versuche als rote Marker hinzufügen
    for i, (lat_i, lon_i) in enumerate(st.session_state.guesses):
        popup = f"Versuch {i+1}"
        folium.Marker(
            location=[lat_i, lon_i],
            popup=popup,
            icon=folium.Icon(color='red', icon='question', prefix='fa')
        ).add_to(fg)
    
    # Lösung als grünen Marker hinzufügen wenn Runde vorbei
    if game.round_over:
        coords = get_centroid_coords(country['name']['common'])
        if coords:
            folium.CircleMarker(
                location=coords,
                radius=8,
                popup=f"Lösung: {country['name']['common']}",
                color='green',
                fill=True,
                fill_opacity=0.7
            ).add_to(fg)
    
    # Feature Group zur Karte hinzufügen
    fg.add_to(m)
    
    st.write("### Klicke auf die Karte, wo du das Land vermutest:")
    
    # Wichtig: Unique Key für jede Karte, der sich NICHT bei jedem Klick ändert
    map_key = f'gdp_map_{game.current_player_index}_{len(st.session_state.guesses)}'
    
    # Rendering der Karte mit dynamischen Callbacks
    map_data = st_folium(
        m,
        height=500,
        width=700,
        key=map_key,
        returned_objects=['last_clicked']
    )
    
    # Klick verarbeiten, wenn die Runde noch läuft
    if map_data and map_data.get('last_clicked') and not game.round_over:
        lat = map_data['last_clicked']['lat']
        lon = map_data['last_clicked']['lng']
        
        # Nur neue Klicks verarbeiten
        click_data = (lat, lon)
        if click_data != st.session_state.last_click_processed:
            st.session_state.last_click_processed = click_data
            st.session_state.guesses.append(click_data)
            
            # Land getroffen?
            guess_pt = Point(lon, lat)
            row = world_gdf[world_gdf['name_lower'] == country['name']['common'].lower()]
            
            if not row.empty and row.iloc[0]['geometry'].contains(guess_pt):
                pts = max(5 - (game.hint_index - 1), 1)
                game.get_current_player().add_score(pts)
                game.message = f"🎉 Treffer innerhalb der Landesgrenzen! +{pts} Punkte."
                game.round_over = True
            else:
                # In der Nähe des richtigen Landes?
                correct = get_centroid_coords(country['name']['common'])
                if correct:
                    dist = geodesic((lat, lon), tuple(correct)).kilometers
                    if dist <= 250:
                        pts = max(5 - (game.hint_index - 1), 1)
                        game.get_current_player().add_score(pts)
                        game.message = f"🎉 Treffer! Distanz: {int(dist)} km → +{pts} Punkte."
                        game.round_over = True
                    else:
                        game.guess_count += 1
                        if game.hint_index < 5:
                            game.hint_index += 1
                        game.message = f"❌ Falsch – {int(dist)} km entfernt."
                        if game.guess_count >= 5:
                            game.get_current_player().add_score(0)
                            game.message += f" Runde vorbei. Antwort: {country['name']['common']}."
                            game.round_over = True
            st.rerun()

    st.write("🎲 Tippe einfach auf die Karte, um zu raten! Deine bisherigen Versuche sind rot markiert.")
    
    # Removed display of distances for previous attempts here, as they'll be shown in the right column

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
        caps = country.get("capital") or []
        return "Capital: " + ", ".join(caps) if caps else "Capital: Unknown"
    if i == 4:
        flag = country.get("flags", {})
        return flag.get("png") or flag.get("svg") or ""
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
            self.message = f"✅ Richtig! +{pts} Punkte."
            self.round_over = True
        else:
            self.guess_count += 1
            if self.hint_index < 5:
                self.hint_index += 1
            if self.hint_index > 5 or self.guess_count >= 5:
                self.get_current_player().add_score(0)
                self.message = f"❌ Falsch. Antwort: {self.country['name']['common']}."
                self.round_over = True
            else:
                self.message = "❌ Falsch, weiter versuchen!"

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
    st.title("Country Guesser Setup")
    with st.form("setup"):
        names = st.text_input("Players (comma-separated)", "Alice, Bob")
        target = st.number_input("Target Score", min_value=1, value=20)
        if st.form_submit_button("Start Game"):
            pl = [n.strip() for n in names.split(",") if n.strip()]
            cnt = fetch_top_gdp_countries()
            mapping = {c["cca3"]: c["name"]["common"] for c in cnt if c.get("cca3")}
            st.session_state.country_code_mapping = mapping
            st.session_state.game = Game(pl, target, cnt)
            st.rerun()

if "game" in st.session_state:
    game = st.session_state.game
    player = game.get_current_player()

    st.title("🌍 Country Guesser")
    st.subheader(f"Aktuelle Runde: {player.name}")
    st.markdown("**Punktestand:** " + ", ".join(f"{p.name}: {p.score}" for p in game.players))

    display_leaderboard_top5()

    # Zwei Spalten: Karte (65%) | Infos (35%)
    left_col, right_col = st.columns([2.2, 1.5], gap="large")

    with left_col:
        display_interactive_map(game.country, game)

    with right_col:
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
            if i == 4 and h.startswith("http"):
                st.write("**Hint 4: Flag**")
                st.image(h, width=150)
            else:
                st.markdown(f"**Hint {i}:** {h}")

        if st.session_state.guesses:
            st.markdown("### Deine bisherigen Versuche:")
            correct = get_centroid_coords(game.country['name']['common'])
            if correct:
                for i, (lat_i, lon_i) in enumerate(st.session_state.guesses):
                    dist = geodesic((lat_i, lon_i), tuple(correct)).kilometers
                    st.write(f"Versuch {i+1}: {int(dist)} km entfernt")

        if game.round_over:
            if game.is_game_over():
                update_leaderboard_accuracy(game.players)
                winner = game.get_winner()
                if isinstance(winner, list):
                    st.success(f"🎉 Spiel vorbei! Unentschieden: {', '.join(p.name for p in winner)}")
                else:
                    st.success(f"🏆 Spiel vorbei! Gewinner: **{winner.name}**")
                display_leaderboard_top5()
                if st.button("🔁 Neues Spiel starten"):
                    for key in list(st.session_state.keys()):
                        del st.session_state[key]
                    st.rerun()
            else:
                if st.button("➡️ Nächste Runde"):
                    game.next_player()
                    game.new_round()
                    st.rerun()