from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
from .models import Service, Customer, Lead, Invoice, Payment

class BaseTest(TestCase):
    """Base test class to handle common setup"""
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_superuser(
            username='testadmin',
            email='admin@test.com',
            password='adminpass123'
        )
        self.client.login(username='testadmin', password='adminpass123')

class ServiceTest(BaseTest):
    def test_service_creation(self):
        response = self.client.post(reverse('service-create'), {
            'name': 'Test Service',
            'description': 'Test Description',
            'price': '100.00',
            'is_active': True
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Service.objects.filter(name='Test Service').exists())

    def test_service_list(self):
        Service.objects.create(
            name='Test Service',
            description='Test Description',
            price='100.00'
        )
        response = self.client.get(reverse('service-list'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'core/service_list.html')

class CustomerTest(BaseTest):
    def test_customer_creation(self):
        response = self.client.post(reverse('customer-create'), {
            'company_name': 'Test Company',
            'contact_person': 'John Doe',
            'email': 'john@testcompany.com',
            'phone': '1234567890',
            'address': 'Test Address',
            'city': 'Test City',
            'state': 'Test State',
            'zip_code': '12345',
            'status': 'active'
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Customer.objects.filter(company_name='Test Company').exists())

    def test_customer_list(self):
        Customer.objects.create(
            company_name='Test Company',
            contact_person='John Doe',
            email='john@testcompany.com',
            phone='1234567890',
            address='Test Address',
            city='Test City',
            state='Test State',
            zip_code='12345'
        )
        response = self.client.get(reverse('customer-list'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'core/customer_list.html')

class LeadTest(BaseTest):
    def test_lead_creation(self):
        response = self.client.post(reverse('lead-create'), {
            'company_name': 'Lead Company',
            'contact_person': 'Jane Doe',
            'email': 'jane@leadcompany.com',
            'phone': '0987654321',
            'source': 'website',
            'status': 'new'
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Lead.objects.filter(company_name='Lead Company').exists())

    def test_lead_list(self):
        Lead.objects.create(
            company_name='Lead Company',
            contact_person='Jane Doe',
            email='jane@leadcompany.com',
            phone='0987654321',
            source='website',
            status='new'
        )
        response = self.client.get(reverse('lead-list'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'core/lead_list.html')

class BillingTest(BaseTest):
    def setUp(self):
        super().setUp()
        self.customer = Customer.objects.create(
            company_name='Billing Test Company',
            contact_person='Bill Test',
            email='bill@test.com',
            phone='1234567890',
            address='Test Address',
            city='Test City',
            state='Test State',
            zip_code='12345'
        )

    def test_invoice_creation(self):
        invoice_data = {
            'customer': self.customer.id,
            'invoice_number': f'INV-{timezone.now().strftime("%Y%m%d")}-001',
            'issue_date': timezone.now().date(),
            'due_date': timezone.now().date() + timedelta(days=30),
            'total_amount': '100.00',
            'status': 'pending'
        }
        response = self.client.post(reverse('invoice-create'), invoice_data)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Invoice.objects.filter(customer=self.customer).exists())

    def test_payment_creation(self):
        invoice = Invoice.objects.create(
            customer=self.customer,
            invoice_number=f'INV-{timezone.now().strftime("%Y%m%d")}-001',
            issue_date=timezone.now().date(),
            due_date=timezone.now().date() + timedelta(days=30),
            total_amount='100.00',
            status='pending'
        )

        payment_data = {
            'customer': self.customer.id,
            'invoice': invoice.id,
            'amount': '100.00',
            'status': 'completed'
        }
        response = self.client.post(reverse('payment-create'), payment_data)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Payment.objects.filter(invoice=invoice).exists())
