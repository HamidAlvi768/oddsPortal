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

# Configuration
LEAGUE_URLS = {
    # "Premier League": "https://www.oddsportal.com/football/england/premier-league/",
    # "Ligue 1": "https://www.oddsportal.com/football/france/ligue-1/",
    # "Bundesliga": "https://www.oddsportal.com/football/germany/bundesliga/",
    "LaLiga": "https://www.oddsportal.com/football/spain/laliga/",
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
    urls = []
    wait = WebDriverWait(driver, 20)
    try:
        cookie_button = wait.until(EC.element_to_be_clickable((By.ID, 'onetrust-accept-btn-handler')))
        cookie_button.click()
        print("Accepted cookies.")
        time.sleep(2)
    except Exception:
        print("Cookie banner not found or could not be clicked. Continuing...")
    try:
        wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, 'div.eventRow')))
        time.sleep(3)
        match_elements = driver.find_elements(By.CSS_SELECTOR, 'div.eventRow a')
        for elem in match_elements:
            href = elem.get_attribute('href')
            # Only add URLs that look like real match pages (contain a dash and not just /football/ or /england/ etc)
            if href and '/football/' in href and '-' in href.split('/')[-2] and href not in urls:
                urls.append(href)
        print(f"Found {len(urls)} match URLs.")
    except Exception as e:
        print(f"Error finding match URLs on {league_url}: {e}")
    return urls

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
    try:
        for sheet_name, league_url in LEAGUE_URLS.items():
            print(f"\n--- Scraping {sheet_name} ---")
            match_urls = get_match_urls(driver, league_url)
            if not match_urls:
                print(f"No match URLs found for {sheet_name}. Skipping.")
                continue
            league_data = []
            for url in match_urls:
                match_data = parse_match_page(driver, url)
                if match_data:
                    league_data.append(match_data)
                time.sleep(1)
            all_data[sheet_name] = league_data
    finally:
        print("Closing the browser.")
        driver.quit()
    if all_data:
        print("\nFormatting data for Excel export...")
        with pd.ExcelWriter("OddsPortal_Scrape_2024-2025.xlsx", engine='openpyxl') as writer:
            for sheet_name, league_data in all_data.items():
                df = format_data_for_excel(league_data)
                df.to_excel(writer, sheet_name=sheet_name)  # index included by default
        print("Export complete.")
    else:
        print("\nNo data was scraped. The output file was not created.")