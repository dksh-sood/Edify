from fastapi import APIRouter, HTTPException
from typing import List, Dict
from playwright.async_api import async_playwright

router = APIRouter()

async def scrape_hackathons() -> List[Dict[str, str]]:
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto("https://devpost.com/hackathons")
        items = await page.evaluate("""
            () => Array.from(document.querySelectorAll('.hackathon-tile')).map(card => ({
                title: card.querySelector('h3')?.textContent?.trim() || 'N/A',
                location: card.querySelector('.location')?.textContent?.trim() || 'Online',
                dates: card.querySelector('.submission-period')?.textContent?.trim() || 'N/A',
                link: card.querySelector('a')?.href || 'No link'
            }))
        """)
        await browser.close()
        return items

async def scrape_meetups() -> List[Dict[str, str]]:
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto("https://www.meetup.com/find/events/")
        try:
            await page.wait_for_selector('div[data-testid="categoryResults-eventCard"]', timeout=10000)
        except Exception:
            await browser.close()
            return []
        items = await page.evaluate("""
            () => Array.from(document.querySelectorAll('div[data-testid="categoryResults-eventCard"]')).map(card => ({
                title: card.querySelector('h2')?.textContent?.trim() || 'N/A',
                location: card.querySelector('p.line-clamp-1')?.textContent?.trim() || 'Online',
                date: card.querySelector('time')?.getAttribute('datetime') || 'No date',
                link: card.querySelector('a')?.getAttribute('href') || 'No link'
            }))
        """)
        await browser.close()
        return items

@router.get("")
async def get_events():
    try:
        hackathons = await scrape_hackathons()
        meetups = await scrape_meetups()
        events = [
            *[{
                "title": h.get("title"),
                "location": h.get("location"),
                "date": h.get("dates"),
                "link": h.get("link"),
                "type": "hackathon",
            } for h in hackathons],
            *[{
                "title": m.get("title"),
                "location": m.get("location"),
                "date": m.get("date"),
                "link": m.get("link"),
                "type": "meetup",
            } for m in meetups],
        ]
        return events
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to fetch events")
