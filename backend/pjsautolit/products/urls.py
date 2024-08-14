from django.urls import path

from . import views

urlpatterns = [
    path('fetch-items/', views.fetch_all_items, name='fetch_items'),
    path('generate-html/', views.generate_html_view, name='generate_html_pages'),
    path('', views.landing_page, name='landing_page'),
    path('admin-view/', views.admin_page, name='admin_page'),
    path('product/', views.product_list, name='product_list'),
    path('product/<slug:product_slug>/', views.product_detail, name='product_detail'),
    path('cron/', views.cron, name='cron'), 
]