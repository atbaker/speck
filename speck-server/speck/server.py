from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from playwright.async_api import async_playwright

from core import routes as core_routes
from emails import routes as email_routes


app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        'https://mail.google.com',
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(email_routes.router)
app.include_router(core_routes.router)


@app.get("/")
async def hello_world():
    from core.cache import cache
    return {"output": f"Hello, world! Last task was {cache.get('last_task')}"}

@app.get('/playwright-test')
async def playwright_test():
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=False
        )
        context = await browser.new_context()
        page = await context.new_page()

        # Your existing code
        await page.goto("https://informeddelivery.usps.com/")
        await page.get_by_role("link", name="Sign In", exact=True).click()
        await page.get_by_placeholder("Username").click()
        await page.get_by_placeholder("Username").fill("<username>")
        await page.get_by_placeholder("Password").click()
        await page.get_by_placeholder("Password").fill("<password>")
        await page.get_by_role("button", name="Sign In").click()
        await page.get_by_role("link", name="Wednesday(3)").click()

        print(await page.locator('#CurrentMailpieces').text_content())

        # Close the browser context
        await browser.close()
    return {"output": "Hello, world!"}
