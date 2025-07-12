from pyexpat import features
from django.db import models
from django.contrib.auth.models import AbstractUser, Group, Permission
from django.utils import timezone

# ---------------------
# Feature
# ---------------------
class Feature(models.Model):
    code = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=100)


    def __str__(self):
        return self.name

# ---------------------
# Role Model
# ---------------------
class Role(models.Model):
    name = models.CharField(max_length=100)
    features = models.ManyToManyField(Feature, blank=True)
    business = models.ForeignKey('Business', on_delete=models.CASCADE, related_name='roles')

    def __str__(self):
        return self.name

# ---------------------
# User & Employee
# ---------------------
class User(AbstractUser):
    role = models.ForeignKey(Role, on_delete=models.SET_NULL, null=True, blank=True)
    business = models.ForeignKey('Business', on_delete=models.CASCADE, null=True, blank=True)
    groups = models.ManyToManyField(
        Group,
        related_name='salon_users',
        blank=True,
        help_text='The groups this user belongs to.',
        verbose_name='groups',
    )
    user_permissions = models.ManyToManyField(
        Permission,
        related_name='salon_users_permissions',
        blank=True,
        help_text='Specific permissions for this user.',
        verbose_name='user permissions',
    )

    def __str__(self):
        return self.get_full_name() or self.username

    def is_admin(self):
        return self.role and (self.role.name == 'Admin' or self.id == User.objects.order_by('id').first().id)

class Employee(models.Model):
    business = models.ForeignKey('Business', on_delete=models.CASCADE)
    branch = models.ForeignKey('Branch', on_delete=models.CASCADE)
    user = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, blank=True)
    name = models.CharField(max_length=100, blank=True)
    position = models.ForeignKey('Position', on_delete=models.SET_NULL, null=True, blank=True)
    performance_score = models.FloatField(default=0)

    def __str__(self):
        return self.name or (self.user.get_full_name() if self.user else "Unnamed Employee")

# ---------------------
# Business & Branch
# ---------------------
class Business(models.Model):
    name = models.CharField(max_length=255)
    address = models.CharField(max_length=255, blank=True)
    standard_haircut_points = models.FloatField(default=1, help_text="Points awarded per completed haircut for all employees")
    loyalty_point_value = models.DecimalField(max_digits=10, decimal_places=2, default=10.00, help_text="Monetary value of one customer loyalty point in UGX")
    def __str__(self):
        return self.name

class Branch(models.Model):
    business = models.ForeignKey(Business, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    address = models.TextField()
    phone = models.CharField(max_length=15)

    def __str__(self):
        return f"{self.name} ({self.business.name})"

# ---------------------
# Customer
# ---------------------
class Customer(models.Model):
    GENDER_CHOICES = [
        ('MALE', 'Male'),
        ('FEMALE', 'Female'),
    ]
    business = models.ForeignKey(Business, on_delete=models.CASCADE)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_customers')
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=15)
    email = models.EmailField(blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    gender = models.CharField(max_length=6, choices=GENDER_CHOICES, default='MALE')
    preferences = models.TextField(blank=True, null=True)
    join_date = models.DateField(auto_now_add=True)
    loyalty_points = models.FloatField(default=0)

    def __str__(self):
        return self.name

# ---------------------
# Service
# ---------------------
class Service(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name

# ---------------------
# Service Points
# ---------------------
class ServicePoints(models.Model):
    service = models.ForeignKey(Service, on_delete=models.CASCADE)
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE)
    business = models.ForeignKey(Business, on_delete=models.CASCADE)
    loyalty_points = models.FloatField(default=0, help_text="Loyalty points awarded to customer for this service")

    class Meta:
        unique_together = ('service', 'branch', 'business')

    def __str__(self):
        return f"{self.service.name} - {self.loyalty_points} points ({self.branch.name})"

# ---------------------
# Appointment
# ---------------------
class Appointment(models.Model):
    customer = models.ForeignKey('Customer', on_delete=models.CASCADE)
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE)
    service = models.ForeignKey('Service', on_delete=models.CASCADE)
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    date_time = models.DateTimeField()
    status = models.CharField(max_length=20, choices=[('BOOKED', 'Booked'), ('COMPLETED', 'Completed'), ('CANCELLED', 'Cancelled')], default='BOOKED')
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        was_completed = not is_new and Appointment.objects.get(pk=self.pk).status == 'COMPLETED'
        super().save(*args, **kwargs)
        if self.status == 'COMPLETED' and (is_new or not was_completed):
            # Award customer loyalty points
            service_points = ServicePoints.objects.filter(
                service=self.service, branch=self.branch, business=self.employee.business
            ).first()
            if service_points:
                # Convert Decimal to float before adding
                self.customer.loyalty_points += float(service_points.loyalty_points)
                self.customer.save()
            # Award employee performance points for haircut
            if self.service.name.lower().find('haircut') != -1:
                points = self.employee.business.standard_haircut_points
                self.employee.performance_score += points
                self.employee.save()

    def __str__(self):
        return f"{self.customer.name} - {self.service.name} on {self.date_time.strftime('%Y-%m-%d %H:%M')}"

# ---------------------
# Coupon
# ---------------------
class Coupon(models.Model):
    code = models.CharField(max_length=20, unique=True)
    discount_percent = models.PositiveIntegerField()
    min_spend = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    expiry_date = models.DateField()
    applicable_services = models.ManyToManyField(Service, blank=True)

    def __str__(self):
        return self.code

# ---------------------
# Payment
# ---------------------
class Payment(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, null=True, blank=True)
    appointment = models.OneToOneField('Appointment', null=True, blank=True, on_delete=models.SET_NULL)
    additional_services = models.ManyToManyField(Service, blank=True, related_name='additional_payments')
    products = models.ManyToManyField('Product', blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    method = models.CharField(max_length=20, choices=[
        ('CASH', 'Cash'), ('MOBILE_MONEY', 'Mobile Money'), ('CARD', 'Card')
    ])
    timestamp = models.DateTimeField(auto_now_add=True)
    coupon = models.ForeignKey(Coupon, null=True, blank=True, on_delete=models.SET_NULL)
    used_loyalty_points = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.customer.name if self.customer else 'No Customer'} - {self.amount} {self.method}"

# ---------------------
# Expense
# ---------------------
class Expense(models.Model):
    CATEGORY_CHOICES = [
        ('UTILITIES', 'Utilities'),
        ('WAGES', 'Staff Wages'),
        ('PRODUCTS', 'Product Purchases'),
        ('OTHER', 'Other'),
    ]
    branch = models.ForeignKey('Branch', on_delete=models.CASCADE)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField(blank=True, null=True)
    date = models.DateField()

    def __str__(self):
        return f"{self.category} - {self.amount} on {self.date}"

# ---------------------
# Payroll
# ---------------------
class Payroll(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    month = models.DateField()
    breakdown = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.employee} - {self.month.strftime('%B %Y')}"

# ---------------------
# Messaging Log
# ---------------------
class MessageLog(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    message = models.TextField()
    channel = models.CharField(max_length=10, choices=[('SMS', 'SMS'), ('EMAIL', 'Email')])
    status = models.CharField(max_length=10, choices=[('SENT', 'Sent'), ('FAILED', 'Failed')], default='SENT')
    sent_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.customer.name} - {self.channel} at {self.sent_at.strftime('%Y-%m-%d %H:%M')}"

# ---------------------
# System Settings
# ---------------------
class SystemSetting(models.Model):
    key = models.CharField(max_length=100, unique=True)
    value = models.TextField()
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.key

# ---------------------
# Report Log
# ---------------------
class ReportLog(models.Model):
    report_type = models.CharField(max_length=50)
    generated_by = models.ForeignKey(User, on_delete=models.CASCADE)
    generated_at = models.DateTimeField(auto_now_add=True)
    export_format = models.CharField(max_length=10, choices=[('PDF', 'PDF'), ('EXCEL', 'Excel')])
    filters_applied = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.report_type} by {self.generated_by} on {self.generated_at.strftime('%Y-%m-%d')}"

class Message(models.Model):
    customer = models.ForeignKey('Customer', on_delete=models.CASCADE)
    appointment = models.ForeignKey('Appointment', on_delete=models.CASCADE, null=True, blank=True)
    message_type = models.CharField(max_length=20, choices=[('reminder', 'Reminder'), ('promo', 'Promotion')])
    sent_at = models.DateTimeField(default=timezone.now)
    method = models.CharField(max_length=10, choices=[('email', 'Email'), ('sms', 'SMS')])
    content = models.TextField()

    def __str__(self):
        return f"{self.customer.name} - {self.message_type} at {self.sent_at.strftime('%Y-%m-%d %H:%M')}"

class Promotion(models.Model):
    subject = models.CharField(max_length=255)
    message = models.TextField()
    sms_message = models.CharField(max_length=160, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sent = models.BooleanField(default=False)

    def __str__(self):
        return self.subject

# ---------------------
# Position
# ---------------------
class Position(models.Model):
    name = models.CharField(max_length=100)
    business = models.ForeignKey('Business', on_delete=models.CASCADE)

    def __str__(self):
        return self.name
    
class Product(models.Model):
    business = models.ForeignKey(Business, on_delete=models.CASCADE)
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    stock_quantity = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    sku = models.CharField(max_length=50, blank=True, null=True)

    def __str__(self):
        return self.name
    
class ServicePoints(models.Model):
    service = models.ForeignKey(Service, on_delete=models.CASCADE)
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE)
    business = models.ForeignKey(Business, on_delete=models.CASCADE)
    loyalty_points = models.DecimalField(max_digits=10, decimal_places=1, help_text="Customer loyalty points awarded for this service at this branch")
    employee_points = models.FloatField(default=1, help_text="Employee performance points awarded for this service at this branch")
    
    def __str__(self):
        return f"{self.service.name} - {self.branch.name} - {self.loyalty_points} customer points, {self.employee_points} employee points"