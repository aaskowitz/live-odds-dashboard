import streamlit as st
import requests
import pandas as pd
import os

st.set_page_config(page_title="Live NFL Odds", layout="wide")
st.title("🏈 Live NFL Head-to-Head Odds")

# In the next steps, we will add your API key to Streamlit's secrets
API_KEY = st.secrets.get("ODDS_API_KEY", os.environ.get('ODDS_API_KEY'))

@st.cache_data(ttl=600)
def get_odds_data():
    if not API_KEY:
        st.error("API key not found. Please ensure it's set in your Streamlit secrets.")
        return None

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
    
    rows = []
    for game in odds_json:
        home_team = game['home_team']
        away_team = game['away_team']
        commence_time = pd.to_datetime(game['commence_time'])

        for bookmaker in game['bookmakers']:
            bookmaker_title = bookmaker['title']
            outcomes = bookmaker['markets'][0]['outcomes']
            home_odds = next((o['price'] for o in outcomes if o['name'] == home_team), None)
            away_odds = next((o['price'] for o in outcomes if o['name'] == away_team), None)

            rows.append({
                'Game': f"{away_team} @ {home_team}",
                'Time (UTC)': commence_time.strftime('%Y-%m-%d %H:%M'),
                'Bookmaker': bookmaker_title,
                f'{away_team} Odds': away_odds,
                f'{home_team} Odds': home_odds
            })

    return pd.DataFrame(rows)

if st.button("Refresh Data"):
    st.cache_data.clear()

odds_df = get_odds_data()

if odds_df is not None and not odds_df.empty:
    st.dataframe(odds_df, use_container_width=True)
    st.write("Data is cached for 10 minutes.")
else:
    st.warning("Could not retrieve odds data.")

st.write("---")
st.write("Data sourced from The Odds API.")
