from duckduckgo_search import DDGS
from duckduckgo_search.exceptions import RatelimitException, TimeoutException
import logging
from playwright.sync_api import sync_playwright
from .utils import load_data, save_data, clear_data
from urllib.parse import urljoin, urlparse, urlunparse
from .ai_integration import find_links
import requests
from bs4 import BeautifulSoup
import time
import random
import re
import json
import os
from .ai_integration import summarize_text, DEFAULT_SYSTEM_MESSAGE, generate_search_query

# Path to the data.json and results.json files
DATA_FILE = "data.json"
RESULTS_FILE = "results.json"

# Configure logging
logging.basicConfig(
    filename='scraper.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

def load_data(file_path):
    """Load existing data from a JSON file or return an empty dictionary."""
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as file:
            return json.load(file)
    return {}

def save_data(data, file_path):
    """Save data to a JSON file."""
    with open(file_path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4)

def clear_data(file_path):
    """Clear a JSON file by resetting it to an empty dictionary."""
    with open(file_path, "w", encoding="utf-8") as file:
        json.dump({}, file, indent=4)
    logging.info("Cleared %s", file_path)
    
def perform_web_search(query, max_results=5):
    """Perform AI-optimized web search using the duckduckgo_search library."""
    try:
        # Initialize the DDGS class
        ddgs = DDGS()

        # Perform the search
        results = ddgs.text(
            keywords=query,
            region="wt-wt",  # Worldwide region
            safesearch="moderate",  # Moderate safe search
            max_results=max_results  # Limit the number of results
        )

        # Log the results
        logging.info(f"Found {len(results)} search results for query: {query}")

        # Format the results
        formatted_results = []
        for result in results:
            formatted_results.append({
                'title': result.get('title', 'No Title'),
                'url': result.get('href', 'No URL'),
                'snippet': result.get('body', 'No Snippet')
            })

        return formatted_results

    except RatelimitException as e:
        logging.error(f"Rate limit exceeded: {str(e)}")
        return None
    except TimeoutException as e:
        logging.error(f"Search timeout: {str(e)}")
        return None
    except Exception as e:
        logging.error(f"Search error: {str(e)}")
        return None

def fetch_page(url):
    """Fetch webpage using Playwright with advanced anti-detection measures."""
    try:
        # Preserve query parameters in the URL
        parsed_url = urlparse(url)
        clean_url = urlunparse(parsed_url._replace(query='')) if not parsed_url.query else url
        logging.info("Cleaned URL: %s", clean_url)

        with sync_playwright() as p:
            # Launch browser with stealth settings
            browser = p.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-features=site-per-process,TranslateUI',
                    '--no-sandbox',
                    '--disable-setuid-sandbox'
                ]
            )

            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
                viewport={'width': 1920, 'height': 1080},
                ignore_https_errors=True,
                java_script_enabled=True
            )

            # Stealth modifications
            context.add_init_script("""
                delete Object.getPrototypeOf(navigator).webdriver;
                window.chrome = {runtime: {}};
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3]
                });
            """)

            page = context.new_page()
            page.set_extra_http_headers({
                'Accept-Language': 'en-US,en;q=0.9',
                'Referer': 'https://www.google.com/'
            })

            # Randomized browsing pattern
            page.goto(clean_url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(random.randint(500, 2000))  # Human-like delay

            # Scroll through the page
            for _ in range(3):
                page.mouse.wheel(0, random.randint(200, 500))
                page.wait_for_timeout(random.randint(300, 800))

            content = page.content()
            browser.close()
            return content

    except Exception as e:
        logging.error("Playwright failed: %s", str(e)[:200])
        # Fallback to requests + BeautifulSoup
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
                "Accept-Encoding": "gzip, deflate, br"
            }
            response = requests.get(clean_url, headers=headers, timeout=15)
            response.raise_for_status()
            return response.text
        except Exception as req_error:
            logging.error("Fallback failed: %s", str(req_error)[:200])
            return None

def extract_clean_text(html_content):
    """Extract clean text from HTML content, excluding tags, scripts, and styles."""
    soup = BeautifulSoup(html_content, 'lxml')

    # Remove unwanted tags (scripts, styles, etc.)
    for element in soup(['script', 'style', 'noscript', 'iframe', 'svg', 'img', 'header', 'nav']):
        element.decompose()

    # Get clean text
    clean_text = soup.get_text(separator=' ')

    # Remove extra whitespace and newlines
    clean_text = re.sub(r'\s+', ' ', clean_text).strip()

    return clean_text

def scrape_website(url):
    """Main scraping function with enhanced error handling, clean text extraction, and JSON storage."""
    logging.info("========== Scraping =========== %s", url)

    try:
        # Clear data.json and results.json for every new submission
        clear_data(DATA_FILE)
        clear_data(RESULTS_FILE)

        # Load existing data (should be empty after clearing)
        data = load_data(DATA_FILE)
        results = load_data(RESULTS_FILE)

        # Scrape the main page
        content = fetch_page(url)
        if not content:
            logging.warning("Primary scraping failed, attempting direct link collection")
            return None

        logging.info("Scraped %d characters", len(content))

        # Extract clean text from the main page
        main_page_text = extract_clean_text(content)
        logging.info("Extracted %d characters of clean text from main page", len(main_page_text))

        # Save the main page text to data.json
        data[url] = main_page_text
        save_data(data, DATA_FILE)

        # Extract links using BeautifulSoup
        soup = BeautifulSoup(content, 'lxml')
        all_links = [a.get('href') for a in soup.find_all('a', href=True)]
        logging.info("Found %d links", len(all_links))

        # AI-powered link selection
        links_response = find_links(all_links, url)

        print(f"AI selected links: {links_response}")

        useful_links = links_response.get("links", [])[:4]
        print(f"AI selected links: {useful_links}")
        logging.info("AI selected links: %s", useful_links)

        # Scrape additional pages and extract clean text
        for rel_link in useful_links:
            try:
                full_url = urljoin(url, rel_link)

                logging.info("Scraping additional page: %s", full_url)
                additional_content = fetch_page(full_url)
                if additional_content:
                    additional_clean_text = extract_clean_text(additional_content)
                    logging.info("Extracted %d characters from %s", len(additional_clean_text), full_url)

                    # Save the additional page text to data.json
                    data[full_url] = additional_clean_text
                    save_data(data, DATA_FILE)
            except Exception as e:
                logging.error("Error scraping %s: %s", full_url, str(e)[:200])

        # Summarize pages and update results
        for page_url, page_text in data.items():
            logging.info("Summarizing %s...", page_url)
            page_summary, error = summarize_text(
                page_text,
                DEFAULT_SYSTEM_MESSAGE,
                RESULTS_FILE
            )

            if error:
                logging.error("Summary failed: %s", error)
                continue

            logging.info("Added %d contacts", len(page_summary.get("decision_makers", [])))

        # Final load to return current state
        final_results = load_data(RESULTS_FILE)
        return {
            "data": data,
            "results": final_results,
            "all_links": all_links[:50]
        }

    except Exception as e:
        logging.error("Scraping failed: %s", str(e)[:200])
        return None
