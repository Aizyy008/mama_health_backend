from django.urls import path

from apps.reports.views import AdminStatsView, PatientSummaryReportView, SearchView

urlpatterns = [
    path("patient-summary/", PatientSummaryReportView.as_view(), name="report-patient-summary"),
    path("admin/stats/", AdminStatsView.as_view(), name="report-admin-stats"),
    path("search/", SearchView.as_view(), name="report-search"),
]
