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