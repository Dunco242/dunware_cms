from django.urls import path
from . import views

app_name = 'onboarding'

urlpatterns = [
    # Employee / Admin facing views
    path('dashboard/', views.OnboardingDashboardView.as_view(), name='dashboard'),
    path('plans/', views.OnboardingPlanListView.as_view(), name='plan_list'),
    path('plans/<int:pk>/', views.OnboardingPlanDetailView.as_view(), name='plan_detail'),

    # Customer onboarding management
    path('customer-onboardings/create/', views.CreateCustomerOnboardingView.as_view(), name='create_customer_onboarding'),
    path('customer-onboardings/create/<int:customer_id>/', views.CreateCustomerOnboardingView.as_view(), name='create_customer_onboarding_for_customer'),
    path('customer-onboardings/<int:pk>/', views.CustomerOnboardingDetailView.as_view(), name='customer_onboarding_detail'),

    # Step management
    path('customer-onboardings/<int:onboarding_id>/step/<int:step_id>/', views.StepDetailView.as_view(), name='step_detail'),
    path('customer-onboardings/<int:onboarding_id>/step/<int:step_id>/import/', views.submit_import_job, name='submit_import_job'),

    # Data import tools
    path('import-template/<str:import_type>/', views.generate_import_template, name='generate_import_template'),

    # Feedback
    path('feedback/create/<int:onboarding_id>/', views.SubmitFeedbackView.as_view(), name='submit_feedback'),
    path('feedback/create/<int:onboarding_id>/step/<int:step_id>/', views.SubmitFeedbackView.as_view(), name='submit_step_feedback'),

    # Analytics
    path('analytics/', views.OnboardingAnalyticsView.as_view(), name='analytics'),

    # Customer-facing views
    path('welcome/', views.WelcomeView.as_view(), name='welcome'),
    path('progress/', views.CustomerDashboardView.as_view(), name='customer_dashboard'),
    path('step/<int:step_id>/', views.CustomerOnboardingStepView.as_view(), name='customer_step'),
]
