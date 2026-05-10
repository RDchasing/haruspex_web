from django.urls import path

from . import views


app_name = "analysis"

urlpatterns = [
    path("", views.index, name="index"),
    path("jobs/", views.create_job, name="create_job"),
    path("jobs/<uuid:job_id>/", views.job_detail, name="job_detail"),
    path("jobs/<uuid:job_id>/status/", views.job_status, name="job_status"),
    path("jobs/<uuid:job_id>/download/", views.download_result, name="download_result"),
]
