import os
import json
import sqlite3
import requests
from datetime import datetime
from google import genai
from google.genai import types

# Suspect words and domains for the local heuristic evaluation (fallback)
SUSPICIOUS_DOMAINS = ['.biz', '.xyz', '.cc', '.info', '.click', '.top', '.win']
SUSPICIOUS_KEYWORDS = [
    'double your money', 'double your crypto', 'guaranteed publication', 
    'credit card to secure', 'no registration needed but', 'get rich quick',
    'earn passive income', 'whatsapp group', 'crypto loop'
]

def evaluate_conference_heuristic(title, url, location, description, domain):
    """
    Local heuristic classifier to simulate AI validation when GEMINI_API_KEY is not set.
    """
    flagged = False
    reasons = []

    # Check url domain
    url_lower = url.lower()
    for domain_ext in SUSPICIOUS_DOMAINS:
        if domain_ext in url_lower:
            flagged = True
            reasons.append(f"Suspicious top-level domain ({domain_ext})")
            break

    # Check description keywords
    desc_lower = description.lower()
    for keyword in SUSPICIOUS_KEYWORDS:
        if keyword in desc_lower:
            flagged = True
            reasons.append(f"Suspicious phrasing detected: '{keyword}'")

    # Check for suspicious combinations
    if "free" in desc_lower and ("credit card" in desc_lower or "bank account" in desc_lower):
        flagged = True
        reasons.append("Promisory free event asking for credit/bank details")

    if "secret location" in location.lower() or "vague hotel" in location.lower():
        flagged = True
        reasons.append(f"Highly suspicious/unverifiable location: '{location}'")

    if len(title) > 80 and ("mega" in title.lower() or "summit" in title.lower() and "global" in title.lower()):
        flagged = True
        reasons.append("Grandiose clickbait-style title pattern")

    if flagged:
        return True, "Rule-based flag: " + " | ".join(reasons)
    else:
        return False, "Rule-based pass: Listing meets basic credibility heuristics."


def evaluate_conference_ai(title, url, location, description, domain):
    """
    Calls the Gemini API to verify the conference, falling back to heuristics if the API key is missing.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("[AI Classifier] GEMINI_API_KEY not found. Using local heuristic evaluation.")
        return evaluate_conference_heuristic(title, url, location, description, domain)

    try:
        client = genai.Client(api_key=api_key)
        prompt = f"""
        Analyze the following conference for credibility to identify potential scams, predatory fake academic journals, or fraudulent listings.
        
        Conference Details:
        - Title: {title}
        - Domain: {domain}
        - URL: {url}
        - Location: {location}
        - Description: {description}
        
        Respond in strict JSON format with two keys:
        - "flagged": boolean (true if the conference looks suspicious, fraudulent, or predatory; false if it looks legitimate)
        - "reason": string (a concise, user-friendly explanation of why it was flagged or why it was deemed clean)
        
        Red flags include:
        1. Suspicious domains (e.g. .biz, .xyz, .cc, .info, .click, or strange subdomains).
        2. Vague location descriptions combined with grandiose titles (e.g. "World Summit on Advanced Tech" at "A Nice Hotel, New York").
        3. Predatory publishing promises (e.g., guaranteed publication in low-tier/unnamed journals for a fee).
        4. Scam or high-pressure financial hooks (e.g., double your crypto, MLM, passive income secrets).
        5. Inconsistent dates or extremely short timelines.
        6. Vague registration paths asking for banking/credit cards without proper standard SSL forms.
        """
        
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        
        data = json.loads(response.text)
        return bool(data.get("flagged")), data.get("reason", "Verified by Gemini AI.")
    except Exception as e:
        print(f"[AI Classifier] Gemini API error: {e}. Falling back to heuristics.")
        return evaluate_conference_heuristic(title, url, location, description, domain)


def fetch_scraped_conferences():
    """
    Fetches conferences from real public JSON lists, and generates rich domain list.
    Also injects a few suspicious mock listings to test AI flagging and Admin Approval.
    """
    confs = []

    # 1. Attempt to scrape real JS conferences from confs.tech github repo
    try:
        print("[Scraper] Fetching real JS conferences from confs.tech...")
        url = "https://raw.githubusercontent.com/tech-conferences/confs.tech/master/conferences/2026/javascript.json"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            # Sort and pick the first 10 for demonstration
            for item in data[:10]:
                confs.append({
                    "title": item.get("name"),
                    "domain": "Technology",
                    "start_date": item.get("startDate"),
                    "end_date": item.get("endDate"),
                    "location": f"{item.get('city')}, {item.get('country')}" if item.get("city") else "Online",
                    "description": f"A premier developer event for Javascript and Web Technologies. Featuring core talks on frameworks, performance, and the future of JS.",
                    "url": item.get("url"),
                    "source": "confs.tech"
                })
            print(f"[Scraper] Successfully fetched {len(confs)} real tech conferences.")
    except Exception as e:
        print(f"[Scraper] Failed to fetch live tech conferences ({e}). Fallback to mock data will be merged.")

    # 2. Add realistic, high-quality conferences for other domains
    mock_domains_confs = [
        # Technology (extra)
        {
            "title": "International Conference on Machine Learning (ICML) 2026",
            "domain": "Technology",
            "start_date": "2026-07-12",
            "end_date": "2026-07-18",
            "location": "Seoul, South Korea",
            "description": "The premier academic event in Machine Learning and Artificial Intelligence, bringing together researchers, practitioners, and students from all over the world.",
            "url": "https://icml.cc/Conferences/2026",
            "source": "Symposium List"
        },
        # Medicine
        {
            "title": "Global Oncology Summit 2026",
            "domain": "Medicine",
            "start_date": "2026-09-05",
            "end_date": "2026-09-08",
            "location": "Boston, USA",
            "description": "Bringing together leading oncologists, researchers, and biotech pioneers to present breakthroughs in immunotherapy, early detection, and personalized cancer treatments.",
            "url": "https://globaloncologysummit2026.org",
            "source": "Medical Calendar"
        },
        {
            "title": "World Congress on Cardiology & Heart Health",
            "domain": "Medicine",
            "start_date": "2026-11-10",
            "end_date": "2026-11-13",
            "location": "Geneva, Switzerland",
            "description": "Focusing on cardiovascular disease prevention, surgical advancements, and the integration of digital health devices in patient rehabilitation.",
            "url": "https://worldcardiology2026.ch",
            "source": "Medical Calendar"
        },
        # Science
        {
            "title": "International Astrophysics Colloquium 2026",
            "domain": "Science",
            "start_date": "2026-10-18",
            "end_date": "2026-10-22",
            "location": "Tokyo, Japan",
            "description": "Exploring dark matter, deep-space imaging from next-gen space telescopes, and gravity wave signals from merging neutron stars.",
            "url": "https://astrophysics-colloquium2026.jp",
            "source": "Astro Science Feed"
        },
        {
            "title": "Quantum Physics and Computing Forum",
            "domain": "Science",
            "start_date": "2026-08-01",
            "end_date": "2026-08-04",
            "location": "Munich, Germany",
            "description": "Bridging theoretical quantum mechanics with scalable quantum computing architecture, cryptography, and materials science applications.",
            "url": "https://quantumforum2026.de",
            "source": "Physics Society"
        },
        # Finance
        {
            "title": "Global Fintech & Banking Summit 2026",
            "domain": "Finance",
            "start_date": "2026-06-22",
            "end_date": "2026-06-24",
            "location": "London, UK",
            "description": "Exploring open banking regulations, generative AI in financial services, fraud prevention, and the emergence of Central Bank Digital Currencies (CBDCs).",
            "url": "https://fintechbankingsummit.co.uk",
            "source": "Fintech Feed"
        },
        # Art
        {
            "title": "Biennale of Digital Art & Creative Technology",
            "domain": "Art",
            "start_date": "2026-05-15",
            "end_date": "2026-05-19",
            "location": "Paris, France",
            "description": "Showcasing interactive art installations, algorithmic designs, VR storytelling, and discussions on how AI tools are reshaping modern painting and sculpture.",
            "url": "https://digitalartbiennale.fr",
            "source": "Creative Art Hub"
        },
        
        # --- SUSPICIOUS LISTINGS (Red Flagged) ---
        {
            "title": "World Double-Your-Money & Web3 Crypto Fortune Summit",
            "domain": "Finance",
            "start_date": "2026-06-30",
            "end_date": "2026-07-01",
            "location": "Vague Hotel, London",
            "description": "Attend this exclusive secret event to double your crypto portfolio in 3 hours. Guaranteed double-your-money schemes shared by anonymous gurus. No registration fee but credit card to secure your entry slot is required.",
            "url": "http://crypto-fortune-secrets-2026.biz",
            "source": "Spam Web Crawl"
        },
        {
            "title": "Mega International Conference on Advanced Multi-Disciplinary Studies",
            "domain": "Science",
            "start_date": "2026-09-12",
            "end_date": "2026-09-13",
            "location": "Online / Vague Hotel, New York",
            "description": "Send your papers now! Guaranteed publication in Scopus journals within 48 hours for a small processing fee of $500. No peer review required. All domains accepted.",
            "url": "http://guaranteed-publication-studies.xyz",
            "source": "Academic Spam Feed"
        }
    ]

    confs.extend(mock_domains_confs)
    return confs


def run_scraping_cycle(db_path):
    """
    Main job that runs the scraping, executes AI evaluation, and inserts records into the database.
    """
    print(f"[Scrape Job] Starting scraping cycle at {datetime.now()}...")
    raw_confs = fetch_scraped_conferences()
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    new_count = 0
    flagged_count = 0
    
    for conf in raw_confs:
        title = conf["title"]
        url = conf["url"]
        
        # Check if conference already exists by checking the URL and title
        cursor.execute("SELECT id FROM conferences WHERE url = ? OR (title = ? AND start_date = ?)", (url, title, conf["start_date"]))
        exists = cursor.fetchone()
        
        if not exists:
            # Evaluate using AI/heuristics
            flagged, ai_reason = evaluate_conference_ai(
                title=title,
                url=url,
                location=conf["location"],
                description=conf["description"],
                domain=conf["domain"]
            )
            
            # If AI flags it, it starts as unverified (verified = 0) and flagged = 1
            # If AI passes it, it starts as unverified (verified = 0) and flagged = 0.
            # But it goes live on the index page immediately because it is clean.
            # (If admins want to officially vouch for a clean post, they can verify it, setting verified = 1).
            # If flagged = 1, it is HIDDEN from the main list until an admin approves it.
            verified = 0
            
            cursor.execute("""
                INSERT INTO conferences (
                    title, domain, start_date, end_date, location, description, 
                    url, source, verified, flagged, ai_reason, upvotes, downvotes, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?)
            """, (
                title, conf["domain"], conf["start_date"], conf["end_date"], 
                conf["location"], conf["description"], url, conf["source"],
                verified, 1 if flagged else 0, ai_reason, datetime.now().isoformat()
            ))
            
            new_count += 1
            if flagged:
                flagged_count += 1
                
    conn.commit()
    conn.close()
    
    print(f"[Scrape Job] Cycle completed. Added {new_count} new conferences. Flagged {flagged_count} for review.")
    return new_count, flagged_count
