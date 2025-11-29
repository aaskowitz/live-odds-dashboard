import streamlit as st
import requests
import pandas as pd
import os

# --- Page Configuration ---
st.set_page_config(page_title="Live NFL Odds Comparator", layout="wide")
st.title("🏈 Live NFL Odds Comparator")
st.write("Compare live odds and find Positive Expected Value (+EV) bets from a curated list of sportsbooks.")

# --- WHITELIST & API CONFIGURATION ---
# Define the specific list of sportsbooks we want to display.
ALLOWED_BOOKS_RAW = {
    'FanDuel', 'DraftKings', 'Underdog Fantasy', 'Fliff', 'Caesars', 'BetMGM', 
    'ESPN BET', 'Fanatics Sportsbook', 'Pinnacle'
}
# **NEW**: Create a lowercase version for case-insensitive matching
ALLOWED_BOOKS_LOWER = {book.lower() for book in ALLOWED_BOOKS_RAW}

SHARP_BOOK_PRIORITY = ['Pinnacle', 'Circa Sports', 'BookMaker']
API_KEY = st.secrets.get("ODDS_API_KEY", os.environ.get('ODDS_API_KEY'))

# (Helper functions are unchanged)
def highlight_favorable_odds(row):
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
    if american_odds > 0:
        potential_winnings = american_odds
    else:
        potential_winnings = 100 / (abs(american_odds) / 100)
    win_amount = potential_winnings * true_prob
    loss_amount = 100 * (1 - true_prob)
    ev_percentage = (win_amount - loss_amount) / 100
    return ev_percentage

@st.cache_data(ttl=600)
def get_h2h_data():
    if not API_KEY: return None, "API key not found."
    st.write("Fetching new moneyline data from The Odds API...")
    response = requests.get(
        'https://api.the-odds-api.com/v4/sports/americanfootball_nfl/odds',
        params={'api_key': API_KEY, 'regions': 'us,eu', 'markets': 'h2h', 'oddsFormat': 'american'}
    )
    if response.status_code != 200: return None, f"API Error: {response.status_code}"
    return response.json(), None

# --- Main App Logic ---
if st.button("Refresh Data"): st.cache_data.clear()

data, error = get_h2h_data()

# --- Diagnostic Tool ---
st.markdown("---")
with st.expander("See sportsbook data diagnostics"):
    if data:
        all_bookmakers_from_api = sorted(list({book['title'] for game in data for book in game['bookmakers']}))
        st.write("**All Sportsbooks Received from API:**")
        st.write(all_bookmakers_from_api)
        st.write("**Your Curated List (Whitelist):**")
        st.write(sorted(list(ALLOWED_BOOKS_RAW)))
        
        # **NEW**: Diagnostic check using the case-insensitive logic
        used_books = [b for b in all_bookmakers_from_api if b.lower() in ALLOWED_BOOKS_LOWER]
        st.write("**Sportsbooks Being Used in Dashboard (Case-Insensitive):**")
        st.write(used_books)

# --- UI TABS ---
tab1, tab2 = st.tabs(["Odds Comparator", "EV Finder"])

with tab1:
    st.header("Head-to-Head Moneyline Odds")
    if error: st.error(error)
    elif data:
        long_format = []
        for game in data:
            home_team, away_team = game['home_team'], game['away_team']
            # **MODIFIED**: Apply the case-insensitive filter here
            filtered_bookmakers = [b for b in game['bookmakers'] if b['title'].lower() in ALLOWED_BOOKS_LOWER]
            for book in filtered_bookmakers:
                for outcome in book['markets'][0]['outcomes']:
                    team = home_team if home_team in outcome['name'] else away_team
                    long_format.append({'game': f"{away_team} @ {home_team}", 'team': team, 'bookmaker': book['title'], 'odds': outcome['price']})
        
        if long_format:
            df = pd.DataFrame(long_format)
            for game_name in sorted(df['game'].unique()):
                st.subheader(game_name)
                game_df = df[df['game'] == game_name]
                pivoted = game_df.pivot_table(index='team', columns='bookmaker', values='odds', aggfunc='first')
                st.dataframe(pivoted.style.apply(highlight_favorable_odds, axis=1).format("{:+.0f}", na_rep="-"), use_container_width=True)

with tab2:
    st.header(f"Positive Expected Value (+EV) Bets")
    if error: st.error(error)
    elif data:
        ev_bets_found = False
        for game in data:
            game_name, home_team, away_team = f"{game['away_team']} @ {game['home_team']}", game['home_team'], game['away_team']
            
            # **MODIFIED**: Apply case-insensitive filter
            filtered_bookmakers = [b for b in game['bookmakers'] if b['title'].lower() in ALLOWED_BOOKS_LOWER]
            
            baseline_book_name, sharp_odds_raw = None, None
            for book_name in SHARP_BOOK_PRIORITY:
                found_book = [b for b in filtered_bookmakers if b['title'] == book_name]
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
            for book in filtered_bookmakers:
                if book['title'] == baseline_book_name: continue
                
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
                st.subheader(game_name)
                st.write(f"Comparing against **{baseline_book_name}**'s no-vig line: **{away_team} ({true_away_prob:.2%})** vs **{home_team} ({true_home_prob:.2%})**")
                ev_df = pd.DataFrame.from_dict(display_data, orient='index')
                st.dataframe(ev_df.fillna('-'), use_container_width=True)
        
        if not ev_bets_found:
            st.warning("No Positive EV bets found in the current data from your curated list of sportsbooks.")
