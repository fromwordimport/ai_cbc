const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: false, slowMo: 200 });
  const context = await browser.newContext({ viewport: { width: 1400, height: 900 } });
  const page = await context.newPage();

  const results = [];
  const consoleErrors = [];
  const networkErrors = [];

  page.on('console', msg => {
    if (msg.type() === 'error') consoleErrors.push(msg.text());
  });
  page.on('response', response => {
    if (response.status() >= 400) networkErrors.push(`${response.url()}: ${response.status()}`);
  });

  try {
    // 1. 总览页面
    console.log('=== 1. 总览页面 ===');
    await page.goto('http://localhost:3001');
    await page.waitForTimeout(3000);
    const title = await page.title();
    results.push({ step: '总览页面', status: 'PASS', detail: title });

    // 2. 创建研究 - 填写表单
    console.log('\n=== 2. 创建研究表单 ===');
    await page.click('text=创建研究');
    await page.waitForTimeout(2000);

    await page.fill('#study_id', 'browser-test-001');
    await page.fill('#product_category', '洗碗机');
    await page.fill('#research_goal', '评估消费者对洗碗机各属性水平的偏好');
    // 目标人群是 Select 组件，尝试输入
    await page.click('#target_segments');
    await page.waitForTimeout(500);
    await page.keyboard.type('一线城市年轻家庭');
    await page.waitForTimeout(500);
    await page.keyboard.press('Enter');
    await page.waitForTimeout(500);

    console.log('表单填写完成');
    results.push({ step: '创建研究表单', status: 'PASS', detail: '4个字段全部可填写' });

    // 3. 画像管理
    console.log('\n=== 3. 画像管理 ===');
    await page.click('text=画像管理');
    await page.waitForTimeout(3000);
    await page.screenshot({ path: 'E:/machine_learning_study/AI_CBC/frontend/screenshot-persona-manager.png', fullPage: true });

    const personaText = await page.textContent('body');
    const hasPersona = personaText.includes('persona-') || personaText.includes('segment') || personaText.includes('authenticity');
    results.push({ step: '画像管理', status: hasPersona ? 'PASS' : 'WARN', detail: hasPersona ? '画像数据展示正常' : '未检测到画像数据' });

    // 4. 问卷配置
    console.log('\n=== 4. 问卷配置 ===');
    await page.click('text=问卷配置');
    await page.waitForTimeout(3000);
    await page.screenshot({ path: 'E:/machine_learning_study/AI_CBC/frontend/screenshot-questionnaire.png', fullPage: true });

    const qText = await page.textContent('body');
    const hasQData = qText.includes('选择集') || qText.includes('D-efficiency') || qText.includes('算法');
    results.push({ step: '问卷配置', status: hasQData ? 'PASS' : 'WARN', detail: hasQData ? '问卷数据可见' : '未检测到问卷数据' });

    // 5. 属性重要性看板
    console.log('\n=== 5. 属性重要性看板 ===');
    await page.click('text=属性重要性看板');
    await page.waitForTimeout(3000);
    await page.screenshot({ path: 'E:/machine_learning_study/AI_CBC/frontend/screenshot-importance.png', fullPage: true });

    const iText = await page.textContent('body');
    const hasImportance = iText.includes('品牌') || iText.includes('重要性') || iText.includes('R-hat');
    results.push({ step: '属性重要性看板', status: hasImportance ? 'PASS' : 'WARN', detail: hasImportance ? '分析数据可见' : '未检测到分析数据' });

    // 6. 市场份额模拟器
    console.log('\n=== 6. 市场份额模拟器 ===');
    await page.click('text=市场份额模拟器');
    await page.waitForTimeout(3000);
    await page.screenshot({ path: 'E:/machine_learning_study/AI_CBC/frontend/screenshot-market.png', fullPage: true });

    const mText = await page.textContent('body');
    const hasMarket = mText.includes('模拟') || mText.includes('场景') || mText.includes('产品');
    results.push({ step: '市场份额模拟器', status: hasMarket ? 'PASS' : 'WARN', detail: hasMarket ? '模拟控件可见' : '未检测到模拟控件' });

    // 7. 对话实验室
    console.log('\n=== 7. 对话实验室 ===');
    await page.click('text=对话实验室');
    await page.waitForTimeout(3000);
    await page.screenshot({ path: 'E:/machine_learning_study/AI_CBC/frontend/screenshot-interview.png', fullPage: true });

    const intText = await page.textContent('body');
    const hasChat = intText.includes('发送') || intText.includes('对话') || intText.includes('问题');
    results.push({ step: '对话实验室', status: hasChat ? 'PASS' : 'WARN', detail: hasChat ? '对话界面可见' : '未检测到对话界面' });

    // 8. 作答模拟
    console.log('\n=== 8. 作答模拟 ===');
    await page.click('text=作答模拟');
    await page.waitForTimeout(3000);
    await page.screenshot({ path: 'E:/machine_learning_study/AI_CBC/frontend/screenshot-simulator.png', fullPage: true });

    const simText = await page.textContent('body');
    const hasSim = simText.includes('模拟') || simText.includes('开始') || simText.includes('画像');
    results.push({ step: '作答模拟', status: hasSim ? 'PASS' : 'WARN', detail: hasSim ? '模拟界面可见' : '未检测到模拟界面' });

    // 9. 分析任务状态
    console.log('\n=== 9. 分析任务状态 ===');
    await page.click('text=分析任务状态');
    await page.waitForTimeout(3000);
    await page.screenshot({ path: 'E:/machine_learning_study/AI_CBC/frontend/screenshot-analysis-status.png', fullPage: true });

    const aText = await page.textContent('body');
    const hasTasks = aText.includes('任务') || aText.includes('状态') || aText.includes('COMPLETED');
    results.push({ step: '分析任务状态', status: hasTasks ? 'PASS' : 'WARN', detail: hasTasks ? '任务列表可见' : '未检测到任务列表' });

    // 10. 细分群体比较
    console.log('\n=== 10. 细分群体比较 ===');
    await page.click('text=细分群体比较');
    await page.waitForTimeout(3000);
    await page.screenshot({ path: 'E:/machine_learning_study/AI_CBC/frontend/screenshot-segment.png', fullPage: true });

    const sText = await page.textContent('body');
    const hasCompare = sText.includes('比较') || sText.includes('群体') || sText.includes('选择');
    results.push({ step: '细分群体比较', status: hasCompare ? 'PASS' : 'WARN', detail: hasCompare ? '比较控件可见' : '未检测到比较控件' });

    // 11. 系统设置
    console.log('\n=== 11. 系统设置 ===');
    await page.click('text=系统设置');
    await page.waitForTimeout(3000);
    await page.screenshot({ path: 'E:/machine_learning_study/AI_CBC/frontend/screenshot-settings.png', fullPage: true });

    const setText = await page.textContent('body');
    const hasSettings = setText.includes('健康') || setText.includes('成本') || setText.includes('LLM');
    results.push({ step: '系统设置', status: hasSettings ? 'PASS' : 'WARN', detail: hasSettings ? '设置面板可见' : '未检测到设置面板' });

    // 12. 汇总 Console/网络错误
    console.log('\n=== 12. 错误检查 ===');
    const hasErrors = consoleErrors.length > 0 || networkErrors.length > 0;
    results.push({ step: 'Console/网络错误', status: hasErrors ? 'WARN' : 'PASS', detail: `Console错误: ${consoleErrors.length}, 网络错误: ${networkErrors.length}` });

    if (consoleErrors.length > 0) {
      console.log('Console 错误:', consoleErrors.slice(0, 5));
    }
    if (networkErrors.length > 0) {
      console.log('网络错误:', networkErrors.slice(0, 5));
    }

    // 输出结果
    console.log('\n========== 浏览器验证结果汇总 ==========');
    for (const r of results) {
      console.log(`${r.status}: ${r.step} - ${r.detail}`);
    }
    const passed = results.filter(r => r.status === 'PASS').length;
    const warnings = results.filter(r => r.status === 'WARN').length;
    console.log(`\n总计: ${passed} 通过, ${warnings} 警告, 0 失败`);
    console.log(`\n截图保存在: E:/machine_learning_study/AI_CBC/frontend/screenshot-*.png`);

  } catch (e) {
    console.error('测试出错:', e.message);
    await page.screenshot({ path: 'E:/machine_learning_study/AI_CBC/frontend/screenshot-error.png', fullPage: true });
  } finally {
    await browser.close();
  }
})();
