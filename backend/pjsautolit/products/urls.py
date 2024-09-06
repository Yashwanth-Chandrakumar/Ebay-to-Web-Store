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
    path('cleandesc/', views.clean_description, name='clean'), 
    path('sync/', views.run_daily_update, name='sync'), 
    # path('tasks/', views.get_running_tasks, name='tasks'), 
    path('fetch-changelog/', views.fetch_changelog, name='fetch_changelog'),
    path('download-excel/', views.download_excel, name='download_excel'),
    path('fetch-and-clean-descriptions/', views.fetch_and_print_descriptions, name='international'),
    path('add-to-cart/<int:product_id>/', views.add_to_cart, name='add_to_cart'),
    path('cart/', views.view_cart, name='view_cart'),
    path('cart/update/<int:item_id>/', views.update_cart, name='update_cart'),
    path('cart/remove/<int:item_id>/', views.remove_from_cart, name='remove_from_cart'),
    path('checkout/', views.checkout, name='checkout'),
    path('order-confirmation/<int:order_id>/', views.order_confirmation, name='order_confirmation'),
path('process-payment/', views.process_payment, name='process_payment'),

]

