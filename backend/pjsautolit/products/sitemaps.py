from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from .models import Product


class ProductSitemap(Sitemap):
    changefreq = 'weekly'
    priority = 0.8

    def items(self):
        return Product.objects.all()

    def location(self, obj):
        return f'/product/{obj.html_link}'

    def lastmod(self, obj):
        return obj.item_creation_date
    

from django.contrib.sitemaps import Sitemap
from django.urls import reverse


class CustomPageSitemap(Sitemap):
    changefreq = 'monthly'
    priority = 0.5

    def items(self):
        return [
            'landing_page',
            'product_list',
            'terms',
            'admin_page',
            'admin_page2', 
            'admin_page3', 
            'admin_page4',
            'view_cart',
            'checkout',
            'order_list',
        ]

    def location(self, item):
        return reverse(item)