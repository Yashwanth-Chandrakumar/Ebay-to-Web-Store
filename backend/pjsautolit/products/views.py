import ast
import datetime
import io
import json
import logging
import os
import queue
import re
import threading
import time
import traceback
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from signal import signal
from threading import Lock

import requests
from bs4 import BeautifulSoup
from celery import shared_task
from django.conf import settings
from django.contrib import messages
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.db.models import BigIntegerField, F, Q, Value
from django.http import HttpResponse, HttpResponseNotFound, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template import Context, Template
from django.utils import timezone
from django.views.decorators.http import require_GET
from django.views.generic.detail import DetailView
from requests.exceptions import HTTPError, RequestException

from .models import Cart, CartItem, FetchStatus, Order, Product, ProductChangeLog

EBAY_APP_ID = settings.EBAY_APP_ID
EBAY_AUTH_TOKEN = settings.EBAY_AUTH_TOKEN
FINDING_API_URL = (
    "https://svcs.ebay.com/services/search/FindingService/v1"  # gets basic info
)
BROWSE_API_URL = (
    "https://api.ebay.com/buy/browse/v1/item/v1|{item_id}|0"  # gets detailed info
)

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
    cache.set("fetch_items_progress", {"progress": 0, "completed": False})
    total_items = 0
    min_price = 1.00
    max_price = 10.00
    price_increment = 10.00
    total_price_ranges = (4000.00 - min_price) / price_increment

    q = queue.Queue()
    num_worker_threads = 5
    threads = []

    def update_progress(current_price):
        progress = int((current_price / 4000.00) * 100)
        cache.set("fetch_items_progress", {"progress": progress, "completed": False})

    # Start worker threads
    for _ in range(num_worker_threads):
        t = threading.Thread(target=process_queue, args=(q,))
        t.start()
        threads.append(t)

    try:
        while min_price <= 4000.00:
            current_page = 1
            total_pages = 1

            while current_page <= total_pages:
                try:
                    items, total_pages = fetch_finding_api_data(
                        page_number=current_page,
                        min_price=min_price,
                        max_price=max_price,
                    )

                    for item in items:
                        item_id = item["item_id"]
                        try:
                            if not Product.objects.filter(item_id=item_id).exists():
                                browse_data = fetch_browse_api_data(item_id)
                                combined_data = {**item, **browse_data}
                                q.put(combined_data)
                                total_items += 1
                            else:
                                print(
                                    f"product skipped {item_id} in page {current_page}, price range ${min_price}-${max_price}"
                                )
                        except Exception as e:
                            print(f"Error processing item {item_id}: {e}")

                except Exception as e:
                    print(
                        f"Error fetching data for page {current_page}, price range ${min_price}-${max_price}: {e}"
                    )

                current_page += 1

            update_progress(min_price)
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

        cache.set("fetch_items_progress", {"progress": 100, "completed": True})
        return JsonResponse(
            {
                "status": "success",
                "message": f"Fetched and stored information for {total_items} items",
                "total_items": total_items,
            },
            status=200,
        )

    except Exception as e:
        print(f"Error in fetch_all_items: {e}")
        cache.set("fetch_items_progress", {"progress": 0, "completed": True})
        return JsonResponse({"status": "error", "message": str(e)}, status=500)


@require_GET
def get_fetch_items_progress(request):
    progress_info = cache.get(
        "fetch_items_progress", {"progress": 0, "completed": False}
    )
    return JsonResponse(progress_info)


# def fetch_product_data(item_id):
#     finding_data = fetch_finding_api_data(item_id)
#     browse_data = fetch_browse_api_data(item_id)
#     return {**finding_data, **browse_data}


def fetch_finding_api_data(page_number=1, min_price=1.00, max_price=10.00):
    headers = {
        "X-EBAY-SOA-SECURITY-APPNAME": "PJsAutoL-keyset-PRD-d2986db2a-865af761",
        "X-EBAY-SOA-OPERATION-NAME": "findItemsIneBayStores",
        "Content-Type": "text/xml",
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
            namespace = {"ns": "http://www.ebay.com/marketplace/search/v1/services"}

            # Check for eBay API errors
            ack = root.find(".//ns:ack", namespace)
            if ack is not None and ack.text != "Success":
                error_message = root.find(
                    ".//ns:errorMessage/ns:error/ns:message", namespace
                )
                error_code = root.find(
                    ".//ns:errorMessage/ns:error/ns:errorId", namespace
                )
                if error_message is not None and error_code is not None:
                    raise Exception(
                        f"eBay API Error {error_code.text}: {error_message.text}"
                    )
                else:
                    raise Exception(f"Unknown eBay API Error: {ack.text}")

            items = root.findall(".//ns:item", namespace)
            total_pages = int(root.find(".//ns:totalPages", namespace).text)

            results = []
            for item in items:
                data = {
                    "item_id": item.find("ns:itemId", namespace).text,
                    "title": item.find("ns:title", namespace).text,
                    "global_id": item.find("ns:globalId", namespace).text,
                    "category_id": item.find(
                        "ns:primaryCategory/ns:categoryId", namespace
                    ).text,
                    "category_name": item.find(
                        "ns:primaryCategory/ns:categoryName", namespace
                    ).text,
                    "gallery_url": item.find("ns:galleryURL", namespace).text,
                    "view_item_url": item.find("ns:viewItemURL", namespace).text,
                    "auto_pay": item.find("ns:autoPay", namespace).text == "true",
                    "postal_code": item.find("ns:postalCode", namespace).text,
                    "location": item.find("ns:location", namespace).text,
                    "country": item.find("ns:country", namespace).text,
                    "shipping_type": item.find(
                        "ns:shippingInfo/ns:shippingType", namespace
                    ).text,
                    "ship_to_locations": item.find(
                        "ns:shippingInfo/ns:shipToLocations", namespace
                    ).text,
                    "expedited_shipping": item.find(
                        "ns:shippingInfo/ns:expeditedShipping", namespace
                    ).text
                    == "true",
                    "one_day_shipping_available": item.find(
                        "ns:shippingInfo/ns:oneDayShippingAvailable", namespace
                    ).text
                    == "true",
                    "handling_time": (
                        int(
                            item.find("ns:shippingInfo/ns:handlingTime", namespace).text
                        )
                        if item.find("ns:shippingInfo/ns:handlingTime", namespace)
                        is not None
                        else None
                    ),
                    "price": float(
                        item.find("ns:sellingStatus/ns:currentPrice", namespace).text
                    ),
                    "selling_state": item.find(
                        "ns:sellingStatus/ns:sellingState", namespace
                    ).text,
                    "time_left": item.find(
                        "ns:sellingStatus/ns:timeLeft", namespace
                    ).text,
                    "best_offer_enabled": item.find(
                        "ns:listingInfo/ns:bestOfferEnabled", namespace
                    ).text
                    == "true",
                    "buy_it_now_available": item.find(
                        "ns:listingInfo/ns:buyItNowAvailable", namespace
                    ).text
                    == "true",
                    "start_time": item.find(
                        "ns:listingInfo/ns:startTime", namespace
                    ).text,
                    "end_time": item.find("ns:listingInfo/ns:endTime", namespace).text,
                    "listing_type": item.find(
                        "ns:listingInfo/ns:listingType", namespace
                    ).text,
                    "gift": item.find("ns:listingInfo/ns:gift", namespace).text
                    == "true",
                    "watch_count": (
                        int(item.find("ns:listingInfo/ns:watchCount", namespace).text)
                        if item.find("ns:listingInfo/ns:watchCount", namespace)
                        is not None
                        else None
                    ),
                    "returns_accepted": item.find("ns:returnsAccepted", namespace).text
                    == "true",
                    "is_multi_variation_listing": item.find(
                        "ns:isMultiVariationListing", namespace
                    ).text
                    == "true",
                    "top_rated_listing": item.find("ns:topRatedListing", namespace).text
                    == "true",
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
        time.sleep(RETRY_DELAY * (2**attempt))  # Exponential backoff

    print(f"Failed to fetch FindingService API data after {MAX_RETRIES} attempts")
    return [], 0


def fetch_new_access_token():
    url = "https://api.ebay.com/identity/v1/oauth2/token"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": "Basic UEpzQXV0b0wta2V5c2V0LVBSRC1kMjk4NmRiMmEtODY1YWY3NjE6UFJELTI5ODZkYjJhMjg4NS01ZTE0LTQyNWMtOThlMS04Y2Fl",  # Replace with your actual credentials
    }
    data = {
        "grant_type": "refresh_token",
        "refresh_token": "v^1.1#i^1#f^0#p^3#I^3#r^1#t^Ul4xMF84OjNDRDY3NkNBOURFNzk4QzRFRDA1MTgzQTY5QTEzQTA3XzBfMSNFXjI2MA==",  # Replace with your actual refresh token
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


# Global variables for rate limiting
RATE_LIMIT_PER_SECOND = 5
RATE_LIMIT_PERIOD = 1.0
token_bucket = RATE_LIMIT_PER_SECOND
last_request_time = time.time()
bucket_lock = Lock()


logger = logging.getLogger(__name__)


def fetch_browse_api_data(item_id):
    global token_bucket, last_request_time

    url = BROWSE_API_URL.format(item_id=item_id)

    headers = {
        "Authorization": f"Bearer {settings.EBAY_AUTH_TOKEN}",
        "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
        "X-EBAY-C-ENDUSERCTX": "sessionId=12345",
    }

    attempt = 0
    while attempt < MAX_RETRIES:
        try:
            with bucket_lock:
                current_time = time.time()
                time_passed = current_time - last_request_time
                token_bucket += time_passed * (
                    RATE_LIMIT_PER_SECOND / RATE_LIMIT_PERIOD
                )
                if token_bucket > RATE_LIMIT_PER_SECOND:
                    token_bucket = RATE_LIMIT_PER_SECOND

                if token_bucket < 1:
                    sleep_time = (1 - token_bucket) * (
                        RATE_LIMIT_PERIOD / RATE_LIMIT_PER_SECOND
                    )
                    time.sleep(sleep_time)
                    token_bucket = 1

                token_bucket -= 1
                last_request_time = time.time()

            response = requests.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()

            if not data:
                logger.error(f"Empty response for item_id: {item_id}")
                return {}

            item_data = data.get("item", {})
            additional_images = data.get("additionalImages", [])
            additional_image_urls = [img["imageUrl"] for img in additional_images]

            result = {
                "description": data.get("description", ""),
                "price": (
                    float(data["price"]["value"])
                    if "price" in data and "value" in data["price"]
                    else None
                ),
                "currency": (
                    data["price"]["currency"]
                    if "price" in data and "currency" in data["price"]
                    else None
                ),
                "category_path": data.get("categoryPath", ""),
                "category_id_path": data.get("categoryIdPath", ""),
                "item_creation_date": data.get("itemCreationDate"),
                "estimated_availability_status": data.get(
                    "estimatedAvailabilities", [{}]
                )[0].get("estimatedAvailabilityStatus", ""),
                "estimated_available_quantity": data.get(
                    "estimatedAvailabilities", [{}]
                )[0].get("estimatedAvailableQuantity"),
                "estimated_sold_quantity": data.get("estimatedAvailabilities", [{}])[
                    0
                ].get("estimatedSoldQuantity"),
                "enabled_for_guest_checkout": data.get(
                    "enabledForGuestCheckout", False
                ),
                "eligible_for_inline_checkout": data.get(
                    "eligibleForInlineCheckout", False
                ),
                "lot_size": data.get("lotSize", 0),
                "legacy_item_id": data.get("legacyItemId", ""),
                "priority_listing": data.get("priorityListing", False),
                "adult_only": data.get("adultOnly", False),
                "listing_marketplace_id": data.get("listingMarketplaceId", ""),
                "shipping_service_code": data.get("shippingOptions", [{}])[0].get(
                    "shippingServiceCode", ""
                ),
                "shipping_carrier_code": data.get("shippingOptions", [{}])[0].get(
                    "shippingCarrierCode", ""
                ),
                "min_estimated_delivery_date": data.get("shippingOptions", [{}])[0].get(
                    "minEstimatedDeliveryDate"
                ),
                "max_estimated_delivery_date": data.get("shippingOptions", [{}])[0].get(
                    "maxEstimatedDeliveryDate"
                ),
                "shipping_cost": float(
                    data.get("shippingOptions", [{}])[0]
                    .get("shippingCost", {})
                    .get("value", 0)
                ),
                "shipping_cost_type": data.get("shippingOptions", [{}])[0].get(
                    "shippingCostType", ""
                ),
                "primary_image_url": (
                    data["image"]["imageUrl"]
                    if "image" in data and "imageUrl" in data["image"]
                    else None
                ),
                "additional_image_urls": additional_image_urls,
            }

            # Log any fields that are None
            none_fields = [field for field, value in result.items() if value is None]
            if none_fields:
                logger.warning(
                    f"Fields with None values for item_id {item_id}: {', '.join(none_fields)}"
                )

            return result

        except HTTPError as e:
            if response.status_code == 401:
                logger.warning("Access token expired, fetching a new one...")
                new_token = fetch_new_access_token()
                if new_token:
                    headers["Authorization"] = f"Bearer {new_token}"
                    continue
            logger.error(f"Error fetching Browse API data (attempt {attempt + 1}): {e}")
            attempt += 1
            time.sleep(RETRY_DELAY * (2**attempt))  # Exponential backoff

        except RequestException as e:
            logger.error(f"Error fetching Browse API data (attempt {attempt + 1}): {e}")
            attempt += 1
            time.sleep(RETRY_DELAY * (2**attempt))  # Exponential backoff

    logger.error(
        f"Failed to fetch Browse API data after {MAX_RETRIES} attempts for item_id: {item_id}"
    )
    return {}


from django.utils.text import slugify


def save_product_data(product_data):
    try:
        sanitized_name = slugify(product_data["title"])
        base_name = sanitized_name
        counter = 1
        while Product.objects.filter(html_link=sanitized_name).exists():
            sanitized_name = f"{base_name}-{counter}"
            counter += 1

        description = product_data.get("description") or product_data.get(
            "short_description", ""
        )

        # print(f"description {description}")
        cleaned_description = clean_description(description)

        defaults = {
            "title": product_data["title"],
            "global_id": product_data.get("global_id"),
            "category_id": product_data.get("category_id"),
            "category_name": product_data.get("category_name"),
            "gallery_url": product_data.get("gallery_url"),
            "view_item_url": product_data.get("view_item_url"),
            "auto_pay": product_data.get("auto_pay", False),
            "postal_code": product_data.get("postal_code"),
            "location": product_data.get("location"),
            "country": product_data.get("country"),
            "selling_state": product_data.get("selling_state"),
            "time_left": product_data.get("time_left"),
            "best_offer_enabled": product_data.get("best_offer_enabled", False),
            "buy_it_now_available": product_data.get("buy_it_now_available", False),
            "start_time": product_data.get("start_time"),
            "end_time": product_data.get("end_time"),
            "listing_type": product_data.get("listing_type"),
            "gift": product_data.get("gift", False),
            "watch_count": product_data.get("watch_count"),
            "returns_accepted": product_data.get("returns_accepted", False),
            "is_multi_variation_listing": product_data.get(
                "is_multi_variation_listing", False
            ),
            "top_rated_listing": product_data.get("top_rated_listing", False),
            "short_description": cleaned_description,
            "price": product_data.get("price"),
            "currency": product_data.get("currency"),
            "category_path": product_data.get("category_path", ""),
            "category_id_path": product_data.get("category_id_path", ""),
            "item_creation_date": product_data.get("item_creation_date"),
            "estimated_availability_status": product_data.get(
                "estimated_availability_status", ""
            ),
            "estimated_available_quantity": product_data.get(
                "estimated_available_quantity"
            ),
            "estimated_sold_quantity": product_data.get("estimated_sold_quantity"),
            "enabled_for_guest_checkout": product_data.get(
                "enabled_for_guest_checkout", False
            ),
            "eligible_for_inline_checkout": product_data.get(
                "eligible_for_inline_checkout", False
            ),
            "lot_size": product_data.get("lot_size", 0),
            "legacy_item_id": product_data.get("legacy_item_id", ""),
            "priority_listing": product_data.get("priority_listing", False),
            "adult_only": product_data.get("adult_only", False),
            "listing_marketplace_id": product_data.get("listing_marketplace_id", ""),
            "seller_username": product_data.get("seller_username"),
            "feedback_score": product_data.get("feedback_score"),
            "positive_feedback_percent": product_data.get("positive_feedback_percent"),
            "feedback_rating_star": product_data.get("feedback_rating_star"),
            "top_rated_seller": product_data.get("top_rated_seller", False),
            "shipping_type": product_data.get("shipping_type"),
            "ship_to_locations": product_data.get("ship_to_locations"),
            "expedited_shipping": product_data.get("expedited_shipping", False),
            "one_day_shipping_available": product_data.get(
                "one_day_shipping_available", False
            ),
            "handling_time": product_data.get("handling_time"),
            "shipping_service_code": product_data.get("shipping_service_code"),
            "shipping_carrier_code": product_data.get("shipping_carrier_code"),
            "min_estimated_delivery_date": product_data.get(
                "min_estimated_delivery_date"
            ),
            "max_estimated_delivery_date": product_data.get(
                "max_estimated_delivery_date"
            ),
            "shipping_cost": product_data.get("shipping_cost"),
            "shipping_cost_type": product_data.get("shipping_cost_type"),
            "primary_image_url": product_data.get("primary_image_url"),
            "additional_image_urls": product_data.get("additional_image_urls"),
            "html_link": sanitized_name,
        }

        product, created = Product.objects.update_or_create(
            item_id=product_data["item_id"], defaults=defaults
        )

        if created:
            logger.info(
                f"Created new product: {product_data['title']} - {product_data['item_id']}"
            )
        else:
            logger.info(
                f"Updated existing product: {product_data['title']} - {product_data['item_id']}"
            )

    except IntegrityError as e:
        logger.error(
            f"IntegrityError while saving product {product_data['item_id']}: {e}"
        )
    except Exception as e:
        logger.error(f"Error saving product data: {e}")
        logger.error(f"Product data: {product_data['item_id']}")


import ast
import logging
import os

from celery import shared_task
from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from django.template import loader
from django.views.decorators.http import require_GET

from .models import Product  # Ensure this import is correct for your project structure

logger = logging.getLogger(__name__)


@shared_task
def generate_html_pages_async():
    # Check if the generation is already in progress
    if cache.get("html_generation_in_progress"):
        logger.warning("HTML generation is already in progress.")
        return

    # Set the in-progress flag
    cache.set("html_generation_in_progress", True)

    output_dir = os.path.join(settings.BASE_DIR, "products", "viewproduct")
    os.makedirs(output_dir, exist_ok=True)

    products = Product.objects.all()
    total_products = products.count()
    completed = 0
    errors = []

    try:
        template = loader.get_template("pages/template.html")
    except Exception as e:
        logger.error(f"Error loading template: {e}")
        cache.set("html_generation_in_progress", False)
        return

    for product in products:
        if product.additional_image_urls:
            try:
                additional_images = ast.literal_eval(product.additional_image_urls)
                additional_images = [
                    str(url).strip() for url in additional_images if url
                ]
                print(
                    f"Product {product.item_id} - Additional images: {additional_images}"
                )  # Add this line
            except Exception as e:
                logger.error(
                    f"Error parsing additional image URLs for product {product.item_id}: {e}"
                )
                additional_images = []
        else:
            additional_images = []

        context = {"product": product, "additional_images": additional_images}

        try:
            rendered_html = template.render(context)
        except Exception as e:
            errors.append(f"Error rendering HTML for product {product.item_id}: {e}")
            continue

        filename = f"{product.html_link}.html"
        filepath = os.path.join(output_dir, filename)

        try:
            with open(filepath, "w", encoding="utf-8") as file:
                file.write(rendered_html)
        except Exception as e:
            errors.append(f"Error writing file for product {product.item_id}: {e}")

        # Update progress
        completed += 1
        progress = (
            int((completed / total_products) * 100) if total_products > 0 else 100
        )
        cache.set(
            "html_generation_progress", {"progress": progress, "completed": False}
        )

    # Mark as completed
    cache.set("html_generation_progress", {"progress": 100, "completed": True})
    cache.set("html_generation_in_progress", False)  # Reset in-progress flag

    if errors:
        logger.error(f"Errors encountered while generating HTML pages: {errors}")
    else:
        logger.info("HTML pages generated successfully.")


@require_GET
def run_html_generation(request):
    try:
        generate_html_pages_async.delay()
        return JsonResponse(
            {"status": "success", "message": "HTML generation task has been scheduled"}
        )
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)})


def get_html_generation_progress(request):
    progress_info = cache.get(
        "html_generation_progress", {"progress": 0, "completed": False}
    )
    return JsonResponse(progress_info)


def initiate_html_generation(request):
    if request.method == "GET":
        # Reset progress for a new generation
        cache.set("html_generation_progress", {"progress": 0, "completed": False})

        # Start the generation process
        generate_html_pages()
        return JsonResponse({"message": "HTML generation started."})


def landing_page(request):
    cart_count = 0

    # Check if there's a cart in the session
    cart_id = request.session.get("cart_id")
    if cart_id:
        try:
            # Get all cart items related to the cart
            cart_items = CartItem.objects.filter(cart_id=cart_id)
            # Sum up the quantity of all items in the cart to get the cart count
            cart_count = sum(item.quantity for item in cart_items)
        except CartItem.DoesNotExist:
            # If the cart items don't exist, the cart is empty or invalid
            cart_count = 0

    return render(
        request,
        "pages/landing.html",
        {
            "cart_count": cart_count,
        },
    )


def terms_view(request):
    cart_count = 0

    # Check if there's a cart in the session
    cart_id = request.session.get("cart_id")
    if cart_id:
        try:
            # Get all cart items related to the cart
            cart_items = CartItem.objects.filter(cart_id=cart_id)
            # Sum up the quantity of all items in the cart to get the cart count
            cart_count = sum(item.quantity for item in cart_items)
        except CartItem.DoesNotExist:
            # If the cart items don't exist, the cart is empty or invalid
            cart_count = 0
    return render(
        request,
        "pages/terms.html",
        {
            "cart_count": cart_count,
        },
    )


def admin_page(request):
    return render(request, "pages/admin.html")


def admin_page2(request):
    return render(request, "pages/admin-2.html")


def admin_page3(request):
    return render(request, "pages/admin-3.html")


# views.py


def product_list(request):
    query = request.GET.get("query", "")
    products = Product.objects.all()

    cart_count = 0
    cart_id = request.session.get("cart_id")

    if cart_id:
        try:
            # Get all cart items related to the cart
            cart_items = CartItem.objects.filter(cart_id=cart_id)
            # Sum up the quantity of all items in the cart to get the cart count
            cart_count = sum(item.quantity for item in cart_items)
        except CartItem.DoesNotExist:
            # If the cart items don't exist, the cart is empty or invalid
            cart_count = 0

    if query:
        products = products.filter(title__icontains=query)

    paginator = Paginator(products, 10)  # Show 10 products per page.
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    context = {
        "page_obj": page_obj,
        "query": query,
        "cart_count": cart_count,
    }
    return render(request, "pages/product_list.html", context)


def cron(request):
    return HttpResponse("Happy")


def clean_description(description):
    # Check if the description contains HTML
    if "<" in description and ">" in description:
        # Parse the HTML and extract the text content
        soup = BeautifulSoup(description, "html.parser")
        text_content = soup.get_text()
    else:
        # If it's not HTML, use the description as is
        text_content = description

    # Remove unwanted characters (like Â from encoding issues)
    cleaned_text = text_content.replace("Â", "")

    # Remove everything after the first occurrence of the word "condition"
    cleaned_text = (
        re.split(r"(condition)\b", cleaned_text, flags=re.IGNORECASE)[0] + "condition."
    )

    # Remove extra whitespace
    cleaned_text = re.sub(r"\s+", " ", cleaned_text).strip()

    return cleaned_text


import threading


def clean_short_description(description):
    if not description:
        return description
    cleaned_text = (
        re.split(r"(condition)\b.*", description, flags=re.IGNORECASE)[0] + " condition"
    )
    return cleaned_text.strip()


def process_product(q, updated_count, updated_count_lock):
    while True:
        product = q.get()
        if product is None:
            break

        original_description = product.short_description
        cleaned_description = clean_short_description(original_description)

        if original_description != cleaned_description:
            product.short_description = cleaned_description
            product.save()

            with updated_count_lock:
                updated_count[0] += 1

        q.task_done()


@require_GET
def fetch_and_print_descriptions(request):
    try:
        products = Product.objects.exclude(short_description__isnull=True)
        updated_count = [0]  # Use a list to allow modification within threads
        updated_count_lock = threading.Lock()

        q = queue.Queue()

        # Start worker threads
        threads = []
        for _ in range(30):
            t = threading.Thread(
                target=process_product, args=(q, updated_count, updated_count_lock)
            )
            t.start()
            threads.append(t)

        # Queue the products for processing
        for product in products:
            q.put(product)

        # Wait for the queue to be processed
        q.join()

        # Stop worker threads
        for _ in range(30):
            q.put(None)
        for t in threads:
            t.join()

        return JsonResponse(
            {
                "status": "success",
                "message": f"Cleaned and updated {updated_count[0]} descriptions.",
            },
            status=200,
        )

    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)


from concurrent.futures import ThreadPoolExecutor, as_completed

MAX_WORKERS = 30


def process_price_range(
    min_price, max_price, existing_item_ids, updated_item_ids_queue, fields_to_check
):
    print(f"Processing price range: ${min_price:.2f} - ${max_price:.2f}")
    current_page = 1
    total_pages = 1
    local_updated_item_ids = set()

    # Field mapping for mismatched names
    field_mapping = {
        "description": "short_description",
        # Add any other mismatched field names here
    }

    while current_page <= total_pages:
        try:
            items, total_pages = fetch_finding_api_data(
                page_number=current_page, min_price=min_price, max_price=max_price
            )
            print(
                f"Fetched page {current_page} of {total_pages} for price range ${min_price:.2f} - ${max_price:.2f}"
            )

            for item in items:
                item_id = item["item_id"]
                local_updated_item_ids.add(item_id)

                # Apply field mapping
                mapped_item = {
                    field_mapping.get(k, k): v
                    for k, v in item.items()
                    if k in fields_to_check
                }

                try:
                    product = Product.objects.get(item_id=item_id)
                    before_dict = {
                        key: getattr(product, key)
                        for key in fields_to_check
                        if hasattr(product, key)
                    }
                    after_dict = {
                        key: value
                        for key, value in mapped_item.items()
                        if key in fields_to_check and hasattr(product, key)
                    }

                    changes = {
                        key: value
                        for key, value in after_dict.items()
                        if before_dict.get(key) != value
                    }

                    if changes:
                        for key, value in changes.items():
                            setattr(product, key, value)
                        product.save()
                        print(f"Updated product: {item_id} - {product.title}")
                        print(f"Changes: {changes}")

                        change_log = ProductChangeLog.objects.create(
                            item_id=item_id,
                            product_name=product.title,
                            operation="updated",
                        )
                        change_log.set_changes(before_dict, after_dict)
                        change_log.save()
                    else:
                        print(
                            f"No changes for checked fields in product: {item_id} - {product.title}"
                        )
                except Product.DoesNotExist:
                    browse_data = fetch_browse_api_data(item_id)
                    mapped_browse_data = {
                        field_mapping.get(k, k): v
                        for k, v in browse_data.items()
                        if k in fields_to_check
                    }
                    combined_data = {**mapped_item, **mapped_browse_data}
                    new_product = Product.objects.create(**combined_data)
                    print(f"Created new product: {item_id} - {new_product.title}")
                    ProductChangeLog.objects.create(
                        item_id=item_id,
                        product_name=new_product.title,
                        operation="created",
                    )

            current_page += 1

        except Exception as e:
            print(
                f"Error fetching data for page {current_page}, price range ${min_price:.2f} - ${max_price:.2f}: {e}"
            )

    updated_item_ids_queue.put(local_updated_item_ids)


from django.utils import timezone
from django.views.decorators.http import require_GET


@shared_task
def run_daily_update_async():
    print("Starting daily update...")
    fetch_status, created = FetchStatus.objects.get_or_create(fetch_type="daily")

    existing_item_ids = set(Product.objects.values_list("item_id", flat=True))
    updated_item_ids = set()

    price_ranges = []
    min_price = 1.00
    max_price = 10.00
    price_increment = 10.00

    while min_price <= 4000.00:
        price_ranges.append((min_price, max_price))
        min_price = max_price + 0.01
        max_price += price_increment

    fields_to_check = [
        "item_id",
        "title",
        "global_id",
        "category_id",
        "category_name",
        "gallery_url",
        "view_item_url",
        "auto_pay",
        "postal_code",
        "location",
        "country",
        "shipping_type",
        "ship_to_locations",
    ]

    field_mapping = {
        "description": "short_description",
        # Add any other mismatched field names here
    }

    try:
        for min_price, max_price in price_ranges:
            print(f"Processing price range: ${min_price:.2f} - ${max_price:.2f}")
            current_page = 1
            total_pages = 1

            while current_page <= total_pages:
                try:
                    items, total_pages = fetch_finding_api_data(
                        page_number=current_page,
                        min_price=min_price,
                        max_price=max_price,
                    )
                    print(
                        f"Fetched page {current_page} of {total_pages} for price range ${min_price:.2f} - ${max_price:.2f}"
                    )

                    for item in items:
                        item_id = item["item_id"]
                        updated_item_ids.add(item_id)

                        # Apply field mapping
                        mapped_item = {
                            field_mapping.get(k, k): v for k, v in item.items()
                        }

                        try:
                            product = Product.objects.get(item_id=item_id)
                            before_dict = {
                                key: getattr(product, key)
                                for key in fields_to_check
                                if hasattr(product, key)
                            }
                            after_dict = {
                                key: value
                                for key, value in mapped_item.items()
                                if key in fields_to_check and hasattr(product, key)
                            }

                            changes = {
                                key: value
                                for key, value in after_dict.items()
                                if before_dict.get(key) != value
                            }

                            if changes:
                                for key, value in changes.items():
                                    setattr(product, key, value)
                                product.save()
                                print(f"Updated product: {item_id} - {product.title}")
                                print(f"Changes: {changes}")

                                change_log = ProductChangeLog.objects.create(
                                    item_id=item_id,
                                    product_name=product.title,
                                    operation="updated",
                                )
                                change_log.set_changes(before_dict, after_dict)
                                change_log.save()
                        except Product.DoesNotExist:
                            browse_data = fetch_browse_api_data(item_id)
                            mapped_browse_data = {
                                field_mapping.get(k, k): v
                                for k, v in browse_data.items()
                            }
                            combined_data = {**mapped_item, **mapped_browse_data}
                            save_product_data(combined_data)
                            print(
                                f"Created new product: {item_id} - {combined_data.get('title', 'Unknown Title')}"
                            )

                            ProductChangeLog.objects.create(
                                item_id=item_id,
                                product_name=combined_data.get(
                                    "title", "Unknown Title"
                                ),
                                operation="created",
                            )

                    current_page += 1

                except Exception as e:
                    print(
                        f"Error fetching data for page {current_page}, price range ${min_price:.2f} - ${max_price:.2f}: {e}"
                    )

    except Exception as e:
        print(f"Error during daily update: {e}")

    # Deletion process
    items_to_delete = existing_item_ids - updated_item_ids
    for item_id in items_to_delete:
        listing_status = get_ebay_listing_status(item_id)
        if listing_status != "Active":
            try:
                product = Product.objects.get(item_id=item_id)
                product_name = product.title
                product.delete()
                print(f"Deleted inactive product: {item_id} - {product_name}")
                ProductChangeLog.objects.create(
                    item_id=item_id, product_name=product_name, operation="deleted"
                )
            except Product.DoesNotExist:
                print(f"Product {item_id} not found in database, skipping deletion")

    fetch_status.last_run = timezone.now()
    fetch_status.save()
    generate_html_pages_async.delay()

    print("Daily update completed.")


@require_GET
def run_daily_update(request):
    try:
        run_daily_update_async.delay()
        return JsonResponse(
            {"status": "success", "message": "Daily update task has been scheduled"}
        )
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)})


# Add any other view functions here

# @require_GET
# def run_daily_update(request):
#     cache.set('generate_report_progress', {'progress': 0, 'completed': False})

#     try:
#         fetch_status, created = FetchStatus.objects.get_or_create(fetch_type='daily')
#         existing_item_ids = set(Product.objects.values_list('item_id', flat=True))
#         updated_item_ids = set()

#         price_ranges = []
#         min_price = 1.00
#         max_price = 10.00
#         price_increment = 10.00

#         while min_price <= 4000.00:
#             price_ranges.append((min_price, max_price))
#             min_price = max_price + 0.01
#             max_price += price_increment

#         fields_to_check = ['item_id', 'title', 'global_id', 'category_id', 'category_name', 'gallery_url',
#                            'view_item_url', 'auto_pay', 'postal_code', 'location', 'country', 'shipping_type',
#                            'ship_to_locations']
#         field_mapping = {
#             'description': 'short_description',
#         }

#         for index, (min_price, max_price) in enumerate(price_ranges):
#             current_page = 1
#             total_pages = 1

#             while current_page <= total_pages:
#                 try:
#                     items, total_pages = fetch_finding_api_data(page_number=current_page, min_price=min_price, max_price=max_price)

#                     for item in items:
#                         item_id = item['item_id']
#                         updated_item_ids.add(item_id)

#                         # Apply field mapping to the fetched item
#                         mapped_item = {field_mapping.get(k, k): v for k, v in item.items() if k in fields_to_check}

#                         try:
#                             product = Product.objects.get(item_id=item_id)
#                             before_dict = {key: getattr(product, key) for key in fields_to_check if hasattr(product, key)}
#                             after_dict = {key: value for key, value in mapped_item.items() if key in fields_to_check and hasattr(product, key)}

#                             changes = {key: value for key, value in after_dict.items() if before_dict.get(key) != value}

#                             if changes:
#                                 # Print the product ID and what has changed
#                                 print(f"Updating product {item_id}: {changes}", flush=True)

#                                 for key, value in changes.items():
#                                     setattr(product, key, value)
#                                 product.save()

#                                 change_log = ProductChangeLog.objects.create(
#                                     item_id=item_id,
#                                     product_name=product.title,
#                                     operation='updated'
#                                 )
#                                 change_log.set_changes(before_dict, after_dict)
#                                 change_log.save()
#                         except Product.DoesNotExist:
#                             browse_data = fetch_browse_api_data(item_id)
#                             # Apply field mapping to the browse data
#                             mapped_browse_data = {field_mapping.get(k, k): v for k, v in browse_data.items() if k in fields_to_check}
#                             combined_data = {**mapped_item, **mapped_browse_data}
#                             new_product = Product.objects.create(**combined_data)
#                             print(f"Created new product {item_id}", flush=True)  # Print new product creation
#                             ProductChangeLog.objects.create(
#                                 item_id=item_id,
#                                 product_name=new_product.title,
#                                 operation='created'
#                             )

#                     current_page += 1

#                 except Exception as e:
#                     print(f"Error fetching data for page {current_page}, price range ${min_price:.2f}-${max_price:.2f}: {e}", flush=True)

#             # Update progress
#             progress = int(((index + 1) / len(price_ranges)) * 100)
#             cache.set('generate_report_progress', {'progress': progress, 'completed': False})

#         deleted_item_ids = existing_item_ids - updated_item_ids
#         for item_id in deleted_item_ids:
#             product = Product.objects.get(item_id=item_id)
#             product_name = product.title
#             product.delete()
#             print(f"Deleted product {item_id}", flush=True)  # Print product deletion
#             ProductChangeLog.objects.create(
#                 item_id=item_id,
#                 product_name=product_name,
#                 operation='deleted'
#             )

#         fetch_status.last_run = timezone.now()
#         fetch_status.save()

#         cache.set('generate_report_progress', {'progress': 100, 'completed': True})
#         return JsonResponse({"status": "success", "message": "Daily update completed successfully"})

#     except Exception as e:
#         print(f"Error in run_daily_update: {e}", flush=True)
#         cache.set('generate_report_progress', {'progress': 0, 'completed': True})
#         return JsonResponse({"status": "error", "message": str(e)})


import datetime
import io

# Generate report only:
import json
import logging
from datetime import datetime

from celery import shared_task
from django.http import StreamingHttpResponse
from django.utils import timezone

from .models import FetchStatus, Product, Report

logger = logging.getLogger(__name__)


class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.strftime("%Y-%m-%d %H:%M:%S")
        return super().default(obj)


@shared_task(bind=True)
def generate_report_async(self):
    logger.info("Starting the report generation task.")
    self.update_state(state="PROGRESS", meta={"progress": 0})

    fetch_status, created = FetchStatus.objects.get_or_create(fetch_type="report")

    total_products = Product.objects.count()
    processed_items = 0

    existing_item_ids = set(Product.objects.values_list("item_id", flat=True))
    updated_item_ids = set()

    price_ranges = []
    min_price = 1.00
    max_price = 10.00
    price_increment = 10.00

    while min_price <= 4000.00:
        price_ranges.append((min_price, max_price))
        min_price = max_price + 0.01
        max_price += price_increment

    fields_to_check = [
        "item_id",
        "title",
        "global_id",
        "category_id",
        "category_name",
        "gallery_url",
        "view_item_url",
        "auto_pay",
        "postal_code",
        "location",
        "country",
        "shipping_type",
        "ship_to_locations",
    ]

    field_mapping = {
        "description": "short_description",
    }

    reports = []

    try:
        for min_price, max_price in price_ranges:
            logger.info(f"Processing price range: ${min_price:.2f} - ${max_price:.2f}")
            current_page = 1
            range_total_pages = 1

            while current_page <= range_total_pages:
                try:
                    logger.info(
                        f"Fetching data for page {current_page}, price range ${min_price:.2f} - ${max_price:.2f}"
                    )
                    items, range_total_pages = fetch_finding_api_data(
                        page_number=current_page,
                        min_price=min_price,
                        max_price=max_price,
                    )

                    for item in items:
                        item_id = item["item_id"]
                        updated_item_ids.add(item_id)

                        mapped_item = {
                            field_mapping.get(k, k): v for k, v in item.items()
                        }

                        product = Product.objects.filter(item_id=item_id).first()
                        if product:
                            before_dict = {
                                key: getattr(product, key)
                                for key in fields_to_check
                                if hasattr(product, key)
                            }
                            after_dict = {
                                key: value
                                for key, value in mapped_item.items()
                                if key in fields_to_check and hasattr(product, key)
                            }

                            changes = {
                                key: value
                                for key, value in after_dict.items()
                                if before_dict.get(key) != value
                            }

                            if changes:
                                logger.info(
                                    f"Changes detected for product: {item_id} - {product.title}"
                                )
                                report = Report(
                                    item_id=item_id,
                                    product_name=product.title,
                                    operation="changes_detected",
                                )
                                report.set_changes(before_dict, after_dict)
                                reports.append(report)
                        else:
                            logger.info(
                                f"New product detected: {item_id} - {mapped_item.get('title')}"
                            )
                            report = Report(
                                item_id=item_id,
                                product_name=mapped_item.get("title"),
                                operation="new_product_detected",
                                changes=None,  # Set changes to None for new products
                            )
                            reports.append(report)

                        processed_items += 1
                        progress = int(processed_items / total_products * 100)
                        self.update_state(state="PROGRESS", meta={"progress": progress})

                    current_page += 1

                except Exception as e:
                    logger.error(
                        f"Error fetching data for page {current_page}, price range ${min_price:.2f} - ${max_price:.2f}: {e}"
                    )

    except Exception as e:
        logger.error(f"Error during report generation: {e}")

    # Check for potentially deleted items
    items_to_delete = existing_item_ids - updated_item_ids
    for item_id in items_to_delete:
        product = Product.objects.filter(item_id=item_id).first()
        if product:
            report = Report(
                item_id=item_id,
                product_name=product.title,
                operation="potential_deletion",
                changes=None,  # Set changes to None for deleted products
            )
            reports.append(report)
            logger.info(f"Potential deletion detected: {item_id} - {product.title}")

    # Save all reports to the database
    if reports:
        Report.objects.bulk_create(reports)

    fetch_status.last_run = timezone.now()
    fetch_status.save()

    logger.info("Report generation task completed successfully.")
    return {"status": "completed", "progress": 100}


def generate_report(request):
    task = generate_report_async.delay()
    return JsonResponse({"task_id": task.id})


from django.http import StreamingHttpResponse


def report_progress(request, task_id):
    response = StreamingHttpResponse(
        event_stream(task_id), content_type="text/event-stream"
    )
    response["Cache-Control"] = "no-cache"
    return response


def event_stream(task_id):
    task = generate_report_async.AsyncResult(task_id)
    previous_progress = 0

    while not task.ready():
        # Get the current state
        current_state = task.info  # task.info holds the meta data from update_state
        if current_state and isinstance(current_state, dict):
            progress = current_state.get("progress", 0)

            if progress != previous_progress:
                yield f"data: {json.dumps({'progress': progress})}\n\n"
                previous_progress = progress

        time.sleep(1)  # Adjust polling interval

    # Final completion message
    yield f"data: {json.dumps({'status': 'completed'})}\n\n"


import datetime

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET

from .models import Report


@require_GET
def fetch_report_log(request):
    try:
        date_str = request.GET.get("date")

        if date_str:
            try:
                selected_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                return JsonResponse({"error": "Invalid date format"}, status=400)
        else:
            # Fetch the latest report date if no date is provided
            latest_log_date = Report.objects.aggregate(Max("date"))["date__max"]
            if latest_log_date is None:
                return JsonResponse({"error": "No report entries found"}, status=404)
            selected_date = latest_log_date.date()

        start_date = timezone.make_aware(
            datetime.datetime.combine(selected_date, datetime.time.min)
        )
        end_date = timezone.make_aware(
            datetime.datetime.combine(selected_date, datetime.time.max)
        )

        # Fetch all reports for the selected date
        reports = Report.objects.filter(date__range=(start_date, end_date)).order_by(
            "-date"
        )

        print("Fetching reports from", start_date, "to", end_date)
        print("Number of reports found:", reports.count())

        data = []
        for report in reports:
            try:
                report_data = {
                    "item_id": report.item_id,
                    "product_name": report.product_name,
                    "operation": report.get_operation_display(),
                    "date": report.date.isoformat(),
                    "changes": report.changes,  # Assuming 'changes' is already a dict
                }
                data.append(report_data)
            except Exception as e:
                print(f"Error processing report entry {report.id}: {str(e)}")

        return JsonResponse(
            {
                "date": selected_date.isoformat(),
                "data": data,
            },
            safe=False,
        )

    except Exception as e:
        print(f"Unexpected error in fetch_report_log: {str(e)}", exc_info=True)
        return JsonResponse({"error": "An unexpected error occurred"}, status=500)


from django.views.decorators.http import require_http_methods


@require_http_methods(["DELETE"])
def delete_report(request):
    date_str = request.GET.get("date")
    if not date_str:
        return JsonResponse({"error": "Date parameter is required"}, status=400)

    try:
        date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
        start_datetime = timezone.make_aware(
            datetime.datetime.combine(date, datetime.time.min)
        )
        end_datetime = timezone.make_aware(
            datetime.datetime.combine(date, datetime.time.max)
        )

        deleted_count, _ = Report.objects.filter(
            date__range=(start_datetime, end_datetime)
        ).delete()

        if deleted_count > 0:
            return JsonResponse(
                {
                    "success": True,
                    "message": f"Deleted {deleted_count} report entries for {date_str}",
                }
            )
        else:
            return JsonResponse(
                {"success": False, "error": f"No report entries found for {date_str}"},
                status=404,
            )

    except ValueError:
        return JsonResponse({"error": "Invalid date format"}, status=400)
    except Exception as e:
        logger.error(f"Error deleting report for {date_str}: {str(e)}")
        return JsonResponse(
            {"error": "An unexpected error occurred while deleting the report"},
            status=500,
        )


from celery.result import AsyncResult
from django.http import JsonResponse


def cancel_report_task(request):
    task_id = request.GET.get("task_id")
    if not task_id:
        return JsonResponse({"error": "Task ID is required"}, status=400)

    try:
        task = AsyncResult(task_id)
        task.revoke(terminate=True)
        return JsonResponse(
            {"success": True, "message": f"Task {task_id} canceled successfully"}
        )
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@require_GET
def download_report_excel(request):
    date_str = request.GET.get("date")

    if not date_str:
        return HttpResponse("Date parameter is required", status=400)

    try:
        date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
        start_datetime = timezone.make_aware(
            datetime.datetime.combine(date, datetime.time.min)
        )
        end_datetime = timezone.make_aware(
            datetime.datetime.combine(date, datetime.time.max)
        )
        reports = Report.objects.filter(date__range=(start_datetime, end_datetime))
    except ValueError:
        return HttpResponse("Invalid date format", status=400)

    wb = Workbook()
    ws = wb.active
    ws.title = f"Report {date_str}"

    headers = ["Item ID", "Product Name", "Operation", "Date", "Changes"]
    for col, header in enumerate(headers, start=1):
        ws.cell(row=1, column=col, value=header)

    for row, report in enumerate(reports, start=2):
        ws.cell(row=row, column=1, value=report.item_id)
        ws.cell(row=row, column=2, value=report.product_name)
        ws.cell(row=row, column=3, value=report.get_operation_display())
        ws.cell(row=row, column=4, value=report.date.strftime("%Y-%m-%d %H:%M:%S"))
        ws.cell(row=row, column=5, value=report.changes)

    excel_file = io.BytesIO()
    wb.save(excel_file)
    excel_file.seek(0)

    response = HttpResponse(
        excel_file.read(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f"attachment; filename=report_{date_str}.xlsx"

    return response


# @require_GET
# def get_generate_report_progress(request):
#     progress_info = cache.get(
#         "generate_report_progress", {"progress": 0, "completed": False}
#     )
#     return JsonResponse(progress_info)


import datetime
import logging

from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Max
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET

from .models import ProductChangeLog

logger = logging.getLogger(__name__)


import datetime
import io
import logging

from django.core.paginator import Paginator
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Max
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET
from openpyxl import Workbook

from .models import ProductChangeLog

logger = logging.getLogger(__name__)


@require_GET
def fetch_changelog(request):
    try:
        # Get date from request, default to the latest date if not provided
        date_str = request.GET.get("date")

        if date_str:
            try:
                selected_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                return JsonResponse({"error": "Invalid date format"}, status=400)
        else:
            latest_log_date = ProductChangeLog.objects.aggregate(Max("date"))[
                "date__max"
            ]
            if latest_log_date is None:
                return JsonResponse({"error": "No changelog entries found"}, status=404)
            selected_date = latest_log_date.date()

        start_date = timezone.make_aware(
            datetime.datetime.combine(selected_date, datetime.time.min)
        )
        end_date = timezone.make_aware(
            datetime.datetime.combine(selected_date, datetime.time.max)
        )

        logs = ProductChangeLog.objects.filter(
            date__range=(start_date, end_date)
        ).order_by("-date")

        logger.info(f"Fetching all changelog entries for {selected_date}")

        data = []
        for log in logs:
            try:
                log_data = {
                    "item_id": log.item_id,
                    "product_name": log.product_name,
                    "operation": log.get_operation_display(),
                    "date": log.date.isoformat(),
                    "changes": log.changes,
                }
                data.append(log_data)
            except Exception as e:
                logger.error(f"Error processing log entry {log.id}: {str(e)}")

        return JsonResponse(
            {
                "date": selected_date.isoformat(),
                "data": data,
            },
            safe=False,
            encoder=DjangoJSONEncoder,
        )

    except Exception as e:
        logger.error(f"Unexpected error in fetch_changelog: {str(e)}", exc_info=True)
        return JsonResponse({"error": "An unexpected error occurred"}, status=500)


from django.views.decorators.http import require_GET
from openpyxl import Workbook


@require_GET
def download_excel(request):
    date_str = request.GET.get("date")

    if not date_str:
        return HttpResponse("Date parameter is required", status=400)

    try:
        date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
        start_datetime = timezone.make_aware(
            datetime.datetime.combine(date, datetime.time.min)
        )
        end_datetime = timezone.make_aware(
            datetime.datetime.combine(date, datetime.time.max)
        )
        logs = ProductChangeLog.objects.filter(
            date__range=(start_datetime, end_datetime)
        )
    except ValueError:
        return HttpResponse("Invalid date format", status=400)

    # Create a new workbook and select the active sheet
    wb = Workbook()
    ws = wb.active
    ws.title = f"Changelog {date_str}"

    # Write headers
    headers = ["Item ID", "Product Name", "Operation", "Date"]
    for col, header in enumerate(headers, start=1):
        ws.cell(row=1, column=col, value=header)

    # Write data
    for row, log in enumerate(logs, start=2):
        ws.cell(row=row, column=1, value=log.item_id)
        ws.cell(row=row, column=2, value=log.product_name)
        ws.cell(row=row, column=3, value=log.get_operation_display())
        ws.cell(row=row, column=4, value=log.date.strftime("%Y-%m-%d %H:%M:%S"))

    # Save the workbook to a BytesIO object
    excel_file = io.BytesIO()
    wb.save(excel_file)
    excel_file.seek(0)

    # Prepare the response
    response = HttpResponse(
        excel_file.read(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f"attachment; filename=changelog_{date_str}.xlsx"

    return response


# Cart


from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt
from square.client import Client


@csrf_exempt
def process_payment(request):
    if request.method == "POST":
        try:
            # Step 1: Parse the JSON request body
            data = json.loads(request.body)
            token = data.get("sourceId")
            location_id = data.get("locationId")

            # Step 2: Retrieve the cart from the session
            cart_id = request.session.get("cart_id")
            if not cart_id:
                return JsonResponse({"error": "Cart not found"}, status=404)

            cart = get_object_or_404(Cart, id=cart_id)
            cart_total = int(cart.total_amount() * 100)  # Convert total to cents

            # Step 3: Initialize Square Client
            client = Client(
                access_token=settings.SQUARE_ACCESS_TOKEN,
                environment="sandbox",  # Change to 'production' for live payments
            )

            # Step 4: Create a unique idempotency key
            idempotency_key = str(uuid.uuid4())

            # Step 5: Create the payment using the Square Payments API
            result = client.payments.create_payment(
                body={
                    "source_id": token,  # The payment token provided from Square frontend
                    "amount_money": {
                        "amount": cart_total,  # Total in cents
                        "currency": "USD",
                    },
                    "idempotency_key": idempotency_key,  # Ensure no duplicate payments
                    "location_id": location_id,  # Square location ID
                }
            )

            # Step 6: Handle the payment response
            if result.is_success():
                payment_id = result.body["payment"]["id"]

                # Create an order after a successful payment
                order = Order.objects.create(
                    cart=cart,
                    status="completed",
                    total_amount=cart.total_amount(),  # Store amount in dollars
                    square_payment_id=payment_id,  # Store Square payment ID
                )

                # Clear the cart (optional)
                request.session.pop("cart_id", None)

                return JsonResponse(
                    {"status": "Payment Successful", "order_id": order.id}
                )
            else:
                # Payment failed, return the errors
                return JsonResponse({"error": result.errors}, status=400)

        except Exception as e:
            # Handle unexpected errors and log them
            return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"error": "Invalid request method"}, status=400)


def add_to_cart(request, product_id):
    product = get_object_or_404(Product, item_id=product_id)
    cart, created = Cart.objects.get_or_create(id=request.session.get("cart_id"))

    print("Proceeding for weight checking")
    weight = get_ebay_product_weight(product.item_id)
    print(f"Fetched weight for product {product_id}: {weight}")  # Debugging output

    if weight is None:
        messages.error(
            request,
            f"Unable to fetch weight for {product.title}. Please try again later.",
        )
        return redirect("product_list")

    if not created:
        cart_item, item_created = CartItem.objects.get_or_create(
            cart=cart, product=product
        )
        if not item_created:
            cart_item.quantity += 1
        cart_item.weight = weight  # Update weight
        cart_item.save()
    else:
        request.session["cart_id"] = cart.id
        CartItem.objects.create(cart=cart, product=product, quantity=1, weight=weight)

    messages.success(request, f"{product.title} has been added to your cart.")
    return redirect("product_list")


from django.db.models.functions import Cast


def view_cart(request):
    cart_id = request.session.get("cart_id")
    cart_count = 0
    if cart_id:
        try:
            cart = get_object_or_404(Cart, id=cart_id)
            cart_items = cart.cartitem_set.select_related("product").all()
            cart_count = sum(item.quantity for item in cart_items)
            valid_cart_items = []
            invalid_items = []
            for item in cart_items:
                try:
                    # Use item.product directly since it's now correctly linked by item_id
                    item.product = Product.objects.get(item_id=item.product.item_id)
                    valid_cart_items.append(item)
                except Product.DoesNotExist:
                    invalid_items.append(item)

            # Delete invalid items
            CartItem.objects.filter(id__in=[item.id for item in invalid_items]).delete()

            # Recalculate cart total using only valid items
            cart_total = sum(
                item.product.price * item.quantity for item in valid_cart_items
            )
        except Exception as e:
            # Log the full error traceback
            print(f"Error processing cart:\n{traceback.format_exc()}")
            valid_cart_items = []
            cart_total = 0
            cart_count = 0
    else:
        valid_cart_items = []
        cart_total = 0
        cart_count = 0

    return render(
        request,
        "pages/cart.html",
        {
            "cart_items": valid_cart_items,
            "cart_total": cart_total,
            "cart_count": cart_count,
        },
    )


def update_cart(request, item_id):
    cart_item = get_object_or_404(CartItem, id=item_id)
    quantity = int(request.POST.get("quantity", 1))
    if quantity > 0:
        cart_item.quantity = quantity
        cart_item.save()
    else:
        cart_item.delete()
    return redirect("view_cart")


def remove_from_cart(request, item_id):
    cart_item = get_object_or_404(CartItem, id=item_id)
    cart_item.delete()
    return redirect("view_cart")


from square.client import Client

logger = logging.getLogger(__name__)


def checkout(request):
    try:
        # Step 1: Check if cart_id is in session
        cart_id = request.session.get("cart_id")
        cart_count = 0
        if cart_id:
            try:
                # Get all cart items related to the cart
                cart_items = CartItem.objects.filter(cart_id=cart_id)
                # Sum up the quantity of all items in the cart to get the cart count
                cart_count = sum(item.quantity for item in cart_items)
            except CartItem.DoesNotExist:
                # If the cart items don't exist, the cart is empty or invalid
                cart_count = 0
        print("Cart ID:", cart_id)  # Debugging output
        if not cart_id:
            print("No cart ID in session")
            return redirect("view_cart")

        # Step 2: Fetch the cart and its items
        cart = get_object_or_404(Cart, id=cart_id)
        cart_items = cart.cartitem_set.all()
        cart_total = cart.total_amount()
        cart_total_weight = (
            cart.total_weight()
        )  # Assuming this method returns total weight in pounds
        print("Cart Total:", cart_total)  # Debugging output
        print("Cart Total Weight:", cart_total_weight)  # Debugging output

        # Calculate weight in pounds and ounces
        total_weight_major = int(cart_total_weight)  # Pounds
        total_weight_minor = int(
            (cart_total_weight - total_weight_major) * 16
        )  # Ounces

        print("Weight Major (pounds):", total_weight_major)
        print("Weight Minor (ounces):", total_weight_minor)

        def calculate_usps_media_mail_cost(weight):
            base_rate = 3.65
            additional_rate = 0.70
            # Round up to the nearest whole pound
            rounded_weight = int(weight) if weight == int(weight) else int(weight) + 1
            if rounded_weight <= 1:
                return base_rate
            else:
                return base_rate + (rounded_weight - 1) * additional_rate

        shipping_cost = calculate_usps_media_mail_cost(cart_total_weight) + 2.00
        total_including_shipping = cart_total + Decimal(shipping_cost)
        total_including_shipping = total_including_shipping.quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        if request.method == "POST":
            # Step 3: Initialize Square client
            client = Client(
                access_token=settings.SQUARE_ACCESS_TOKEN,
                environment="sandbox",  # Ensure this is correct for your setup
            )
            print("Square client initialized")  # Debugging output

            payment_api = client.payments

            # Step 4: Make payment request
            result = payment_api.create_payment(
                source_id=request.POST["nonce"],
                amount_money={
                    "amount": int(
                        (cart_total + shipping_cost) * 100
                    ),  # Amount in cents, including shipping cost
                    "currency": "USD",
                },
                idempotency_key=str(cart.id),
                location_id=settings.SQUARE_LOCATION_ID,
            )
            print("Payment result:", result)  # Debugging output

            # Step 5: Handle payment result
            if result.is_success():
                print("Payment successful")  # Debugging output
                order = Order.objects.create(
                    cart=cart,
                    status="completed",
                    total_amount=cart_total
                    + shipping_cost,  # Include shipping cost in total amount
                    shipping_cost=shipping_cost,
                    square_payment_id=result.body["payment"]["id"],
                )
                del request.session["cart_id"]
                return redirect("order_confirmation", order_id=order.id)
            else:
                print("Payment failed:", result.errors)  # Debugging output
                logger.error(f"Payment error: {result.errors}")
                return render(request, "pages/error.html", {"error": result.errors})

        # If GET request, render the checkout page
        return render(
            request,
            "pages/checkout.html",
            {
                "cart_items": cart_items,
                "cart_total": cart_total,
                "total_weight_major": total_weight_major,
                "total_weight_minor": total_weight_minor,
                "shipping_cost": shipping_cost,
                "square_application_id": settings.SQUARE_APPLICATION_ID,
                "square_location_id": settings.SQUARE_LOCATION_ID,
                "total_including_shipping": total_including_shipping,
                "cart_count": cart_count,
            },
        )
    except Exception as e:
        print("Exception occurred:", str(e))  # Debugging output
        logger.error(f"Checkout error: {str(e)}", exc_info=True)
        return render(request, "pages/error.html", {"error": str(e)})


logger = logging.getLogger(__name__)


def order_confirmation(request, order_id):
    try:
        order = get_object_or_404(Order, id=order_id)
        order_items = order.cart.cartitem_set.all()
        order_total = order.total_amount

        return render(
            request,
            "pages/order_confirmation.html",
            {"order": order, "order_items": order_items, "order_total": order_total},
        )

    except Exception as e:
        logger.error(
            f"Error in order_confirmation view for order_id {order_id}: {e}",
            exc_info=True,
        )
        return render(
            request, "pages/error.html", {"error": "An unexpected error occurred."}
        )


def product_detail(request, product_slug):
    product = get_object_or_404(Product, html_link=product_slug)
    html_file_path = os.path.join(
        "products", "viewproduct", f"{product.html_link}.html"
    )

    if os.path.exists(html_file_path):
        with open(html_file_path, "r") as file:
            html_content = file.read()
        return HttpResponse(html_content)
    else:
        return HttpResponseNotFound("Page not found")


def get_ebay_product_weight(item_id):
    print(f"Fetching weight for item ID: {item_id}")
    url = "https://api.ebay.com/ws/api.dll"
    headers = {
        "X-EBAY-API-SITEID": "0",
        "X-EBAY-API-COMPATIBILITY-LEVEL": "967",
        "X-EBAY-API-CALL-NAME": "GetItem",
        "X-EBAY-API-IAF-TOKEN": EBAY_AUTH_TOKEN,
        "Content-Type": "text/xml",
    }
    body = f"""
    <?xml version="1.0" encoding="utf-8"?>
    <GetItemRequest xmlns="urn:ebay:apis:eBLBaseComponents">    
        <ErrorLanguage>en_US</ErrorLanguage>
        <WarningLevel>High</WarningLevel>
        <ItemID>{item_id}</ItemID>
    </GetItemRequest>
    """

    while True:
        try:
            response = requests.post(url, headers=headers, data=body)
            print("Response Status Code:", response.status_code)

            if response.status_code == 200:
                response_content = response.content.decode("utf-8")

                if (
                    "<ShortMessage>Expired IAF token.</ShortMessage>"
                    in response_content
                ):
                    print("Expired IAF token error detected")
                    print("Access token expired, fetching a new one...")
                    new_token = fetch_new_access_token()
                    if new_token:
                        headers["X-EBAY-API-IAF-TOKEN"] = new_token
                        print("New token fetched and set")
                        continue
                    else:
                        print("Failed to fetch a new access token")
                        return None

                root = ET.fromstring(response_content)

                namespace = {"ns": "urn:ebay:apis:eBLBaseComponents"}

                weight_major_elem = root.find(
                    ".//ns:ShippingPackageDetails/ns:WeightMajor", namespace
                )
                weight_minor_elem = root.find(
                    ".//ns:ShippingPackageDetails/ns:WeightMinor", namespace
                )

                if weight_major_elem is not None:
                    weight_major = weight_major_elem.text
                else:
                    print("WeightMajor element not found")
                    weight_major = "0"

                if weight_minor_elem is not None:
                    weight_minor = weight_minor_elem.text
                else:
                    print("WeightMinor element not found")
                    weight_minor = "0"

                weight_major = float(weight_major)
                weight_minor = float(weight_minor)
                print(f"{item_id} - weight - {weight_major} , {weight_minor}")

                total_weight_lbs = weight_major + (weight_minor / 16)
                return total_weight_lbs

            else:
                print("Failed to fetch data from eBay API")
                print("Response Content:", response_content)
                return None

        except Exception as e:
            print("Exception occurred:", str(e))
            return None


def get_ebay_listing_status(item_id):
    print(f"Fetching status for item ID: {item_id}")
    url = "https://api.ebay.com/ws/api.dll"
    headers = {
        "X-EBAY-API-SITEID": "0",
        "X-EBAY-API-COMPATIBILITY-LEVEL": "967",
        "X-EBAY-API-CALL-NAME": "GetItem",
        "X-EBAY-API-IAF-TOKEN": EBAY_AUTH_TOKEN,
        "Content-Type": "text/xml",
    }
    body = f"""
    <?xml version="1.0" encoding="utf-8"?>
    <GetItemRequest xmlns="urn:ebay:apis:eBLBaseComponents">    
        <ErrorLanguage>en_US</ErrorLanguage>
        <WarningLevel>High</WarningLevel>
        <ItemID>{item_id}</ItemID>
    </GetItemRequest>
    """

    max_retries = 3
    retry_delay = 5  # seconds

    for attempt in range(max_retries):
        try:
            response = requests.post(url, headers=headers, data=body)
            print("Response Status Code:", response.status_code)

            if response.status_code == 200:
                response_content = response.content.decode("utf-8")

                if (
                    "<ShortMessage>Expired IAF token.</ShortMessage>"
                    in response_content
                ):
                    print("Expired IAF token error detected")
                    print("Access token expired, fetching a new one...")
                    new_token = fetch_new_access_token()
                    if new_token:
                        headers["X-EBAY-API-IAF-TOKEN"] = new_token
                        print("New token fetched and set")
                        continue
                    else:
                        print("Failed to fetch a new access token")
                        return None

                root = ET.fromstring(response_content)

                namespace = {"ns": "urn:ebay:apis:eBLBaseComponents"}

                status_elem = root.find(".//ns:ListingStatus", namespace)

                if status_elem is not None:
                    listing_status = status_elem.text
                    print(f"{item_id} - status - {listing_status}")
                    return listing_status
                else:
                    print("ListingStatus element not found")
                    return None

            else:
                print("Failed to fetch data from eBay API")
                print("Response Content:", response.content.decode("utf-8"))

                if attempt < max_retries - 1:
                    print(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    print("Max retries reached. Giving up.")
                    return None

        except Exception as e:
            print("Exception occurred:", str(e))
            if attempt < max_retries - 1:
                print(f"Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
            else:
                print("Max retries reached. Giving up.")
                return None

    return None  # If we've exhausted all retries
