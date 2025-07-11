from bs4 import BeautifulSoup

with open('inspectSource.html', 'r', encoding='utf-8') as f:
    html = f.read()

soup = BeautifulSoup(html, 'html.parser')

match_rows = soup.find_all('div', {'data-testid': 'game-row'})
unique_matches = set()
for row in match_rows:
    participants = row.find_all('p', class_='participant-name')
    if len(participants) == 2:
        home = participants[0].get_text(strip=True)
        away = participants[1].get_text(strip=True)
        unique_matches.add((home, away))

print(f"Total unique matches found on first page: {len(unique_matches)}")
for idx, (home, away) in enumerate(sorted(unique_matches), 1):
    print(f"{idx}. {home} vs {away}") 