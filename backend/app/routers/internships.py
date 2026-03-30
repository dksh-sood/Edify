from fastapi import APIRouter, HTTPException
from typing import List, Dict
from playwright.async_api import async_playwright

router = APIRouter()

async def scrape_internships() -> List[Dict[str, str]]:
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto("https://internshala.com/internships/")
        try:
            await page.wait_for_selector('.individual_internship', timeout=10000)
        except Exception:
            await browser.close()
            return []
        items = await page.evaluate("""
            () => Array.from(document.querySelectorAll('.individual_internship')).map(card => ({
                title: card.querySelector('.job-title-href')?.textContent?.trim() || 'N/A',
                company: card.querySelector('.company-name')?.textContent?.trim() || 'N/A',
                location: card.querySelector('.location')?.textContent?.trim() || 'Online',
                duration: card.querySelector('.duration')?.textContent?.trim() || 'N/A',
                stipend: card.querySelector('.stipend')?.textContent?.trim() || 'N/A',
                posted_time: card.querySelector('.status-success')?.textContent?.trim() || 'N/A',
                link: card.getAttribute('data-href') ? `https://internshala.com${card.getAttribute('data-href')}` : 'No link'
            }))
        """)
        await browser.close()
        return items

@router.get("")
async def get_internships():
    try:
        internships = await scrape_internships()
        return internships
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to fetch internships")
