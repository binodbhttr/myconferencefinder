import os
import hashlib
import json
from datetime import datetime
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.core.management import call_command
from django.conf import settings
from .models import Conference, Vote

def get_hashed_ip(request):
    """Generates a stable, GDPR-compliant SHA-256 hash of the voter's IP address."""
    # Handle forwarding headers if behind a proxy
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    
    # Anonymizing Salt
    salt = "conferenza_voter_salt_98765"
    return hashlib.sha256((ip + salt).encode('utf-8')).hexdigest()


# --- HTML PAGE VIEWS ---

def index_page(request):
    """Renders the main directory index page."""
    return render(request, 'conferences/index.html')


def admin_page(request):
    """Renders the admin review dashboard page."""
    return render(request, 'conferences/admin.html')


# --- REST API VIEWS ---

def get_conferences(request):
    """
    Lists clean conferences (flagged=False).
    Supports GET parameters: 'domain' and 'search'.
    Includes 'user_vote' if 'X-Device-ID' header is supplied.
    """
    domain = request.GET.get('domain', 'All').strip()
    search = request.GET.get('search', '').strip()
    device_id = request.headers.get('X-Device-ID', '').strip()
    ip_hash = get_hashed_ip(request)

    # Fetch user's existing votes
    user_votes = {}
    
    # Let's import Q locally or globally. Let's do it in the code.
    from django.db.models import Q
    if device_id:
        votes = Vote.objects.filter(Q(device_id=device_id) | Q(ip_hash=ip_hash))
        user_votes = {v.conference_id: v.vote_type for v in votes}

    confs = Conference.objects.filter(flagged=False)
    
    if domain != "All":
        confs = confs.filter(domain=domain)
        
    if search:
        confs = confs.filter(
            Q(title__icontains=search) | 
            Q(description__icontains=search) | 
            Q(location__icontains=search)
        )
        
    # Order: verified first, then upvotes desc, then start_date asc
    confs = confs.order_by('-verified', '-upvotes', 'start_date')

    data = []
    for c in confs:
        # Convert start/end date to ISO string safely
        start_str = c.start_date.strftime("%Y-%m-%d") if c.start_date else ""
        end_str = c.end_date.strftime("%Y-%m-%d") if c.end_date else ""
        
        data.append({
            "id": c.id,
            "title": c.title,
            "domain": c.domain,
            "start_date": start_str,
            "end_date": end_str,
            "location": c.location,
            "description": c.description,
            "url": c.url,
            "source": c.source,
            "verified": 1 if c.verified else 0,
            "flagged": 1 if c.flagged else 0,
            "ai_reason": c.ai_reason,
            "upvotes": c.upvotes,
            "downvotes": c.downvotes,
            "user_vote": user_votes.get(c.id, None)
        })

    return JsonResponse(data, safe=False)


@csrf_exempt
def vote_conference(request, conf_id):
    """
    Submits, toggles, or retracts a vote on a conference card.
    Requires JSON: {"type": "up" | "down"} and X-Device-ID header.
    """
    if request.method != 'POST':
        return JsonResponse({"error": "Only POST requests allowed"}, status=405)

    device_id = request.headers.get('X-Device-ID', '').strip()
    if not device_id:
        return JsonResponse({"error": "Missing client identifier (X-Device-ID header)"}, status=400)

    try:
        body = json.loads(request.body)
        vote_type = body.get('type')
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({"error": "Invalid JSON payload"}, status=400)

    if vote_type not in ['up', 'down']:
        return JsonResponse({"error": "Vote type must be 'up' or 'down'"}, status=400)

    try:
        conference = Conference.objects.get(id=conf_id)
    except Conference.DoesNotExist:
        return JsonResponse({"error": "Conference not found"}, status=404)

    ip_hash = get_hashed_ip(request)
    
    # Check for existing vote by this device OR IP
    from django.db.models import Q
    existing_vote = Vote.objects.filter(
        Q(conference=conference) & (Q(device_id=device_id) | Q(ip_hash=ip_hash))
    ).first()

    action = None
    user_vote = None

    if not existing_vote:
        # Create new vote log
        Vote.objects.create(
            conference=conference,
            device_id=device_id,
            ip_hash=ip_hash,
            vote_type=vote_type
        )
        # Update counter
        if vote_type == 'up':
            conference.upvotes += 1
        else:
            conference.downvotes += 1
        conference.save()
        action = "added"
        user_vote = vote_type
    else:
        if existing_vote.vote_type == vote_type:
            # Retract vote
            existing_vote.delete()
            if vote_type == 'up':
                conference.upvotes -= 1
            else:
                conference.downvotes -= 1
            conference.save()
            action = "retracted"
            user_vote = None
        else:
            # Toggle vote
            existing_vote.vote_type = vote_type
            existing_vote.device_id = device_id
            existing_vote.ip_hash = ip_hash
            existing_vote.save()
            
            # Recalculate counters
            if vote_type == 'up':
                conference.upvotes += 1
                conference.downvotes -= 1
            else:
                conference.upvotes -= 1
                conference.downvotes += 1
            conference.save()
            action = "toggled"
            user_vote = vote_type

    return JsonResponse({
        "success": True,
        "action": action,
        "upvotes": conference.upvotes,
        "downvotes": conference.downvotes,
        "user_vote": user_vote
    })


# --- ADMIN REST VIEWS ---

def get_flagged_conferences(request):
    """Fetches flagged conferences that need review."""
    confs = Conference.objects.filter(flagged=True).order_by('-created_at')
    
    data_list = []
    for c in confs:
        start_str = c.start_date.strftime("%Y-%m-%d") if c.start_date else ""
        end_str = c.end_date.strftime("%Y-%m-%d") if c.end_date else ""
        data_list.append({
            "id": c.id,
            "title": c.title,
            "domain": c.domain,
            "start_date": start_str,
            "end_date": end_str,
            "location": c.location,
            "description": c.description,
            "url": c.url,
            "source": c.source,
            "verified": 1 if c.verified else 0,
            "flagged": 1 if c.flagged else 0,
            "ai_reason": c.ai_reason,
            "upvotes": c.upvotes,
            "downvotes": c.downvotes
        })
        
    # Check if Gemini API key is active
    gemini_active = bool(settings.get("GEMINI_API_KEY", os.environ.get("GEMINI_API_KEY"))) if hasattr(settings, "GEMINI_API_KEY") else bool(os.environ.get("GEMINI_API_KEY"))

    return JsonResponse({
        "conferences": data_list,
        "gemini_active": gemini_active
    })


@csrf_exempt
def approve_conference(request, conf_id):
    """Approves a flagged conference, marking it verified and clean."""
    if request.method != 'POST':
        return JsonResponse({"error": "Only POST allowed"}, status=405)
        
    try:
        c = Conference.objects.get(id=conf_id)
        c.verified = True
        c.flagged = False
        c.save()
        return JsonResponse({"success": True, "message": "Conference approved and verified."})
    except Conference.DoesNotExist:
        return JsonResponse({"error": "Conference not found"}, status=404)


@csrf_exempt
def reject_conference(request, conf_id):
    """Rejects a flagged conference, deleting it completely."""
    if request.method != 'POST':
        return JsonResponse({"error": "Only POST allowed"}, status=405)
        
    try:
        c = Conference.objects.get(id=conf_id)
        c.delete()
        return JsonResponse({"success": True, "message": "Conference rejected and deleted."})
    except Conference.DoesNotExist:
        return JsonResponse({"error": "Conference not found"}, status=404)


@csrf_exempt
def trigger_scrape(request):
    """Runs the scraping command in a separate thread context and returns count outcomes."""
    if request.method != 'POST':
        return JsonResponse({"error": "Only POST allowed"}, status=405)
        
    try:
        # call_command returns the output of the command handle
        res = call_command('run_scraper')
        new_c, flagged_c = map(int, res.split(','))
        return JsonResponse({
            "success": True,
            "new_count": new_c,
            "flagged_count": flagged_c
        })
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)
