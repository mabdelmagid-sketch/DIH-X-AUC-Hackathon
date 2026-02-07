const { chromium } = require('playwright');
const path = require('path');

const SCREENSHOT_DIR = '/home/yahyahammoudeh/Documents/Dih/DIH-X-AUC-Hackathon/test-screenshots';

async function runTests() {
  const results = {};

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 }
  });
  const page = await context.newPage();

  // Collect console errors
  const consoleErrors = [];
  page.on('console', msg => {
    if (msg.type() === 'error') {
      consoleErrors.push(msg.text());
    }
  });

  // ========== TEST 1: Dashboard ==========
  console.log('\n===== TEST 1: DASHBOARD (http://localhost:3000) =====');
  try {
    const dashResponse = await page.goto('http://localhost:3000', {
      waitUntil: 'networkidle',
      timeout: 30000
    });

    await page.waitForTimeout(2000); // Allow dynamic content to render

    const dashStatus = dashResponse.status();
    console.log(`HTTP Status: ${dashStatus}`);

    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '01-dashboard.png'),
      fullPage: true
    });
    console.log('Screenshot saved: 01-dashboard.png');

    // Check sidebar navigation
    const sidebarLinks = await page.evaluate(() => {
      const links = [];
      // Look for navigation links in common sidebar patterns
      const allLinks = document.querySelectorAll('nav a, aside a, [class*="sidebar"] a, [class*="nav"] a, [role="navigation"] a');
      allLinks.forEach(a => {
        links.push({ text: a.textContent.trim(), href: a.getAttribute('href') });
      });

      // Also check for any link-like elements
      const allElements = document.querySelectorAll('a');
      allElements.forEach(a => {
        const text = a.textContent.trim();
        const href = a.getAttribute('href');
        if (text && href && !links.find(l => l.text === text && l.href === href)) {
          links.push({ text, href });
        }
      });

      return links;
    });

    console.log('\nAll links found on page:');
    sidebarLinks.forEach(l => console.log(`  - "${l.text}" -> ${l.href}`));

    const expectedNavItems = ['Dashboard', 'Inventory', 'Forecast', 'Expiring', 'Promotions', 'Insights', 'Simulator'];
    const foundNav = {};

    for (const item of expectedNavItems) {
      const found = sidebarLinks.some(l =>
        l.text.toLowerCase().includes(item.toLowerCase())
      );
      foundNav[item] = found;
      console.log(`  Sidebar link "${item}": ${found ? 'FOUND' : 'NOT FOUND'}`);
    }

    // Get page title and visible content summary
    const pageTitle = await page.title();
    console.log(`\nPage title: "${pageTitle}"`);

    const visibleText = await page.evaluate(() => {
      const headings = [];
      document.querySelectorAll('h1, h2, h3').forEach(h => {
        if (h.textContent.trim()) headings.push(h.textContent.trim());
      });
      return headings;
    });
    console.log('Headings found:', visibleText);

    // Check for error indicators
    const hasErrorScreen = await page.evaluate(() => {
      const body = document.body.innerText.toLowerCase();
      return body.includes('error') && body.includes('500') ||
             body.includes('page not found') ||
             body.includes('application error');
    });

    results.dashboard = {
      status: dashStatus,
      loaded: dashStatus === 200 && !hasErrorScreen,
      sidebarLinks: foundNav,
      headings: visibleText,
      hasError: hasErrorScreen
    };

  } catch (err) {
    console.log(`DASHBOARD ERROR: ${err.message}`);
    results.dashboard = { loaded: false, error: err.message };
  }

  // ========== TEST 2: Inventory Page ==========
  console.log('\n===== TEST 2: INVENTORY (http://localhost:3000/inventory) =====');
  try {
    consoleErrors.length = 0;
    const invResponse = await page.goto('http://localhost:3000/inventory', {
      waitUntil: 'networkidle',
      timeout: 30000
    });
    await page.waitForTimeout(2000);

    const invStatus = invResponse.status();
    console.log(`HTTP Status: ${invStatus}`);

    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '02-inventory.png'),
      fullPage: true
    });
    console.log('Screenshot saved: 02-inventory.png');

    const invContent = await page.evaluate(() => {
      const headings = [];
      document.querySelectorAll('h1, h2, h3').forEach(h => {
        if (h.textContent.trim()) headings.push(h.textContent.trim());
      });

      const hasTables = document.querySelectorAll('table').length;
      const hasCards = document.querySelectorAll('[class*="card"], [class*="Card"]').length;
      const hasCharts = document.querySelectorAll('canvas, svg, [class*="chart"], [class*="Chart"]').length;

      return { headings, hasTables, hasCards, hasCharts };
    });

    console.log('Headings:', invContent.headings);
    console.log(`Tables: ${invContent.hasTables}, Cards: ${invContent.hasCards}, Charts: ${invContent.hasCharts}`);

    if (consoleErrors.length > 0) {
      console.log('Console errors:', consoleErrors);
    }

    const hasErrorScreen = await page.evaluate(() => {
      const body = document.body.innerText.toLowerCase();
      return (body.includes('error') && body.includes('500')) ||
             body.includes('page not found') ||
             body.includes('application error');
    });

    results.inventory = {
      status: invStatus,
      loaded: invStatus === 200 && !hasErrorScreen,
      content: invContent,
      hasError: hasErrorScreen,
      consoleErrors: [...consoleErrors]
    };

  } catch (err) {
    console.log(`INVENTORY ERROR: ${err.message}`);
    results.inventory = { loaded: false, error: err.message };
  }

  // ========== TEST 3: Forecast Page ==========
  console.log('\n===== TEST 3: FORECAST (http://localhost:3000/forecast) =====');
  try {
    consoleErrors.length = 0;
    const fcResponse = await page.goto('http://localhost:3000/forecast', {
      waitUntil: 'networkidle',
      timeout: 30000
    });
    await page.waitForTimeout(2000);

    const fcStatus = fcResponse.status();
    console.log(`HTTP Status: ${fcStatus}`);

    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '03-forecast.png'),
      fullPage: true
    });
    console.log('Screenshot saved: 03-forecast.png');

    const fcContent = await page.evaluate(() => {
      const headings = [];
      document.querySelectorAll('h1, h2, h3').forEach(h => {
        if (h.textContent.trim()) headings.push(h.textContent.trim());
      });

      const hasTables = document.querySelectorAll('table').length;
      const hasCards = document.querySelectorAll('[class*="card"], [class*="Card"]').length;
      const hasCharts = document.querySelectorAll('canvas, svg, [class*="chart"], [class*="Chart"]').length;

      return { headings, hasTables, hasCards, hasCharts };
    });

    console.log('Headings:', fcContent.headings);
    console.log(`Tables: ${fcContent.hasTables}, Cards: ${fcContent.hasCards}, Charts: ${fcContent.hasCharts}`);

    if (consoleErrors.length > 0) {
      console.log('Console errors:', consoleErrors);
    }

    const hasErrorScreen = await page.evaluate(() => {
      const body = document.body.innerText.toLowerCase();
      return (body.includes('error') && body.includes('500')) ||
             body.includes('page not found') ||
             body.includes('application error');
    });

    results.forecast = {
      status: fcStatus,
      loaded: fcStatus === 200 && !hasErrorScreen,
      content: fcContent,
      hasError: hasErrorScreen,
      consoleErrors: [...consoleErrors]
    };

  } catch (err) {
    console.log(`FORECAST ERROR: ${err.message}`);
    results.forecast = { loaded: false, error: err.message };
  }

  // ========== TEST 4: Insights Page ==========
  console.log('\n===== TEST 4: INSIGHTS (http://localhost:3000/insights) =====');
  try {
    consoleErrors.length = 0;
    const insResponse = await page.goto('http://localhost:3000/insights', {
      waitUntil: 'networkidle',
      timeout: 30000
    });
    await page.waitForTimeout(2000);

    const insStatus = insResponse.status();
    console.log(`HTTP Status: ${insStatus}`);

    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '04-insights.png'),
      fullPage: true
    });
    console.log('Screenshot saved: 04-insights.png');

    const insContent = await page.evaluate(() => {
      const headings = [];
      document.querySelectorAll('h1, h2, h3').forEach(h => {
        if (h.textContent.trim()) headings.push(h.textContent.trim());
      });

      const hasTables = document.querySelectorAll('table').length;
      const hasCards = document.querySelectorAll('[class*="card"], [class*="Card"]').length;
      const hasCharts = document.querySelectorAll('canvas, svg, [class*="chart"], [class*="Chart"]').length;

      return { headings, hasTables, hasCards, hasCharts };
    });

    console.log('Headings:', insContent.headings);
    console.log(`Tables: ${insContent.hasTables}, Cards: ${insContent.hasCards}, Charts: ${insContent.hasCharts}`);

    if (consoleErrors.length > 0) {
      console.log('Console errors:', consoleErrors);
    }

    const hasErrorScreen = await page.evaluate(() => {
      const body = document.body.innerText.toLowerCase();
      return (body.includes('error') && body.includes('500')) ||
             body.includes('page not found') ||
             body.includes('application error');
    });

    results.insights = {
      status: insStatus,
      loaded: insStatus === 200 && !hasErrorScreen,
      content: insContent,
      hasError: hasErrorScreen,
      consoleErrors: [...consoleErrors]
    };

  } catch (err) {
    console.log(`INSIGHTS ERROR: ${err.message}`);
    results.insights = { loaded: false, error: err.message };
  }

  // ========== TEST 5: Simulator Page ==========
  console.log('\n===== TEST 5: SIMULATOR (http://localhost:3000/simulator) =====');
  try {
    consoleErrors.length = 0;
    const simResponse = await page.goto('http://localhost:3000/simulator', {
      waitUntil: 'networkidle',
      timeout: 30000
    });
    await page.waitForTimeout(2000);

    const simStatus = simResponse.status();
    console.log(`HTTP Status: ${simStatus}`);

    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '05-simulator.png'),
      fullPage: true
    });
    console.log('Screenshot saved: 05-simulator.png');

    const simContent = await page.evaluate(() => {
      const headings = [];
      document.querySelectorAll('h1, h2, h3').forEach(h => {
        if (h.textContent.trim()) headings.push(h.textContent.trim());
      });

      const hasTables = document.querySelectorAll('table').length;
      const hasCards = document.querySelectorAll('[class*="card"], [class*="Card"]').length;
      const hasCharts = document.querySelectorAll('canvas, svg, [class*="chart"], [class*="Chart"]').length;
      const hasInputs = document.querySelectorAll('input, select, textarea, [class*="slider"], [class*="Slider"]').length;
      const hasButtons = document.querySelectorAll('button').length;

      return { headings, hasTables, hasCards, hasCharts, hasInputs, hasButtons };
    });

    console.log('Headings:', simContent.headings);
    console.log(`Tables: ${simContent.hasTables}, Cards: ${simContent.hasCards}, Charts: ${simContent.hasCharts}`);
    console.log(`Inputs: ${simContent.hasInputs}, Buttons: ${simContent.hasButtons}`);

    if (consoleErrors.length > 0) {
      console.log('Console errors:', consoleErrors);
    }

    const hasErrorScreen = await page.evaluate(() => {
      const body = document.body.innerText.toLowerCase();
      return (body.includes('error') && body.includes('500')) ||
             body.includes('page not found') ||
             body.includes('application error');
    });

    results.simulator = {
      status: simStatus,
      loaded: simStatus === 200 && !hasErrorScreen,
      content: simContent,
      hasError: hasErrorScreen,
      consoleErrors: [...consoleErrors]
    };

  } catch (err) {
    console.log(`SIMULATOR ERROR: ${err.message}`);
    results.simulator = { loaded: false, error: err.message };
  }

  await browser.close();

  // Final summary
  console.log('\n\n========== FINAL TEST SUMMARY ==========');
  console.log(JSON.stringify(results, null, 2));
}

runTests().catch(err => {
  console.error('Test runner failed:', err);
  process.exit(1);
});
