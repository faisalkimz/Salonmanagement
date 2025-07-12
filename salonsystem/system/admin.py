from django.contrib import admin
from .models import (
    User, Employee, Business, Branch, Customer, Service, Appointment,
    Coupon, Payment, Expense, Payroll, MessageLog, SystemSetting, ReportLog
)

admin.site.register(User)
admin.site.register(Employee)
admin.site.register(Business)
admin.site.register(Branch)
admin.site.register(Customer)
admin.site.register(Service)
admin.site.register(Appointment)
admin.site.register(Coupon)
admin.site.register(Payment)
admin.site.register(Expense)
admin.site.register(Payroll)
admin.site.register(MessageLog)
admin.site.register(SystemSetting)
admin.site.register(ReportLog)
