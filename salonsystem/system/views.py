from decimal import Decimal
import json
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.shortcuts import render, redirect, get_object_or_404
from .models import Coupon, Customer, Appointment, Payment, Position, Product, Service, Employee, Expense, Branch, Payroll, Promotion, Role, Business, ServicePoints, User, Feature
from .forms import BranchForm, CouponForm, CustomerForm, PaymentForm, PositionForm, ProductForm, ServiceForm, AppointmentForm, EmployeeForm, ExpenseForm, PayrollForm, RevenueFilterForm, PromotionForm, ServicePointsForm, UserCreationForm, BusinessForm, AdminCreationForm, RoleForm, BusinessHaircutPointsForm
from django.db.models import Sum, Count, Q
from django.utils.timezone import now
from datetime import timedelta
from django.contrib.auth import logout
from django.template.loader import render_to_string
from openpyxl import Workbook
from django.http import HttpResponse, JsonResponse
import datetime
from xhtml2pdf import pisa
from django.contrib import messages
from django.utils import timezone
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponseRedirect
from django.urls import reverse
from .tasks import send_reminders, send_promotional_message
from django.contrib.auth import authenticate, login
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.models import Permission
from functools import wraps

def feature_required(feature_code):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if request.user.is_superuser or request.user.is_admin():
                return view_func(request, *args, **kwargs)
            if request.user.role and request.user.role.features.filter(code=feature_code).exists():
                return view_func(request, *args, **kwargs)
            messages.error(request, "You do not have permission to access this feature.")
            return redirect('dashboard')
        return _wrapped_view
    return decorator
def customer_list(request):
    customers = Customer.objects.filter(business=request.user.business)

    query = request.GET.get('q')
    if query:
        customers = customers.filter(
            Q(name__icontains=query) |
            Q(phone__icontains=query) |
            Q(email__icontains=query)
        )

    for customer in customers:
        customer.total_visits = Appointment.objects.filter(customer=customer).count()
        customer.total_spent = Payment.objects.filter(customer=customer).aggregate(total=Sum('amount'))['total'] or 0

    return render(request, 'system/customer_list.html', {'customers': customers, 'query': query})


@feature_required('add_customer')
def add_customer(request):
    if not request.user.business:
        messages.error(request, "You are not assigned to a business. Contact an admin.")
        return redirect('dashboard')

    if request.method == 'POST':
        print("POST DATA:", request.POST)  # Debug POST data
        form = CustomerForm(request.POST, user=request.user)
        if form.is_valid():
            customer = form.save(commit=False)
            customer.business = request.user.business  # Ensure business is set
            customer.save()
            messages.success(request, "Customer added successfully.")
            return redirect('add_customer')
        else:
            messages.error(request, "Please correct the errors below.")
            print("FORM ERRORS:", form.errors)
    else:
        form = CustomerForm(user=request.user)

    query = request.GET.get('q')
    customers = Customer.objects.filter(business=request.user.business) if request.user.business else Customer.objects.none()
    if query:
        customers = customers.filter(
            Q(name__icontains=query) |
            Q(phone__icontains=query) |
            Q(email__icontains=query)
        )

    for customer in customers:
        customer.total_visits = Appointment.objects.filter(customer=customer).count()
        customer.total_spent = Payment.objects.filter(customer=customer).aggregate(total=Sum('amount'))['total'] or 0

    return render(request, 'system/add_customer.html', {
        'form': form,
        'customers': customers,
        'query': query,
    })
def dashboard(request):
    user = request.user
    # If superuser and no business exists, start onboarding
    from .models import Business, User
    if user.is_superuser and not Business.objects.exists():
        return redirect('onboarding')
    # If not superuser, but no business or admin exists, block access or show message
    if not user.is_superuser and (not user.business or not user.role):
        messages.error(request, "You do not have access to the dashboard. Contact admin.")
        return redirect('login')

    branch_id = request.GET.get('branch')

    # Restrict non-superusers to their branch
    if not request.user.is_superuser:
        if hasattr(request.user, 'employee'):
            branch_id = request.user.employee.branch_id
        else:
            branch_id = None  # Or handle as needed

    if branch_id:
        customers = Customer.objects.filter(branch_id=branch_id)
        appointments_today = Appointment.objects.filter(branch_id=branch_id, date_time__date=now().date()).count()
        total_revenue = Payment.objects.filter(appointment__branch_id=branch_id).aggregate(total=Sum('amount'))['total'] or 0
    else:
        customers = Customer.objects.all()
        appointments_today = Appointment.objects.filter(date_time__date=now().date()).count()
        total_revenue = Payment.objects.aggregate(total=Sum('amount'))['total'] or 0

    total_customers = customers.count()
    top_service = Service.objects.annotate(
        total_used=Count('appointment')
    ).order_by('-total_used').first()
    recent_appointments = Appointment.objects.select_related(
        'customer', 'service', 'employee', 'employee__user'
    ).order_by('-date_time')[:5]


    promotions = Promotion.objects.order_by('-created_at')[:5]  # Show latest 5 promotions

    return render(request, 'system/dashboard.html', {
        'total_customers': total_customers,
        'appointments_today': appointments_today,
        'total_revenue': total_revenue,
        'top_service': top_service or {'name': 'N/A'},
        'recent_appointments': recent_appointments,
        'selected_branch': str(branch_id) if branch_id else '',
        'promotions': promotions,
    })
def service_list(request):
    services = Service.objects.filter(branch__business=request.user.business)
    return render(request, 'system/service_list.html', {'services': services})

def add_service(request):
    if request.method == 'POST':
        form = ServiceForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('service_list')
    else:
        form = ServiceForm()
    return render(request, 'system/service_form.html', {'form': form, 'title': 'Add Service'})

def edit_service(request, service_id):
    service = get_object_or_404(Service, id=service_id)
    if request.method == 'POST':
        form = ServiceForm(request.POST, instance=service)
        if form.is_valid():
            form.save()
            return redirect('service_list')
    else:
        form = ServiceForm(instance=service)
    return render(request, 'system/service_form.html', {'form': form, 'title': 'Edit Service'})

def appointment_list(request):
    appointments = Appointment.objects.select_related('customer', 'service', 'employee', 'branch').order_by('-date_time')
    return render(request, 'system/appointment_list.html', {'appointments': appointments})

def add_appointment(request):
    if request.method == 'POST':
        form = AppointmentForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('appointment_list')
    else:
        form = AppointmentForm()
    return render(request, 'system/appointment_form.html', {'form': form, 'title': 'Add Appointment'})

def edit_appointment(request, appointment_id):
    appointment = get_object_or_404(Appointment, id=appointment_id)
    if request.method == 'POST':
        form = AppointmentForm(request.POST, instance=appointment)
        if form.is_valid():
            form.save()
            return redirect('appointment_list')
    else:
        form = AppointmentForm(instance=appointment)
    return render(request, 'system/appointment_form.html', {'form': form, 'title': 'Edit Appointment'})
def feature_required(feature_code):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if request.user.is_superuser or request.user.is_admin():
                return view_func(request, *args, **kwargs)
            if request.user.role and request.user.role.features.filter(code=feature_code).exists():
                return view_func(request, *args, **kwargs)
            messages.error(request, "You do not have permission to access this feature.")
            return redirect('dashboard')
        return _wrapped_view
    return decorator
@login_required
def settings(request):
    if not request.user.business:
        messages.error(request, "You are not assigned to a business. Contact an admin.")
        return redirect('dashboard')
    can_set_loyalty_points = request.user.is_superuser or (request.user.role and request.user.role.features.filter(code='can_set_loyalty_points').exists())
    can_set_performance_score = request.user.is_superuser or (request.user.role and request.user.role.features.filter(code='can_set_performance_score').exists())
    if not (can_set_loyalty_points or can_set_performance_score):
        messages.error(request, "You do not have permission to access settings.")
        return redirect('dashboard')
    service_points = ServicePoints.objects.filter(business=request.user.business).select_related('service', 'branch') if can_set_loyalty_points else []
    business_form = BusinessHaircutPointsForm(instance=request.user.business) if can_set_performance_score else None
    service_points_form = ServicePointsForm(business=request.user.business) if can_set_loyalty_points else None
    if request.method == 'POST':
        if 'standard_haircut_points' in request.POST and can_set_performance_score:
            business_form = BusinessHaircutPointsForm(request.POST, instance=request.user.business)
            if business_form.is_valid():
                business_form.save()
                messages.success(request, "Business settings updated successfully.")
                return redirect('settings')
            else:
                messages.error(request, "Failed to update settings. Please check the input.")
        elif 'service' in request.POST and 'add_service_points_form' in request.POST and can_set_loyalty_points:
            service_points_form = ServicePointsForm(request.POST, business=request.user.business)
            if service_points_form.is_valid():
                service_points_entry = service_points_form.save(commit=False)
                service_points_entry.business = request.user.business
                service_points_entry.save()
                messages.success(request, "Service points added successfully.")
                return redirect('settings')
            else:
                messages.error(request, "Failed to add service points. Please check the input.")
        elif 'service_points_id' in request.POST and 'edit_service_points_form' in request.POST and can_set_loyalty_points:
            service_points_id = request.POST.get('service_points_id')
            service_points = get_object_or_404(ServicePoints, id=service_points_id, business=request.user.business)
            service_points_form = ServicePointsForm(request.POST, instance=service_points, business=request.user.business)
            if service_points_form.is_valid():
                service_points_form.save()
                messages.success(request, "Service points updated successfully.")
                return redirect('settings')
            else:
                messages.error(request, "Failed to update service points. Please check the input.")
        elif 'service_points_id' in request.POST and 'delete_service_points_form' in request.POST and can_set_loyalty_points:
            service_points_id = request.POST.get('service_points_id')
            service_points = get_object_or_404(ServicePoints, id=service_points_id, business=request.user.business)
            service_points.delete()
            messages.success(request, "Service points deleted successfully.")
            return redirect('settings')
    return render(request, 'system/settings.html', {
        'service_points': service_points,
        'business_form': business_form,
        'service_points_form': service_points_form,
        'can_set_loyalty_points': can_set_loyalty_points,
        'can_set_performance_score': can_set_performance_score,
    })
@login_required
def employee_list(request):
    if not request.user.business:
        messages.error(request, "You are not assigned to a business. Contact an admin.")
        return redirect('dashboard')

    employees = Employee.objects.filter(business=request.user.business).select_related('branch', 'position')
    positions = Position.objects.filter(business=request.user.business)
    business_form = None
    if request.user.is_superuser or (request.user.role and request.user.role.features.filter(code='can_set_performance_score').exists()):
        business_form = BusinessHaircutPointsForm(instance=request.user.business)
    
    if request.method == 'POST':
        if 'standard_haircut_points' in request.POST:
            if not (request.user.is_superuser or request.user.role.features.filter(code='can_set_performance_score').exists()):
                messages.error(request, "You do not have permission to set haircut points.")
                return redirect('employee_list')
            business_form = BusinessHaircutPointsForm(request.POST, instance=request.user.business)
            if business_form.is_valid():
                business_form.save()
                messages.success(request, "Standard haircut points updated successfully.")
                return redirect('employee_list')
            else:
                messages.error(request, "Failed to update haircut points. Please check the input.")
        elif 'name' in request.POST and 'add_position_form' in request.POST:
            form = PositionForm(request.POST)
            if form.is_valid():
                position = form.save(commit=False)
                position.business = request.user.business
                position.save()
                messages.success(request, "Position added successfully.")
                return redirect('employee_list')
            else:
                messages.error(request, "Failed to add position. Please check the input.")
        elif 'position_id' in request.POST and 'edit_position_form' in request.POST:
            position_id = request.POST.get('position_id')
            position = get_object_or_404(Position, id=position_id, business=request.user.business)
            form = PositionForm(request.POST, instance=position)
            if form.is_valid():
                form.save()
                messages.success(request, "Position updated successfully.")
                return redirect('employee_list')
            else:
                messages.error(request, "Failed to update position. Please check the input.")

    return render(request, 'system/employee_list.html', {
        'employees': employees,
        'positions': positions,
        'add_position_form': PositionForm(),
        'edit_position_form': PositionForm(),
        'business_form': business_form,
    })

@login_required
def add_employee(request):
    if not request.user.business:
        messages.error(request, "You are not assigned to a business. Contact an admin.")
        return redirect('dashboard')

    if request.method == 'POST':
        form = EmployeeForm(request.POST, business=request.user.business)
        if form.is_valid():
            employee = form.save(commit=False)
            employee.business = request.user.business
            employee.save()
            messages.success(request, "Employee added successfully.")
            return redirect('employee_list')
        else:
            messages.error(request, "Failed to add employee. Please check the input.")
    else:
        form = EmployeeForm(business=request.user.business)
    return render(request, 'system/employee_form.html', {
        'form': form,
        'title': 'Add Employee',
        'add_position_form': PositionForm(),
    })

@login_required
def edit_employee(request, employee_id):
    if not request.user.business:
        messages.error(request, "You are not assigned to a business. Contact an admin.")
        return redirect('dashboard')

    employee = get_object_or_404(Employee, id=employee_id, business=request.user.business)
    if request.method == 'POST':
        form = EmployeeForm(request.POST, instance=employee, business=request.user.business)
        if form.is_valid():
            form.save()
            messages.success(request, "Employee updated successfully.")
            return redirect('employee_list')
        else:
            messages.error(request, "Failed to update employee. Please check the input.")
    else:
        form = EmployeeForm(instance=employee, business=request.user.business)
    return render(request, 'system/employee_form.html', {
        'form': form,
        'title': 'Edit Employee',
        'add_position_form': PositionForm(),
    })

@login_required
def delete_employee(request, employee_id):
    if not request.user.business:
        messages.error(request, "You are not assigned to a business. Contact an admin.")
        return redirect('dashboard')

    employee = get_object_or_404(Employee, id=employee_id, business=request.user.business)
    if request.method == 'POST':
        employee.delete()
        messages.success(request, "Employee deleted successfully.")
        return redirect('employee_list')
    return render(request, 'system/employee_list.html', {
        'employees': Employee.objects.filter(business=request.user.business).select_related('branch', 'position'),
        'positions': Position.objects.filter(business=request.user.business),
        'add_position_form': PositionForm(),
        'edit_position_form': PositionForm(),
    })

@login_required
def settings(request):
    if not request.user.business:
        messages.error(request, "You are not assigned to a business. Contact an admin.")
        return redirect('dashboard')

    # Check permissions
    can_set_loyalty_points = request.user.is_superuser or (request.user.role and request.user.role.features.filter(code='can_set_loyalty_points').exists())
    can_set_performance_score = request.user.is_superuser or (request.user.role and request.user.role.features.filter(code='can_set_performance_score').exists())

    if not (can_set_loyalty_points or can_set_performance_score):
        messages.error(request, "You do not have permission to access settings.")
        return redirect('dashboard')

    service_points = ServicePoints.objects.filter(business=request.user.business).select_related('service', 'branch') if can_set_loyalty_points else []
    business_form = BusinessHaircutPointsForm(instance=request.user.business) if can_set_performance_score else None
    service_points_form = ServicePointsForm(business=request.user.business) if can_set_loyalty_points else None

    if request.method == 'POST':
        if 'standard_haircut_points' in request.POST and can_set_performance_score:
            business_form = BusinessHaircutPointsForm(request.POST, instance=request.user.business)
            if business_form.is_valid():
                business_form.save()
                messages.success(request, "Standard haircut points updated successfully.")
                return redirect('settings')
            else:
                messages.error(request, "Failed to update haircut points. Please check the input.")
        elif 'service' in request.POST and 'add_service_points_form' in request.POST and can_set_loyalty_points:
            service_points_form = ServicePointsForm(request.POST, business=request.user.business)
            if service_points_form.is_valid():
                service_points_entry = service_points_form.save(commit=False)
                service_points_entry.business = request.user.business
                service_points_entry.save()
                messages.success(request, "Service points added successfully.")
                return redirect('settings')
            else:
                messages.error(request, "Failed to add service points. Please check the input.")
        elif 'service_points_id' in request.POST and 'edit_service_points_form' in request.POST and can_set_loyalty_points:
            service_points_id = request.POST.get('service_points_id')
            service_points = get_object_or_404(ServicePoints, id=service_points_id, business=request.user.business)
            service_points_form = ServicePointsForm(request.POST, instance=service_points, business=request.user.business)
            if service_points_form.is_valid():
                service_points_form.save()
                messages.success(request, "Service points updated successfully.")
                return redirect('settings')
            else:
                messages.error(request, "Failed to update service points. Please check the input.")
        elif 'service_points_id' in request.POST and 'delete_service_points_form' in request.POST and can_set_loyalty_points:
            service_points_id = request.POST.get('service_points_id')
            service_points = get_object_or_404(ServicePoints, id=service_points_id, business=request.user.business)
            service_points.delete()
            messages.success(request, "Service points deleted successfully.")
            return redirect('settings')

    return render(request, 'system/settings.html', {
        'service_points': service_points,
        'business_form': business_form,
        'service_points_form': service_points_form,
        'can_set_loyalty_points': can_set_loyalty_points,
        'can_set_performance_score': can_set_performance_score,
    })
def expense_list(request):
    expenses = Expense.objects.select_related('branch').all().order_by('-date')

    branch_id = request.GET.get('branch')
    category = request.GET.get('category')
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')

    if branch_id:
        expenses = expenses.filter(branch_id=branch_id)
    if category:
        expenses = expenses.filter(category=category)
    if start_date:
        expenses = expenses.filter(date__gte=start_date)
    if end_date:
        expenses = expenses.filter(date__lte=end_date)

    total_expenses = expenses.aggregate(total=Sum('amount'))['total'] or 0

    all_branches = Branch.objects.all()
    category_choices = Expense.CATEGORY_CHOICES

    return render(request, 'system/expense_list.html', {
        'expenses': expenses,
        'total_expenses': total_expenses,
        'branches': all_branches,
        'selected_branch': branch_id,
        'category_choices': category_choices,
        'selected_category': category,
        'start_date': start_date,
        'end_date': end_date,
    })

def add_expense(request):
    if request.method == 'POST':
        form = ExpenseForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('expense_list')
    else:
        form = ExpenseForm()
    return render(request, 'system/expense_form.html', {'form': form, 'title': 'Add Expense'})

def edit_expense(request, expense_id):
    expense = get_object_or_404(Expense, id=expense_id)
    if request.method == 'POST':
        form = ExpenseForm(request.POST, instance=expense)
        if form.is_valid():
            form.save()
            return redirect('expense_list')
    else:
        form = ExpenseForm(instance=expense)
    return render(request, 'system/expense_form.html', {'form': form, 'title': 'Edit Expense'})
def payroll_list(request):
    payrolls = Payroll.objects.select_related('employee', 'employee__user', 'employee__branch').order_by('-month')
    
    branch_id = request.GET.get('branch')
    if branch_id:
        payrolls = payrolls.filter(employee__branch_id=branch_id)

    branches = Branch.objects.all()
    return render(request, 'system/payroll_list.html', {
        'payrolls': payrolls,
        'selected_branch': branch_id,
        'branches': branches
    })

def generate_payroll(request):
    if request.method == 'POST':
        form = PayrollForm(request.POST)
        if form.is_valid():
            employee = form.cleaned_data['employee']
            month = form.cleaned_data['month']

            start_date = month.replace(day=1)
            next_month = (start_date.replace(day=28) + timedelta(days=4)).replace(day=1)
            end_date = next_month - timedelta(days=1)

            # Check for existing payroll
            if Payroll.objects.filter(employee=employee, month=month).exists():
                messages.warning(request, "Payroll for this employee and month already exists.")
                return redirect('generate_payroll')

            appointments = Appointment.objects.filter(
                employee=employee,
                date_time__date__range=(start_date, end_date),
                status='COMPLETED'
            )

            revenue = Payment.objects.filter(
                appointment__in=appointments
            ).aggregate(total=Sum('amount'))['total'] or 0
            clients_served = appointments.count()
            base_pay = 150000
            bonus = clients_served * 2000 + (revenue * 0.05)  # 5% commission on revenue
            total = base_pay + bonus

            breakdown = (
                f"Base Pay: UGX {base_pay}\n"
                f"Clients Served: {clients_served} x 2000 = UGX {clients_served * 2000}\n"
                f"Revenue Commission (5%): UGX {revenue * 0.05}\n"
                f"Total: UGX {total}"
            )

            Payroll.objects.create(
                employee=employee,
                amount=total,
                month=month,
                breakdown=breakdown
            )
            messages.success(request, "Payroll generated successfully.")
            return redirect('payroll_list')
    else:
        form = PayrollForm()
    return render(request, 'system/payroll_form.html', {'form': form, 'title': 'Generate Payroll'})

def delete_payroll(request, payroll_id):
    payroll = get_object_or_404(Payroll, id=payroll_id)
    if request.method == 'POST':
        payroll.delete()
        messages.success(request, "Payroll record deleted successfully.")
        return redirect('payroll_list')
    return render(request, 'system/confirm_delete.html', {'payroll': payroll, 'title': 'Delete Payroll'})
def revenue_dashboard(request):
    branch_id = request.GET.get('branch')
    form = RevenueFilterForm(request.GET or None)

    payments = Payment.objects.all()
    if branch_id:
        payments = payments.filter(appointment__branch_id=branch_id)

    # Set default date range
    today = now().date()
    month_start = today.replace(day=1)
    start_date = month_start
    end_date = today
    user = None
    service = None

    if form.is_valid():
        start_date = form.cleaned_data.get('start_date') or month_start
        end_date = form.cleaned_data.get('end_date') or today
        user = form.cleaned_data.get('user')
        service = form.cleaned_data.get('service')
        if start_date:
            payments = payments.filter(date__gte=start_date)
        if end_date:
            payments = payments.filter(date__lte=end_date)
        if user:
            payments = payments.filter(appointment__employee=user)
        if service:
            payments = payments.filter(appointment__service=service)

    # Use start_date and end_date for top customers queries
    customer_qs = Customer.objects.all()
    if branch_id:
        customer_qs = customer_qs.filter(branch_id=branch_id)

    top_customers_by_visits = customer_qs.annotate(
        visit_count=Count('appointment', filter=Q(
            appointment__date_time__date__gte=start_date,
            appointment__date_time__date__lte=end_date
        ))
    ).order_by('-visit_count')[:5]

    top_customers_by_spending = customer_qs.annotate(
        total_spent=Sum(
            'payment__amount',
            filter=Q(payment__timestamp__date__gte=start_date) & Q(payment__timestamp__date__lte=end_date)
        )
    ).order_by('-total_spent')[:5]

    today = now().date()
    month_start = today.replace(day=1)

    total_appointments = Appointment.objects.filter(branch_id=branch_id).count() if branch_id else Appointment.objects.count()
    completed_appointments = Appointment.objects.filter(status='COMPLETED', branch_id=branch_id).count() if branch_id else Appointment.objects.filter(status='COMPLETED').count()
    total_coupons = Coupon.objects.count()
    total_revenue = payments.aggregate(total=Sum('amount'))['total'] or 0
    total_payroll = Payroll.objects.filter(employee__branch_id=branch_id).aggregate(total=Sum('amount'))['total'] or 0 if branch_id else Payroll.objects.aggregate(total=Sum('amount'))['total'] or 0
    total_expenses = Expense.objects.filter(branch_id=branch_id).aggregate(total=Sum('amount'))['total'] or 0 if branch_id else Expense.objects.aggregate(total=Sum('amount'))['total'] or 0

    # Calculate profit
    profit = total_revenue - total_expenses

    # Get all employees for the branch or all branches
    if branch_id:
        employees = Employee.objects.filter(branch_id=branch_id)
    else:
        employees = Employee.objects.all()

    # Revenue by employee in the selected period
    revenue_by_employee = (
        payments.values('appointment__employee__id', 'appointment__employee__user__first_name', 'appointment__employee__user__last_name')
        .annotate(total_revenue=Sum('amount'))
        .order_by('-total_revenue')
    )

    # Convert to a list for easy template use
    revenue_by_employee = list(revenue_by_employee)

    branches = Branch.objects.all()
    promotions = Promotion.objects.order_by('-created_at')[:5]  # Show latest 5 promotions
    return render(request, 'system/revenue_dashboard.html', {
        'total_appointments': total_appointments,
        'completed_appointments': completed_appointments,
        'total_coupons': total_coupons,
        'total_revenue': total_revenue,
        'total_payroll': total_payroll,
        'total_expenses': total_expenses,
        'profit': profit,
        'top_customers_by_visits': top_customers_by_visits,
        'top_customers_by_spending': top_customers_by_spending,
        'branches': branches,
        'selected_branch': str(branch_id) if branch_id else '',
        'form': form,
        'revenue_by_employee': revenue_by_employee,
        'promotions': promotions,
        'promotion_form': PromotionForm(),
    })
    
    
def branch_list(request):
    branches = Branch.objects.select_related('business').all()
    return render(request, 'system/branch_list.html', {'branches': branches})


def add_branch(request):
    if request.method == 'POST':
        form = BranchForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('branch_list')
    else:
        form = BranchForm()
    return render(request, 'system/branch_form.html', {'form': form, 'title': 'Add Branch'})


def edit_branch(request, branch_id):
    branch = get_object_or_404(Branch, id=branch_id)
    if request.method == 'POST':
        form = BranchForm(request.POST, instance=branch)
        if form.is_valid():
            form.save()
            return redirect('branch_list')
    else:
        form = BranchForm(instance=branch)
    return render(request, 'system/branch_form.html', {'form': form, 'title': 'Edit Branch'})
def report_dashboard(request):
    today = now().date()
    total_appointments = Appointment.objects.count()
    completed_appointments = Appointment.objects.filter(status='COMPLETED').count()
    total_revenue = Payment.objects.aggregate(total=Sum('amount'))['total'] or 0
    total_expenses = Expense.objects.aggregate(total=Sum('amount'))['total'] or 0
    total_payroll = Payroll.objects.aggregate(total=Sum('amount'))['total'] or 0

    return render(request, 'system/report_dashboard.html', {
        'total_appointments': total_appointments,
        'completed_appointments': completed_appointments,
        'total_revenue': total_revenue,
        'total_expenses': total_expenses,
        'total_payroll': total_payroll,
    })


def export_report_excel(request):
    wb = Workbook()
    ws = wb.active
    ws.title = "Report Summary"

    ws.append(["Metric", "Value"])
    ws.append(["Total Appointments", Appointment.objects.count()])
    ws.append(["Completed Appointments", Appointment.objects.filter(status='COMPLETED').count()])
    ws.append(["Total Revenue", Payment.objects.aggregate(total=Sum('amount'))['total'] or 0])
    ws.append(["Total Payroll Paid", Payroll.objects.aggregate(total=Sum('amount'))['total'] or 0])
    ws.append(["Total Expenses", Expense.objects.aggregate(total=Sum('amount'))['total'] or 0])

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename=report_summary.xlsx'
    wb.save(response)
    return response


def export_report_pdf(request):
    context = {
        'date': datetime.date.today(),
        'total_appointments': Appointment.objects.count(),
        'completed_appointments': Appointment.objects.filter(status='COMPLETED').count(),
        'total_revenue': Payment.objects.aggregate(total=Sum('amount'))['total'] or 0,
        'total_expenses': Expense.objects.aggregate(total=Sum('amount'))['total'] or 0,
        'total_payroll': Payroll.objects.aggregate(total=Sum('amount'))['total'] or 0,
    }
    html = render_to_string("system/report_pdf_template.html", context)
    response = HttpResponse(content_type="application/pdf")
    response['Content-Disposition'] = "inline; filename=report_summary.pdf"
    pisa_status = pisa.CreatePDF(html, dest=response)
    if pisa_status.err:
        return HttpResponse("PDF generation failed")
    return response
def coupon_list(request):
    coupons = Coupon.objects.prefetch_related('applicable_services').all()
    total_coupons = coupons.count()
    return render(request, 'system/coupon_list.html', {
        'coupons': coupons,
        'total_coupons': total_coupons,
    })


def add_coupon(request):
    if request.method == 'POST':
        form = CouponForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('coupon_list')
    else:
        form = CouponForm()
    return render(request, 'system/coupon_form.html', {'form': form, 'title': 'Add Coupon'})


def edit_coupon(request, coupon_id):
    coupon = get_object_or_404(Coupon, id=coupon_id)
    if request.method == 'POST':
        form = CouponForm(request.POST, instance=coupon)
        if form.is_valid():
            form.save()
            return redirect('coupon_list')
    else:
        form = CouponForm(instance=coupon)
    return render(request, 'system/coupon_form.html', {'form': form, 'title': 'Edit Coupon'})
@feature_required('complete_appointment')
def complete_appointment(request, appointment_id):
    try:
        appointment = Appointment.objects.get(id=appointment_id)
    except Appointment.DoesNotExist:
        messages.error(request, "Appointment not found.")
        return redirect('appointment_list')
    
    if appointment.status == 'COMPLETED':
        messages.error(request, "This appointment is already completed.")
        return redirect('appointment_list')
    
    if not request.user.business or appointment.branch.business != request.user.business:
        messages.error(request, "You are not authorized to process this payment.")
        return redirect('appointment_list')

    loyalty_points = appointment.customer.loyalty_points
    business = request.user.business
    earned_points = Decimal('0.0')
    employee_earned_points = 0.0

    if request.method == 'POST':
        form = PaymentForm(request.POST, user=request.user, appointment=appointment)
        if form.is_valid():
            payment = form.save(commit=False)
            payment.appointment = appointment
            payment.customer = appointment.customer
            
            # Calculate total amount
            total = appointment.service.price
            additional_services = form.cleaned_data['additional_services']
            products = form.cleaned_data['products']
            
            for service in additional_services:
                total += service.price
            for product in products:
                total += product.price
            
            # Calculate earned customer loyalty points and employee points
            sp = ServicePoints.objects.filter(service=appointment.service, branch=appointment.branch).first()
            if sp:
                earned_points += sp.loyalty_points
                employee_earned_points += sp.employee_points
            else:
                employee_earned_points += business.standard_haircut_points
            for service in additional_services:
                sp = ServicePoints.objects.filter(service=service, branch=appointment.branch).first()
                if sp:
                    earned_points += sp.loyalty_points
                    employee_earned_points += sp.employee_points
                else:
                    employee_earned_points += business.standard_haircut_points
            
            # Apply loyalty discount
            if form.cleaned_data['used_loyalty_points'] and loyalty_points > 0:
                points_to_use = min(loyalty_points, Decimal('100.0'))  # Max 100 points per transaction
                discount = points_to_use * business.loyalty_point_value
                total -= discount
                payment.used_loyalty_points = points_to_use
            
            # Apply coupon
            coupon = form.cleaned_data['coupon']
            if coupon and coupon.expiry_date >= timezone.now().date():
                applicable = not coupon.applicable_services.exists() or \
                             appointment.service in coupon.applicable_services.all() or \
                             any(service in coupon.applicable_services.all() for service in additional_services)
                if applicable and (not coupon.min_spend or total >= coupon.min_spend):
                    total *= (1 - coupon.discount_percent / 100)

            payment.amount = max(total, Decimal('0.0'))
            payment.save()
            
            # Save additional services and products
            payment.additional_services.set(additional_services)
            payment.products.set(products)
            
            # Update appointment status
            appointment.status = 'COMPLETED'
            appointment.save()
            
            # Update customer loyalty points
            appointment.customer.loyalty_points += earned_points
            if form.cleaned_data['used_loyalty_points']:
                appointment.customer.loyalty_points -= payment.used_loyalty_points
            appointment.customer.save()
            
            # Update employee performance points
            appointment.employee.performance_points += employee_earned_points
            appointment.employee.save()
            
            # Update product stock
            for product in products:
                product.stock_quantity -= 1
                product.save()
            
            messages.success(request, f"Payment completed successfully. Earned {earned_points} customer loyalty points.")
            return redirect('appointment_list')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = PaymentForm(user=request.user, appointment=appointment, initial={'customer': appointment.customer})

    return render(request, 'system/complete_payment.html', {
        'form': form,
        'appointment': appointment,
        'loyalty_points': loyalty_points,
        'earned_points': earned_points,
        'loyalty_point_value': business.loyalty_point_value,
    })

@feature_required('buy_product')
def buy_product(request):
    if not request.user.business:
        messages.error(request, "You are not assigned to a business.")
        return redirect('dashboard')
    
    # Get query parameters for pre-selection
    service_id = request.GET.get('service_id')
    product_id = request.GET.get('product_id')
    initial_data = {}
    preselected_service = None
    preselected_product = None
    loyalty_points = None
    
    if service_id:
        try:
            preselected_service = Service.objects.get(id=service_id, branch__business=request.user.business, is_active=True)
            initial_data['additional_services'] = [preselected_service.id]
        except Service.DoesNotExist:
            messages.error(request, "Selected service is not available.")
    
    if product_id:
        try:
            preselected_product = Product.objects.get(id=product_id, branch__business=request.user.business, is_active=True, stock_quantity__gt=0)
            initial_data['products'] = [preselected_product.id]
        except Product.DoesNotExist:
            messages.error(request, "Selected product is not available.")
    
    if request.method == 'POST':
        form = PaymentForm(request.POST, user=request.user)
        if form.is_valid():
            payment = form.save(commit=False)
            customer = form.cleaned_data['customer']
            payment.customer = customer  # Allow customer for loyalty points
            
            # Calculate total amount
            total = Decimal('0.0')
            additional_services = form.cleaned_data['additional_services']
            products = form.cleaned_data['products']
            
            for service in additional_services:
                total += service.price
            for product in products:
                total += product.price
            
            # Apply loyalty points discount
            used_loyalty_points = form.cleaned_data['used_loyalty_points']
            if used_loyalty_points and customer:
                points_available = customer.loyalty_points
                points_to_use = min(points_available, Decimal('100.0'))  # Max 100 points
                discount = points_to_use * request.user.business.loyalty_point_value
                total -= discount
                payment.used_loyalty_points = points_to_use
                customer.loyalty_points -= points_to_use
                customer.save()
            
            # Apply coupon
            coupon = form.cleaned_data['coupon']
            if coupon and coupon.expiry_date >= timezone.now().date():
                applicable = not coupon.applicable_services.exists() or \
                             any(service in coupon.applicable_services.all() for service in additional_services)
                if applicable and (not coupon.min_spend or total >= coupon.min_spend):
                    total *= (1 - coupon.discount_percent / 100)

            payment.amount = max(total, Decimal('0.0'))
            payment.save()
            
            # Save additional services and products
            payment.additional_services.set(additional_services)
            payment.products.set(products)
            
            # Update product stock
            for product in products:
                product.stock_quantity -= 1
                product.save()
            
            messages.success(request, "Purchase completed successfully.")
            return redirect('service_list')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = PaymentForm(user=request.user, initial=initial_data)
        if form.initial.get('customer'):
            customer = Customer.objects.get(id=form.initial['customer'])
            loyalty_points = customer.loyalty_points

    return render(request, 'system/complete_payment.html', {
        'form': form,
        'preselected_service': preselected_service,
        'preselected_product': preselected_product,
        'loyalty_points': loyalty_points,
        'loyalty_point_value': request.user.business.loyalty_point_value if request.user.business else Decimal('10.00'),
    })
def generate_payroll(request):
    if request.method == 'POST':
        form = PayrollForm(request.POST)
        if form.is_valid():
            employee = form.cleaned_data['employee']
            month = form.cleaned_data['month']

            start_date = month.replace(day=1)
            next_month = (start_date.replace(day=28) + timedelta(days=4)).replace(day=1)
            end_date = next_month - timedelta(days=1)

            # Check for existing payroll
            if Payroll.objects.filter(employee=employee, month=month).exists():
                messages.warning(request, "Payroll for this employee and month already exists.")
                return redirect('generate_payroll')

            appointments = Appointment.objects.filter(
                employee=employee,
                date_time__date__range=(start_date, end_date),
                status='COMPLETED'
            )

            revenue = Payment.objects.filter(
                appointment__in=appointments
            ).aggregate(total=Sum('amount'))['total' or 0]
            clients_served = appointments.count()
            base_pay = 150000
            bonus = clients_served * 2000 + (revenue * 0.05)  # 5% commission on revenue
            total = base_pay + bonus

            breakdown = (
                f"Base Pay: UGX {base_pay}\n"
                f"Clients Served: {clients_served} x 2000 = UGX {clients_served * 2000}\n"
                f"Revenue Commission (5%): UGX {revenue * 0.05}\n"
                f"Total: UGX {total}"
            )

            Payroll.objects.create(
                employee=employee,
                amount=total,
                month=month,
                breakdown=breakdown
            )
            messages.success(request, "Payroll generated successfully.")
            return redirect('payroll_list')
    else:
        form = PayrollForm()
    return render(request, 'system/payroll_form.html', {'form': form, 'title': 'Generate Payroll'})

def loyalty_report(request):
    branch_id = request.GET.get('branch')
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')

    customers = Customer.objects.all()
    if branch_id:
        customers = customers.filter(branch_id=branch_id)

    # Visits and spending in date range
    for customer in customers:
        appointments = Appointment.objects.filter(customer=customer)
        if start_date:
            appointments = appointments.filter(date_time__date__gte=start_date)
        if end_date:
            appointments = appointments.filter(date_time__date__lte=end_date)
        customer.visits_in_range = appointments.count()
        customer.spent_in_range = Payment.objects.filter(
            customer=customer,
            date__gte=start_date if start_date else None,
            date__lte=end_date if end_date else None
        ).aggregate(total=Sum('amount'))['total' or 0]

    return render(request, 'system/loyalty_report.html', {
        'customers': customers,
        'selected_branch': branch_id,
        'start_date': start_date,
        'end_date': end_date,
    })

@staff_member_required
def send_manual_reminders(request):
    if request.method == "POST":
        send_reminders.delay()
        messages.success(request, "Reminders are being sent!")
        return HttpResponseRedirect(reverse('dashboard'))
    return HttpResponseRedirect(reverse('dashboard'))

def create_promotion(request):
    if request.method == 'POST':
        form = PromotionForm(request.POST)
        if form.is_valid():
            promo = form.save()
            # Trigger the Celery task
            send_promotional_message.delay(
                promo.subject, promo.message, promo.sms_message
            )
            promo.sent = True
            promo.save()
            return redirect('promotion_success')
    else:
        form = PromotionForm()
    return render(request, 'system/create_promotion.html', {'form': form})

def promotion_list(request):
    promotions = Promotion.objects.order_by('-created_at')
    return render(request, 'system/promotion_list.html', {'promotions': promotions})

def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        # Special case: admin/admin triggers onboarding
        if username == 'admin' and password == 'admin':
            request.session['onboarding'] = True  # <-- Set the session flag!
            return redirect('onboarding')

        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('dashboard')
        else:
            messages.error(request, "Invalid username or password.")
    return render(request, 'system/login.html')

def logout_view(request):
    logout(request)
    return redirect('login')

@login_required
def create_user(request):
    User = get_user_model()
    if not (request.user.is_superuser or (hasattr(request.user, 'role') and request.user.role and request.user.role.name == 'Admin')):
        messages.error(request, 'Only admins can create or edit users.')
        return redirect('dashboard')
    
    users = User.objects.filter(business=request.user.business)
    roles = Role.objects.filter(business=request.user.business)
    all_permissions = Permission.objects.all()
    all_features = Feature.objects.all()

    if request.method == 'POST':
        edit_user_id = request.POST.get('edit_user_id')
        if edit_user_id:
            old_user = get_object_or_404(User, id=edit_user_id, business=request.user.business)
            old_user.delete()
            form = UserCreationForm(request.POST, business=request.user.business)  # <-- pass business here!
            if form.is_valid():
                user = form.save(commit=False)
                user.business = request.user.business
                user.is_active = True
                user.save()
                role_id = request.POST.get('role')
                if role_id:
                    user.role = Role.objects.get(id=role_id, business=request.user.business)
                user.save()
                messages.success(request, f'User {user.username} updated successfully.')
                return redirect('create_user')
            else:
                messages.error(request, "Please correct the errors below.")
        else:
            form = UserCreationForm(request.POST, business=request.user.business)  # <-- pass business here!
            if form.is_valid():
                user = form.save(commit=False)
                user.business = request.user.business
                user.is_active = True
                user.save()
                role_id = request.POST.get('role')
                if role_id:
                    user.role = Role.objects.get(id=role_id, business=request.user.business)
                user.save()
                messages.success(request, f'User {user.username} created successfully.')
                return redirect('create_user')
            else:
                messages.error(request, "Please correct the errors below.")
    else:
        form = UserCreationForm(business=request.user.business)  # <-- pass business here!

    return render(request, 'system/create_user.html', {
        'form': form,
        'users': users,
        'roles': roles,
        'all_permissions': all_permissions,
        'all_features': all_features,
    })

@login_required
def user_list(request):
    if not request.user.role or request.user.role.name != 'Admin':
        messages.error(request, "Only admins can manage users.")
        return redirect('dashboard')
    User = get_user_model()
    users = User.objects.all()
    return render(request, 'system/user_list.html', {'users': users})

def onboarding(request):
    # Only allow onboarding if session flag is set
    if not request.session.get('onboarding', False):
        return redirect('login')

    # Step 1: Create Business
    if 'business_id' not in request.session:
        if request.method == 'POST':
            form = BusinessForm(request.POST)
            if form.is_valid():
                business = form.save()
                request.session['business_id'] = business.id
                return redirect('onboarding')
        else:
            form = BusinessForm()
        return render(request, 'system/onboarding_business.html', {'form': form})

    business = Business.objects.get(id=request.session['business_id'])
    if request.method == 'POST':
        form = AdminCreationForm(request.POST)
        if form.is_valid():
            admin_user = form.save(commit=False)
            admin_user.business = business
            admin_role, _ = Role.objects.get_or_create(name='Admin')
            admin_user.role = admin_role
            admin_user.set_password(form.cleaned_data['password'])
            admin_user.save()
            del request.session['business_id']
            messages.success(request, "Admin account created. Please log in as admin.")
            return redirect('logout')
    else:
        form = AdminCreationForm()
    return render(request, 'system/onboarding_admin.html', {'form': form, 'business': business})

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from .models import Role, Feature

@login_required
def add_role(request):
    if request.method == 'POST':
        form = RoleForm(request.POST)
        if form.is_valid():
            role = form.save(commit=False)
            role.business = request.user.business  # This is correct!
            role.save()
            form.save_m2m()
            messages.success(request, f"Role '{role.name}' created successfully.")
        else:
            messages.error(request, "Please correct the errors below.")
    return redirect('create_user')

@login_required
def edit_user(request, user_id):
    user = get_object_or_404(User, id=user_id)
    if request.method == 'POST':
        form = UserCreationForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            messages.success(request, f'User {user.username} updated successfully.')
            return redirect('user_list')
    else:
        form = UserCreationForm(instance=user)
    return render(request, 'system/edit_user.html', {'form': form, 'user': user})

    # Handle edit user POST
    if request.method == 'POST' and 'edit_user_id' in request.POST:
        user_id = request.POST.get('edit_user_id')
        user = get_object_or_404(User, id=user_id)
        role_id = request.POST.get('role')
        permission_ids = request.POST.getlist('permissions')
        if role_id:
            user.role = Role.objects.get(id=role_id)
        user.save()
        if user.role:
            user.role.permissions.set(permission_ids)
        messages.success(request, f'User {user.username} updated successfully.')
        return redirect('create_user')
@login_required
def position_list(request):
    positions = Position.objects.filter(business=request.user.business)
    return render(request, 'system/position_list.html', {
        'positions': positions,
        'add_form': PositionForm(),
        'edit_form': PositionForm(),
    })

@login_required
def add_position(request):
    if request.method == 'POST':
        form = PositionForm(request.POST)
        print("Form data:", request.POST)  # Log submitted data
        if form.is_valid():
            print("Form is valid, cleaned data:", form.cleaned_data)  # Log cleaned data
            position = form.save(commit=False)
            print("User business:", request.user.business)  # Log business
            if not request.user.business:
                messages.error(request, "You are not assigned to a business.")
                return redirect('position_list')
            position.business = request.user.business
            position.save()
            print("Saved position:", position)  # Confirm save
            messages.success(request, "Position added successfully.")
            return redirect('position_list')
        else:
            print("Form errors:", form.errors)  # Log errors
            messages.error(request, "Something went wrong. Please check the form.")
    else:
        form = PositionForm()
    positions = Position.objects.filter(business=request.user.business)
    print("Queried positions:", positions)  # Log queried positions
    return render(request, 'system/position_list.html', {
        'form': form,
        'title': 'Add Position',
        'positions': positions
    })

@login_required
def edit_position(request, position_id):
    position = get_object_or_404(Position, id=position_id, business=request.user.business)
    if request.method == 'POST':
        form = PositionForm(request.POST, instance=position)
        if form.is_valid():
            form.save()
            messages.success(request, "Position updated successfully.")
            return redirect('position_list')
        else:
            messages.error(request, "Failed to update position. Please check the input.")
    else:
        form = PositionForm(instance=position)
    return render(request, 'system/position_list.html', {
        'positions': Position.objects.filter(business=request.user.business),
        'add_form': PositionForm(),
        'edit_form': form,
    })

@login_required
def delete_position(request, position_id):
    position = get_object_or_404(Position, id=position_id, business=request.user.business)
    if request.method == 'POST':
        position.delete()
        messages.success(request, "Position deleted successfully.")
        return redirect('position_list')
    return render(request, 'system/position_list.html', {
        'positions': Position.objects.filter(business=request.user.business),
        'add_form': PositionForm(),
        'edit_form': PositionForm(),
    })
@feature_required(['service_list'])
def service_list(request):
    if not request.user.business:
        messages.error(request, "You are not assigned to a business. Contact an admin.")
        return redirect('dashboard')
    services = Service.objects.filter(branch__business=request.user.business)
    return render(request, 'system/service_list.html', {'services': services})

@feature_required(['service_list'])
def add_service(request):
    if not request.user.business:
        messages.error(request, "You are not assigned to a business. Contact an admin.")
        return redirect('dashboard')
    if request.method == 'POST':
        form = ServiceForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('service_list')
    else:
        form = ServiceForm()
    return render(request, 'system/service_form.html', {'form': form, 'title': 'Add Service'})

@feature_required(['service_list'])
def edit_service(request, service_id):
    if not request.user.business:
        messages.error(request, "You are not assigned to a business. Contact an admin.")
        return redirect('dashboard')
    service = get_object_or_404(Service, id=service_id, branch__business=request.user.business)
    if request.method == 'POST':
        form = ServiceForm(request.POST, instance=service)
        if form.is_valid():
            form.save()
            return redirect('service_list')
    else:
        form = ServiceForm(instance=service)
    return render(request, 'system/service_form.html', {'form': form, 'title': 'Edit Service'})

@feature_required(['can_set_loyalty_points'])
def service_points_list(request):
    if not request.user.business:
        messages.error(request, "You are not assigned to a business. Contact an admin.")
        return redirect('dashboard')
    service_points = ServicePoints.objects.filter(business=request.user.business).select_related('service', 'branch')
    add_form = ServicePointsForm(business=request.user.business)
    if request.method == 'POST':
        if 'add_service_points_form' in request.POST:
            add_form = ServicePointsForm(request.POST, business=request.user.business)
            if add_form.is_valid():
                service_points_entry = add_form.save(commit=False)
                service_points_entry.business = request.user.business
                service_points_entry.save()
                messages.success(request, "Service points added successfully.")
                return redirect('service_points_list')
            else:
                messages.error(request, "Failed to add service points. Please check the input.")
        elif 'edit_service_points_form' in request.POST:
            service_points_id = request.POST.get('service_points_id')
            service_points = get_object_or_404(ServicePoints, id=service_points_id, business=request.user.business)
            edit_form = ServicePointsForm(request.POST, instance=service_points, business=request.user.business)
            if edit_form.is_valid():
                edit_form.save()
                messages.success(request, "Service points updated successfully.")
                return redirect('service_points_list')
            else:
                messages.error(request, "Failed to update service points. Please check the input.")
        elif 'delete_service_points_form' in request.POST:
            service_points_id = request.POST.get('service_points_id')
            service_points = get_object_or_404(ServicePoints, id=service_points_id, business=request.user.business)
            service_points.delete()
            messages.success(request, "Service points deleted successfully.")
            return redirect('service_points_list')
    return render(request, 'system/service_points_list.html', {
        'service_points': service_points,
        'add_form': add_form,
    })
@login_required
def service_list(request):
    services = Service.objects.filter(branch__business=request.user.business)
    products = Product.objects.filter(branch__business=request.user.business)

    if request.method == 'POST':
        form = ProductForm(request.POST)
        if form.is_valid():
            product = form.save(commit=False)
            product.business = request.user.business
            product.save()
            messages.success(request, "Product added successfully.")
            return redirect('service_list')
        else:
            messages.error(request, "There was an error adding the product.")
    else:
        form = ProductForm()

    context = {
        'services': services,
        'products': products,
        'product_form': form
    }
    return render(request, 'system/service_list.html', context)
@feature_required('can_set_loyalty_points')
def service_points_list(request):
    if not request.user.business:
        messages.error(request, "You are not assigned to a business. Contact an admin.")
        return redirect('dashboard')
    
    can_set_loyalty_points = request.user.is_superuser or (request.user.role and request.user.role.features.filter(code='can_set_loyalty_points').exists())
    can_set_performance_score = request.user.is_superuser or (request.user.role and request.user.role.features.filter(code='can_set_performance_score').exists())
    
    if not (can_set_loyalty_points or can_set_performance_score):
        messages.error(request, "You do not have permission to manage points.")
        return redirect('dashboard')
    
    service_points = ServicePoints.objects.filter(business=request.user.business).select_related('service', 'branch')
    service_points_form = ServicePointsForm(business=request.user.business) if can_set_loyalty_points or can_set_performance_score else None
    business_form = BusinessHaircutPointsForm(instance=request.user.business) if can_set_loyalty_points or can_set_performance_score else None
    
    if request.method == 'POST':
        if 'add_service_points_form' in request.POST and (can_set_loyalty_points or can_set_performance_score):
            service_points_form = ServicePointsForm(request.POST, business=request.user.business)
            if service_points_form.is_valid():
                service_points_entry = service_points_form.save(commit=False)
                service_points_entry.business = request.user.business
                service_points_entry.save()
                messages.success(request, "Service points added successfully.")
                return redirect('service_points_list')
            else:
                messages.error(request, "Failed to add service points. Please check the input.")
        elif 'edit_service_points_form' in request.POST and (can_set_loyalty_points or can_set_performance_score):
            service_points_id = request.POST.get('service_points_id')
            service_points = get_object_or_404(ServicePoints, id=service_points_id, business=request.user.business)
            service_points_form = ServicePointsForm(request.POST, instance=service_points, business=request.user.business)
            if service_points_form.is_valid():
                service_points_form.save()
                messages.success(request, "Service points updated successfully.")
                return redirect('service_points_list')
            else:
                messages.error(request, "Failed to update service points. Please check the input.")
        elif 'delete_service_points_form' in request.POST and (can_set_loyalty_points or can_set_performance_score):
            service_points_id = request.POST.get('service_points_id')
            service_points = get_object_or_404(ServicePoints, id=service_points_id, business=request.user.business)
            service_points.delete()
            messages.success(request, "Service points deleted successfully.")
            return redirect('service_points_list')
        elif 'business_form' in request.POST and (can_set_loyalty_points or can_set_performance_score):
            business_form = BusinessHaircutPointsForm(request.POST, instance=request.user.business)
            if business_form.is_valid():
                business_form.save()
                messages.success(request, "Business point settings updated successfully.")
                return redirect('service_points_list')
            else:
                messages.error(request, "Failed to update business settings. Please check the input.")
    
    return render(request, 'system/service_points_list.html', {
        'service_points': service_points,
        'service_points_form': service_points_form,
        'business_form': business_form,
        'can_set_loyalty_points': can_set_loyalty_points,
        'can_set_performance_score': can_set_performance_score,
    })
