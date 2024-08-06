from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('products.urls')),  # Replace 'products' with your app name if different
]