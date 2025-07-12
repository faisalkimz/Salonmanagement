from django import forms
from .models import Customer, Position, Product, Service, Appointment, Employee, Expense, Payroll, Branch, Coupon, Payment, Promotion, User, Business, Role, Feature, ServicePoints

class CustomerForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user and user.business:
            # Restrict business to user's business
            self.fields['business'].queryset = Business.objects.filter(id=user.business.id)
            self.fields['business'].initial = user.business
            self.fields['business'].required = False  # Prevent validation error
            self.fields['business'].widget = forms.HiddenInput()  # Hide field
        elif user and not user.business:
            # Handle users without a business
            self.add_error('business', 'You are not assigned to a business.')

    class Meta:
        model = Customer
        fields = ['business', 'name', 'phone', 'email', 'address', 'gender', 'preferences']

class ServiceForm(forms.ModelForm):
    class Meta:
        model = Service
        fields = ['branch', 'name', 'price', 'is_active']

class AppointmentForm(forms.ModelForm):
    class Meta:
        model = Appointment
        fields = ['customer', 'branch', 'service', 'employee', 'date_time', 'status']
        widgets = {
            'date_time': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }

class EmployeeForm(forms.ModelForm):
    name = forms.CharField(max_length=100, required=True, label="Employee Name")

    def __init__(self, *args, **kwargs):
        business = kwargs.pop('business', None)
        super().__init__(*args, **kwargs)
        if business:
            self.fields['branch'].queryset = Branch.objects.filter(business=business)
            self.fields['position'].queryset = Position.objects.filter(business=business)

    class Meta:
        model = Employee
        fields = ['name', 'branch', 'position']

class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = ['branch', 'category', 'amount', 'description', 'date']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'})
        }

class PayrollForm(forms.ModelForm):
    class Meta:
        model = Payroll
        fields = ['employee', 'month']
        widgets = {
            'month': forms.DateInput(attrs={'type': 'month'})
        }

class RevenueFilterForm(forms.Form):
    start_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    end_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    user = forms.ModelChoiceField(queryset=Employee.objects.all(), required=False)
    service = forms.ModelChoiceField(queryset=Service.objects.all(), required=False)

class BranchForm(forms.ModelForm):
    class Meta:
        model = Branch
        fields = ['business', 'name', 'address', 'phone']

class CouponForm(forms.ModelForm):
    class Meta:
        model = Coupon
        fields = ['code', 'discount_percent', 'min_spend', 'expiry_date', 'applicable_services']
        widgets = {
            'expiry_date': forms.DateInput(attrs={'type': 'date'}),
            'applicable_services': forms.SelectMultiple(attrs={'class': 'form-select'})
        }

class PaymentForm(forms.ModelForm):
    customer = forms.ModelChoiceField(
        queryset=Customer.objects.none(),
        required=False,
        label="Customer",
        empty_label="Select a customer (optional)"
    )
    additional_services = forms.ModelMultipleChoiceField(
        queryset=Service.objects.none(),
        required=False,
        widget=forms.SelectMultiple(attrs={'class': 'form-select'}),
        label="Additional Services"
    )
    products = forms.ModelMultipleChoiceField(
        queryset=Product.objects.none(),
        required=False,
        widget=forms.SelectMultiple(attrs={'class': 'form-select'}),
        label="Products"
    )
    used_loyalty_points = forms.BooleanField(
        required=False,
        label="Use Loyalty Points"
    )

    class Meta:
        model = Payment
        fields = ['customer', 'additional_services', 'products', 'method', 'coupon', 'used_loyalty_points']
        widgets = {
            'method': forms.Select(attrs={'class': 'form-select'}),
            'coupon': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter coupon code'}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        self.appointment = kwargs.pop('appointment', None)
        super().__init__(*args, **kwargs)
        
        if self.user and self.user.business:
            self.fields['customer'].queryset = Customer.objects.filter(business=self.user.business)
            self.fields['additional_services'].queryset = Service.objects.filter(
                branch__business=self.user.business, is_active=True
            )
            self.fields['products'].queryset = Product.objects.filter(
                branch__business=self.user.business, is_active=True, stock_quantity__gt=0
            )
        
        if self.appointment:
            self.fields['customer'].initial = self.appointment.customer
            self.fields['customer'].required = True
            self.fields['customer'].widget.attrs['readonly'] = True
        else:
            self.fields['customer'].queryset = Customer.objects.filter(business=self.user.business)
            self.fields['customer'].widget = forms.Select(attrs={'class': 'form-select'})

    def clean_customer(self):
        customer = self.cleaned_data.get('customer')
        if self.appointment and not customer:
            return self.appointment.customer
        return customer

    def clean(self):
        cleaned_data = super().clean()
        customer = cleaned_data.get('customer')
        used_loyalty_points = cleaned_data.get('used_loyalty_points')
        additional_services = cleaned_data.get('additional_services')
        products = cleaned_data.get('products')

        if used_loyalty_points and not customer:
            raise forms.ValidationError("A customer must be selected to use loyalty points.")
        
        if additional_services and products:
            raise forms.ValidationError("You cannot select both services and products. Please choose one type.")

        return cleaned_data
class PromotionForm(forms.ModelForm):
    class Meta:
        model = Promotion
        fields = ['subject', 'message', 'sms_message']

class UserCreationForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput)
    role = forms.ModelChoiceField(queryset=Role.objects.none(), required=True)

    def __init__(self, *args, **kwargs):
        business = kwargs.pop('business', None)
        super().__init__(*args, **kwargs)
        if business:
            self.fields['role'].queryset = Role.objects.filter(business=business)
        else:
            self.fields['role'].queryset = Role.objects.none()

    def save(self, commit=True):
        user = super().save(commit=False)
        password = self.cleaned_data.get("password")
        if password:
            user.set_password(password)
        if commit:
            user.save()
        return user

    class Meta:
        model = User
        fields = ['username', 'email', 'password', 'role']
class BusinessForm(forms.ModelForm):
    class Meta:
        model = Business
        fields = ['name', 'address']

class AdminCreationForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput)
    class Meta:
        model = User
        fields = ['username', 'email', 'password']

class RoleForm(forms.ModelForm):
    class Meta:
        model = Role
        fields = ['name', 'features']
        widgets = {
            'features': forms.CheckboxSelectMultiple,
        }

class PositionForm(forms.ModelForm):
    class Meta:
        model = Position
        fields = ['name']

class BusinessHaircutPointsForm(forms.ModelForm):
    class Meta:
        model = Business
        fields = ['standard_haircut_points', 'loyalty_point_value']
        widgets = {
            'standard_haircut_points': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}),
            'loyalty_point_value': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }
class ServicePointsForm(forms.ModelForm):
    class Meta:
        model = ServicePoints
        fields = ['service', 'branch', 'loyalty_points']
        widgets = {
            'service': forms.Select(attrs={'class': 'form-select'}),
            'branch': forms.Select(attrs={'class': 'form-select'}),
            'loyalty_points': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}),
        }

    def __init__(self, *args, **kwargs):
        business = kwargs.pop('business', None)
        super().__init__(*args, **kwargs)
        if business:
            self.fields['service'].queryset = Service.objects.filter(branch__business=business)
            self.fields['branch'].queryset = Branch.objects.filter(business=business)
class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['branch', 'name', 'price', 'stock_quantity', 'sku', 'is_active']
        
class ServicePointsForm(forms.ModelForm):
    class Meta:
        model = ServicePoints
        fields = ['service', 'branch', 'loyalty_points', 'employee_points']
        widgets = {
            'service': forms.Select(attrs={'class': 'form-select'}),
            'branch': forms.Select(attrs={'class': 'form-select'}),
            'loyalty_points': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}),
            'employee_points': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}),
        }

    def __init__(self, *args, **kwargs):
        business = kwargs.pop('business', None)
        super().__init__(*args, **kwargs)
        if business:
            self.fields['service'].queryset = Service.objects.filter(branch__business=business)
            self.fields['branch'].queryset = Branch.objects.filter(business=business)
