from django.db import models

class Conference(models.Model):
    title = models.CharField(max_length=255)
    domain = models.CharField(max_length=100)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    location = models.CharField(max_length=255, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    url = models.URLField(max_length=500, null=True, blank=True)
    source = models.CharField(max_length=100, null=True, blank=True)
    verified = models.BooleanField(default=False)
    flagged = models.BooleanField(default=False)
    ai_reason = models.TextField(null=True, blank=True)
    upvotes = models.IntegerField(default=0)
    downvotes = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class Vote(models.Model):
    VOTE_CHOICES = [
        ('up', 'Up'),
        ('down', 'Down'),
    ]
    conference = models.ForeignKey(Conference, on_delete=models.CASCADE, related_name='votes')
    device_id = models.CharField(max_length=255)
    ip_hash = models.CharField(max_length=255)
    vote_type = models.CharField(max_length=10, choices=VOTE_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['conference', 'device_id'], name='unique_conference_device'),
            models.UniqueConstraint(fields=['conference', 'ip_hash'], name='unique_conference_ip'),
        ]

    def __str__(self):
        return f"{self.vote_type} vote on {self.conference.title} by {self.device_id[:8]}"
