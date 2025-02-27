
# Python Standard Library
import os
import csv
import logging
import tempfile
import json
import email
import uuid
import time
import traceback
import imaplib
import smtplib
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from core.utils import send_email_message
from email.mime.multipart import MIMEMultipart
from io import BytesIO
from datetime import datetime, timedelta
from django.utils.timezone import now
from decimal import Decimal
from core.mixins import EmployeeRequiredMixin



# Django Core
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction, models
from django.contrib.contenttypes.models import ContentType

from core.services.scheduling import SchedulingService
from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse, HttpResponseRedirect
from django.urls import reverse_lazy, reverse
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.utils.timezone import make_aware
from django.db.models import Q, Sum, Count, Max, Prefetch, Subquery, OuterRef, F
from django.db.models.functions import TruncDate
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import update_session_auth_hash
from django.core.paginator import Paginator
from django.template.loader import render_to_string
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.csrf import csrf_protect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.utils.decorators import method_decorator
from .utils import get_privacy_policy_content
from core.services.scheduling import SchedulingService
from django.contrib.auth.models import User

# Django Class-Based Views
from django.views.generic import (
    ListView, DetailView, CreateView, UpdateView, DeleteView, TemplateView
)
from django.views.generic.edit import FormView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin, PermissionRequiredMixin

# Third-Party Libraries
import pytz
from dateutil.parser import parse
from weasyprint import HTML
from zoomus import ZoomClient
from icalendar import Calendar
from googleapiclient.discovery import build

# Forms
from django.contrib.auth.forms import PasswordChangeForm
from .forms import (
    UserRegistrationForm,
    EmployeeForm,
    CustomerForm,
    LeadForm,
    ServiceForm,
    NoteForm,
    TaskForm,
    MeetingForm,
    MeetingSearchForm,
    TaskSearchForm,
    InvoiceForm,
    PaymentForm,
    SubscriptionForm,
    ServiceSubscriptionForm,
    ICSUploadForm,  # If this is a form
    EventForm,
    ScheduleRuleForm,
    EmailComposeForm,
    EmailAccountForm
)

# Models
from .models import (
    Employee,
    Customer,
    Lead,
    Service,
    Note,
    Task,
    Meeting,
    Invoice,
    Payment,
    Subscription,
    Transaction,
    ServiceSubscription,
    UploadedICSFile,  # If this is a model
    Event,
    IPAccess,
    PrivacyPolicyAcceptance,
    ScheduleRule,
    ChatMessage,
    ChatSession,
    EmailAccount,
    EmailMessage,
    EmailTemplate,
    EmailAttachment,
    EmailFolder,
    EmailFolderMessage,
    EmailTracker,
    EmailProvider
)

from customer_projects.models import (
    Project,
    ProjectPhase,
    ProjectTask,
    ProjectComment,
    TimeEntry
)
