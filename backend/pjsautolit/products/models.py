from django.db import models


class Product(models.Model):
    item_id = models.CharField(max_length=100, unique=True)
    title = models.CharField(max_length=255)
    global_id = models.CharField(max_length=20, blank=True, null=True)
    category_id = models.CharField(max_length=20, blank=True, null=True)
    category_name = models.CharField(max_length=255, blank=True, null=True)
    gallery_url = models.URLField(blank=True, null=True)
    view_item_url = models.URLField(blank=True, null=True)
    auto_pay = models.BooleanField(default=False)
    postal_code = models.CharField(max_length=10, blank=True, null=True)
    location = models.CharField(max_length=100, blank=True, null=True)
    country = models.CharField(max_length=2, blank=True, null=True)
    selling_state = models.CharField(max_length=20, blank=True, null=True)
    time_left = models.CharField(max_length=20, blank=True, null=True)
    best_offer_enabled = models.BooleanField(default=False)
    buy_it_now_available = models.BooleanField(default=False)
    start_time = models.DateTimeField(null=True, blank=True)
    end_time = models.DateTimeField(null=True, blank=True)
    listing_type = models.CharField(max_length=20, blank=True, null=True)
    gift = models.BooleanField(default=False)
    watch_count = models.IntegerField(null=True, blank=True)
    returns_accepted = models.BooleanField(default=False)
    is_multi_variation_listing = models.BooleanField(default=False)
    top_rated_listing = models.BooleanField(default=False)
    short_description = models.TextField(blank=True, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, blank=True, null=True)
    category_path = models.CharField(max_length=255, blank=True, null=True)
    category_id_path = models.CharField(max_length=100, blank=True, null=True)
    item_creation_date = models.DateTimeField(null=True, blank=True)
    estimated_availability_status = models.CharField(max_length=20, blank=True, null=True)
    estimated_available_quantity = models.IntegerField(null=True, blank=True)
    estimated_sold_quantity = models.IntegerField(null=True, blank=True)
    enabled_for_guest_checkout = models.BooleanField(default=False)
    eligible_for_inline_checkout = models.BooleanField(default=False)
    lot_size = models.IntegerField(default=0)
    legacy_item_id = models.CharField(max_length=100, blank=True, null=True)
    priority_listing = models.BooleanField(default=False)
    adult_only = models.BooleanField(default=False)
    listing_marketplace_id = models.CharField(max_length=20, blank=True, null=True)
    seller_username = models.CharField(max_length=100, blank=True, null=True)
    feedback_score = models.IntegerField(null=True, blank=True)
    positive_feedback_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    feedback_rating_star = models.CharField(max_length=20, blank=True, null=True)
    top_rated_seller = models.BooleanField(default=False)
    shipping_type = models.CharField(max_length=20, blank=True, null=True)
    ship_to_locations = models.CharField(max_length=100, blank=True, null=True)
    expedited_shipping = models.BooleanField(default=False)
    one_day_shipping_available = models.BooleanField(default=False)
    handling_time = models.IntegerField(null=True, blank=True)
    shipping_service_code = models.CharField(max_length=50, blank=True, null=True)
    shipping_carrier_code = models.CharField(max_length=20, blank=True, null=True)
    min_estimated_delivery_date = models.DateTimeField(null=True, blank=True)
    max_estimated_delivery_date = models.DateTimeField(null=True, blank=True)
    shipping_cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    shipping_cost_type = models.CharField(max_length=20, blank=True, null=True)
    primary_image_url = models.URLField(blank=True, null=True)
    additional_image_urls = models.TextField(blank=True, null=True)
    html_link = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return self.title
    
class FetchStatus(models.Model):
    FETCH_TYPES = (
        ('initial', 'Initial Fetch'),
        ('daily', 'Daily Update'),
    )
    fetch_type = models.CharField(max_length=10, choices=FETCH_TYPES, unique=True)
    last_processed_page = models.IntegerField(default=0)
    last_processed_id = models.CharField(max_length=50, blank=True)
    last_run = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.get_fetch_type_display()} - Last run: {self.last_run}"