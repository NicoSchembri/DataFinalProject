import requests
import csv
import json
from bs4 import BeautifulSoup
from time import sleep
import random

def scrape_letterboxd_movie(url, headers):
    """Scrape data from a single Letterboxd movie page"""
    r = requests.get(url, headers=headers)
    soup = BeautifulSoup(r.content, 'lxml')
    item = {}

    try:
        # Extract title and year
        title_meta = soup.find('meta', {'property': 'og:title'})
        if title_meta:
            title_content = title_meta.get('content', '')
            if '(' in title_content and title_content.endswith(')'):
                title_part, year_part = title_content.rsplit('(', 1)
                item['title'] = title_part.strip()
                item['year'] = year_part.replace(')', '').strip()
            else:
                item['title'] = title_content
                item['year'] = ''

        # Extract first 5 cast members (unique names only)
        cast = list({cast.text for cast in soup.find_all('a', {'class': 'text-slug tooltip'})})[:5]
        item['cast'] = ', '.join(cast)

        # Extract director (unique names only)
        directors = list({d.text for d in soup.select('a[href^="/director/"]')})
        item['director'] = ', '.join(directors)

        # Extract rating from original method
        rating_meta = soup.find('meta', {'name': 'twitter:data2'})
        item['rating'] = rating_meta.get('content') if rating_meta else ''

        # Extract genres
        genres = soup.find('div', {'class': 'text-sluglist capitalize'})
        item['genres'] = ', '.join([g.text for g in genres.find_all('a')]) if genres else ''

        # Extract total rating count from JSON-LD
        json_ld_script = soup.find('script', type='application/ld+json')
        if json_ld_script:
            try:
                json_str = json_ld_script.string.strip()
                if json_str.startswith('{'):
                    data = json.loads(json_str)
                else:
                    json_objects = [obj for obj in json_str.split('\n') if obj.strip().startswith('{')]
                    data = json.loads(json_objects[0]) if json_objects else {}
                
                aggregate_rating = data.get('aggregateRating', {})
                total_ratings = aggregate_rating.get('ratingCount', '')
                
                if isinstance(total_ratings, int):
                    item['total_rating_count'] = f"{total_ratings:,}"
                elif isinstance(total_ratings, str) and total_ratings.isdigit():
                    item['total_rating_count'] = f"{int(total_ratings):,}"
                else:
                    item['total_rating_count'] = str(total_ratings) if total_ratings else ''
            except Exception as e:
                print(f"Error parsing JSON-LD for {url}: {e}")
                item['total_rating_count'] = ''
        else:
            item['total_rating_count'] = ''

    except Exception as e:
        print(f"Error scraping {url}: {str(e)}")
        return None

    return item

def letterboxd_batch():
    headers = {
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'referer': 'https://letterboxd.com/'
    }

    with open('urls.txt', 'r') as f:
        urls = [line.strip() for line in f.readlines() if line.strip()]

    with open('movies_data.csv', 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = [
            'title', 
            'year', 
            'cast', 
            'director', 
            'rating',
            'total_rating_count',
            'genres'
        ]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        for url in urls:
            print(f"Scraping {url}...")
            movie_data = scrape_letterboxd_movie(url, headers)
            if movie_data:
                writer.writerow(movie_data)
            sleep(random.uniform(2, 4))

    print("Scraping complete. Data saved to movies_data.csv")

if __name__ == '__main__':
    letterboxd_batch()