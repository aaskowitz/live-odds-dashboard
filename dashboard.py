import streamlit as st
import requests
import pandas as pd
import os
from datetime import datetime

# --- Page Configuration ---
st.set_page_config(page_title="Live NFL Odds Comparator", layout="wide")
st.title("🏈 Live NFL Odds Comparator")
st.write("Use the dropdown menu to select a market and compare live odds from a curated list of sportsbooks.")

# --- WHITELIST & API CONFIGURATION ---
ALLOWED_BOOKS_RAW = {
    'FanDuel', 'DraftKings', 'Underdog Fantasy', 'Fliff', 'Caesars', 'BetMGM',
    'ESPN BET', 'Fanatics Sportsbook', 'Pinnacle'
}
LOWER_TO_PROPER_CASE_MAP = {book.lower(): book for book in ALLOWED_BOOKS_RAW}
ALLOWED_BOOKS_LOWER = set(LOWER_TO_PROPER_CASE_MAP.keys())
API_KEY = st.secrets.get("ODDS_API_KEY", os.environ.get('ODDS_API_KEY'))
USER_TIMEZONE = "America/New_York"

# (Helper functions are unchanged)
def highlight_favorable_odds(row):
    numeric_row = pd.to_numeric(row, errors='coerce').dropna()
    if not numeric_row.empty:
        max_value = numeric_row.max()
        return ['background-color: #2E8B57' if v == max_value else '' for v in row]
    return ['' for v in row]

@st.cache_data(ttl=600)
def get_market_data(market_key):
    """Fetches and standardizes data for a given market."""
    if not API_KEY: return None, "API key not found."
    st.write(f"Fetching new '{market_key}' data from The Odds API...")
    
    response = requests.get(
        'https://api.the-odds-api.com/v4/sports/americanfootball_nfl/odds',
        params={'api_key': API_KEY, 'regions': 'us,eu', 'markets': market_key, 'oddsFormat': 'american'}
    )
    
    if response.status_code != 200: return None, f"API Error: {response.status_code}"
    
    raw_data = response.json()
    standardized_data = []
    for game in raw_data:
        game['commence_time_dt'] = datetime.fromisoformat(game['commence_time'].replace('Z', '+00:00'))
        
        standardized_bookmakers = []
        for book in game['bookmakers']:
            book_title_lower = book['title'].lower()
            if book_title_lower in ALLOWED_BOOKS_LOWER:
                book_copy = book.copy()
                book_copy['title'] = LOWER_TO_PROPER_CASE_MAP[book_title_lower]
                standardized_bookmakers.append(book_copy)
        
        if standardized_bookmakers:
            game_copy = game.copy()
            game_copy['bookmakers'] = standardized_bookmakers
            standardized_data.append(game_copy)
            
    standardized_data.sort(key=lambda x: x['commence_time_dt'])
    return standardized_data, None

# --- Main App Logic ---

# --- NEW: Dropdown Market Selector ---
market_options = {
    "Moneyline": "h2h",
    "Point Spreads": "spreads",
    "Game Totals (O/U)": "totals"
}
selected_market_name = st.selectbox("Select a Market:", options=list(market_options.keys()))
selected_market_key = market_options[selected_market_name]

if st.button(f"Refresh {selected_market_name} Data"):
    st.cache_data.clear()

# Fetch data for the selected market
data, error = get_market_data(selected_market_key)

if error:
    st.error(error)
elif not data:
    st.warning("No game data available for this market at the moment.")
else:
    # Get shared game time information
    unique_games_ordered = [f"{g['away_team']} @ {g['home_team']}" for g in data]
    game_times = {f"{g['away_team']} @ {g['home_team']}": g['commence_time_dt'] for g in data}

    # --- Conditional Display based on Dropdown ---

    # MONEYLINE DISPLAY
    if selected_market_key == 'h2h':
        long_format = []
        for game in data:
            home_team, away_team = game['home_team'], game['away_team']
            for book in game['bookmakers']:
                for outcome in book['markets'][0]['outcomes']:
                    team = home_team if home_team in outcome['name'] else away_team
                    long_format.append({'game_id': f"{away_team} @ {home_team}", 'team': team, 'bookmaker': book['title'], 'odds': outcome['price']})
        
        df = pd.DataFrame(long_format)
        for game_name in unique_games_ordered:
            game_time_local = game_times[game_name].astimezone(pd.Timestamp(datetime.now(), tz=USER_TIMEZONE).tz)
            formatted_time = game_time_local.strftime('%a, %b %d - %I:%M %p %Z')
            st.subheader(f"{game_name} ({formatted_time})")
            game_df = df[df['game_id'] == game_name]
            pivoted = game_df.pivot_table(index='team', columns='bookmaker', values='odds', aggfunc='first')
            st.dataframe(pivoted.style.apply(highlight_favorable_odds, axis=1).format("{:+.0f}", na_rep="-"), use_container_width=True)

    # TOTALS (O/U) DISPLAY
    elif selected_market_key == 'totals':
        totals_long_format = []
        for game in data:
            for book in game['bookmakers']:
                for market in book['markets']:
                    for outcome in market['outcomes']:
                        totals_long_format.append({'game_id': f"{game['away_team']} @ {game['home_team']}", 'bookmaker': book['title'], 'outcome': outcome['name'], 'total_line': outcome['point'], 'odds': outcome['price']})
        
        df_totals = pd.DataFrame(totals_long_format)
        for game_name in unique_games_ordered:
            game_time_local = game_times[game_name].astimezone(pd.Timestamp(datetime.now(), tz=USER_TIMEZONE).tz)
            formatted_time = game_time_local.strftime('%a, %b %d - %I:%M %p %Z')
            st.subheader(f"{game_name} ({formatted_time})")
            game_df = df_totals[df_totals['game_id'] == game_name]
            for total_line, group in game_df.groupby('total_line'):
                st.write(f"**Total: {total_line}**")
                pivoted = group.pivot_table(index='outcome', columns='bookmaker', values='odds', aggfunc='first').reindex(['Over', 'Under'])
                st.dataframe(pivoted.style.apply(highlight_favorable_odds, axis=1).format("{:+.0f}", na_rep="-"), use_container_width=True)
    
    # SPREADS DISPLAY
    elif selected_market_key == 'spreads':
        spreads_long_format = []
        for game in data:
            home_team, away_team = game['home_team'], game['away_team']
            for book in game['bookmakers']:
                for market in book['markets']:
                    for outcome in market['outcomes']:
                        spreads_long_format.append({'game_id': f"{away_team} @ {home_team}", 'bookmaker': book['title'], 'team': outcome['name'], 'spread_point': outcome['point'], 'odds': outcome['price']})

        df_spreads = pd.DataFrame(spreads_long_format)
        for game_name in unique_games_ordered:
            game_time_local = game_times[game_name].astimezone(pd.Timestamp(datetime.now(), tz=USER_TIMEZONE).tz)
            formatted_time = game_time_local.strftime('%a, %b %d - %I:%M %p %Z')
            st.subheader(f"{game_name} ({formatted_time})")
            game_df = df_spreads[df_spreads['game_id'] == game_name]
            # Pivot with a multi-index to group by team and then by spread
            pivoted = game_df.pivot_table(index=['team', 'spread_point'], columns='bookmaker', values='odds', aggfunc='first')
            st.dataframe(pivoted.style.apply(highlight_favorable_odds, axis=1).format("{:+.0f}", na_rep="-"), use_container_width=True)

