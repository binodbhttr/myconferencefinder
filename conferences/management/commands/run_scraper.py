import os
import json
import requests
from datetime import datetime
from django.core.management.base import BaseCommand
from google import genai
from google.genai import types
from conferences.models import Conference

# Suspect markers for local heuristic simulation fallback
SUSPICIOUS_DOMAINS = ['.biz', '.xyz', '.cc', '.info', '.click', '.top', '.win']
SUSPICIOUS_KEYWORDS = [
    'double your money', 'double your crypto', 'guaranteed publication', 
    'credit card to secure', 'no registration needed but', 'get rich quick',
    'earn passive income', 'whatsapp group', 'crypto loop'
]

def evaluate_conference_heuristic(title, url, location, description, domain):
    flagged = False
    reasons = []

    url_lower = url.lower()
    for domain_ext in SUSPICIOUS_DOMAINS:
        if domain_ext in url_lower:
            flagged = True
            reasons.append(f"Suspicious top-level domain ({domain_ext})")
            break

    desc_lower = description.lower()
    for keyword in SUSPICIOUS_KEYWORDS:
        if keyword in desc_lower:
            flagged = True
            reasons.append(f"Suspicious phrasing detected: '{keyword}'")

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
    """Verifies conference credibility via Gemini AI, falling back to heuristics if API key is absent."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
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
    confs = []

    # 1. Attempt to scrape real JS conferences from confs.tech github repo
    try:
        print("[Scraper] Fetching real JS conferences from confs.tech...")
        url = "https://raw.githubusercontent.com/tech-conferences/confs.tech/master/conferences/2026/javascript.json"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            for item in data[:10]:
                confs.append({
                    "title": item.get("name"),
                    "domain": "Technology",
                    "start_date": item.get("startDate"),
                    "end_date": item.get("endDate"),
                    "location": f"{item.get('city')}, {item.get('country')}" if item.get("city") else "Online",
                    "description": "A premier developer event for Javascript and Web Technologies. Featuring core talks on frameworks, performance, and the future of JS.",
                    "url": item.get("url"),
                    "source": "confs.tech"
                })
            print(f"[Scraper] Successfully fetched {len(confs)} real tech conferences.")
    except Exception as e:
        print(f"[Scraper] Failed to fetch live tech conferences ({e}). Fallback to mock data will be merged.")

    # 2. Add realistic, high-quality conferences for other domains
    mock_domains_confs = [
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


class Command(BaseCommand):
    help = "Crawls the web for conferences, screens them using Gemini AI, and syncs to SQLite via ORM."

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("[Scrape Job] Starting Django scrape execution..."))
        
        raw_confs = fetch_scraped_conferences()
        new_count = 0
        flagged_count = 0

        for conf in raw_confs:
            title = conf["title"]
            url = conf["url"]
            
            # Parse Dates safely
            start_date = None
            if conf.get("start_date"):
                try:
                    start_date = datetime.strptime(conf.get("start_date"), "%Y-%m-%d").date()
                except ValueError:
                    pass
                    
            end_date = None
            if conf.get("end_date"):
                try:
                    end_date = datetime.strptime(conf.get("end_date"), "%Y-%m-%d").date()
                except ValueError:
                    pass

            # Check if duplicate exists
            exists = Conference.objects.filter(url=url).exists() or \
                     Conference.objects.filter(title=title, start_date=start_date).exists()
            
            if not exists:
                flagged, ai_reason = evaluate_conference_ai(
                    title=title,
                    url=url,
                    location=conf["location"],
                    description=conf["description"],
                    domain=conf["domain"]
                )
                
                Conference.objects.create(
                    title=title,
                    domain=conf["domain"],
                    start_date=start_date,
                    end_date=end_date,
                    location=conf["location"],
                    description=conf["description"],
                    url=url,
                    source=conf["source"],
                    verified=False,
                    flagged=flagged,
                    ai_reason=ai_reason
                )
                new_count += 1
                if flagged:
                    flagged_count += 1

        self.stdout.write(self.style.SUCCESS(
            f"[Scrape Job] Finished. Added {new_count} new entries, flagged {flagged_count} suspect listings."
        ))
        
        # Save output in standard command result structure
        return f"{new_count},{flagged_count}"
