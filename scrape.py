import json
import pandas as pd
from bs4 import BeautifulSoup
from datetime import datetime
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import re

# Configuration
LEAGUE_URLS = {
    # "Premier League": "https://www.oddsportal.com/football/england/premier-league/",
    # "Ligue 1": "https://www.oddsportal.com/football/france/ligue-1/",
    # "Bundesliga": "https://www.oddsportal.com/football/germany/bundesliga/",
    "LaLiga": "https://www.oddsportal.com/football/spain/laliga-2024-2025/results/",
    # "Serie A": "https://www.oddsportal.com/football/italy/serie-a/"
}

BET_TYPE_MAPPING = {
    "1X2": "1X2 - Full time",
    "1st Half 1X2": "1X2 - 1st half",
    "Over/Under +1.5": "OVER/UNDER - Full time - over/under +1.5",
    "Over/Under +2.5": "OVER/UNDER - Full time - over/under +2.5",
    "Over/Under +3.5": "OVER/UNDER - Full time - over/under +3.5",
    "1st Half Over/Under +0.5": "OVER/UNDER - 1st half - over/under +0.5",
    "1st Half Over/Under +1.5": "OVER/UNDER - 1st half - over/under +1.5",
    "1st Half Over/Under +2.5": "OVER/UNDER - 1st half - over/under +2.5",
    "Both Teams To Score": "BOTH TEAMS TO SCORE",
}

def setup_driver():
    options = Options()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("start-maximized")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    return driver

def get_match_urls(driver, league_url):
    print(f"Navigating to league page: {league_url}")
    driver.get(league_url)
    matches = []
    wait = WebDriverWait(driver, 20)
    time.sleep(2)
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    pagination_links = soup.find_all('a', class_='pagination-link', attrs={'data-number': True})
    if pagination_links:
        page_numbers = [int(link['data-number']) for link in pagination_links if link['data-number'].isdigit()]
        max_page = max(page_numbers) if page_numbers else 1
    else:
        max_page = 1
    print(f"Found {max_page} pages of results.")
    def extract_matches_from_soup(soup):
        match_list = []
        for row in soup.find_all('div', {'data-testid': 'game-row'}):
            participants = row.find_all('p', class_='participant-name')
            if len(participants) == 2:
                home = participants[0].get_text(strip=True)
                away = participants[1].get_text(strip=True)
                # Try to find a clickable match URL in this row
                a_tag = row.find('a', href=True)
                url = None
                if a_tag:
                    href = a_tag['href']
                    if href.startswith('http'):
                        url = href
                    else:
                        url = 'https://www.oddsportal.com' + href
                match_list.append({'home': home, 'away': away, 'url': url})
        return match_list
    all_matches = []
    for page in range(1, max_page + 1):
        if page == 1:
            page_soup = soup
        else:
            paged_url = league_url.split('#')[0] + f"#/page/{page}/"
            print(f"Navigating to page {page}: {paged_url}")
            driver.get(paged_url)
            time.sleep(2)
            page_soup = BeautifulSoup(driver.page_source, 'html.parser')
        match_list = extract_matches_from_soup(page_soup)
        all_matches.extend(match_list)
    print(f"Found {len(all_matches)} matches across all pages.")
    print("Matches found (home vs away, url):")
    for m in all_matches:
        print(f"{m['home']} vs {m['away']} | {m['url']}")
    return all_matches

def parse_match_page(driver, match_url):
    print(f"Processing match: {match_url}")
    try:
        driver.get(match_url)
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, 'react-event-header')))
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        data_div = soup.find('div', {'id': 'react-event-header'})
        if not data_div or not data_div.get('data'):
            print(f"Could not find JSON data on page: {match_url}")
            return None
        data = json.loads(data_div['data'])
        home_team = data.get('eventData', {}).get('home')
        away_team = data.get('eventData', {}).get('away')
        start_timestamp = data.get('eventBody', {}).get('startDate')
        match_date = datetime.fromtimestamp(start_timestamp).strftime('%d.%m.%Y %H:%M') if start_timestamp else None

        odds_data = {}
        # Find all bookmaker rows
        rows = soup.find_all('div', attrs={'data-testid': 'over-under-expanded-row'})
        for row in rows:
            # Extract bookmaker name
            bookmaker_tag = row.find('p', attrs={'data-testid': 'outrights-expanded-bookmaker-name'})
            bookmaker = bookmaker_tag.get_text(strip=True) if bookmaker_tag else None
            if not bookmaker:
                continue
            # Extract odds (1, X, 2)
            odds_tags = row.find_all('div', attrs={'data-testid': 'odd-container'})
            odds = [odd_tag.find('p').get_text(strip=True) if odd_tag.find('p') else None for odd_tag in odds_tags]
            if len(odds) >= 3:
                odds_data[bookmaker] = {"1": odds[0], "X": odds[1], "2": odds[2]}
                print(f"Bookmaker: {bookmaker}, Odds: {odds[:3]}")

        match_record = {
            "Date": match_date,
            "Home Team": home_team,
            "Away Team": away_team,
            "Odds": odds_data,
            "URL": match_url
        }
        return match_record
    except Exception as e:
        print(f"An unexpected error occurred while parsing {match_url}: {e}")
        return None

def format_data_for_excel(all_matches_data):
    if not all_matches_data:
        return pd.DataFrame()
    bookmakers = ["Pinnacle", "bet365", "1xBet"]
    bet_types = [
        ("1X2 - Full time", "Full Time", "1X2"),
        ("1X2 - 1st half", "1st Half", "1X2")
    ]
    outcomes = ["1", "X", "2"]
    columns = [
        ("Date", "", ""),
        ("Home Team", "", ""),
        ("Away Team", "", ""),
        ("Result full time", "", ""),
        ("Result 1st half", "", ""),
        ("Result 2nd half", "", "")
    ]
    for bet_type, _, _ in bet_types:
        for bookmaker in bookmakers:
            for outcome in outcomes:
                columns.append((bet_type, bookmaker, outcome))
    processed_rows = []
    for record in all_matches_data:
        base_row = {
            ("Date", "", ""): record["Date"],
            ("Home Team", "", ""): record["Home Team"],
            ("Away Team", "", ""): record["Away Team"],
            ("Result full time", "", ""): "",
            ("Result 1st half", "", ""): "",
            ("Result 2nd half", "", ""): ""
        }
        for bet_type, _, _ in bet_types:
            for bookmaker in bookmakers:
                for outcome in outcomes:
                    odds = ""
                    if "Odds" in record and bookmaker in record["Odds"]:
                        odds = record["Odds"][bookmaker].get(outcome, "")
                    base_row[(bet_type, bookmaker, outcome)] = odds
        processed_rows.append(base_row)
    df = pd.DataFrame(processed_rows, columns=pd.MultiIndex.from_tuples(columns))
    return df

if __name__ == "__main__":
    driver = setup_driver()
    all_data = {}
    parsed_matches = []  # For logging (home, away) pairs
    try:
        for sheet_name, league_url in LEAGUE_URLS.items():
            print(f"\n--- Scraping {sheet_name} ---")
            match_infos = get_match_urls(driver, league_url)
            if not match_infos:
                print(f"No matches found for {sheet_name}. Skipping.")
                continue
            league_data = []
            for match in match_infos:
                url = match['url']
                if url:
                    match_data = parse_match_page(driver, url)
                    if match_data:
                        league_data.append(match_data)
                        parsed_matches.append((match_data["Home Team"], match_data["Away Team"]))
                    else:
                        print(f"Failed to parse match: {url}")
                else:
                    print(f"No URL for match: {match['home']} vs {match['away']}")
                time.sleep(1)
            all_data[sheet_name] = league_data
    finally:
        print("Closing the browser.")
        driver.quit()
    # Write parsed (home, away) pairs to a text file for comparison
    with open("parsed_matches.txt", "w", encoding="utf-8") as f:
        for home, away in parsed_matches:
            f.write(f"{home} vs {away}\n")
    if all_data:
        print("\nFormatting data for Excel export...")
        with pd.ExcelWriter("OddsPortal_Scrape_2024-2025.xlsx", engine='openpyxl') as writer:
            for sheet_name, league_data in all_data.items():
                df = format_data_for_excel(league_data)
                df.to_excel(writer, sheet_name=sheet_name)  # index included by default
        print("Export complete.")
    else:
        print("\nNo data was scraped. The output file was not created.")