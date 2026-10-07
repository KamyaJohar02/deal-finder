import streamlit as st
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from urllib.parse import quote
import pandas as pd
import re
import time


# =========================================================
# PAGE CONFIG
# =========================================================

st.set_page_config(
    page_title="Deal Finder 🔥",
    page_icon="🔥",
    layout="wide"
)

st.title("🔥 Multi-Store Deal Finder")
st.caption("Flipkart • Amazon India • Myntra")


# =========================================================
# STORE CONFIG
# =========================================================

STORE_CONFIG = {

    "Flipkart": {
        "base_url": "https://www.flipkart.com/search?q=",
        "product_selector": "a[href*='/p/']",
    },

    "Amazon": {
        "base_url": "https://www.amazon.in/s?k=",
        "product_selector": "a[href*='/dp/'], a[href*='/gp/product/']",
    },

    "Myntra": {
        "base_url": "https://www.myntra.com/search?q=",
        "product_selector": "a[href*='/buy/'], a[href*='/product/']",
    }
}


# =========================================================
# HELPERS
# =========================================================

def clean_text(text):
    if not text:
        return ""

    return re.sub(r"\s+", " ", text).strip()


def extract_number(value):
    if value is None:
        return None

    value = str(value)

    # ₹1,299
    match = re.search(r"[\d,]+(?:\.\d+)?", value)

    if not match:
        return None

    try:
        return float(match.group().replace(",", ""))
    except:
        return None


def extract_discount(text):
    if not text:
        return None

    patterns = [
        r"(\d{1,3})\s*%\s*off",
        r"(\d{1,3})\s*%\s*OFF",
        r"(\d{1,3})%\s*discount",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.I)

        if match:
            try:
                return float(match.group(1))
            except:
                pass

    return None


def extract_rating(text):
    if not text:
        return None

    patterns = [
        r"([0-5](?:\.\d)?)\s*(?:★|stars?)",
        r"([0-5](?:\.\d)?)\s*\/\s*5",
    ]

    for pattern in patterns:

        match = re.search(pattern, text, re.I)

        if match:
            try:
                rating = float(match.group(1))

                if 0 <= rating <= 5:
                    return rating

            except:
                pass

    return None


def extract_prices(text):

    if not text:
        return None, None

    # ₹1,299 / ₹999 etc.
    prices = re.findall(
        r"(?:₹|Rs\.?|INR)\s*[\d,]+(?:\.\d+)?",
        text,
        re.I
    )

    numbers = []

    for price in prices:

        number = extract_number(price)

        if number:
            numbers.append(number)

    # remove duplicates
    numbers = list(dict.fromkeys(numbers))

    if not numbers:
        return None, None

    # Usually first = selling price, second = MRP
    current_price = min(numbers)

    mrp = max(numbers)

    if mrp == current_price:
        mrp = None

    return current_price, mrp


def get_image_from_element(element):

    try:

        image = element.query_selector("img")

        if not image:
            return None

        attributes = [
            "src",
            "data-src",
            "data-lazy-src",
            "data-original",
            "data-image-url",
            "data-image"
        ]

        for attr in attributes:

            try:
                value = image.get_attribute(attr)

                if value and value.startswith("http"):
                    return value
            except:
                pass

        # srcset
        try:

            srcset = image.get_attribute("srcset")

            if srcset:

                parts = srcset.split(",")

                if parts:

                    url = parts[-1].strip().split(" ")[0]

                    if url.startswith("http"):
                        return url

        except:
            pass

    except:
        pass

    return None


# =========================================================
# SCROLL PAGE TO LOAD LAZY IMAGES
# =========================================================

def scroll_page(page):

    try:

        for _ in range(5):

            page.mouse.wheel(0, 1200)

            time.sleep(0.5)

        page.mouse.wheel(0, -6000)

        time.sleep(1)

    except:
        pass


# =========================================================
# BUILD SEARCH URL
# =========================================================

def build_url(store, query, page_number):

    encoded_query = quote(query)

    if store == "Amazon":

        # IMPORTANT:
        # Always Amazon India
        return (
            f"https://www.amazon.in/s?k={encoded_query}"
            f"&page={page_number}"
        )

    elif store == "Flipkart":

        return (
            f"https://www.flipkart.com/search?q={encoded_query}"
            f"&page={page_number}"
        )

    elif store == "Myntra":

        return (
            f"https://www.myntra.com/search?q={encoded_query}"
            f"&p={page_number}"
        )


# =========================================================
# FIND PRODUCT CARD
# =========================================================

def find_card(element, store):

    try:

        if store == "Amazon":

            # Amazon search result container
            card = element.locator(
                "xpath=ancestor::*[@data-component-type='s-search-result'][1]"
            )

            if card.count() > 0:
                return card.first

        elif store == "Flipkart":

            # Walk upwards until a reasonably sized container
            card = element.locator(
                "xpath=ancestor::div[.//img][1]"
            )

            if card.count() > 0:
                return card.first

        elif store == "Myntra":

            card = element.locator(
                "xpath=ancestor::li[.//img][1]"
            )

            if card.count() > 0:
                return card.first

            card = element.locator(
                "xpath=ancestor::div[.//img][1]"
            )

            if card.count() > 0:
                return card.first

    except:
        pass

    return element


# =========================================================
# SCRAPE ONE PAGE
# =========================================================

def scrape_page(page, store, search_query, page_number):

    url = build_url(
        store,
        search_query,
        page_number
    )

    st.write(
        f"🔎 **{store} — Page {page_number}**"
    )

    try:

        page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=45000
        )

        # Give dynamic content time
        time.sleep(3)

        # Check current URL
        current_url = page.url

        if store == "Amazon":

            if "amazon.in" not in current_url.lower():

                st.warning(
                    f"Amazon redirected unexpectedly:\n{current_url}"
                )

                # Try direct Amazon India again
                page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=45000
                )

                time.sleep(3)

        # Scroll so lazy images load
        scroll_page(page)

        selector = STORE_CONFIG[store]["product_selector"]

        try:

            page.wait_for_selector(
                selector,
                timeout=15000
            )

        except PlaywrightTimeoutError:

            return [], f"No product links found on page {page_number}"

        links = page.locator(selector)

        count = links.count()

        products = []

        seen_links = set()

        # Don't scrape infinite junk links
        max_links = min(count, 80)

        for i in range(max_links):

            try:

                link_element = links.nth(i)

                href = link_element.get_attribute("href")

                if not href:
                    continue

                # Convert relative links
                if href.startswith("/"):

                    if store == "Amazon":
                        href = "https://www.amazon.in" + href

                    elif store == "Flipkart":
                        href = "https://www.flipkart.com" + href

                    elif store == "Myntra":
                        href = "https://www.myntra.com" + href

                # Clean URL
                href = href.split("?")[0]

                if href in seen_links:
                    continue

                seen_links.add(href)

                # Find card
                card = find_card(
                    link_element,
                    store
                )

                # Get card text
                try:
                    text = clean_text(
                        card.inner_text(timeout=3000)
                    )
                except:
                    text = clean_text(
                        link_element.inner_text(timeout=2000)
                    )

                if not text:
                    continue

                # -----------------------------
                # IMAGE
                # -----------------------------

                image_url = get_image_from_element(card)

                # If card doesn't have image, try parent
                if not image_url:

                    try:

                        parent = link_element.locator(
                            "xpath=.."
                        )

                        image_url = get_image_from_element(
                            parent
                        )

                    except:
                        pass

                # -----------------------------
                # PRICE
                # -----------------------------

                current_price, mrp = extract_prices(text)

                if not current_price:
                    continue

                # -----------------------------
                # DISCOUNT
                # -----------------------------

                discount = extract_discount(text)

                # Calculate discount ourselves
                if (
                    discount is None
                    and mrp
                    and mrp > current_price
                ):

                    discount = round(
                        ((mrp - current_price) / mrp) * 100,
                        1
                    )

                # -----------------------------
                # RATING
                # -----------------------------

                rating = extract_rating(text)

                # -----------------------------
                # PRODUCT TITLE
                # -----------------------------

                title = ""

                try:

                    # Try common title elements
                    title_selectors = [
                        "h2",
                        "h3",
                        "[data-cy='title-recipe']",
                        "[class*='title']",
                        "[class*='Title']"
                    ]

                    for selector_title in title_selectors:

                        try:

                            title_element = card.locator(
                                selector_title
                            )

                            if title_element.count() > 0:

                                candidate = clean_text(
                                    title_element.first.inner_text(
                                        timeout=1000
                                    )
                                )

                                if (
                                    candidate
                                    and len(candidate) > 5
                                ):
                                    title = candidate
                                    break

                        except:
                            pass

                except:
                    pass

                # Fallback
                if not title:

                    try:
                        title = clean_text(
                            link_element.inner_text(
                                timeout=1000
                            )
                        )
                    except:
                        title = ""

                # Clean weird titles
                title = title[:300]

                # -----------------------------
                # PRODUCT
                # -----------------------------

                products.append({

                    "Store": store,

                    "Page": page_number,

                    "Product": title,

                    "Price": current_price,

                    "MRP": mrp,

                    "Discount %": discount,

                    "Rating": rating,

                    "Image": image_url,

                    "Link": href

                })

            except Exception:
                continue

        return products, None

    except Exception as e:

        return [], str(e)


# =========================================================
# SCRAPE STORE
# =========================================================

def scrape_store(
    browser,
    store,
    search_query,
    pages
):

    results = []

    context = None

    try:

        # India locale
        context = browser.new_context(

            locale="en-IN",

            timezone_id="Asia/Kolkata",

            viewport={
                "width": 1440,
                "height": 1000
            },

            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/154.0.0.0 Safari/537.36"
            )
        )

        page = context.new_page()

        # Block unnecessary resources only
        # DON'T block images!
        page.route(
            "**/*",
            lambda route: (
                route.abort()
                if route.request.resource_type in [
                    "font",
                    "media"
                ]
                else route.continue_()
            )
        )

        for page_number in range(1, pages + 1):

            page_products, error = scrape_page(
                page,
                store,
                search_query,
                page_number
            )

            if error:

                st.warning(
                    f"⚠️ {store} Page {page_number}: {error}"
                )

            if page_products:

                results.extend(page_products)

            # Small pause between pages
            time.sleep(1)

    except Exception as e:

        st.error(
            f"❌ {store} failed: {str(e)}"
        )

    finally:

        try:

            if context:
                context.close()

        except:
            pass

    return results


# =========================================================
# UI
# =========================================================

st.divider()

col1, col2 = st.columns(2)

with col1:

    store_choice = st.selectbox(
        "🛒 Store",
        [
            "Flipkart",
            "Amazon",
            "Myntra",
            "All 3"
        ]
    )

    product = st.text_input(
        "🔍 Product",
        placeholder="e.g. tshirt, shoes, laptop"
    )

    gender = st.selectbox(
        "👤 Gender",
        [
            "Any",
            "Women",
            "Men",
            "Kids",
            "Unisex"
        ]
    )

    brand = st.text_input(
        "🏷️ Brand (optional)",
        placeholder="e.g. adidas, Nike, Puma"
    )

with col2:

    max_price = st.number_input(
        "💰 Maximum price (₹)",
        min_value=0,
        value=1000,
        step=100
    )

    min_rating = st.number_input(
        "⭐ Minimum rating",
        min_value=0.0,
        max_value=5.0,
        value=0.0,
        step=0.1
    )

    sort_by = st.selectbox(
        "📊 Sort by",
        [
            "Cheapest",
            "Highest Discount",
            "Best Rating"
        ]
    )

    pages_to_scrape = st.number_input(
        "📄 Number of pages",
        min_value=1,
        max_value=10,
        value=3,
        step=1,
        help="Page 1, 2, 3... jitne select karoge utne pages scan honge."
    )


# =========================================================
# SEARCH
# =========================================================

if st.button(
    "🔥 FIND BEST DEALS",
    use_container_width=True
):

    if not product.strip():

        st.warning(
            "Please enter a product name."
        )

        st.stop()

    # -----------------------------
    # BUILD QUERY
    # -----------------------------

    search_parts = []

    if brand.strip():
        search_parts.append(
            brand.strip()
        )

    if gender != "Any":
        search_parts.append(
            gender
        )

    search_parts.append(
        product.strip()
    )

    search_query = " ".join(
        search_parts
    )

    st.info(
        f"🔎 Searching for: **{search_query}**"
    )

    # -----------------------------
    # WHICH STORES?
    # -----------------------------

    if store_choice == "All 3":

        stores = [
            "Flipkart",
            "Amazon",
            "Myntra"
        ]

    else:

        stores = [
            store_choice
        ]

    all_products = []

    # -----------------------------
    # BROWSER
    # -----------------------------

    with st.spinner(
        "🔥 Searching stores..."
    ):

        with sync_playwright() as p:

            try:

                browser = p.chromium.launch(

                    channel="chrome",

                    headless=False,

                    args=[
                        "--disable-http2",
                        "--disable-quic",
                        "--lang=en-IN",
                        "--disable-blink-features=AutomationControlled"
                    ]
                )

            except Exception:

                # Fallback if Chrome channel isn't available
                browser = p.chromium.launch(

                    headless=False,

                    args=[
                        "--disable-http2",
                        "--disable-quic",
                        "--lang=en-IN"
                    ]
                )

            # -----------------------------
            # EACH STORE
            # -----------------------------

            for store in stores:

                st.subheader(
                    f"🔎 {store}: {search_query}"
                )

                products = scrape_store(

                    browser,

                    store,

                    search_query,

                    int(pages_to_scrape)
                )

                all_products.extend(
                    products
                )

            try:
                browser.close()
            except:
                pass

    # =====================================================
    # DATA PROCESSING
    # =====================================================

    if not all_products:

        st.error(
            "😕 No products were found."
        )

        st.info(
            "Try a broader product name, lower rating filter, "
            "or fewer filters."
        )

        st.stop()

    df = pd.DataFrame(
        all_products
    )

    # -----------------------------
    # PRICE FILTER
    # -----------------------------

    if max_price > 0:

        df = df[
            df["Price"] <= max_price
        ]

    # -----------------------------
    # RATING FILTER
    # -----------------------------

    if min_rating > 0:

        # Keep products with unknown rating out
        df = df[
            df["Rating"].fillna(0)
            >= min_rating
        ]

    # -----------------------------
    # REMOVE DUPLICATES
    # -----------------------------

    df = df.drop_duplicates(
        subset=["Link"]
    )

    # -----------------------------
    # SORT
    # -----------------------------

    if sort_by == "Cheapest":

        df = df.sort_values(
            by="Price",
            ascending=True
        )

    elif sort_by == "Highest Discount":

        df["DiscountSort"] = df[
            "Discount %"
        ].fillna(0)

        df = df.sort_values(
            by="DiscountSort",
            ascending=False
        )

    elif sort_by == "Best Rating":

        df["RatingSort"] = df[
            "Rating"
        ].fillna(0)

        df = df.sort_values(
            by="RatingSort",
            ascending=False
        )

    # Reset index
    df = df.reset_index(
        drop=True
    )

    # =====================================================
    # RESULTS
    # =====================================================

    st.success(
        f"🔥 Found **{len(df)} products** across "
        f"{len(stores)} store(s) and "
        f"{int(pages_to_scrape)} page(s)."
    )

    # =====================================================
    # STORE SUMMARY
    # =====================================================

    summary_cols = st.columns(
        len(stores)
    )

    for i, store in enumerate(stores):

        count = len(
            df[df["Store"] == store]
        )

        with summary_cols[i]:

            st.metric(
                store,
                count
            )

    st.divider()

    # =====================================================
    # PAGE-WISE RESULTS
    # =====================================================

    available_pages = sorted(
        df["Page"]
        .dropna()
        .unique()
    )

    page_tabs = st.tabs(
        [
            f"📄 Page {int(page)}"
            for page in available_pages
        ]
    )

    for tab, page_number in zip(
        page_tabs,
        available_pages
    ):

        with tab:

            page_df = df[
                df["Page"] == page_number
            ]

            st.caption(
                f"{len(page_df)} products found on Page {int(page_number)}"
            )

            # Product cards
            for _, row in page_df.iterrows():

                with st.container(
                    border=True
                ):

                    col_img, col_info = st.columns(
                        [1, 3]
                    )

                    # -------------------------
                    # IMAGE
                    # -------------------------

                    with col_img:

                        image_url = row.get(
                            "Image"
                        )

                        if (
                            image_url
                            and str(image_url).startswith(
                                "http"
                            )
                        ):

                            try:

                                st.image(
                                    image_url,
                                    use_container_width=True
                                )

                            except:

                                st.write(
                                    "📷 Image unavailable"
                                )

                        else:

                            st.write(
                                "📷 Image unavailable"
                            )

                    # -------------------------
                    # INFO
                    # -------------------------

                    with col_info:

                        st.markdown(
                            f"### {row['Product']}"
                        )

                        st.write(
                            f"🛒 **{row['Store']}**  "
                            f"• 📄 Page {int(row['Page'])}"
                        )

                        price = row["Price"]

                        st.markdown(
                            f"## ₹{price:,.0f}"
                        )

                        if pd.notna(
                            row["MRP"]
                        ):

                            st.write(
                                f"~~MRP ₹{row['MRP']:,.0f}~~"
                            )

                        if pd.notna(
                            row["Discount %"]
                        ):

                            st.success(
                                f"🔥 {row['Discount %']:.0f}% OFF"
                            )

                        if pd.notna(
                            row["Rating"]
                        ):

                            st.write(
                                f"⭐ {row['Rating']:.1f}/5"
                            )

                        st.link_button(
                            "🛍️ OPEN PRODUCT",
                            row["Link"]
                        )

    # =====================================================
    # TABLE
    # =====================================================

    st.divider()

    st.subheader(
        "📊 All Products"
    )

    display_df = df[
        [
            "Store",
            "Page",
            "Product",
            "Price",
            "MRP",
            "Discount %",
            "Rating",
            "Link"
        ]
    ].copy()

    display_df["Price"] = display_df[
        "Price"
    ].apply(
        lambda x: f"₹{x:,.0f}"
    )

    display_df["MRP"] = display_df[
        "MRP"
    ].apply(
        lambda x: (
            f"₹{x:,.0f}"
            if pd.notna(x)
            else "-"
        )
    )

    display_df["Discount %"] = display_df[
        "Discount %"
    ].apply(
        lambda x: (
            f"{x:.0f}%"
            if pd.notna(x)
            else "-"
        )
    )

    display_df["Rating"] = display_df[
        "Rating"
    ].apply(
        lambda x: (
            f"{x:.1f}"
            if pd.notna(x)
            else "-"
        )
    )

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Link": st.column_config.LinkColumn(
                "Product Link"
            )
        }
    )

    # =====================================================
    # CSV DOWNLOAD
    # =====================================================

    csv = df.to_csv(
        index=False
    ).encode("utf-8")

    st.download_button(
        "⬇️ Download all results as CSV",
        csv,
        "deal_finder_results.csv",
        "text/csv"
    )