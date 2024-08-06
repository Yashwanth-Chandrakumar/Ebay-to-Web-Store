from django.urls import path

from . import views

urlpatterns = [
    path('update-product/<str:item_id>/', views.update_product_view, name='update_product'),
    path('generate-html/', views.generate_html_view, name='generate_html'),
    path('products/', views.get_products, name='get_products'),
    path('fetch-items/', views.fetch_all_items, name='fetch_items'),
    path('product/<int:product_id>/', views.ProductDetailView.as_view(), name='product_detail'),
    
]