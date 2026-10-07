import streamlit as st
import pandas as pd
import re
import time
import sys
import subprocess
from urllib.parse import quote
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


# =========================================================
# PAGE CONFIG
# =========================================================

st.set_page_config(
    page_title="Deal Finder",
    page_icon="🔥",
    layout="wide"
)


# =========================================================
# PLAYWRIGHT BROWSER SETUP
# =========================================================

@st.cache_resource
def start_playwright():

    try:
        playwright = sync_playwright().start()

        # First try normal Chromium
        try:
            browser = playwright.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-http2",
                    "--disable-quic",
                    "--disable-gpu",
                ]
            )

            return playwright, browser

        except Exception:

            # Browser binary may not exist on Streamlit Cloud
            try:
                subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "playwright",
                        "install",
                        "chromium"
                    ],
                    check=True,
                    timeout=300
                )

                browser = playwright.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-http2",
                        "--disable-quic",
                        "--disable-gpu",
                    ]
                )

                return playwright, browser

            except Exception as install_error:

                playwright.stop()

                raise RuntimeError(
                    "Playwright Chromium could not be installed. "
                    f"Details: {install_error}"
                )

    except Exception as e:

        raise RuntimeError(
            f"Browser startup failed: {e}"
        )


# =========================================================
# STORE CONFIG
# =========================================================

STORE_CONFIG = {

    "Flipkart": {
        "selector": "a[href*='/p/']"
    },

    "Amazon": {
        "selector": (
            "a[href*='/dp/'], "
            "a[href*='/gp/product/']"
        )
    },

    "Myntra": {
        "selector": (
            "a[href*='/buy/'], "
            "a[href*='/product/']"
        )
    }
}


# =========================================================
# BASIC HELPERS
# =========================================================

def clean_text(text):

    if not text:
        return ""

    return re.sub(
        r"\s+",
        " ",
        str(text)
    ).strip()


def extract_number(text):

    if text is None:
        return None

    match = re.search(
        r"[\d,]+(?:\.\d+)?",
        str(text)
    )

    if not match:
        return None

    try:
        return float(
            match.group().replace(",", "")
        )
    except:
        return None


# =========================================================
# PRICE
# =========================================================

def extract_prices(text):

    if not text:
        return None, None

    prices = re.findall(
        r"(?:₹|Rs\.?|INR)\s*[\d,]+(?:\.\d+)?",
        text,
        re.I
    )

    values = []

    for price in prices:

        number = extract_number(price)

        if number is not None:
            values.append(number)

    values = list(
        dict.fromkeys(values)
    )

    if not values:
        return None, None

    # Cheapest number is generally selling price
    current_price = min(values)

    # Highest number generally MRP
    mrp = max(values)

    if mrp == current_price:
        mrp = None

    return current_price, mrp


# =========================================================
# DISCOUNT
# =========================================================

def extract_discount(text):

    if not text:
        return None

    patterns = [
        r"(\d{1,3})\s*%\s*off",
        r"(\d{1,3})\s*%\s*discount",
        r"(\d{1,3})\s*%\s*OFF"
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            re.I
        )

        if match:

            try:
                return float(
                    match.group(1)
                )
            except:
                pass

    return None


# =========================================================
# RATING
# =========================================================

def extract_rating(text):

    if not text:
        return None

    patterns = [
        r"([0-5](?:\.\d)?)\s*(?:★|stars?)",
        r"([0-5](?:\.\d)?)\s*/\s*5"
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            re.I
        )

        if match:

            try:

                rating = float(
                    match.group(1)
                )

                if 0 <= rating <= 5:
                    return rating

            except:
                pass

    return None


# =========================================================
# IMAGE EXTRACTION
# =========================================================

def get_image(element):

    try:

        image = element.locator("img")

        if image.count() == 0:
            return None

        image = image.first

        attributes = [
            "src",
            "data-src",
            "data-lazy-src",
            "data-original",
            "data-image",
            "data-image-url"
        ]

        for attribute in attributes:

            try:

                value = image.get_attribute(
                    attribute
                )

                if (
                    value
                    and value.startswith("http")
                    and not value.startswith("data:")
                ):
                    return value

            except:
                pass

        # srcset
        try:

            srcset = image.get_attribute(
                "srcset"
            )

            if srcset:

                candidates = []

                for item in srcset.split(","):

                    item = item.strip()

                    if not item:
                        continue

                    url = item.split(" ")[0]

                    if url.startswith("http"):
                        candidates.append(url)

                if candidates:
                    return candidates[-1]

        except:
            pass

    except:
        pass

    return None


# =========================================================
# SCROLL
# =========================================================

def scroll_page(page):

    try:

        for _ in range(6):

            page.mouse.wheel(
                0,
                1200
            )

            time.sleep(0.4)

        time.sleep(1)

    except:
        pass


# =========================================================
# URL BUILDERS
# =========================================================

def build_url(
    store,
    query,
    page_number
):

    encoded = quote(
        query
    )

    # -------------------------------------
    # AMAZON INDIA
    # -------------------------------------

    if store == "Amazon":

        return (
            "https://www.amazon.in/"
            f"s?k={encoded}"
            f"&page={page_number}"
        )

    # -------------------------------------
    # FLIPKART
    # -------------------------------------

    if store == "Flipkart":

        if page_number == 1:

            return (
                "https://www.flipkart.com/"
                f"search?q={encoded}"
            )

        return (
            "https://www.flipkart.com/"
            f"search?q={encoded}"
            f"&page={page_number}"
        )

    # -------------------------------------
    # MYNTRA
    # -------------------------------------

    if store == "Myntra":

        return (
            "https://www.myntra.com/"
            f"search?q={encoded}"
            f"&p={page_number}"
        )

    return ""


# =========================================================
# PRODUCT CARD
# =========================================================

def find_card(
    link_element,
    store
):

    try:

        if store == "Amazon":

            card = link_element.locator(
                "xpath="
                "ancestor::*"
                "[@data-component-type="
                "'s-search-result'][1]"
            )

            if card.count() > 0:
                return card.first

        elif store == "Myntra":

            card = link_element.locator(
                "xpath="
                "ancestor::li[.//img][1]"
            )

            if card.count() > 0:
                return card.first

        # Generic fallback
        card = link_element.locator(
            "xpath="
            "ancestor::*[.//img][1]"
        )

        if card.count() > 0:
            return card.first

    except:
        pass

    return link_element


# =========================================================
# TITLE
# =========================================================

def get_title(
    card,
    link_element
):

    selectors = [
        "h2",
        "h3",
        "[class*='title']",
        "[class*='Title']",
        "[class*='productName']",
        "[class*='ProductName']"
    ]

    for selector in selectors:

        try:

            element = card.locator(
                selector
            )

            if element.count() > 0:

                title = clean_text(
                    element.first.inner_text(
                        timeout=1000
                    )
                )

                if len(title) > 5:

                    return title[:300]

        except:
            pass

    try:

        title = clean_text(
            link_element.inner_text(
                timeout=1000
            )
        )

        return title[:300]

    except:
        return ""


# =========================================================
# SCRAPE ONE PAGE
# =========================================================

def scrape_page(
    page,
    store,
    search_query,
    page_number
):

    url = build_url(
        store,
        search_query,
        page_number
    )

    try:

        page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=45000
        )

        time.sleep(3)

        # -----------------------------------------
        # AMAZON MUST STAY INDIA
        # -----------------------------------------

        if store == "Amazon":

            current_url = page.url.lower()

            if "amazon.in" not in current_url:

                # Retry once
                page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=45000
                )

                time.sleep(3)

                current_url = page.url.lower()

                if "amazon.in" not in current_url:

                    return [], (
                        "Amazon redirected away from "
                        f"amazon.in: {page.url}"
                    )

        # -----------------------------------------
        # LOAD LAZY CONTENT
        # -----------------------------------------

        scroll_page(page)

        selector = STORE_CONFIG[
            store
        ]["selector"]

        try:

            page.wait_for_selector(
                selector,
                timeout=15000
            )

        except PlaywrightTimeoutError:

            return [], (
                f"No products found on page "
                f"{page_number}"
            )

        links = page.locator(
            selector
        )

        count = links.count()

        products = []

        seen = set()

        # Limit per page
        max_links = min(
            count,
            100
        )

        for i in range(
            max_links
        ):

            try:

                link_element = links.nth(i)

                href = link_element.get_attribute(
                    "href"
                )

                if not href:
                    continue

                # ---------------------------------
                # ABSOLUTE LINK
                # ---------------------------------

                if href.startswith("/"):

                    if store == "Amazon":

                        href = (
                            "https://www.amazon.in"
                            + href
                        )

                    elif store == "Flipkart":

                        href = (
                            "https://www.flipkart.com"
                            + href
                        )

                    elif store == "Myntra":

                        href = (
                            "https://www.myntra.com"
                            + href
                        )

                href = href.split("?")[0]

                if href in seen:
                    continue

                seen.add(href)

                # ---------------------------------
                # CARD
                # ---------------------------------

                card = find_card(
                    link_element,
                    store
                )

                # ---------------------------------
                # TEXT
                # ---------------------------------

                try:

                    text = clean_text(
                        card.inner_text(
                            timeout=3000
                        )
                    )

                except:

                    try:

                        text = clean_text(
                            link_element.inner_text(
                                timeout=2000
                            )
                        )

                    except:

                        text = ""

                if not text:
                    continue

                # ---------------------------------
                # PRICE
                # ---------------------------------

                current_price, mrp = extract_prices(
                    text
                )

                if current_price is None:
                    continue

                # ---------------------------------
                # DISCOUNT
                # ---------------------------------

                discount = extract_discount(
                    text
                )

                if (
                    discount is None
                    and mrp
                    and mrp > current_price
                ):

                    discount = round(
                        (
                            (mrp - current_price)
                            / mrp
                        ) * 100,
                        1
                    )

                # ---------------------------------
                # RATING
                # ---------------------------------

                rating = extract_rating(
                    text
                )

                # ---------------------------------
                # IMAGE
                # ---------------------------------

                image_url = get_image(
                    card
                )

                if not image_url:

                    try:

                        parent = link_element.locator(
                            "xpath=.."
                        )

                        image_url = get_image(
                            parent
                        )

                    except:
                        pass

                # ---------------------------------
                # TITLE
                # ---------------------------------

                title = get_title(
                    card,
                    link_element
                )

                if not title:

                    title = "Product"

                # ---------------------------------
                # SAVE
                # ---------------------------------

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

            except:
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

        context = browser.new_context(

            locale="en-IN",

            timezone_id="Asia/Kolkata",

            viewport={
                "width": 1440,
                "height": 1000
            },

            user_agent=(
                "Mozilla/5.0 "
                "(X11; Linux x86_64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/131.0.0.0 "
                "Safari/537.36"
            )
        )

        page = context.new_page()

        for page_number in range(
            1,
            pages + 1
        ):

            st.write(
                f"🔎 {store} — "
                f"Page {page_number}"
            )

            page_products, error = scrape_page(
                page,
                store,
                search_query,
                page_number
            )

            if error:

                st.warning(
                    f"⚠️ {store} Page "
                    f"{page_number}: {error}"
                )

            if page_products:

                results.extend(
                    page_products
                )

            time.sleep(1)

    except Exception as e:

        st.warning(
            f"⚠️ {store} could not be searched: "
            f"{e}"
        )

    finally:

        try:

            if context:
                context.close()

        except:
            pass

    return results


# =========================================================
# HEADER
# =========================================================

st.title(
    "🔥 Deal Finder"
)

st.caption(
    "Compare deals across Flipkart, Amazon India & Myntra"
)


# =========================================================
# SIDEBAR
# =========================================================

with st.sidebar:

    st.header(
        "🔎 Search Filters"
    )

    store_choice = st.selectbox(
        "🛒 Store",
        [
            "All 3",
            "Flipkart",
            "Amazon",
            "Myntra"
        ]
    )

    product = st.text_input(
        "🔍 Product",
        placeholder="e.g. shoes"
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
        "🏷️ Brand",
        placeholder="Optional"
    )

    max_price = st.number_input(
        "💰 Maximum price",
        min_value=0,
        value=2000,
        step=100
    )

    min_rating = st.number_input(
        "⭐ Minimum rating",
        min_value=0.0,
        max_value=5.0,
        value=0.0,
        step=0.1
    )

    pages_to_scrape = st.number_input(
        "📄 Pages to search",
        min_value=1,
        max_value=10,
        value=3,
        step=1
    )

    sort_by = st.selectbox(
        "📊 Sort results",
        [
            "Cheapest",
            "Highest Discount",
            "Best Rating"
        ]
    )


# =========================================================
# SEARCH BUTTON
# =========================================================

search_clicked = st.button(
    "🔥 FIND BEST DEALS",
    type="primary",
    use_container_width=True
)


# =========================================================
# SEARCH
# =========================================================

if search_clicked:

    if not product.strip():

        st.error(
            "Please enter a product name."
        )

        st.stop()

    # -----------------------------------------
    # BUILD QUERY
    # -----------------------------------------

    query_parts = []

    if brand.strip():

        query_parts.append(
            brand.strip()
        )

    if gender != "Any":

        query_parts.append(
            gender
        )

    query_parts.append(
        product.strip()
    )

    search_query = " ".join(
        query_parts
    )

    st.info(
        f"🔍 Searching for: **{search_query}**"
    )

    # -----------------------------------------
    # STORES
    # -----------------------------------------

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

    # -----------------------------------------
    # BROWSER
    # -----------------------------------------

    try:

        with st.spinner(
            "🚀 Starting browser..."
        ):

            playwright, browser = start_playwright()

    except Exception as e:

        st.error(
            "❌ Browser could not start."
        )

        st.code(
            str(e)
        )

        st.stop()

    all_products = []

    # -----------------------------------------
    # SEARCH STORES
    # -----------------------------------------

    for store in stores:

        st.subheader(
            f"🛒 {store}"
        )

        with st.spinner(
            f"Searching {store}..."
        ):

            products = scrape_store(
                browser,
                store,
                search_query,
                int(pages_to_scrape)
            )

        if products:

            st.success(
                f"{store}: "
                f"{len(products)} products found"
            )

            all_products.extend(
                products
            )

        else:

            st.warning(
                f"{store}: No products found"
            )

    # -----------------------------------------
    # CLOSE
    # -----------------------------------------

    try:

        browser.close()
        playwright.stop()

    except:
        pass

    # =====================================================
    # NO RESULTS
    # =====================================================

    if not all_products:

        st.error(
            "😕 No products found."
        )

        st.info(
            "Try a broader search such as "
            "'shoes', 'tshirt' or 'laptop'."
        )

        st.stop()

    # =====================================================
    # DATAFRAME
    # =====================================================

    df = pd.DataFrame(
        all_products
    )

    # -----------------------------------------
    # REMOVE DUPLICATES
    # -----------------------------------------

    df = df.drop_duplicates(
        subset=["Link"]
    )

    # -----------------------------------------
    # PRICE FILTER
    # -----------------------------------------

    if max_price > 0:

        df = df[
            df["Price"] <= max_price
        ]

    # -----------------------------------------
    # RATING FILTER
    # -----------------------------------------

    if min_rating > 0:

        df = df[
            df["Rating"].fillna(0)
            >= min_rating
        ]

    # -----------------------------------------
    # SORT
    # -----------------------------------------

    if sort_by == "Cheapest":

        df = df.sort_values(
            by="Price",
            ascending=True
        )

    elif sort_by == "Highest Discount":

        df["_sort"] = df[
            "Discount %"
        ].fillna(0)

        df = df.sort_values(
            by="_sort",
            ascending=False
        )

        df = df.drop(
            columns=["_sort"]
        )

    elif sort_by == "Best Rating":

        df["_sort"] = df[
            "Rating"
        ].fillna(0)

        df = df.sort_values(
            by="_sort",
            ascending=False
        )

        df = df.drop(
            columns=["_sort"]
        )

    df = df.reset_index(
        drop=True
    )

    # =====================================================
    # SUMMARY
    # =====================================================

    st.success(
        f"🔥 {len(df)} products found"
    )

    col1, col2, col3 = st.columns(3)

    with col1:

        st.metric(
            "Products",
            len(df)
        )

    with col2:

        if len(df) > 0:

            cheapest = df[
                "Price"
            ].min()

            st.metric(
                "Cheapest",
                f"₹{cheapest:,.0f}"
            )

    with col3:

        if len(df) > 0:

            best_discount = df[
                "Discount %"
            ].dropna()

            if len(best_discount):

                st.metric(
                    "Best Discount",
                    f"{best_discount.max():.0f}%"
                )

    st.divider()

    # =====================================================
    # PAGE TABS
    # =====================================================

    pages_found = sorted(
        df["Page"]
        .dropna()
        .unique()
    )

    tabs = st.tabs(
        [
            f"📄 Page {int(p)}"
            for p in pages_found
        ]
    )

    for tab, page_number in zip(
        tabs,
        pages_found
    ):

        with tab:

            page_df = df[
                df["Page"] == page_number
            ]

            st.caption(
                f"{len(page_df)} products"
            )

            # -----------------------------------------
            # PRODUCT CARDS
            # -----------------------------------------

            for _, row in page_df.iterrows():

                with st.container(
                    border=True
                ):

                    image_col, info_col = st.columns(
                        [1, 3]
                    )

                    # IMAGE
                    with image_col:

                        image = row.get(
                            "Image"
                        )

                        if (
                            image
                            and isinstance(
                                image,
                                str
                            )
                            and image.startswith(
                                "http"
                            )
                        ):

                            try:

                                st.image(
                                    image,
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

                    # INFO
                    with info_col:

                        st.markdown(
                            f"### {row['Product']}"
                        )

                        st.write(
                            f"🛒 {row['Store']} "
                            f"• Page {int(row['Page'])}"
                        )

                        st.markdown(
                            f"## ₹{row['Price']:,.0f}"
                        )

                        if pd.notna(
                            row["MRP"]
                        ):

                            st.write(
                                f"MRP: ₹{row['MRP']:,.0f}"
                            )

                        if pd.notna(
                            row["Discount %"]
                        ):

                            st.success(
                                f"🔥 "
                                f"{row['Discount %']:.0f}% OFF"
                            )

                        if pd.notna(
                            row["Rating"]
                        ):

                            st.write(
                                f"⭐ "
                                f"{row['Rating']:.1f}/5"
                            )

                        st.link_button(
                            "🛍️ Open Product",
                            row["Link"]
                        )

    # =====================================================
    # COMPLETE TABLE
    # =====================================================

    st.divider()

    st.subheader(
        "📊 All Results"
    )

    table = df[
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

    table["Price"] = table[
        "Price"
    ].apply(
        lambda x:
        f"₹{x:,.0f}"
    )

    table["MRP"] = table[
        "MRP"
    ].apply(
        lambda x:
        f"₹{x:,.0f}"
        if pd.notna(x)
        else "-"
    )

    table["Discount %"] = table[
        "Discount %"
    ].apply(
        lambda x:
        f"{x:.0f}%"
        if pd.notna(x)
        else "-"
    )

    table["Rating"] = table[
        "Rating"
    ].apply(
        lambda x:
        f"{x:.1f}"
        if pd.notna(x)
        else "-"
    )

    st.dataframe(
        table,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Link": st.column_config.LinkColumn(
                "Product Link"
            )
        }
    )

    # =====================================================
    # CSV
    # =====================================================

    csv = df.to_csv(
        index=False
    ).encode("utf-8")

    st.download_button(
        "⬇️ Download Results CSV",
        data=csv,
        file_name="deal_finder_results.csv",
        mime="text/csv",
        use_container_width=True
    )