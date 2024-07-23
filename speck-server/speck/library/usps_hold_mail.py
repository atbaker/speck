import datetime
from playwright.sync_api import sync_playwright

# TODO: Only importing to get the Playwright environment variable set
from config import settings


def usps_hold_mail(
        username: str,
        password: str,
        start_date: datetime.date,
        end_date: datetime.date
):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=False
        )
        context = browser.new_context()
        page = context.new_page()

        # Open the hold mail page on usps.com, which will redirect us to log in
        page.goto("https://holdmail.usps.com/holdmail")

        # Log in
        page.get_by_label("* Username").click()
        page.get_by_label("* Username").fill(username)
        page.get_by_label("* Password").click()
        page.get_by_label("* Password").fill(password)
        page.get_by_role("button", name="Sign In").click()

        # Click "Check availability" on the hold mail page
        page.get_by_role("button", name="Check Availability").click()

        # Select the start and end dates
        page.locator("#start-date").fill(start_date.strftime('%m/%d/%Y'))
        page.locator("#end-date").fill(end_date.strftime('%m/%d/%Y'))

        # Click "Schedule Hold Mail"
        # (uncomment to actually schedule the mail hold)
        # page.get_by_role("button", name="Schedule Hold Mail").click()
        import pdb; pdb.set_trace()


# Used for testing
if __name__ == '__main__':
    usps_hold_mail(
        username="<your username goes here>",
        password="<your password goes here>",
        start_date=datetime.date(2024, 7, 25),
        end_date=datetime.date(2024, 7, 30)
    )
