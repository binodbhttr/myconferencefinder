from django.contrib import admin
from .models import Conference, Vote

@admin.register(Conference)
class ConferenceAdmin(admin.ModelAdmin):
    list_display = ('title', 'domain', 'start_date', 'location', 'verified', 'flagged', 'upvotes', 'downvotes')
    list_filter = ('domain', 'verified', 'flagged')
    search_fields = ('title', 'description', 'location')
    ordering = ('start_date',)

@admin.register(Vote)
class VoteAdmin(admin.ModelAdmin):
    list_display = ('conference', 'vote_type', 'device_id', 'ip_hash', 'created_at')
    list_filter = ('vote_type',)
    search_fields = ('conference__title', 'device_id', 'ip_hash')
