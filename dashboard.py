import streamlit as st
import requests
import pandas as pd
import os
from datetime import datetime

# --- Page Configuration ---
st.set_page_config(page_title="Live NFL Odds Comparator", layout="wide")
st.title("🏈 Live NFL Odds Comparator")
st.write("A dashboard to compare live odds and find Positive Expected Value (+EV) bets.")

# --- WHITELIST & API CONFIGURATION ---
ALLOWED_BOOKS_RAW = {
    'FanDuel', 'DraftKings', 'Underdog Fantasy', 'Fliff', 'Caesars', 'BetMGM',
    'ESPN BET', 'Fanatics Sportsbook', 'Pinnacle'
}
LOWER_TO_PROPER_CASE_MAP = {book.lower(): book for book in ALLOWED_BOOKS_RAW}
ALLOWED_BOOKS_LOWER = set(LOWER_TO_PROPER_CASE_MAP.keys())
SHARP_BOOK_PRIORITY = ['Pinnacle', 'Circa Sports', 'BookMaker']
API_KEY = st.secrets.get("ODDS_API_KEY", os.environ.get('ODDS_API_KEY'))
USER_TIMEZONE = "America/New_York"

# --- HELPER FUNCTIONS ---

def format_spread_total(val):
    if not isinstance(val, tuple) or pd.isna(val[0]) or pd.isna(val[1]): return "-"
    point, odds = val
    point_str = f"{point:+.1f}" if point != 0 else f"{point:.1f}"
    odds_str = f"{odds:+.0f}"
    return f'<div style="line-height: 1.2; text-align: center;"><span style="font-weight: bold; font-size: 1.1em;">{point_str}</span><br><span style="font-size: 0.9em; color: #6e6e6e;">{odds_str}</span></div>'

def highlight_favorable_odds_tuple(series):
    def get_odds(val):
        if isinstance(val, tuple) and pd.notna(val[1]): return val[1]
        return -9999
    odds_only = series.apply(get_odds)
    max_odds = odds_only.max()
    return ['background-color: #2E8B57' if v == max_odds and v != -9999 else '' for v in odds_only]

def highlight_favorable_odds_simple(row):
    numeric_row = pd.to_numeric(row, errors='coerce').dropna()
    if not numeric_row.empty:
        max_value = numeric_row.max()
        return ['background-color: #2E8B57' if v == max_value else '' for v in row]
    return ['' for v in row]

def calculate_no_vig_prob(odds1, odds2):
    prob1 = 100 / (odds1 + 100) if odds1 > 0 else abs(odds1) / (abs(odds1) + 100)
    prob2 = 100 / (odds2 + 100) if odds2 > 0 else abs(odds2) / (abs(odds2) + 100)
    total_prob = prob1 + prob2
    if total_prob == 0: return 0, 0
    return prob1 / total_prob, prob2 / total_prob

def calculate_ev(true_prob, american_odds):
    if american_odds > 0: potential_winnings = american_odds
    else: potential_winnings = 100 / (abs(american_odds) / 100)
    win_amount = potential_winnings * true_prob
    loss_amount = 100 * (1 - true_prob)
    return (win_amount - loss_amount) / 100

@st.cache_data(ttl=600)
def get_market_data(market_key):
    if not API_KEY: return None, "API key not found."
    st.write(f"Fetching new '{market_key}' data from The Odds API...")
    response = requests.get('https://api.the-odds-api.com/v4/sports/americanfootball_nfl/odds', params={'api_key': API_KEY, 'regions': 'us,eu', 'markets': market_key, 'oddsFormat': 'american'})
    if response.status_code != 200: return None, f"API Error: {response.status_code}"
    raw_data, standardized_data = response.json(), []
    for game in raw_data:
        game['commence_time_dt'] = datetime.fromisoformat(game['commence_time'].replace('Z', '+00:00'))
        standardized_bookmakers = [b.copy() for b in game['bookmakers'] if b['title'].lower() in ALLOWED_BOOKS_LOWER]
        for book in standardized_bookmakers: book['title'] = LOWER_TO_PROPER_CASE_MAP[book['title'].lower()]
        if standardized_bookmakers:
            game['bookmakers'] = standardized_bookmakers
            standardized_data.append(game)
    standardized_data.sort(key=lambda x: x['commence_time_dt'])
    return standardized_data, None

# --- Main App Logic ---
if st.button("Refresh All Data"): st.cache_data.clear()

tab1, tab2 = st.tabs(["Odds Comparator", "EV Finder"])

with tab1:
    market_options = {"Moneyline": "h2h", "Point Spreads": "spreads", "Game Totals (O/U)": "totals"}
    selected_market_name = st.selectbox("Select a Market:", options=list(market_options.keys()))
    selected_market_key = market_options[selected_market_name]
    
    data, error = get_market_data(selected_market_key)

    if error: st.error(error)
    elif not data: st.warning("No game data available for this market.")
    else:
        game_times = {f"{g['away_team']} @ {g['home_team']}": g['commence_time_dt'] for g in data}

        if selected_market_key == 'h2h':
            long_format = [{'game_id': f"{g['away_team']} @ {g['home_team']}", 'team': o['name'], 'bookmaker': b['title'], 'odds': o['price']} for g in data for b in g['bookmakers'] for o in b['markets'][0]['outcomes']]
            df = pd.DataFrame(long_format)
            for game_name in sorted(game_times.keys(), key=lambda k: game_times[k]):
                game_time_local = game_times[game_name].astimezone(pd.Timestamp(datetime.now(), tz=USER_TIMEZONE).tz)
                st.subheader(f"{game_name} ({game_time_local.strftime('%a, %b %d - %I:%M %p %Z')})")
                pivoted = df[df['game_id'] == game_name].pivot_table(index='team', columns='bookmaker', values='odds', aggfunc='first')
                st.dataframe(pivoted.style.apply(highlight_favorable_odds_simple, axis=1).format("{:+.0f}", na_rep="-"), use_container_width=True)
        else:
            long_format = [{'game_id': f"{g['away_team']} @ {g['home_team']}", 'bookmaker': b['title'], 'outcome_name': o['name'], 'value': (o['point'], o['price'])} for g in data for b in g['bookmakers'] for m in b['markets'] for o in m['outcomes']]
            df = pd.DataFrame(long_format)
            for game_name in sorted(game_times.keys(), key=lambda k: game_times[k]):
                game_time_local = game_times[game_name].astimezone(pd.Timestamp(datetime.now(), tz=USER_TIMEZONE).tz)
                st.subheader(f"{game_name} ({game_time_local.strftime('%a, %b %d - %I:%M %p %Z')})")
                game_df = df[df['game_id'] == game_name]
                pivoted = game_df.pivot_table(index='outcome_name', columns='bookmaker', values='value', aggfunc='first')
                if selected_market_key == 'totals' and 'Over' in pivoted.index and 'Under' in pivoted.index:
                    pivoted = pivoted.reindex(['Over', 'Under'])
                styled_df = pivoted.style.apply(highlight_favorable_odds_tuple, axis=1).format(format_spread_total, na_rep="-")
                st.markdown(styled_df.to_html(), unsafe_allow_html=True)

with tab2:
    st.header(f"Positive Expected Value (+EV) Bets")
    st.info("Finds profitable bets by comparing odds to the 'no-vig' line from the sharpest available bookmaker (Pinnacle, etc.).")
    data, error = get_market_data('h2h')
    if error: st.error(error)
    elif data:
        ev_bets_found = False
        for game in data:
            game_name, home_team, away_team = f"{game['away_team']} @ {game['home_team']}", game['home_team'], game['away_team']
            game_time_local = game['commence_time_dt'].astimezone(pd.Timestamp(datetime.now(), tz=USER_TIMEZONE).tz)
            
            baseline_book_name, sharp_odds_raw = None, None
            for book_name in SHARP_BOOK_PRIORITY:
                found_book = [b for b in game['bookmakers'] if b['title'] == book_name]
                if found_book:
                    baseline_book_name, sharp_odds_raw = book_name, found_book[0]
                    break
            
            if not baseline_book_name: continue

            sharp_outcomes = sharp_odds_raw['markets'][0]['outcomes']
            sharp_away_odds = next((o['price'] for o in sharp_outcomes if away_team in o['name']), None)
            sharp_home_odds = next((o['price'] for o in sharp_outcomes if home_team in o['name']), None)

            if sharp_away_odds is None or sharp_home_odds is None: continue
            
            true_away_prob, true_home_prob = calculate_no_vig_prob(sharp_away_odds, sharp_home_odds)

            display_data = {}
            for book in game['bookmakers']:
                if book['title'] in SHARP_BOOK_PRIORITY: continue
                
                book_outcomes = book['markets'][0]['outcomes']
                book_away_odds = next((o['price'] for o in book_outcomes if away_team in o['name']), None)
                book_home_odds = next((o['price'] for o in book_outcomes if home_team in o['name']), None)

                if book_away_odds:
                    ev = calculate_ev(true_away_prob, book_away_odds)
                    if ev > 0:
                        ev_bets_found, display_data[away_team] = True, display_data.get(away_team, {})
                        display_data[away_team][book['title']] = f"{book_away_odds:+.0f} ({ev:.2%})"
                
                if book_home_odds:
                    ev = calculate_ev(true_home_prob, book_home_odds)
                    if ev > 0:
                        ev_bets_found, display_data[home_team] = True, display_data.get(home_team, {})
                        display_data[home_team][book['title']] = f"{book_home_odds:+.0f} ({ev:.2%})"

            if display_data:
                st.subheader(f"{game_name} ({game_time_local.strftime('%a, %b %d - %I:%M %p %Z')})")
                st.write(f"Comparing against **{baseline_book_name}**'s no-vig line: **{away_team} ({true_away_prob:.2%})** vs **{home_team} ({true_home_prob:.2%})**")
                ev_df = pd.DataFrame.from_dict(display_data, orient='index')
                st.dataframe(ev_df.fillna('-'), use_container_width=True)

        if not ev_bets_found:
            st.warning("No Positive EV bets found in the current data.")

