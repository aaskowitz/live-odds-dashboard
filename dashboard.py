import streamlit as st
import requests
import pandas as pd
import os

# --- Page Configuration ---
st.set_page_config(page_title="Live NFL Odds Comparator", layout="wide")
st.title("🏈 Live NFL Odds Comparator")
st.write("Compare live odds and find Positive Expected Value (+EV) bets.")

# --- API Configuration & Helper Functions ---
API_KEY = st.secrets.get("ODDS_API_KEY", os.environ.get('ODDS_API_KEY'))
SHARP_BOOK = 'Pinnacle' # Define our source of truth

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
    if not API_KEY:
        return None, "API key not found."
    st.write("Fetching new moneyline data from The Odds API...")
    response = requests.get(
        'https://api.the-odds-api.com/v4/sports/americanfootball_nfl/odds',
        params={'api_key': API_KEY, 'regions': 'us', 'markets': 'h2h', 'oddsFormat': 'american'}
    )
    if response.status_code != 200:
        return None, f"API Error: {response.status_code}"
    return response.json(), None

# --- Main App Logic ---
if st.button("Refresh Data"):
    st.cache_data.clear()

data, error = get_h2h_data()

# --- NEW: Diagnostic Tool ---
st.markdown("---")
with st.expander("See all available sportsbooks in the current data feed"):
    if data:
        all_bookmakers = set()
        for game in data:
            for book in game['bookmakers']:
                all_bookmakers.add(book['title'])
        st.write(sorted(list(all_bookmakers)))
        if SHARP_BOOK not in all_bookmakers:
            st.warning(f"**Diagnostic:** '{SHARP_BOOK}' was not found in the current data feed. The EV Finder will not work without it.")
        if "Fliff" not in all_bookmakers:
             st.info("**Diagnostic:** 'Fliff' was not found in the current data feed. The API is not providing it for these games.")
    else:
        st.write("No data fetched yet.")

# --- UI TABS ---
tab1, tab2 = st.tabs(["Odds Comparator", "EV Finder"])

with tab1:
    st.header("Head-to-Head Moneyline Odds")
    if error:
        st.error(error)
    elif data:
        long_format = []
        for game in data:
            for book in game['bookmakers']:
                for outcome in book['markets'][0]['outcomes']:
                    long_format.append({'game': f"{game['away_team']} @ {game['home_team']}", 'team': outcome['name'], 'bookmaker': book['title'], 'odds': outcome['price']})
        
        if long_format:
            df = pd.DataFrame(long_format)
            for game_name in df['game'].unique():
                st.subheader(game_name)
                game_df = df[df['game'] == game_name]
                pivoted = game_df.pivot_table(index='team', columns='bookmaker', values='odds')
                st.dataframe(pivoted.style.apply(highlight_favorable_odds, axis=1).format("{:+.0f}", na_rep="-"), use_container_width=True)

with tab2:
    st.header(f"Positive Expected Value (+EV) Bets (vs. {SHARP_BOOK})")
    if error:
        st.error(error)
    elif data:
        all_bookmakers = {book['title'] for game in data for book in game['bookmakers']}
        if SHARP_BOOK not in all_bookmakers:
            st.error(f"Cannot calculate EV because '{SHARP_BOOK}' is not available in the current data feed. Please check the available sportsbooks list above or your API plan.")
        else:
            ev_bets_found = False
            for game in data:
                game_name = f"{game['away_team']} @ {game['home_team']}"
                sharp_odds_raw = [b for b in game['bookmakers'] if b['title'] == SHARP_BOOK]
                if not sharp_odds_raw: continue

                outcomes = sharp_odds_raw[0]['markets'][0]['outcomes']
                team1_name, team1_odds = outcomes[0]['name'], outcomes[0]['price']
                team2_name, team2_odds = outcomes[1]['name'], outcomes[1]['price']
                true_prob1, true_prob2 = calculate_no_vig_prob(team1_odds, team2_odds)
                true_probs = {team1_name: true_prob1, team2_name: true_prob2}

                display_data = {}
                for book in game['bookmakers']:
                    if book['title'] == SHARP_BOOK: continue
                    for outcome in book['markets'][0]['outcomes']:
                        ev = calculate_ev(true_probs[outcome['name']], outcome['price'])
                        if ev > 0:
                            ev_bets_found = True
                            if outcome['name'] not in display_data:
                                display_data[outcome['name']] = {}
                            display_data[outcome['name']][book['title']] = f"{outcome['price']:+.0f} ({ev:.2%})"

                if display_data:
                    st.subheader(game_name)
                    st.write(f"Comparing against {SHARP_BOOK}'s no-vig line: **{team1_name} ({true_probs[team1_name]:.2%})** vs **{team2_name} ({true_probs[team2_name]:.2%})**")
                    ev_df = pd.DataFrame.from_dict(display_data, orient='index')
                    st.dataframe(ev_df.fillna('-'), use_container_width=True)
            
            if not ev_bets_found:
                st.warning("No Positive EV bets found in the current data. Markets may be efficient or key bookmakers are missing.")
