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

def highlight_favorable_odds(row):
    """Highlights the maximum numeric value in a row."""
    numeric_row = pd.to_numeric(row, errors='coerce').dropna()
    if not numeric_row.empty:
        max_value = numeric_row.max()
        return ['background-color: #2E8B57' if v == max_value else '' for v in row]
    return ['' for v in row]

def calculate_no_vig_prob(odds1, odds2):
    """Removes the vig to find the 'true' probability for two outcomes."""
    prob1 = 100 / (odds1 + 100) if odds1 > 0 else abs(odds1) / (abs(odds1) + 100)
    prob2 = 100 / (odds2 + 100) if odds2 > 0 else abs(odds2) / (abs(odds2) + 100)
    total_prob = prob1 + prob2
    return prob1 / total_prob, prob2 / total_prob

def calculate_ev(true_prob, american_odds):
    """Calculates the Expected Value of a bet."""
    if american_odds > 0:
        potential_winnings = american_odds
    else:
        potential_winnings = 100 / (abs(american_odds) / 100)
    
    win_amount = potential_winnings * true_prob
    loss_amount = 100 * (1 - true_prob)
    
    ev_percentage = (win_amount - loss_amount) / 100
    return ev_percentage

# --- Main Caching and Data Fetching Function ---
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

# --- UI TABS ---
tab1, tab2 = st.tabs(["Odds Comparator", "EV Finder"])

# --- TAB 1: Simple Odds Comparator ---
with tab1:
    st.header("Head-to-Head Moneyline Odds")
    data, error = get_h2h_data()
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
                st.write("---")

# --- TAB 2: Positive EV Finder ---
with tab2:
    st.header(f"Positive Expected Value (+EV) Bets (vs. {SHARP_BOOK})")
    st.info(f"This tool finds profitable betting opportunities by comparing odds from various sportsbooks against the 'no-vig' line from **{SHARP_BOOK}**.")

    data, error = get_h2h_data()
    if error:
        st.error(error)
    elif data:
        ev_bets_found = False
        for game in data:
            game_name = f"{game['away_team']} @ {game['home_team']}"
            
            # Find the sharp book's odds for this game
            sharp_odds_raw = [b for b in game['bookmakers'] if b['title'] == SHARP_BOOK]
            if not sharp_odds_raw:
                continue # Skip this game if Pinnacle odds aren't available

            # Get the odds for both teams from the sharp book
            outcomes = sharp_odds_raw[0]['markets'][0]['outcomes']
            team1_name, team1_odds = outcomes[0]['name'], outcomes[0]['price']
            team2_name, team2_odds = outcomes[1]['name'], outcomes[1]['price']
            
            # Calculate the 'true' probability
            true_prob1, true_prob2 = calculate_no_vig_prob(team1_odds, team2_odds)
            true_probs = {team1_name: true_prob1, team2_name: true_prob2}

            # Now, iterate through all OTHER bookmakers to find +EV spots
            display_data = {}
            for book in game['bookmakers']:
                if book['title'] == SHARP_BOOK:
                    continue # We don't compare the sharp book against itself
                
                for outcome in book['markets'][0]['outcomes']:
                    team_name = outcome['name']
                    offered_odds = outcome['price']
                    
                    # Calculate EV for this specific bet
                    ev = calculate_ev(true_probs[team_name], offered_odds)
                    
                    if ev > 0: # We only care about POSITIVE EV bets
                        ev_bets_found = True
                        if team_name not in display_data:
                            display_data[team_name] = {}
                        # Store the odds and the EV percentage
                        display_data[team_name][book['title']] = f"{offered_odds:+.0f} ({ev:.2%})"

            # Display the results for this game if we found any +EV bets
            if display_data:
                st.subheader(game_name)
                st.write(f"Comparing against {SHARP_BOOK}'s no-vig line: **{team1_name} ({true_probs[team1_name]:.2%})** vs **{team2_name} ({true_probs[team2_name]:.2%})**")
                ev_df = pd.DataFrame.from_dict(display_data, orient='index')
                st.dataframe(ev_df.fillna('-'), use_container_width=True)
                st.write("---")

        if not ev_bets_found:
            st.warning("No Positive EV bets found in the current data. This could be because markets are efficient or key bookmakers are missing from the API response.")

if st.button("Refresh Data"):
    st.cache_data.clear()

st.write("Data sourced from The Odds API.")

