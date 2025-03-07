import os
import json
from .utils import load_data, save_data, clear_data
from openai import OpenAI, BadRequestError, AuthenticationError, NotFoundError, RateLimitError
from dotenv import load_dotenv
from urllib.parse import urlparse, urljoin

load_dotenv()

DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')

client = OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com",
)

# Add the missing process_with_ai function
def process_with_ai(data, system_message):
    """Generic AI processing with JSON output"""
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": f"{system_message}"},
                {"role": "user", "content": str(data)}
            ],
            response_format={"type": "json_object"},
            stream=False
        )
        return json.loads(response.choices[0].message.content)
    except Exception as err:
        print(f"DeepSeek API Error: {err}")
        return {}

        
def find_links(links, input_url):
    """Identify useful links with context length management"""
    system_prompt = """
    Analyze these page links and return 4 most relevant for sales outreach in JSON format:
    {
        "links": ["/about", "/contact", "/leadership", "/careers"]
    }
    Rules:
    1. Prioritize pages with company info, leadership, or contacts
    2. Return only relative paths
    3. Skip invalid/non-existent links
    """
    
    try:
        # Extract base URL dynamically
        parsed_url = urlparse(input_url)
        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
        print(f"Base URL: {base_url}")  # Debugging: Print the base URL
        
        # Preprocess links to avoid context limits
        processed_links = [
            link.rstrip('/')  # Remove trailing slashes
            for link in links
            if link and not link.startswith(('#', 'mailto:'))  # Filter anchors/emails
            and len(link) < 100  # Skip long URLs
        ][:20]  # Only send first 20 relevant links
        
        print(f"Processed Links: {processed_links}")  # Debugging: Print processed links
        
        if not processed_links:
            print("No valid links found after preprocessing.")
            return {"links": []}
            
        # Format for minimal token usage
        links_str = "Links: " + ", ".join(processed_links[:200])  # Truncate if needed
        
        print(f"Sending to AI: {links_str}")  # Debugging: Print links sent to AI
        
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": links_str}
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
            max_tokens=200
        )
        
        print(f"AI Response: {response.choices[0].message.content}")  # Debugging: Print raw AI response
        
        result = json.loads(response.choices[0].message.content)
        
        # Normalize AI-returned links to match processed_links format
        normalized_links = [link.rstrip('/') for link in result.get("links", [])]
        
        print(f"Normalized Links: {normalized_links}")  # Debugging: Print normalized links
        
        # Convert processed links to relative paths for comparison
        processed_relative_links = [
            urlparse(link).path.rstrip('/') for link in processed_links
        ]
        
        print(f"Processed Relative Links: {processed_relative_links}")  # Debugging: Print processed relative links
        
        # Ensure validity by comparing relative paths
        links_array = {
            "links": [
                link for link in normalized_links
            ][:4]
        }

        print(f"AI selected links: {links_array}")
        return links_array
        
    except Exception as err:
        print(f"DeepSeek API Error: {err}")
        return {"links": []}

DEFAULT_SYSTEM_MESSAGE = """
**Sales Intelligence Analysis Framework**

Analyze website content and return structured JSON with verified information:

{
  "company_overview": {
    "official_name": "Full legal name from website",
    "short_name": "Commonly used name",
    "founded_year": "YYYY or 'Not Found'",
    "headquarters": "City, Country"
  },
  "business_analysis": {
    "core_activities": {
      "value": ["List", "of", "primary", "business", "activities"],
      "source": "Page section where found"
    },
    "unique_value_proposition": {
      "value": "1-2 sentence unique selling points",
      "source": "Mission/About page"
    }
  },
  "market_intelligence": {
    "target_geographies": {
      "value": ["Countries/regions served"],
      "source": "Locations page or mentions"
    },
    "key_industries": {
      "value": ["Vertical", "industries", "served"],
      "source": "Case studies/client lists"
    }
  },
  "decision_makers": [
    {
      "name": "Full Name",
      "title": "Executive Title",
      "contact_evidence": {
        "email": "email@company.com (source page)",
        "linkedin": "Profile URL (source)",
        "phone": "+X XXX XXX XXXX (source)"
      },
      "bio_keywords": ["Strategic priorities", "initiatives"]
    }
  ],
  "opportunity_signals": {
    "expansion_signals": {
      "value": ["Job postings", "new office openings"],
      "source": "Careers/News"
    },
    "tech_stack": {
      "value": ["Software", "tools", "platforms", "mentioned"],
      "source": "Technical documentation"
    }
  },
  "competitive_landscape": {
    "direct_competitors": ["Named competitors"],
    "differentiators": ["Unique capabilities"]
  },
  "recent_news": [
    {
      "headline": "News item title",
      "date": "YYYY-MM-DD",
      "implications": "Potential sales opportunities"
    }
  ]
}

**Validation Rules:**
1. ALL fields require source attribution (page section/URL path)
2. Prioritize C-level executives first
3. Phone/email must include parenthetical source (e.g., "Contact page footer")
4. Use "Not Found" for missing required fields
5. Mark speculative insights as "(Needs Verification)"
6. Include only information explicitly stated on website

**Prioritization Guide:**
- Leadership Team > About Page > Careers Page > News Section
- Current Year Initiatives > Historical Information
- Client Lists > General Industry Claims
- Technology Stack > Generic Capability Claims
"""

def recursive_tuple(obj):
    """Recursively convert dictionaries and their contents into tuples."""
    if isinstance(obj, dict):
        return tuple((k, recursive_tuple(v)) for k, v in obj.items())
    elif isinstance(obj, (list, tuple)):
        return tuple(recursive_tuple(x) for x in obj)
    else:
        return obj

def summarize_text(text, system_message, results_file):
    """
    Summarize text and update results.json with validated data.
    Returns tuple: (page_summary, error_message)
    """
    print("\n=== STARTING ANALYSIS ===")
    
    try:
        # Load existing results at start
        results = load_data(results_file)
        
        # Existing validation logic
        if not text or len(str(text)) < 10:
            return {"error": "Invalid text"}, None

        # Generate summary
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": text}
            ],
            response_format={"type": "json_object"},
            temperature=0.5,
        )

        # Parse and validate summary
        page_summary = json.loads(response.choices[0].message.content)
        if not validate_summary(page_summary):
            return {"error": "Invalid summary structure"}, None

        # Merge new data into loaded results
        print(f"\nMerging results for {results_file}...")
        for key, new_value in page_summary.items():
            # Create storage for new key if needed
            if key not in results:
                results[key] = new_value.copy() if isinstance(new_value, (list, dict)) else new_value
                continue

            # Handle lists (prevent duplicates)
            if isinstance(new_value, list):
                existing = {recursive_tuple(item) if isinstance(item, (dict, list)) else item 
                           for item in results[key]}
                results[key].extend(
                    item for item in new_value
                    if (recursive_tuple(item) if isinstance(item, (dict, list)) else item) not in existing
                )

            # Handle dictionaries (merge updates)
            elif isinstance(new_value, dict):
                results[key].update({
                    k: v for k, v in new_value.items()
                    if k not in results[key]
                })

            # Handle other types (overwrite only if empty/missing)
            else:
                if not results[key]:  # Only replace if existing value is empty
                    results[key] = new_value

        # Save updated results immediately
        save_data(results, results_file)
        print(f"Updated results saved to {results_file}")
        
        return page_summary, None

    except Exception as e:
        print(f"Summary error: {str(e)[:200]}")
        return None, str(e)

def validate_summary(summary):
    print("\n=== VALIDATING SUMMARY ===")
    required = ['company_overview', 'business_analysis', 'decision_makers']
    missing = [section for section in required if section not in summary]
    
    if missing:
        print(f"Missing required sections: {missing}")
        return False
        
    print("Checking contact sources...")
    for contact in summary.get('decision_makers', []):
        if 'contact_evidence' not in contact:
            print(f"Missing contact_evidence for {contact.get('name')}")
            return False
            
    print("Validation checks passed")
    return True

def generate_search_query(user_message):
    """Convert user's natural language request into optimized search query"""
    system_prompt = """You are a search optimization expert. Convert the user's request into
    an effective search query following these rules:
    1. Include location if specified
    2. Use site: operator for specific domains when appropriate
    3. Include "contact" or "directory" for business listings
    4. Keep it under 60 characters
    5. Return the output in JSON format.

    Example Output: {"query": "site:.rs inurl:contact construction companies Serbia"}"""

    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ],
        response_format={"type": "json_object"},
        temperature=0.4
    )
    return json.loads(response.choices[0].message.content)["query"]


def analyze_search_results(user_message, search_results):
    """Evaluate search results for relevance to original request"""
    system_prompt = f"""Analyze these search results for relevance to: {user_message}
    For each result calculate:
    - Match score (0-100)
    - Relevance reasoning
    - Confidence factors
    
    Output JSON format:
    {{
        "results": [
            {{
                "url": "https://example.com",
                "title": "Result Title",
                "match_score": 85,
                "reasons": ["Location match", "Industry match"],
                "confidence_factors": ["Official website", "Contact info present"]
            }}
        ],
        "auto_selection": "https://best-match.com"
    }}"""
    
    results_str = "\n".join([f"{res['title']} - {res['url']}" for res in search_results])
    
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": results_str}
        ],
        response_format={"type": "json_object"},
        temperature=0.3
    )
    return json.loads(response.choices[0].message.content)
