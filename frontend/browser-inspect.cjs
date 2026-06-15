const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: false, slowMo: 200 });
  const context = await browser.newContext({ viewport: { width: 1400, height: 900 } });
  const page = await context.newPage();

  try {
    // 访问创建研究页面并检查 DOM
    console.log('=== 访问创建研究页面 ===');
    await page.goto('http://localhost:3001');
    await page.waitForTimeout(2000);
    await page.click('text=创建研究');
    await page.waitForTimeout(3000);

    // 截图
    await page.screenshot({ path: 'E:/machine_learning_study/AI_CBC/frontend/screenshot-study-create.png', fullPage: true });
    console.log('截图已保存');

    // 检查所有 input 和 textarea 元素
    const inputs = await page.locator('input, textarea, .ant-input').all();
    console.log(`\n找到 ${inputs.length} 个输入元素`);
    for (let i = 0; i < Math.min(inputs.length, 10); i++) {
      const placeholder = await inputs[i].getAttribute('placeholder').catch(() => '');
      const name = await inputs[i].getAttribute('name').catch(() => '');
      const id = await inputs[i].getAttribute('id').catch(() => '');
      const type = await inputs[i].getAttribute('type').catch(() => '');
      console.log(`  [${i}] placeholder="${placeholder}" name="${name}" id="${id}" type="${type}"`);
    }

    // 检查所有按钮
    const buttons = await page.locator('button, .ant-btn').all();
    console.log(`\n找到 ${buttons.length} 个按钮`);
    for (let i = 0; i < Math.min(buttons.length, 10); i++) {
      const text = await buttons[i].textContent().catch(() => '');
      const type = await buttons[i].getAttribute('type').catch(() => '');
      console.log(`  [${i}] text="${text.trim()}" type="${type}"`);
    }

    // 检查页面文本内容
    const pageText = await page.textContent('body');
    console.log('\n页面文本片段:', pageText.substring(0, 500));

  } catch (e) {
    console.error('错误:', e.message);
    await page.screenshot({ path: 'E:/machine_learning_study/AI_CBC/frontend/screenshot-error.png', fullPage: true });
  } finally {
    await browser.close();
  }
})();
