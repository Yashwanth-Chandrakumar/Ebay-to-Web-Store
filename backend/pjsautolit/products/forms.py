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
from django import forms
from django.utils import timezone

from .models import Discount


class DiscountForm(forms.ModelForm):
    start_date = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={
            'type': 'datetime-local', 
            'class': 'w-full px-3 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500'
        }),
        initial=timezone.now
    )
    
    end_date = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={
            'type': 'datetime-local', 
            'class': 'w-full px-3 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500'
        }),
        required=False
    )

    class Meta:
        model = Discount
        fields = [
            'name', 'description', 'discount_type', 'discount_value', 
            'apply_to', 'product_tags', 'start_date', 'end_date', 
            'minimum_purchase_amount', 'is_active'
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'w-full px-3 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500',
                'pattern': '[A-Za-z0-9\-_]+',  # Allow letters, numbers, hyphens, and underscores
                'title': 'Enter a valid coupon code using letters, numbers, hyphens, or underscores'
            }),
            'description': forms.Textarea(attrs={'class': 'w-full px-3 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500', 'rows': 3}),
            'discount_type': forms.Select(attrs={'class': 'w-full px-3 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500'}),
            'discount_value': forms.NumberInput(attrs={'class': 'w-full px-3 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500'}),
            'apply_to': forms.Select(attrs={'class': 'w-full px-3 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500'}),
            'product_tags': forms.Textarea(attrs={
                'class': 'w-full px-3 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500', 
                'rows': 2,
                'placeholder': 'Enter comma-separated tags (e.g., smartphone, apple, 2023)'
            }),
            'minimum_purchase_amount': forms.NumberInput(attrs={'class': 'w-full px-3 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-checkbox h-5 w-5 text-blue-600'})
        }

    def clean_product_tags(self):
        product_tags = self.cleaned_data.get('product_tags', '')
        
        # Only validate tags if apply_to is SPECIFIC_PRODUCTS
        apply_to = self.cleaned_data.get('apply_to')
        if apply_to == 'SPECIFIC_PRODUCTS':
            if not product_tags:
                raise forms.ValidationError("Product tags are required when applying to specific products.")
        
        # Clean and validate tags
        if product_tags:
            # Remove extra spaces, convert to lowercase, remove duplicates
            tags = [tag.strip().lower() for tag in product_tags.split(',') if tag.strip()]
            tags = list(dict.fromkeys(tags))  # Remove duplicates while preserving order
            
            # Validate each tag
            for tag in tags:
                if not tag:
                    raise forms.ValidationError("Empty tags are not allowed.")
                if len(tag) > 100:  # Optional: Add a max length for tags
                    raise forms.ValidationError(f"Tag '{tag}' is too long. Maximum 100 characters.")
            
            return ', '.join(tags)
        return product_tags

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')

        if start_date and end_date and end_date < start_date:
            raise forms.ValidationError("End date must be after start date")

        return cleaned_data
    

    def clean_name(self):
        name = self.cleaned_data.get('name')
        discount_type = self.cleaned_data.get('discount_type')

        if discount_type == 'COUPON':
            # Convert to uppercase for coupon codes
            name = name.upper()
            
            # Validate coupon code format
            if not name.replace('-', '').replace('_', '').isalnum():
                raise forms.ValidationError("Coupon code can only contain letters, numbers, hyphens, and underscores")
            if len(name) < 4 or len(name) > 20:
                raise forms.ValidationError("Coupon code must be between 4 and 20 characters")

            # Check if coupon code already exists
            if Discount.objects.filter(name=name).exclude(pk=self.instance.pk if self.instance else None).exists():
                raise forms.ValidationError("This coupon code already exists")

        return name