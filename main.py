from playwright.sync_api import sync_playwright
from dataclasses import dataclass, asdict, field
import pandas as pd
import argparse
import os
import sys
import re

def safe_filename(name: str) -> str:
    """Sanitize filename to remove/replace invalid characters."""
    name = name.strip().replace(' ', '_')
    return re.sub(r'[^\w\-]', '_', name)

@dataclass
class Business:
    name: str = None
    address: str = None
    website: str = None
    phone_number: str = None
    reviews_count: int = None
    reviews_average: float = None
    category: str = None
    subcategory: str = None
    city: str = None
    state: str = None
    area: str = None

@dataclass
class BusinessList:
    business_list: list[Business] = field(default_factory=list)
    save_at = 'output'

    def dataframe(self):
        return pd.json_normalize(
            (asdict(business) for business in self.business_list), sep="_"
        )

    def save_to_excel(self, filename):
        if not os.path.exists(self.save_at):
            os.makedirs(self.save_at)
        self.dataframe().to_excel(f"{self.save_at}/{filename}.xlsx", index=False)

    def save_to_csv(self, filename):
        if not os.path.exists(self.save_at):
            os.makedirs(self.save_at)
        self.dataframe().to_csv(f"{self.save_at}/{filename}.csv", index=False)

def extract_coordinates_from_url(url: str) -> tuple[float, float]:
    coordinates = url.split('/@')[-1].split('/')[0]
    return float(coordinates.split(',')[0]), float(coordinates.split(',')[1])

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-s", "--search", type=str)
    parser.add_argument("-t", "--total", type=int)
    args = parser.parse_args()

    if args.total:
        total = args.total
    else:
        total = 1_000_000

    search_list = []

    if args.search:
        search_list = [{"category": args.search, "city": "", "state": ""}]
    else:
        input_file_path = os.path.join(os.getcwd(), 'input.txt')
        if os.path.exists(input_file_path):
            with open(input_file_path, 'r') as file:
                for line in file.readlines():
                    parts = [part.strip() for part in line.strip().split(',')]
                    if len(parts) == 3:
                        search_list.append({
                            "category": parts[0],
                            "city": parts[1],
                            "state": parts[2]
                        })
        if len(search_list) == 0:
            print("Error: You must either pass the -s search argument, or add searches to input.txt in the format: category,city,state")
            sys.exit()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        page.goto("https://www.google.com/maps", timeout=60000)
        page.wait_for_timeout(5000)

        for search_for_index, search_item in enumerate(search_list):
            category = search_item['category']
            city = search_item['city']
            state = search_item['state']

            search_query = f"{category}, {city}, {state}"
            print(f"-----\n{search_for_index} - {search_query}")

            page.locator('//input[@id="searchboxinput"]').fill(search_query)
            page.wait_for_timeout(3000)
            page.keyboard.press("Enter")
            page.wait_for_timeout(5000)

            page.hover('//a[contains(@href, "https://www.google.com/maps/place")]')

            previously_counted = 0
            while True:
                page.mouse.wheel(0, 10000)
                page.wait_for_timeout(3000)

                current_count = page.locator(
                    '//a[contains(@href, "https://www.google.com/maps/place")]'
                ).count()

                if current_count >= total:
                    listings = page.locator(
                        '//a[contains(@href, "https://www.google.com/maps/place")]'
                    ).all()[:total]
                    listings = [listing.locator("xpath=..") for listing in listings]
                    print(f"Total Scraped: {len(listings)}")
                    break
                elif current_count == previously_counted:
                    listings = page.locator(
                        '//a[contains(@href, "https://www.google.com/maps/place")]'
                    ).all()
                    print(f"Arrived at all available\nTotal Scraped: {len(listings)}")
                    break
                else:
                    previously_counted = current_count
                    print(f"Currently Scraped: {current_count}")

            business_list = BusinessList()

            for listing in listings:
                try:
                    listing.click()
                    page.wait_for_timeout(5000)

                    name_attr = 'aria-label'
                    address_xpath = '//button[@data-item-id="address"]//div[contains(@class, "fontBodyMedium")]'
                    website_xpath = '//a[@data-item-id="authority"]//div[contains(@class, "fontBodyMedium")]'
                    phone_xpath = '//button[contains(@data-item-id, "phone:tel:")]//div[contains(@class, "fontBodyMedium")]'
                    review_count_xpath = '//button[@jsaction="pane.reviewChart.moreReviews"]//span'
                    reviews_avg_xpath = '//div[@jsaction="pane.reviewChart.moreReviews"]//div[@role="img"]'
                    # subcategory_xpath = '//div[@role="main"]//div[contains(@class, "fontBodyMedium") and contains(text(), "·")]/preceding-sibling::div[1]'
                    subcategory_xpath = '//div[contains(@aria-label, "stars")]/following-sibling::div[contains(@class, "fontBodyMedium")]'

                    business = Business()

                    name_val = listing.get_attribute(name_attr)
                    business.name = name_val if name_val else ""

                    business.address = page.locator(address_xpath).nth(0).inner_text() if page.locator(address_xpath).count() > 0 else ""
                    business.website = page.locator(website_xpath).nth(0).inner_text() if page.locator(website_xpath).count() > 0 else ""
                    business.phone_number = page.locator(phone_xpath).nth(0).inner_text() if page.locator(phone_xpath).count() > 0 else ""
                    business.subcategory = page.locator(subcategory_xpath).nth(0).inner_text() if page.locator(subcategory_xpath).count() > 0 else ""

                    if page.locator(review_count_xpath).count() > 0:
                        business.reviews_count = int(
                            page.locator(review_count_xpath).inner_text()
                            .split()[0]
                            .replace(',', '')
                            .strip()
                        )
                    else:
                        business.reviews_count = ""

                    if page.locator(reviews_avg_xpath).count() > 0:
                        business.reviews_average = float(
                            page.locator(reviews_avg_xpath)
                            .get_attribute(name_attr)
                            .split()[0]
                            .replace(',', '.')
                            .strip()
                        )
                    else:
                        business.reviews_average = ""

                    # Subcategory
                    if page.locator(subcategory_xpath).count() > 0:
                        business.subcategory = page.locator(subcategory_xpath).nth(0).inner_text().strip()
                    else:
                        business.subcategory = ""

                    # Area from address (up to second comma)
                    if business.address:
                        addr_parts = business.address.split(',')
                        if len(addr_parts) >= 2:
                            business.area = ','.join(addr_parts[:2]).strip()
                        elif len(addr_parts) >= 1:
                            business.area = addr_parts[0].strip()

                    business.category = category
                    business.city = city
                    business.state = state

                    business_list.business_list.append(business)

                except Exception as e:
                    print(f'Error occurred: {e}')

            safe_name = safe_filename(f"google_maps_data_{category}_{city}_{state}")
            business_list.save_to_csv(safe_name)

        browser.close()

if __name__ == "__main__":
    main()
