from django.urls import path
from . import views

urlpatterns = [
    # Pages
    path('', views.index_page, name='index'),
    path('admin', views.admin_page, name='admin'), # Custom dashboard URL
    path('admin/', views.admin_page, name='admin_slash'),
    
    # REST API Endpoints
    path('api/conferences', views.get_conferences, name='api_conferences'),
    path('api/conferences/<int:conf_id>/vote', views.vote_conference, name='api_vote'),
    path('api/admin/flagged', views.get_flagged_conferences, name='api_admin_flagged'),
    path('api/admin/approve/<int:conf_id>', views.approve_conference, name='api_admin_approve'),
    path('api/admin/reject/<int:conf_id>', views.reject_conference, name='api_admin_reject'),
    path('api/admin/trigger-scrape', views.trigger_scrape, name='api_admin_trigger_scrape'),
]
