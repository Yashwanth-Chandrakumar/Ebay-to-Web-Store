
import ast
import json
import os
import queue
import re
import threading
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from signal import signal

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
FINDING_API_URL = "https://svcs.ebay.com/services/search/FindingService/v1" #gets basic info
BROWSE_API_URL = "https://api.ebay.com/buy/browse/v1/item/v1|{item_id}|0" #gets detailed info

MAX_RETRIES = 5
RETRY_DELAY = 2  # Initial delay in seconds

def process_queue(q):
    while True:
        item = q.get()
        if item is None:
            break
        try:
            save_product_data(item)
        except Exception as e:
            print(f"Error saving product data: {e}")
        time.sleep(2)  # 2-second delay
        q.task_done()

@require_GET
def fetch_all_items(request):
    total_items = 0
    min_price = 01.00
    max_price = 10.00
    price_increment = 10.00

    q = queue.Queue()
    num_worker_threads = 5
    threads = []

    # Start worker threads
    for _ in range(num_worker_threads):
        t = threading.Thread(target=process_queue, args=(q,))
        t.start()
        threads.append(t)

    try:
        is_first_range = False
        while min_price <= 4000.00:  # Assuming 600 is the maximum price as per your example
            if is_first_range:
                current_page = 50  
                is_first_range = False
            else:
                current_page = 1
            total_pages = 1

            while current_page <= total_pages:
                try:
                    items, total_pages = fetch_finding_api_data(page_number=current_page, min_price=min_price, max_price=max_price)
                    
                    # for item in items:
                    #     item_id = item['item_id']
                    #     try:
                    #         browse_data = fetch_browse_api_data(item_id)
                    #         print(f"product covered {item_id} in page {current_page}, price range ${min_price}-${max_price}")
                    #         combined_data = {**item, **browse_data}
                    #         q.put(combined_data)
                    #         total_items += 1
                    #     except Exception as e:
                    #         print(f"Error processing item {item_id}: {e}")
                    for item in items:
                        item_id = item['item_id']
                        try:
                            if not Product.objects.filter(item_id=item_id).exists():
                                browse_data = fetch_browse_api_data(item_id)
                                combined_data = {**item, **browse_data}
                                q.put(combined_data)
                                total_items += 1
                            else:
                                print(f"product skipped {item_id} in page {current_page}, price range ${min_price}-${max_price}")
                        except Exception as e:
                            print(f"Error processing item {item_id}: {e}")
                    
                except Exception as e:
                    print(f"Error fetching data for page {current_page}, price range ${min_price}-${max_price}: {e}")
                
                current_page += 1

            min_price = max_price + 0.01
            max_price += price_increment

        # Wait for the queue to be processed
        q.join()

        # Stop worker threads
        for _ in range(num_worker_threads):
            q.put(None)
        for t in threads:
            t.join()

        # Generate HTML pages after fetching all items
        try:
            generate_html_pages()
        except Exception as e:
            print(f"Error generating HTML pages: {e}")

        return JsonResponse({
            "status": "success",
            "message": f"Fetched and stored information for {total_items} items",
            "total_items": total_items
        }, status=200)

    except Exception as e:
        print(f"Error in fetch_all_items: {e}")
        return JsonResponse({
            "status": "error",
            "message": str(e)
        }, status=500)

# def fetch_product_data(item_id):
#     finding_data = fetch_finding_api_data(item_id)
#     browse_data = fetch_browse_api_data(item_id)
#     return {**finding_data, **browse_data}

import xml.etree.ElementTree as ET

from requests.exceptions import HTTPError, RequestException


def fetch_finding_api_data(page_number=1, min_price=1.00, max_price=10.00):
    headers = {
        "X-EBAY-SOA-SECURITY-APPNAME": "YASHWANT-pjauto-PRD-7c6937daa-890b1640",
        "X-EBAY-SOA-OPERATION-NAME": "findItemsIneBayStores",
        "Content-Type": "text/xml"
    }
    
    xml_payload = f"""<?xml version="1.0" encoding="UTF-8"?>
    <findItemsIneBayStoresRequest xmlns="http://www.ebay.com/marketplace/search/v1/services">
        <storeName>PJ's Auto Literature</storeName>
        <outputSelector>StoreInfo</outputSelector>
        <itemFilter>
            <name>MinPrice</name>
            <value>{min_price:.2f}</value>
            <paramName>Currency</paramName>
            <paramValue>USD</paramValue>
        </itemFilter>
        <itemFilter>
            <name>MaxPrice</name>
            <value>{max_price:.2f}</value>
            <paramName>Currency</paramName>
            <paramValue>USD</paramValue>
        </itemFilter>
        <paginationInput>
            <pageNumber>{page_number}</pageNumber>
            <entriesPerPage>100</entriesPerPage>
        </paginationInput>
    </findItemsIneBayStoresRequest>"""
    
    attempt = 0
    while attempt < MAX_RETRIES:
        try:
            response = requests.post(FINDING_API_URL, headers=headers, data=xml_payload)
            response.raise_for_status()
            
            root = ET.fromstring(response.content)
            namespace = {'ns': 'http://www.ebay.com/marketplace/search/v1/services'}
            
            # Check for eBay API errors
            ack = root.find('.//ns:ack', namespace)
            if ack is not None and ack.text != 'Success':
                error_message = root.find('.//ns:errorMessage/ns:error/ns:message', namespace)
                error_code = root.find('.//ns:errorMessage/ns:error/ns:errorId', namespace)
                if error_message is not None and error_code is not None:
                    raise Exception(f"eBay API Error {error_code.text}: {error_message.text}")
                else:
                    raise Exception(f"Unknown eBay API Error: {ack.text}")
            
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
                        'shipping_type': item.find('ns:shippingInfo/ns:shippingType', namespace).text,
                        'ship_to_locations': item.find('ns:shippingInfo/ns:shipToLocations', namespace).text,
                        'expedited_shipping': item.find('ns:shippingInfo/ns:expeditedShipping', namespace).text == 'true',
                        'one_day_shipping_available': item.find('ns:shippingInfo/ns:oneDayShippingAvailable', namespace).text == 'true',
                        'handling_time': int(item.find('ns:shippingInfo/ns:handlingTime', namespace).text) if item.find('ns:shippingInfo/ns:handlingTime', namespace) is not None else None,
                        'price': float(item.find('ns:sellingStatus/ns:currentPrice', namespace).text),
                        'selling_state': item.find('ns:sellingStatus/ns:sellingState', namespace).text,
                        'time_left': item.find('ns:sellingStatus/ns:timeLeft', namespace).text,
                        'best_offer_enabled': item.find('ns:listingInfo/ns:bestOfferEnabled', namespace).text == 'true',
                        'buy_it_now_available': item.find('ns:listingInfo/ns:buyItNowAvailable', namespace).text == 'true',
                        'start_time': item.find('ns:listingInfo/ns:startTime', namespace).text,
                        'end_time': item.find('ns:listingInfo/ns:endTime', namespace).text,
                        'listing_type': item.find('ns:listingInfo/ns:listingType', namespace).text,
                        'gift': item.find('ns:listingInfo/ns:gift', namespace).text == 'true',
                        'watch_count': int(item.find('ns:listingInfo/ns:watchCount', namespace).text) if item.find('ns:listingInfo/ns:watchCount', namespace) is not None else None,
                        'returns_accepted': item.find('ns:returnsAccepted', namespace).text == 'true',
                        'is_multi_variation_listing': item.find('ns:isMultiVariationListing', namespace).text == 'true',
                        'top_rated_listing': item.find('ns:topRatedListing', namespace).text == 'true',
                    }
                results.append(data)
            
            return results, total_pages
        
        except (RequestException, HTTPError) as e:
            print(f"HTTP Error (attempt {attempt + 1}): {e}")
            print(f"Response status code: {response.status_code}")
            print(f"Response headers: {response.headers}")
            print(f"Response content: {response.content.decode('utf-8')}")
        except ET.ParseError as e:
            print(f"XML Parsing Error (attempt {attempt + 1}): {e}")
            print(f"Response content: {response.content.decode('utf-8')}")
        except Exception as e:
            print(f"General Error (attempt {attempt + 1}): {e}")
        
        attempt += 1
        time.sleep(RETRY_DELAY * (2 ** attempt))  # Exponential backoff
    
    print(f"Failed to fetch FindingService API data after {MAX_RETRIES} attempts")
    return [], 0

def fetch_new_access_token():
    url = "https://api.ebay.com/identity/v1/oauth2/token"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": "Basic WUFTSFdBTlQtcGphdXRvLVBSRC03YzY5MzdkYWEtODkwYjE2NDA6UFJELWM2OTM3ZGFhZGRhOC0yNzgxLTQzMzYtODdlNi0zYzdk"  # Replace with your actual credentials
    }
    data = {
        "grant_type": "refresh_token",
        "refresh_token": "v^1.1#i^1#r^1#p^3#f^0#I^3#t^Ul4xMF8yOjk1RkIxOTc4NDZCODU2MjYxOUUxNjFDRjhFRkZCM0RCXzBfMSNFXjI2MA=="  # Replace with your actual refresh token
    }

    try:
        response = requests.post(url, headers=headers, data=data)
        response.raise_for_status()
        token_data = response.json()
        access_token = token_data.get("access_token")
        
        if access_token:
            # Update the EBAY_AUTH_TOKEN in settings
            settings.EBAY_AUTH_TOKEN = access_token
            return access_token
        else:
            raise ValueError("Failed to obtain access token.")
    except (RequestException, HTTPError) as e:
        print(f"Error fetching new access token: {e}")
        return None
    
import time
from threading import Lock

# Global variables for rate limiting
RATE_LIMIT_PER_SECOND = 5  # Adjust this based on eBay's guidelines
RATE_LIMIT_PERIOD = 1.0  # 1 second
token_bucket = RATE_LIMIT_PER_SECOND
last_request_time = time.time()
bucket_lock = Lock()

def fetch_browse_api_data(item_id):
    global token_bucket, last_request_time

    url = BROWSE_API_URL.format(item_id=item_id)
    
    headers = {
        "Authorization": f"Bearer {settings.EBAY_AUTH_TOKEN}",
        "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
        "X-EBAY-C-ENDUSERCTX": "sessionId=12345"
    }

    attempt = 0
    while attempt < MAX_RETRIES:
        try:
            with bucket_lock:
                current_time = time.time()
                time_passed = current_time - last_request_time
                token_bucket += time_passed * (RATE_LIMIT_PER_SECOND / RATE_LIMIT_PERIOD)
                if token_bucket > RATE_LIMIT_PER_SECOND:
                    token_bucket = RATE_LIMIT_PER_SECOND
                
                if token_bucket < 1:
                    sleep_time = (1 - token_bucket) * (RATE_LIMIT_PERIOD / RATE_LIMIT_PER_SECOND)
                    time.sleep(sleep_time)
                    token_bucket = 1
                
                token_bucket -= 1
                last_request_time = time.time()

            response = requests.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            item_data = data.get('item', {})
            additional_images = data.get('additionalImages', [])
            additional_image_urls = [img['imageUrl'] for img in additional_images]
            return {
                'description': data.get('description', ''),
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

        except HTTPError as e:
            if response.status_code == 401:  # Unauthorized
                print("Access token expired, fetching a new one...")
                new_token = fetch_new_access_token()
                if new_token:
                    headers["Authorization"] = f"Bearer {new_token}"
                    continue
            print(f"Error fetching Browse API data (attempt {attempt + 1}): {e}")
            attempt += 1
            time.sleep(RETRY_DELAY * (2 ** attempt))  # Exponential backoff

        except RequestException as e:
            print(f"Error fetching Browse API data (attempt {attempt + 1}): {e}")
            attempt += 1
            time.sleep(RETRY_DELAY * (2 ** attempt))  # Exponential backoff

    print(f"Failed to fetch Browse API data after {MAX_RETRIES} attempts")
    return {}
import re

from bs4 import BeautifulSoup
from django.utils.text import slugify


def save_product_data(product_data):
    try:
        sanitized_name = slugify(product_data['title'])
        base_name = sanitized_name
        counter = 1
        while Product.objects.filter(html_link=sanitized_name).exists():
            sanitized_name = f"{base_name}-{counter}"
            counter += 1

        description = product_data.get('description', '')
        cleaned_description = clean_description(description)
        print(cleaned_description)

        product, created = Product.objects.update_or_create(
            item_id=product_data['item_id'],
            defaults={
                'title': product_data['title'],
                'global_id': product_data.get('global_id'),
                'category_id': product_data.get('category_id'),
                'category_name': product_data.get('category_name'),
                'gallery_url': product_data.get('gallery_url'),
                'view_item_url': product_data.get('view_item_url'),
                'auto_pay': product_data.get('auto_pay', False),
                'postal_code': product_data.get('postal_code'),
                'location': product_data.get('location'),
                'country': product_data.get('country'),
                'selling_state': product_data.get('selling_state'),
                'time_left': product_data.get('time_left'),
                'best_offer_enabled': product_data.get('best_offer_enabled', False),
                'buy_it_now_available': product_data.get('buy_it_now_available', False),
                'start_time': product_data.get('start_time'),
                'end_time': product_data.get('end_time'),
                'listing_type': product_data.get('listing_type'),
                'gift': product_data.get('gift', False),
                'watch_count': product_data.get('watch_count'),
                'returns_accepted': product_data.get('returns_accepted', False),
                'is_multi_variation_listing': product_data.get('is_multi_variation_listing', False),
                'top_rated_listing': product_data.get('top_rated_listing', False),
                'short_description': cleaned_description,  # Use the parsed description here
                'price': product_data.get('price'),
                'currency': product_data.get('currency'),
                'category_path': product_data.get('category_path', ''),
                'category_id_path': product_data.get('category_id_path', ''),
                'item_creation_date': product_data.get('item_creation_date'),
                'estimated_availability_status': product_data.get('estimated_availability_status', ''),
                'estimated_available_quantity': product_data.get('estimated_available_quantity'),
                'estimated_sold_quantity': product_data.get('estimated_sold_quantity'),
                'enabled_for_guest_checkout': product_data.get('enabled_for_guest_checkout', False),
                'eligible_for_inline_checkout': product_data.get('eligible_for_inline_checkout', False),
                'lot_size': product_data.get('lot_size', 0),
                'legacy_item_id': product_data.get('legacy_item_id', ''),
                'priority_listing': product_data.get('priority_listing', False),
                'adult_only': product_data.get('adult_only', False),
                'listing_marketplace_id': product_data.get('listing_marketplace_id', ''),
                'seller_username': product_data.get('seller_username'),
                'feedback_score': product_data.get('feedback_score'),
                'positive_feedback_percent': product_data.get('positive_feedback_percent'),
                'feedback_rating_star': product_data.get('feedback_rating_star'),
                'top_rated_seller': product_data.get('top_rated_seller', False),
                'shipping_type': product_data.get('shipping_type'),
                'ship_to_locations': product_data.get('ship_to_locations'),
                'expedited_shipping': product_data.get('expedited_shipping', False),
                'one_day_shipping_available': product_data.get('one_day_shipping_available', False),
                'handling_time': product_data.get('handling_time'),
                'shipping_service_code': product_data.get('shipping_service_code'),
                'shipping_carrier_code': product_data.get('shipping_carrier_code'),
                'min_estimated_delivery_date': product_data.get('min_estimated_delivery_date'),
                'max_estimated_delivery_date': product_data.get('max_estimated_delivery_date'),
                'shipping_cost': product_data.get('shipping_cost'),
                'shipping_cost_type': product_data.get('shipping_cost_type'),
                'primary_image_url': product_data.get('primary_image_url'),
                'additional_image_urls': product_data.get('additional_image_urls'),
                'html_link': sanitized_name,
            }
        )
        if created:
            print(f"Created new product: {product_data['title']} - {product_data['item_id']}")
        else:
            print(f"Updated existing product: {product_data['title']} - {product_data['item_id']}")
        
        # Generate and save HTML

    except Exception as e:
        print(f"Error saving product data: {e}")
        print(f"Product data: {product_data['item_id']}")

def generate_html_view(request):
    try:
        generate_html_pages()
        return JsonResponse({"status": "success", "message": "HTML pages generated successfully"})
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)

def generate_html_pages():
    output_dir = os.path.join(settings.BASE_DIR, 'products', 'viewproduct')
    os.makedirs(output_dir, exist_ok=True)

    products = Product.objects.all()
    errors = []
    from django.template import loader

    # HTML template (should replace this with your actual template tell to chao during production)
    try:
        template = loader.get_template('pages/template.html')
    except Exception as e:
        print(f"Error loading template: {e}")
        return

    for product in products:
        # product.short_description = clean_description(product.short_description)
       
        if product.additional_image_urls:
            try:
                additional_images = ast.literal_eval(product.additional_image_urls)
                
                additional_images = [str(url).strip() for url in additional_images if url]
            except:
                print(f"Error parsing additional image URLs for product {product.item_id}: {e}")
                additional_images = []
        else:
            additional_images = []
        context = {
            'product': product,
            'additional_images': additional_images
        }
        try:
            rendered_html = template.render(context)
        except Exception as e:
            errors.append(f"Error rendering HTML for product {product.item_id}: {e}")
            continue
        filename = f"{product.html_link}.html"
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


from django.shortcuts import render


def landing_page(request):
    return render(request, 'pages/landing.html')

def admin_page(request):
    return render(request,'pages/admin.html')

from django.core.paginator import Paginator
# views.py
from django.shortcuts import get_object_or_404, render

from .models import Product


def product_list(request):
    query = request.GET.get('query', '')
    products = Product.objects.all()

    if query:
        products = products.filter(title__icontains=query)

    paginator = Paginator(products, 10)  # Show 10 products per page.
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'query': query
    }
    return render(request, 'pages/product_list.html', context)

def product_detail(request, product_slug):
    product = get_object_or_404(Product, html_link=product_slug)
    html_file_path = os.path.join('products', 'viewproduct', f'{product.html_link}.html')

    if os.path.exists(html_file_path):
        with open(html_file_path, 'r') as file:
            html_content = file.read()
        return HttpResponse(html_content)
    else:
        return HttpResponseNotFound('Page not found')


def cron(request):
    return HttpResponse("Happy")

import re

from bs4 import BeautifulSoup


def clean_description(description):
    # Check if the description is HTML
    if '<' in description and '>' in description:
        # Parse the HTML and extract the text content
        soup = BeautifulSoup(description, 'html.parser')
        text_content = soup.get_text()
    else:
        # If it's not HTML, use the description as is
        text_content = description
    
    # Remove unwanted characters
    cleaned_text = text_content.replace("Â", "")
    
    # Remove everything after "**Please check out**"
    cleaned_text = re.split(r'Please check out', cleaned_text, flags=re.IGNORECASE)[0]
    
    # Remove extra whitespace
    cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip()
    
    return cleaned_text

import queue
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from django.db.models import Q
from django.utils import timezone

from .models import FetchStatus, Product, ProductChangeLog

MAX_WORKERS = 30 

def process_price_range(min_price, max_price, existing_item_ids, updated_item_ids_queue):
    print(f"Processing price range: ${min_price:.2f} - ${max_price:.2f}")
    current_page = 1
    total_pages = 1
    local_updated_item_ids = set()
    
    # Fields to ignore for updates
    ignore_fields = {'time_left', 'start_time', 'end_time'}

    while current_page <= total_pages:
        try:
            items, total_pages = fetch_finding_api_data(page_number=current_page, min_price=min_price, max_price=max_price)
            print(f"Fetched page {current_page} of {total_pages} for price range ${min_price:.2f} - ${max_price:.2f}")

            for item in items:
                item_id = item['item_id']
                local_updated_item_ids.add(item_id)
                
                try:
                    product = Product.objects.get(item_id=item_id)
                    changes = {}
                    for key, value in item.items():
                        if key not in ignore_fields and hasattr(product, key):
                            current_value = getattr(product, key)
                            if current_value != value:
                                changes[key] = value
                    
                    if changes:
                        for key, value in changes.items():
                            setattr(product, key, value)
                        product.save()
                        print(f"Updated product: {item_id} - {product.title}")
                        print(f"Changes: {changes}")
                        ProductChangeLog.objects.create(
                            item_id=item_id,
                            product_name=product.title,
                            operation='updated'
                        )
                    else:
                        print(f"No significant changes for product: {item_id} - {product.title}")
                except Product.DoesNotExist:
                    browse_data = fetch_browse_api_data(item_id)
                    combined_data = {**item, **browse_data}
                    new_product = Product.objects.create(**combined_data)
                    print(f"Created new product: {item_id} - {new_product.title}")
                    ProductChangeLog.objects.create(
                        item_id=item_id,
                        product_name=new_product.title,
                        operation='created'
                    )
            
            current_page += 1
            
        except Exception as e:
            print(f"Error fetching data for page {current_page}, price range ${min_price:.2f} - ${max_price:.2f}: {e}")

    updated_item_ids_queue.put(local_updated_item_ids)

def daily_update():
    print("Starting daily update...")
    fetch_status, created = FetchStatus.objects.get_or_create(fetch_type='daily')
    
    existing_item_ids = set(Product.objects.values_list('item_id', flat=True))
    updated_item_ids_queue = queue.Queue()

    price_ranges = []
    min_price = 01.00
    max_price = 10.00
    price_increment = 10.00

    while min_price <= 4000.00:
        price_ranges.append((min_price, max_price))
        min_price = max_price + 0.01
        max_price += price_increment

    executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)
    futures = []

    try:
        for min_price, max_price in price_ranges:
            future = executor.submit(process_price_range, min_price, max_price, existing_item_ids, updated_item_ids_queue)
            futures.append(future)

        for future in as_completed(futures):
            future.result()  # This will raise any exceptions that occurred in the thread

    except KeyboardInterrupt:
        print("Interrupted by user, shutting down...")
    finally:
        executor.shutdown(wait=True)

    updated_item_ids = set()
    while not updated_item_ids_queue.empty():
        updated_item_ids.update(updated_item_ids_queue.get())

    deleted_item_ids = existing_item_ids - updated_item_ids
    for item_id in deleted_item_ids:
        product = Product.objects.get(item_id=item_id)
        product_name = product.title
        product.delete()
        print(f"Deleted product: {item_id} - {product_name}")
        ProductChangeLog.objects.create(
            item_id=item_id,
            product_name=product_name,
            operation='deleted'
        )
    
    fetch_status.last_run = timezone.now()
    fetch_status.save()
    
    print("Daily update completed.")

def run_daily_update(request):
    try:
        daily_update()
        return JsonResponse({"status": "success", "message": "Daily update completed"})
    except KeyboardInterrupt:
        return JsonResponse({"status": "interrupted", "message": "Daily update was interrupted"})
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)})

import datetime

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET

from .models import ProductChangeLog


@require_GET
def fetch_changelog(request):
    date_str = request.GET.get('date')
    
    if date_str:
        try:
            date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
            start_datetime = timezone.make_aware(datetime.datetime.combine(date, datetime.time.min))
            end_datetime = timezone.make_aware(datetime.datetime.combine(date, datetime.time.max))
            logs = ProductChangeLog.objects.filter(date__range=(start_datetime, end_datetime))
        except ValueError:
            return JsonResponse({'error': 'Invalid date format'}, status=400)
    else:
        # If no date is provided, return logs for the last 7 days
        end_date = timezone.now()
        start_date = end_date - datetime.timedelta(days=7)
        logs = ProductChangeLog.objects.filter(date__range=(start_date, end_date))

    data = [
        {
            'item_id': log.item_id,
            'product_name': log.product_name,
            'operation': log.get_operation_display(),
            'date': log.date.isoformat()
        }
        for log in logs
    ]

    return JsonResponse(data, safe=False)

import datetime
import io

from django.http import HttpResponse
from django.utils import timezone
from django.views.decorators.http import require_GET
from openpyxl import Workbook

from .models import ProductChangeLog


@require_GET
def download_excel(request):
    date_str = request.GET.get('date')
    
    if not date_str:
        return HttpResponse("Date parameter is required", status=400)
    
    try:
        date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
        start_datetime = timezone.make_aware(datetime.datetime.combine(date, datetime.time.min))
        end_datetime = timezone.make_aware(datetime.datetime.combine(date, datetime.time.max))
        logs = ProductChangeLog.objects.filter(date__range=(start_datetime, end_datetime))
    except ValueError:
        return HttpResponse("Invalid date format", status=400)

    # Create a new workbook and select the active sheet
    wb = Workbook()
    ws = wb.active
    ws.title = f"Changelog {date_str}"

    # Write headers
    headers = ['Item ID', 'Product Name', 'Operation', 'Date']
    for col, header in enumerate(headers, start=1):
        ws.cell(row=1, column=col, value=header)

    # Write data
    for row, log in enumerate(logs, start=2):
        ws.cell(row=row, column=1, value=log.item_id)
        ws.cell(row=row, column=2, value=log.product_name)
        ws.cell(row=row, column=3, value=log.get_operation_display())
        ws.cell(row=row, column=4, value=log.date.strftime('%Y-%m-%d %H:%M:%S'))

    # Save the workbook to a BytesIO object
    excel_file = io.BytesIO()
    wb.save(excel_file)
    excel_file.seek(0)

    # Prepare the response
    response = HttpResponse(excel_file.read(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename=changelog_{date_str}.xlsx'

    return response