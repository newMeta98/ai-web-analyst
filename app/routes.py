from flask import Blueprint, render_template, request, redirect, url_for, Response  
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, BooleanField
from wtforms.validators import Optional, URL
from .scraper import scrape_website, perform_web_search
from .ai_integration import summarize_text, DEFAULT_SYSTEM_MESSAGE, generate_search_query, analyze_search_results
import json
import os
import logging
import re

# Path to the results.json file
RESULTS_FILE = "results.json"

bp = Blueprint('main', __name__)

# Custom logging filter
class ExcludeLogsContentFilter(logging.Filter):
    def filter(self, record):
        return not re.search(r'GET /logs-content', record.getMessage())

# Configure logging
logging.basicConfig(
    filename='scraper.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Add filter to the root logger
for handler in logging.root.handlers:
    handler.addFilter(ExcludeLogsContentFilter())

class ScraperForm(FlaskForm):
    url = StringField('URL', validators=[Optional(), URL(message="Please enter a valid URL.")])
    search_query = StringField('Search Query', validators=[Optional()])
    use_web_search = BooleanField('Enable Web Search')
    auto_select = BooleanField('Auto-select Best Result', default=True)
    system_message = TextAreaField('System Message', validators=[Optional()])

def load_results():
    """Load existing results from results.json or return an empty dictionary."""
    if os.path.exists(RESULTS_FILE):
        with open(RESULTS_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    return {}

def clear_results():
    """Clear results.json by resetting it to an empty dictionary."""
    with open(RESULTS_FILE, "w", encoding="utf-8") as file:
        json.dump({}, file, indent=4)
    logging.info("Cleared results.json")

@bp.route('/logs')
def show_logs():
    """Display the logs interface"""
    try:
        with open("scraper.log", "r") as f:
            logs = f.readlines()[-200:]  # Show last 200 lines
    except FileNotFoundError:
        logs = []
    return render_template('logs.html', logs=logs)

@bp.route('/logs-content')
def logs_content():
    """Endpoint to fetch log file contents with proper formatting"""
    try:
        with open("scraper.log", "r") as f:
            logs = f.read()
    except FileNotFoundError:
        logs = "No logs available yet"
    
    # Ensure logs are returned with newlines
    return Response(logs, mimetype='text/plain')

@bp.route('/', methods=['GET', 'POST'])
def index():
    form = ScraperForm()

    if form.validate_on_submit():
        logging.info("=== FORM SUBMITTED ===")
        url = form.url.data
        search_query = form.search_query.data
        use_web_search = form.use_web_search.data
        auto_select = form.auto_select.data
        system_message = form.system_message.data or DEFAULT_SYSTEM_MESSAGE

        logging.info("URL: %s", url)
        logging.info("Search Query: %s", search_query)
        logging.info("Auto-select: %s", auto_select)
        logging.info("Using system message: %s...", system_message[:100])

        if not url and not search_query:
            logging.warning("No URL or search query provided")
            return render_template('index.html', form=form, error="Please provide a URL or search query.")

        # Handle web search
        if use_web_search and search_query:
            logging.info("Performing web search...")

            # Generate AI-optimized query
            ai_query = generate_search_query(search_query)
            logging.info("AI Generated Query: %s", ai_query)

            # Perform search and get multiple results
            search_results = perform_web_search(ai_query)

            if not search_results:
                return render_template('index.html', form=form, error="No results found for the search query.")

            # Analyze results with AI
            analysis = analyze_search_results(search_query, search_results)

            if auto_select:
                # Use AI's auto-selected URL
                url = analysis["auto_selection"]
                logging.info("AI selected URL: %s", url)
            else:
                return render_template('search_results.html',
                                     query=search_query,
                                     results=analysis["results"],
                                     analysis=analysis,
                                     original_results=search_results,
                                     form=form)

        # Scrape the website
        scraped_data = scrape_website(url)
        logging.info("Scraped Data Type: %s", type(scraped_data))

        if scraped_data:
            logging.info("Starting analysis...")
            results = load_results()

            transformed_summary = {
                "company_name": results.get("company_overview", {}).get("official_name", "Not Found"),
                "core_offerings": results.get("business_analysis", {}).get("core_activities", {}).get("value", []),
                "key_contacts": [
                    {
                        "name": contact.get("name", "Not Found"),
                        "title": contact.get("title", "Not Found"),
                        "contact_info": f"Email: {contact.get('contact_evidence', {}).get('email', 'Not Found')}, Phone: {contact.get('contact_evidence', {}).get('phone', 'Not Found')}"
                    }
                    for contact in results.get("decision_makers", [])
                ],
                "opportunities": [
                    f"{news.get('headline', 'No headline')} - {news.get('implications', 'No implications')}"
                    for news in results.get("recent_news", [])
                ]
            }

            return render_template('results.html',
                                 data=scraped_data,
                                 summary=transformed_summary,
                                 results=results,
                                 system_message=system_message)

    form.system_message.data = DEFAULT_SYSTEM_MESSAGE
    return render_template('index.html', form=form)

@bp.route('/process-selected', methods=['GET'])
def process_selected():
    """Handle user-selected URL from search results"""
    selected_url = request.args.get('url')
    if not selected_url:
        return redirect(url_for('main.index'))

    scraped_data = scrape_website(selected_url)

    if not scraped_data:
        return render_template('index.html', form=ScraperForm(), error="Failed to scrape selected website.")

    results = load_results()

    transformed_summary = {
        "company_name": results.get("company_overview", {}).get("official_name", "Not Found"),
        "core_offerings": results.get("business_analysis", {}).get("core_activities", {}).get("value", []),
        "key_contacts": [
            {
                "name": contact.get("name", "Not Found"),
                "title": contact.get("title", "Not Found"),
                "contact_info": f"Email: {contact.get('contact_evidence', {}).get('email', 'Not Found')}, Phone: {contact.get('contact_evidence', {}).get('phone', 'Not Found')}"
            }
            for contact in results.get("decision_makers", [])
        ],
        "opportunities": [
            f"{news.get('headline', 'No headline')} - {news.get('implications', 'No implications')}"
            for news in results.get("recent_news", [])
        ]
    }

    return render_template('results.html',
                         data=scraped_data,
                         summary=transformed_summary,
                         results=results,
                         system_message=DEFAULT_SYSTEM_MESSAGE)
