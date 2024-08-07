
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
        try:
            save_product_data(item)
        except Exception as e:
            print(f"Error saving product data: {e}")
        time.sleep(2)  # 2-second delay
        q.task_done()

@require_GET
def fetch_all_items(request):
    try:
        total_items = 0
        total_pages = 1
        current_page = 1

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

        q.join()

        for _ in range(num_worker_threads):
            q.put(None)
        for t in threads:
            t.join()

        # Generate HTML pages after fetching all items
        generate_html_pages()

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
        "X-EBAY-C-ENDUSERCTX": "sessionId=12345"
    }
    
    attempt = 0
    while attempt < MAX_RETRIES:
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            item_data = data.get('item', {})
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



def save_product_data(product_data):
    try:
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
            'short_description': product_data.get('short_description', ''),
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
            'additional_image_urls': product_data.get('additional_image_urls')
            }
        )
        if created:
            print(f"Created new product: {product_data['title']}")
        else:
            print(f"Updated existing product: {product_data['title']}")
        
        # Generate and save HTML

    except Exception as e:
        print(f"Error saving product data: {e}")

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

    # HTML template (you should replace this with your actual template)
    try:
        template = loader.get_template('pages/template.html')
    except Exception as e:
        print(f"Error loading template: {e}")
        return

    for product in products:
        # Parse the string representation of the list into an actual list
        if product.additional_image_urls:
            try:
                additional_images = ast.literal_eval(product.additional_image_urls)
                # Ensure all items are strings and strip any whitespace
                additional_images = [str(url).strip() for url in additional_images if url]
            except:
                # If there's any error in parsing, default to an empty list
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