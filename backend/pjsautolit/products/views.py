import ast
import json
import os
import queue
import re
import threading
import time
import xml.etree.ElementTree as ET
from datetime import datetime

import requests
from django.conf import settings
from django.http import HttpResponse, HttpResponseNotFound, JsonResponse
from django.template import Context, Template
from django.views.decorators.http import require_GET
from django.views.generic.detail import DetailView
from requests.exceptions import HTTPError, RequestException

from .models import Product

EBAY_APP_ID = settings.EBAY_APP_ID
EBAY_AUTH_TOKEN = settings.EBAY_AUTH_TOKEN
FINDING_API_URL = "https://svcs.ebay.com/services/search/FindingService/v1"
BROWSE_API_URL = "https://api.ebay.com/buy/browse/v1/item/v1|{item_id}|0"


MAX_RETRIES = 5
RETRY_DELAY = 2  # Initial delay in seconds
def process_queue(q):
    while True:
        item = q.get()
        if item is None:
            break
        save_product_data(item)
        time.sleep(2)  # 2-second delay
        q.task_done()

@require_GET
def fetch_all_items(request):
    try:
        total_items = 0
        total_pages = 1
        current_page = 1

        # Create a queue and start worker threads
        q = queue.Queue()
        num_worker_threads = 5
        threads = []
        for _ in range(num_worker_threads):
            t = threading.Thread(target=process_queue, args=(q,))
            t.start()
            threads.append(t)

        while current_page <= total_pages:
            items, total_pages = fetch_finding_api_data(page_number=current_page)
            
            for item in items:
                item_id = item['item_id']
                browse_data = fetch_browse_api_data(item_id)
                combined_data = {**item, **browse_data}
                q.put(combined_data)
                total_items += 1

            current_page += 1

        # Block until all tasks are done
        q.join()

        # Stop worker threads
        for _ in range(num_worker_threads):
            q.put(None)
        for t in threads:
            t.join()

        return JsonResponse({
            "status": "success",
            "message": f"Fetched and stored information for {total_items} items",
            "total_items": total_items
        }, status=200)

    except Exception as e:
        return JsonResponse({
            "status": "error",
            "message": str(e)
        }, status=500)

@require_GET
def update_product_view(request, item_id):
    try:
        product = update_product(item_id)
        return JsonResponse({
            "status": "success",
            "message": f"Product {item_id} updated successfully",
            "product_id": product.id
        }, status=200)
    except Exception as e:
        return JsonResponse({
            "status": "error",
            "message": str(e)
        }, status=500)
def fetch_product_data(item_id):
    finding_data = fetch_finding_api_data(item_id)
    browse_data = fetch_browse_api_data(item_id)
    return {**finding_data, **browse_data}

def fetch_finding_api_data(item_id=None, page_number=1):
    headers = {
        "X-EBAY-SOA-SECURITY-APPNAME": EBAY_APP_ID,
        "X-EBAY-SOA-OPERATION-NAME": "findItemsAdvanced",
        "Content-Type": "application/xml"
    }
    
    xml_payload = f"""
    <findItemsAdvancedRequest xmlns="http://www.ebay.com/marketplace/search/v1/services">
      <itemFilter>
        <name>Seller</name>
        <value>pjsautolit</value>
      </itemFilter>
      <paginationInput>
        <pageNumber>{page_number}</pageNumber>
        <entriesPerPage>100</entriesPerPage>
      </paginationInput>
      <outputSelector>SellerInfo</outputSelector>
    </findItemsAdvancedRequest>
    """
    if item_id:
        xml_payload = xml_payload.replace('</findItemsAdvancedRequest>', f'<keywords>{item_id}</keywords></findItemsAdvancedRequest>')
    
    
    attempt = 0
    while attempt < MAX_RETRIES:
        try:
            response = requests.post(FINDING_API_URL, headers=headers, data=xml_payload)
            response.raise_for_status()
            root = ET.fromstring(response.content)
            namespace = {'ns': 'http://www.ebay.com/marketplace/search/v1/services'}
            
            items = root.findall('.//ns:item', namespace)
            total_pages = int(root.find('.//ns:totalPages', namespace).text)
            
            results = []
            for item in items:
                data = {
                    'item_id': item.find('ns:itemId', namespace).text,
                    'title': item.find('ns:title', namespace).text,
                    'global_id': item.find('ns:globalId', namespace).text,
                    'category_id': item.find('ns:primaryCategory/ns:categoryId', namespace).text,
                    'category_name': item.find('ns:primaryCategory/ns:categoryName', namespace).text,
                    'gallery_url': item.find('ns:galleryURL', namespace).text,
                    'view_item_url': item.find('ns:viewItemURL', namespace).text,
                    'auto_pay': item.find('ns:autoPay', namespace).text == 'true',
                    'postal_code': item.find('ns:postalCode', namespace).text,
                    'location': item.find('ns:location', namespace).text,
                    'country': item.find('ns:country', namespace).text,
                    'selling_state': item.find('ns:sellingStatus/ns:sellingState', namespace).text,
                    'time_left': item.find('ns:sellingStatus/ns:timeLeft', namespace).text,
                    'start_time': item.find('ns:listingInfo/ns:startTime', namespace).text,
                    'end_time': item.find('ns:listingInfo/ns:endTime', namespace).text,
                    'listing_type': item.find('ns:listingInfo/ns:listingType', namespace).text,
                    'best_offer_enabled': item.find('ns:listingInfo/ns:bestOfferEnabled', namespace).text == 'true',
                    'buy_it_now_available': item.find('ns:listingInfo/ns:buyItNowAvailable', namespace).text == 'true',
                    'gift': item.find('ns:listingInfo/ns:gift', namespace).text == 'true',
                    'watch_count': int(item.find('ns:listingInfo/ns:watchCount', namespace).text) if item.find('ns:listingInfo/ns:watchCount', namespace) is not None else None,
                    'returns_accepted': item.find('ns:returnsAccepted', namespace).text == 'true',
                    'is_multi_variation_listing': item.find('ns:isMultiVariationListing', namespace).text == 'true',
                    'top_rated_listing': item.find('ns:topRatedListing', namespace).text == 'true',
                    'seller_username': item.find('ns:sellerInfo/ns:sellerUserName', namespace).text,
                    'feedback_score': int(item.find('ns:sellerInfo/ns:feedbackScore', namespace).text),
                    'positive_feedback_percent': float(item.find('ns:sellerInfo/ns:positiveFeedbackPercent', namespace).text),
                    'feedback_rating_star': item.find('ns:sellerInfo/ns:feedbackRatingStar', namespace).text,
                    'top_rated_seller': item.find('ns:sellerInfo/ns:topRatedSeller', namespace).text == 'true',
                    'shipping_type': item.find('ns:shippingInfo/ns:shippingType', namespace).text,
                    'ship_to_locations': item.find('ns:shippingInfo/ns:shipToLocations', namespace).text,
                    'expedited_shipping': item.find('ns:shippingInfo/ns:expeditedShipping', namespace).text == 'true',
                    'one_day_shipping_available': item.find('ns:shippingInfo/ns:oneDayShippingAvailable', namespace).text == 'true',
                    'handling_time': int(item.find('ns:shippingInfo/ns:handlingTime', namespace).text) if item.find('ns:shippingInfo/ns:handlingTime', namespace) is not None else None,
                }
                results.append(data)
            
            return results, total_pages
        
        except (RequestException, HTTPError) as e:
            print(f"Error fetching FindingService API data (attempt {attempt + 1}): {e}")
            attempt += 1
            time.sleep(RETRY_DELAY * (2 ** attempt))  # Exponential backoff
    
    print(f"Failed to fetch FindingService API data after {MAX_RETRIES} attempts")
    return [], 0

def fetch_browse_api_data(item_id):
    url = BROWSE_API_URL.format(item_id=item_id)
    headers = {
        "Authorization": f"Bearer {EBAY_AUTH_TOKEN}",
        "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
        "X-EBAY-C-ENDUSERCTX": "affiliateCampaignId=<ePNCampaignId>,affiliateReferenceId=<referenceId>",
        "Content-Type": "application/json"
    }
    
    attempt = 0
    while attempt < MAX_RETRIES:
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            
            additional_images = data.get('additionalImages', [])
            additional_image_urls = [img['imageUrl'] for img in additional_images]
            
            return {
                'short_description': data.get('shortDescription', ''),
                'price': float(data['price']['value']),
                'currency': data['price']['currency'],
                'category_path': data.get('categoryPath', ''),
                'category_id_path': data.get('categoryIdPath', ''),
                'item_creation_date': data.get('itemCreationDate'),
                'estimated_availability_status': data.get('estimatedAvailabilities', [{}])[0].get('estimatedAvailabilityStatus', ''),
                'estimated_available_quantity': data.get('estimatedAvailabilities', [{}])[0].get('estimatedAvailableQuantity'),
                'estimated_sold_quantity': data.get('estimatedAvailabilities', [{}])[0].get('estimatedSoldQuantity'),
                'enabled_for_guest_checkout': data.get('enabledForGuestCheckout', False),
                'eligible_for_inline_checkout': data.get('eligibleForInlineCheckout', False),
                'lot_size': data.get('lotSize', 0),
                'legacy_item_id': data.get('legacyItemId', ''),
                'priority_listing': data.get('priorityListing', False),
                'adult_only': data.get('adultOnly', False),
                'listing_marketplace_id': data.get('listingMarketplaceId', ''),
                'shipping_service_code': data.get('shippingOptions', [{}])[0].get('shippingServiceCode', ''),
                'shipping_carrier_code': data.get('shippingOptions', [{}])[0].get('shippingCarrierCode', ''),
                'min_estimated_delivery_date': data.get('shippingOptions', [{}])[0].get('minEstimatedDeliveryDate'),
                'max_estimated_delivery_date': data.get('shippingOptions', [{}])[0].get('maxEstimatedDeliveryDate'),
                'shipping_cost': float(data.get('shippingOptions', [{}])[0].get('shippingCost', {}).get('value', 0)),
                'shipping_cost_type': data.get('shippingOptions', [{}])[0].get('shippingCostType', ''),
                'primary_image_url': data['image']['imageUrl'],
                'additional_image_urls': additional_image_urls,
            }
        except (RequestException, HTTPError) as e:
            print(f"Error fetching Browse API data (attempt {attempt + 1}): {e}")
            attempt += 1
            time.sleep(RETRY_DELAY * (2 ** attempt))  # Exponential backoff
    
    print(f"Failed to fetch Browse API data after {MAX_RETRIES} attempts")
    return {}

def save_product_data(data):
    product, created = Product.objects.update_or_create(
        item_id=data['item_id'],
        defaults={
            'title': data['title'],
            'global_id': data.get('global_id'),
            'category_id': data.get('category_id'),
            'category_name': data.get('category_name'),
            'gallery_url': data.get('gallery_url'),
            'view_item_url': data.get('view_item_url'),
            'auto_pay': data.get('auto_pay', False),
            'postal_code': data.get('postal_code'),
            'location': data.get('location'),
            'country': data.get('country'),
            'selling_state': data.get('selling_state'),
            'time_left': data.get('time_left'),
            'best_offer_enabled': data.get('best_offer_enabled', False),
            'buy_it_now_available': data.get('buy_it_now_available', False),
            'start_time': data.get('start_time'),
            'end_time': data.get('end_time'),
            'listing_type': data.get('listing_type'),
            'gift': data.get('gift', False),
            'watch_count': data.get('watch_count'),
            'returns_accepted': data.get('returns_accepted', False),
            'is_multi_variation_listing': data.get('is_multi_variation_listing', False),
            'top_rated_listing': data.get('top_rated_listing', False),
            'short_description': data.get('short_description', ''),
            'price': data.get('price'),
            'currency': data.get('currency'),
            'category_path': data.get('category_path', ''),
            'category_id_path': data.get('category_id_path', ''),
            'item_creation_date': data.get('item_creation_date'),
            'estimated_availability_status': data.get('estimated_availability_status', ''),
            'estimated_available_quantity': data.get('estimated_available_quantity'),
            'estimated_sold_quantity': data.get('estimated_sold_quantity'),
            'enabled_for_guest_checkout': data.get('enabled_for_guest_checkout', False),
            'eligible_for_inline_checkout': data.get('eligible_for_inline_checkout', False),
            'lot_size': data.get('lot_size', 0),
            'legacy_item_id': data.get('legacy_item_id', ''),
            'priority_listing': data.get('priority_listing', False),
            'adult_only': data.get('adult_only', False),
            'listing_marketplace_id': data.get('listing_marketplace_id', ''),
            'seller_username': data.get('seller_username'),
            'feedback_score': data.get('feedback_score'),
            'positive_feedback_percent': data.get('positive_feedback_percent'),
            'feedback_rating_star': data.get('feedback_rating_star'),
            'top_rated_seller': data.get('top_rated_seller', False),
            'shipping_type': data.get('shipping_type'),
            'ship_to_locations': data.get('ship_to_locations'),
            'expedited_shipping': data.get('expedited_shipping', False),
            'one_day_shipping_available': data.get('one_day_shipping_available', False),
            'handling_time': data.get('handling_time'),
            'shipping_service_code': data.get('shipping_service_code'),
            'shipping_carrier_code': data.get('shipping_carrier_code'),
            'min_estimated_delivery_date': data.get('min_estimated_delivery_date'),
            'max_estimated_delivery_date': data.get('max_estimated_delivery_date'),
            'shipping_cost': data.get('shipping_cost'),
            'shipping_cost_type': data.get('shipping_cost_type'),
            'primary_image_url': data.get('primary_image_url'),
            'additional_image_urls': data.get('additional_image_urls')
        }
    )
    print(f"Saved product: {product.title}") 
    return product

class ProductDetailView(DetailView):
    model = Product
    template_name = 'product_detail.html'
    context_object_name = 'product'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['additional_image_urls'] = self.object.additional_image_urls.split(',')
        return context

@require_GET
def generate_html_view(request):
    try:
        generate_html_pages()
        return JsonResponse({"status": "success"}, status=200)
    except Exception as e:
        print(f"Error generating HTML pages: {e}")
        return JsonResponse({"status": "error", "message": str(e)}, status=500)

def update_product(item_id):
    data = fetch_product_data(item_id)
    product = save_product_data(data)
    return product

def get_products(request):
    products = Product.objects.all().values()
    return JsonResponse(list(products), safe=False)

def update_product(item_id):
    data = fetch_product_data(item_id)
    product = save_product_data(data)
    return product

def generate_html_pages():
    output_dir = os.path.join(settings.BASE_DIR, 'products', 'viewproduct')
    os.makedirs(output_dir, exist_ok=True)

    products = Product.objects.all()
    errors = []

    # HTML template (you should replace this with your actual template)
    html_template = """
    <!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ product.title }}</title>
    <meta name="description" content="{{ product.short_description }}. Buy {{ product.title }} at the best price. Explore more details including condition, seller information, and shipping options.">
    <meta name="keywords" content="{{ product.title }}, {{ product.short_description }}, buy {{ product.title }}, {{ product.condition }}, {{ product.category_name }}, {{ product.category_id }}, eBay">
    <meta name="robots" content="index, follow">
    <meta property="og:title" content="{{ product.title }}">
    <meta property="og:description" content="{{ product.short_description }}. Buy {{ product.title }} at the best price.">
    <meta property="og:image" content="{{ product.primary_image_url }}">
    <meta property="og:url" content="{% url 'product_detail' product_id=product.id %}">
        <meta property="og:type" content="product">
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            margin: 0;
            padding: 0;
            background-color: #ffffff;
            color: #333;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }
        .product-container {
            display: flex;
            flex-wrap: wrap;
            gap: 40px;
        }
        .left-column {
            flex: 0 1 500px;
        }
        .right-column {
            flex: 1 1 300px;
        }
        .large-image-container {
            width: 500px;
            height: 500px;
            display: flex;
            align-items: center;
            justify-content: center;
            overflow: hidden;
            background-color: #f8f8f8;
        }
        .large-image {
            max-width: 100%;
            max-height: 100%;
            object-fit: contain;
        }
        .small-images {
            display: flex;
            flex-wrap: wrap;
            justify-content: flex-start;
            margin-top: 10px;
        }
        .small-images img {
            width: 60px;
            height: 60px;
            margin-right: 10px;
            margin-bottom: 10px;
            cursor: pointer;
            border: 1px solid #e5e5e5;
        }
        .product-title {
            font-size: 24px;
            font-weight: 700;
            margin-bottom: 10px;
        }
        .product-subtitle {
            font-size: 14px;
            color: #767676;
            margin-bottom: 20px;
        }
        .price {
            font-size: 24px;
            font-weight: 700;
            margin-bottom: 20px;
        }
        .add-to-cart-button {
            background-color: #3665f3;
            color: white;
            padding: 10px 20px;
            border: none;
            cursor: pointer;
            font-size: 16px;
            border-radius: 3px;
        }
        .add-to-cart-button:hover {
            background-color: #2b53cc;
        }
        .product-details {
            margin-top: 20px;
            border-top: 1px solid #e5e5e5;
            padding-top: 20px;
        }
        .product-details h2 {
            font-size: 18px;
            margin-bottom: 10px;
        }
        .product-details table {
            width: 100%;
            border-collapse: collapse;
        }
        .product-details td {
            padding: 8px;
            border-bottom: 1px solid #e5e5e5;
        }
        .product-details td:first-child {
            width: 40%;
            color: #767676;
        }
        .more-info{
            width: 100%;
            display: flex;
            justify-content: space-between;
            gap: 5rem;
        }
    </style>
</head>
<body>
        <div class="container">
            <div class="product-container">
                <div class="left-column">
                <div class="large-image-container">
        <img id="largeImage" class="large-image" src="{{ product.primary_image_url }}" alt="Product Image">
    </div>
    <div class="small-images">
        <img src="{{ product.primary_image_url }}" alt="Product Image" onclick="changeImage(this.src)">
        {% if additional_images %}
            {% for image in additional_images %}
                <img src="{{ image }}" alt="Product Image" onclick="changeImage(this.src)">
            {% endfor %}
        {% endif %}
    </div>
            </div>
                <div class="right-column">
                    <h1 class="product-title">{{ product.title }}</h1>
                    <p class="product-subtitle">{{ product.short_description }}</p>
                    <p class="price">{{ product.currency }} {{ product.price }}</p>
                    <button class="add-to-cart-button">Add to cart</button>
                    <div class="product-details">
                        <h2>Item specifics</h2>
                        <table>
                            <tr><td>Condition:</td><td>{{ product.condition }}</td></tr>
                            <tr><td>Category:</td><td>{{ product.category_name }}</td></tr>
                            <tr><td>Location:</td><td>{{ product.location }}</td></tr>
                            <tr><td>Country:</td><td>{{ product.country }}</td></tr>
                            <tr><td>Seller:</td><td>{{ product.seller_username }} (Feedback: {{ product.feedback_score }})</td></tr>
                            <tr><td>Listing Type:</td><td>{{ product.listing_type }}</td></tr>
                            <tr><td>Best Offer Enabled:</td><td>{{ product.best_offer_enabled|yesno:"Yes,No" }}</td></tr>
                            <tr><td>Buy It Now Available:</td><td>{{ product.buy_it_now_available|yesno:"Yes,No" }}</td></tr>
                            <tr><td>Returns Accepted:</td><td>{{ product.returns_accepted|yesno:"Yes,No" }}</td></tr>
                            <tr><td>Top Rated Listing:</td><td>{{ product.top_rated_listing|yesno:"Yes,No" }}</td></tr>
                        </table>
                    </div>
                </div>
                <div class="more-info">
                    <div class="product-details">
                        <h2>Availability</h2>
                        <table>
                            <tr><td>Status:</td><td>{{ product.estimated_availability_status }}</td></tr>
                            <tr><td>Available Quantity:</td><td>{{ product.estimated_available_quantity }}</td></tr>
                            <tr><td>Sold Quantity:</td><td>{{ product.estimated_sold_quantity }}</td></tr>
                            <tr><td>Lot Size:</td><td>{{ product.lot_size }}</td></tr>
                        </table>
                    </div>
                    <div class="product-details">
                        <h2>Shipping</h2>
                        <table>
                            <tr><td>Shipping Type:</td><td>{{ product.shipping_type }}</td></tr>
                            <tr><td>Ship To Locations:</td><td>{{ product.ship_to_locations }}</td></tr>
                            <tr><td>Expedited Shipping:</td><td>{{ product.expedited_shipping|yesno:"Yes,No" }}</td></tr>
                            <tr><td>One Day Shipping:</td><td>{{ product.one_day_shipping_available|yesno:"Yes,No" }}</td></tr>
                            <tr><td>Handling Time:</td><td>{{ product.handling_time }} day(s)</td></tr>
                            <tr><td>Shipping Service:</td><td>{{ product.shipping_service_code }}</td></tr>
                            <tr><td>Shipping Carrier:</td><td>{{ product.shipping_carrier_code }}</td></tr>
                            <tr><td>Estimated Delivery:</td><td>{{ product.min_estimated_delivery_date|date:"Y-m-d" }} - {{ product.max_estimated_delivery_date|date:"Y-m-d" }}</td></tr>
                            <tr><td>Shipping Cost:</td><td>{{ product.currency }} {{ product.shipping_cost }}</td></tr>
                        </table>
                    </div>
                </div>
                <div class="product-details">
                    <h2>Additional Information</h2>
                    <table>
                        <tr><td>Item ID:</td><td>{{ product.item_id }}</td></tr>
                        <tr><td>Global ID:</td><td>{{ product.global_id }}</td></tr>
                        <tr><td>Start Time:</td><td>{{ product.start_time|date:"Y-m-d H:i:s" }}</td></tr>
                        <tr><td>End Time:</td><td>{{ product.end_time|date:"Y-m-d H:i:s" }}</td></tr>
                        <tr><td>Time Left:</td><td>{{ product.time_left }}</td></tr>
                        <tr><td>Watch Count:</td><td>{{ product.watch_count }}</td></tr>
                        <tr><td>Adult Only:</td><td>{{ product.adult_only|yesno:"Yes,No" }}</td></tr>
                        <tr><td>Top Rated Seller:</td><td>{{ product.top_rated_seller|yesno:"Yes,No" }}</td></tr>
                    </table>
                </div>
            </div>
        </div>
        <script>
function changeImage(src) {
    document.getElementById('largeImage').src = src;
}
</script>
    </body>
</html>


    """

    for product in products:
        # Parse the string representation of the list into an actual list
        if product.additional_image_urls:
            try:
                additional_images = ast.literal_eval(product.additional_image_urls)
                # Ensure all items are strings and strip any whitespace
                additional_images = [str(url).strip() for url in additional_images if url]
            except:
                # If there's any error in parsing, default to an empty list
                additional_images = []
        else:
            additional_images = []
        context = {
            'product': product,
            'additional_images': additional_images
        }
        rendered_html = Template(html_template).render(Context(context))
        filename = f"{product.item_id}.html"
        filepath = os.path.join(output_dir, filename)
        try:
            with open(filepath, 'w', encoding='utf-8') as file:
                file.write(rendered_html)
        except Exception as e:
            errors.append(str(e))

    if errors:
        print(f"Errors encountered while generating HTML pages: {errors}")
    else:
        print("HTML pages generated successfully.")

def sanitize_filename(filename):
    # Replace invalid characters with underscores
    return re.sub(r'[<>:"/\\|?*]', '_', filename)


from django.shortcuts import render


def landing_page(request):
    return render(request, 'pages/landing.html')


from django.core.paginator import Paginator
# views.py
from django.shortcuts import get_object_or_404, render

from .models import Product


def product_list(request):
    products = Product.objects.all()
    paginator = Paginator(products, 10)  # Show 10 products per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    return render(request, 'pages/product_list.html', {'page_obj': page_obj})

def product_detail(request, product_id):
    html_file_path = os.path.join('products','viewproduct', f'{product_id}.html')

    # Check if the file exists
    if os.path.exists(html_file_path):
        with open(html_file_path, 'r') as file:
            html_content = file.read()
        return HttpResponse(html_content)
    else:
        return HttpResponseNotFound('Page not found')


def cron(request):
    return HttpResponse("Happy")