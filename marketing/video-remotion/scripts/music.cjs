const { chromium } = require('playwright'); const fs = require('fs');
(async () => { const b = await chromium.launch(); const p = await b.newPage();
  await p.goto('file://' + process.argv[2]);
  const s = await p.evaluate(([d, x]) => renderAudio(d, x), [parseFloat(process.argv[3]), parseFloat(process.argv[4])]);
  fs.writeFileSync(process.argv[5], Buffer.from(s, 'base64')); await b.close(); })();
