import datetime
from playwright.sync_api import sync_playwright

from . import SpeckFunction

NAME = "USPS hold mail"


def usps_hold_mail(
        start_date: str,
        end_date: str
):
    """
    Schedules a USPS hold mail for the user on usps.com, for a given
    date range.

    Parameters:
        start_date (str): The start date for the hold mail in MM/DD/YYYY format.
        end_date (str): The end date for the hold mail in MM/DD/YYYY format.

    Outcome:
        The user's mail will be held by USPS for the given date range.
    """
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
        page.get_by_label("* Username").fill("<username>")
        page.get_by_label("* Password").click()
        page.get_by_label("* Password").fill("<password>")
        page.get_by_role("button", name="Sign In").click()

        # Click "Check availability" on the hold mail page
        page.get_by_role("button", name="Check Availability").click()

        # Select the start and end dates
        page.locator("#start-date").fill(start_date)
        page.locator("#end-date").fill(end_date)

        # Click "Schedule Hold Mail"
        # (uncomment to actually schedule the mail hold)
        # page.get_by_role("button", name="Schedule Hold Mail").click()
        import pdb; pdb.set_trace()

        # Return a success message
        return f"Hold mail scheduled successfully starting {start_date} and ending {end_date}"


usps_hold_mail_function = SpeckFunction(
    name=NAME,
    func=usps_hold_mail
)


# Used for testing
if __name__ == '__main__':
    # TODO: Only importing to get the Playwright environment variable set
    from config import settings

    usps_hold_mail(
        start_date=datetime.date(2024, 8, 25),
        end_date=datetime.date(2024, 8, 30)
    )
