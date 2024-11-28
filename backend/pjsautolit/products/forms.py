from django import forms

from .models import ShippingAddress


class ShippingAddressForm(forms.ModelForm):
    class Meta:
        model = ShippingAddress
        fields = ['first_name', 'last_name', 'email', 'phone', 
                 'address_line1', 'address_line2', 'city', 'state', 
                 'postal_code', 'country']
        widgets = {
            'address_line2': forms.TextInput(attrs={'placeholder': 'Apartment, suite, etc. (optional)'}),
            'phone': forms.TextInput(attrs={'placeholder': 'Format: (123) 456-7890'}),
            'postal_code': forms.TextInput(attrs={'placeholder': '5-digit ZIP code'})
        }


# forms.py
# forms.py
from django import forms
from django.utils import timezone

from .models import Discount


class DiscountForm(forms.ModelForm):
    start_date = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        initial=timezone.now
    )
    end_date = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        required=False
    )

    class Meta:
        model = Discount
        fields = [
            'name', 
            'description', 
            'discount_type', 
            'discount_value', 
            'apply_to', 
            'start_date', 
            'end_date', 
            'minimum_purchase_amount', 
            'is_active'
        ]

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        
        if start_date and end_date and end_date < start_date:
            raise forms.ValidationError("End date must be after start date")
        
        return cleaned_data