const { chromium } = require('/Users/maksos/.nvm/versions/node/v24.11.0/lib/node_modules/likec4/node_modules/playwright');
const path = require('path');
const fs = require('fs');

(async () => {
  const htmlPath = path.resolve('/Users/maksos/Documents/work/hack_ice/vizard-arctic-c4/vizard-architecture.html');
  const pdfPath = path.resolve('/Users/maksos/Documents/work/hack_ice/vizard-arctic-c4/vizard-arctic-architecture.pdf');

  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  await page.goto('file://' + htmlPath, { waitUntil: 'networkidle' });
  await page.pdf({
    path: pdfPath,
    format: 'A4',
    landscape: true,
    printBackground: true,
    margin: { top: '15mm', bottom: '15mm', left: '15mm', right: '15mm' }
  });
  await browser.close();
  console.log('PDF generated:', pdfPath);
})();
