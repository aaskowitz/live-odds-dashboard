import streamlit as st
import requests
import pandas as pd
import os

# --- Page Configuration ---
st.set_page_config(page_title="Live NFL Odds Comparator", layout="wide")
st.title("🏈 Live NFL Head-to-Head Odds Comparator")
st.write("This dashboard fetches live moneyline odds and highlights the most favorable odds for each team across different sportsbooks.")

# --- API Configuration ---
# Your API key is securely retrieved from Streamlit's secrets manager.
API_KEY = st.secrets.get("ODDS_API_KEY", os.environ.get('ODDS_API_KEY'))

# --- Caching and Data Fetching Function ---
@st.cache_data(ttl=600)  # Cache data for 10 minutes
def get_odds_data():
    """
    Fetches live odds data and returns a structured DataFrame for display.
    """
    if not API_KEY:
        st.error("API key not found. Please ensure it's set in your Streamlit secrets.")
        return None

    # This message will only show when the function is re-run (after cache expires)
    st.write("Fetching new data from The Odds API...")
    
    odds_response = requests.get(
        'https://api.the-odds-api.com/v4/sports/americanfootball_nfl/odds',
        params={
            'api_key': API_KEY,
            'regions': 'us',
            'markets': 'h2h',
            'oddsFormat': 'american'
        }
    )

    if odds_response.status_code != 200:
        st.error(f"API Error: {odds_response.status_code} - {odds_response.text}")
        return None
    
    odds_json = odds_response.json()
    
    # Process data into a "long" format first
    long_format_data = []
    for game in odds_json:
        for bookmaker in game['bookmakers']:
            for outcome in bookmaker['markets'][0]['outcomes']:
                long_format_data.append({
                    'game': f"{game['away_team']} @ {game['home_team']}",
                    'team': outcome['name'],
                    'bookmaker': bookmaker['title'],
                    'odds': outcome['price']
                })
    
    if not long_format_data:
        return pd.DataFrame() # Return empty dataframe if no data

    return pd.DataFrame(long_format_data)

def highlight_favorable_odds(row):
    """
    Highlights the maximum value in a row of a DataFrame.
    This works for American odds because the highest number is always the best payout.
    """
    if row.dtype != 'object':
        max_value = row.max()
        return ['background-color: #2E8B57' if v == max_value else '' for v in row]
    return ['' for v in row]


# --- Main Dashboard Logic ---
if st.button("Refresh Data"):
    st.cache_data.clear()

odds_df = get_odds_data()

if odds_df is not None and not odds_df.empty:
    # Get a list of unique games to create a block for each one
    unique_games = odds_df['game'].unique()

    for game in unique_games:
        st.subheader(game)
        
        # Filter the dataframe for the current game
        game_df = odds_df[odds_df['game'] == game]
        
        # Pivot the table to have teams as rows and bookmakers as columns
        pivoted_df = game_df.pivot_table(
            index='team',
            columns='bookmaker',
            values='odds'
        )
        
        # Apply the styling to highlight the best odds in each row
        styled_df = pivoted_df.style.apply(highlight_favorable_odds, axis=1).format("{:+.0f}", na_rep="-")

        st.dataframe(styled_df, use_container_width=True)
        st.write("---") # Add a separator between games

else:
    st.warning("No odds data available to display. This might be due to the off-season or an API issue.")

st.write("Data sourced from The Odds API.")

