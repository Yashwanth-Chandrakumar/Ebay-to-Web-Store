from django.contrib.sitemaps.views import sitemap
from django.urls import path
from django.views.generic import TemplateView

from . import views
from .sitemaps import CustomPageSitemap, ProductSitemap
from .views import ProductLookupView
sitemaps = {
    'products': ProductSitemap,
    'static': CustomPageSitemap,
}

urlpatterns = [
    path("fetch-items/", views.fetch_all_items, name="fetch_items"),
    path("generate-html/", views.run_html_generation, name="generate_html_pages"),
    path('html-generation-progress/', views.get_html_generation_progress, name='html_generation_progress'),
    path("", views.landing_page, name="landing_page"),
    path("admin-view-1/", views.admin_page, name="admin_page"),
    path("admin-view-2/", views.admin_page2, name="admin_page2"),
    path("admin-view-3/", views.admin_page3, name="admin_page3"),
    path("admin-view-4/", views.admin_page4, name="admin_page4"),
    path("product/", views.product_list, name="product_list"),
    path("terms/", views.terms_view, name="terms"),
    path("product/<slug:product_slug>/", views.product_detail, name="product_detail"),
    path("cron/", views.cron, name="cron"),
    path("cleandesc/", views.clean_description, name="clean"),
    path("sync/", views.run_daily_update, name="sync"),
    # path('tasks/', views.get_running_tasks, name='tasks'),
    path("fetch-changelog/", views.fetch_changelog, name="fetch_changelog"),
    path("download-excel/", views.download_excel, name="download_excel"),
    path(
        "fetch-and-clean-descriptions/",
        views.fetch_and_print_descriptions,
        name="international",
    ),
    path("add-to-cart/<int:product_id>/", views.add_to_cart, name="add_to_cart"),
    path("cart/", views.view_cart, name="view_cart"),
    path("cart/update/<int:item_id>/", views.update_cart, name="update_cart"),
    path("cart/remove/<int:item_id>/", views.remove_from_cart, name="remove_from_cart"),
    path("checkout/", views.checkout, name="checkout"),
    path(
        "order-confirmation/<int:order_id>/",
        views.order_confirmation,
        name="order_confirmation",
    ),
    path("process-payment/", views.process_payment, name="process_payment"),
    path(
        "fetch-items-progress/",
        views.get_fetch_items_progress,
        name="fetch_items_progress",
    ),
    path("generate-report/", views.generate_report, name="generate_report_progress"),
    path("fetch-report-changelog/", views.fetch_report_log, name="fetch_report_log"),
    path("delete-report/", views.delete_report, name="delete_report"),
    path(
        "download-report-excel/",
        views.download_report_excel,
        name="download_report_excel",
    ),
    path(
        "cancel-report-task/",
        views.cancel_report_task,
        name="cancel_report_task",
    ),
    path(
        "report_progress/<str:task_id>/", views.report_progress, name="report_progress"
    ),
    path(
        "update_progress/<str:task_id>/", views.update_progress, name="update_progress"
    ),
    path("cancel-update/", views.cancel_update, name="cancel_update"),
    path("add-event/", views.add_event, name="add_event"),
    path('delete-event/<int:event_id>/', views.delete_event, name='delete_event'),
    # path("get-event/<int:event_id>/", views.get_event, name="get_event"),
    
    path('orders/', views.order_list, name='order_list'),
    path('order-details/<int:order_id>/', views.order_details, name='order_details'),
    path('sitemap.xml', sitemap, {'sitemaps': sitemaps}, name='django.contrib.sitemaps.views.sitemap'),
    path('robots.txt', TemplateView.as_view(template_name='robots.txt', content_type='text/plain')),
    path('discounts/', views.discount_list, name='discount_list'),
    path('discounts/create/', views.discount_create, name='discount_create'),
    path('discounts/<int:pk>/update/', views.discount_update, name='discount_update'),
    path('discounts/<int:pk>/delete/', views.discount_delete, name='discount_delete'),
    path('order_information.htm', views.order_information_redirect, name='order_information_redirect'),
    path('get-shipping-cost/<str:item_id>/', views.get_shipping_cost, name='get_shipping_cost'),
    path('product-lookup/', ProductLookupView.as_view(), name='product-lookup'),
    path('create-products/', views.create_products, name='create-products'),
    path('update-products/', views.update_products, name='update-products'),
]
