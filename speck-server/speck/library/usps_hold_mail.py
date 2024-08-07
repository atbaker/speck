import datetime
from playwright.sync_api import sync_playwright

from . import SpeckFunction

NAME = "USPS hold mail"


def usps_hold_mail(
        start_date: str,
        end_date: str
):
    """
    <overview>
    Schedules a USPS hold mail for the user on usps.com, for a given
    date range. Used so that a user's mail is not delivered to their home
    while they are away on a trip.
    </overview>

    <relevant-message-types>
        - Correspondence
        - Tickets and Bookings
    </relevant-message-types>

    <use-cases>
        <use-case>
            When the user has upcoming travel which likely takes them away
            from home.
        </use-case>
        <use-case>
            When the user has purchased airfare, indicating they are likely to
            travel soon.
        </use-case>
    </use-cases>

    <parameters>
        start_date (str): The start date for the hold mail in MM/DD/YYYY format.
        end_date (str): The end date for the hold mail in MM/DD/YYYY format.
    </parameters>

    <example-usage>
        <example>
            <example-email-from-another-user>
                **Andrew,  
                you're all set.**  
                We can't wait to see you on board. Before you fly, view full reservation
                details or make changes to your flight online.  
                ---  
                |  MANAGE TRIP  
                ---  
                Confirmation code:  
                **INDXPU**  
                ---  
                |  |  |  |  **Alaska**   
                Flight 1289  
                Boeing 737-900 (Winglets)  
                ---  
                
                **Traveler(s)**  
                ---  
                Andrew Baker  
                Seat: 22C Class: G (Coach)  
                
                |  |  **Wed, Aug 14  
                10:15 AM **  
                ---  
                **SFO**  
                San Francisco  
                
                ---  
                
                **Wed, Aug 14  
                12:27 PM **  
                ---  
                **SEA**  
                Seattle  
                
                |  |  **Alaska**   
                Flight 1166  
                Boeing 737-900 (Winglets)  
                ---  
                
                **Traveler(s)**  
                ---  
                Andrew Baker  
                Seat: 22D Class: G (Coach)  
                
                |  |  **Wed, Aug 21  
                07:00 AM **  
                ---  
                **SEA**  
                Seattle  
                
                ---  
                
                **Wed, Aug 21  
                09:14 AM **  
                ---  
                **SFO**  
                San Francisco
            </example-email-from-another-user>
            <correct-arguments>
                start_date="08/14/2024"
                end_date="08/21/2024"
            </correct-arguments>
            <example-button-text>
                Schedule USPS hold mail from 08/14/2024 to 08/21/2024
            </example-button-text>
        </example>
    </example-usage>
    """
    with sync_playwright() as playwright:
        browser = playwright.firefox.launch(
            headless=False,
            slow_mo=1500 # For demo purposes
        )
        context = browser.new_context()
        page = context.new_page()

        # Open the hold mail page on usps.com, which will redirect us to log in
        page.goto("https://holdmail.usps.com/holdmail")

        # Log in
        page.get_by_label("* Username").click()
        page.get_by_label("* Username").fill("<your username>")
        page.get_by_label("* Password").click()
        page.get_by_label("* Password").fill("<your password>")
        page.get_by_role("button", name="Sign In").click()

        # Click "Check availability" on the hold mail page
        page.get_by_role("button", name="Check Availability").click()

        # Select the start and end dates
        page.locator("#start-date").fill(start_date)
        page.locator("#end-date").fill(end_date)

        # Click "Schedule Hold Mail"
        # (uncomment to actually schedule the mail hold)
        page.get_by_role("button", name="Schedule Hold Mail").click()

        confirmation_span = page.get_by_text('Your Confirmation Number').first
        confirmation_number = confirmation_span.text_content().split(':')[1].strip()

        # Return a success message
        return f"Hold mail scheduled successfully starting {start_date} and ending {end_date} with confirmation number {confirmation_number}"


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
