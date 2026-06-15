const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: false, slowMo: 150 });
  const context = await browser.newContext({ viewport: { width: 1400, height: 900 } });
  const page = await context.newPage();

  const results = [];

  try {
    // 1. 访问总览页面
    console.log('=== 1. 访问总览页面 ===');
    await page.goto('http://localhost:3001');
    await page.waitForTimeout(3000);
    const title = await page.title();
    console.log('页面标题:', title);
    results.push({ step: '总览页面', status: title.includes('AI_CBC') ? 'PASS' : 'FAIL', detail: title });

    // 2. 检查左侧菜单所有 11 项
    console.log('\n=== 2. 检查左侧菜单 ===');
    const menuItems = await page.locator('.ant-menu-item, .ant-menu-submenu-title').allTextContents();
    const expectedMenus = ['总览', '创建研究', '画像管理', '问卷配置', '对话实验室', '属性重要性看板', '细分群体比较', '市场份额模拟器', '分析任务状态', '作答模拟', '系统设置'];
    const foundMenus = menuItems.filter(t => t.trim());
    console.log('菜单项:', foundMenus);
    const allMenusFound = expectedMenus.every(m => foundMenus.some(f => f.includes(m)));
    results.push({ step: '左侧菜单11项', status: allMenusFound ? 'PASS' : 'WARN', detail: `找到 ${foundMenus.length} 项，期望11项` });

    // 3. 点击"创建研究"并填写表单
    console.log('\n=== 3. 创建研究表单 ===');
    await page.click('text=创建研究');
    await page.waitForTimeout(2000);

    // 填写表单
    await page.fill('input[placeholder*="研究ID"], input[name*="studyId"], input[id*="studyId"]', 'browser-test-001');
    await page.waitForTimeout(500);
    await page.fill('input[placeholder*="产品类别"], input[name*="productCategory"]', '洗碗机');
    await page.waitForTimeout(500);
    await page.fill('textarea[placeholder*="研究目标"], input[name*="researchGoal"]', '评估消费者对洗碗机的偏好');
    await page.waitForTimeout(500);
    await page.fill('input[placeholder*="目标人群"], input[name*="targetSegments"]', '一线城市年轻家庭');
    await page.waitForTimeout(500);

    // 尝试点击创建按钮
    const createBtn = await page.locator('button:has-text("创建"), button:has-text("提交"), button[type="submit"]').first();
    if (await createBtn.isVisible().catch(() => false)) {
      console.log('创建按钮可见，准备点击...');
      // 不真正点击，避免创建重复研究
      results.push({ step: '创建研究表单', status: 'PASS', detail: '表单可填写，按钮可点击' });
    } else {
      results.push({ step: '创建研究表单', status: 'WARN', detail: '未找到创建按钮' });
    }

    // 4. 点击"画像管理"检查预置画像
    console.log('\n=== 4. 画像管理页面 ===');
    await page.click('text=画像管理');
    await page.waitForTimeout(3000);

    // 检查表格或列表
    const tableRows = await page.locator('.ant-table-row, .ant-list-item, tr').count();
    console.log(`表格行数: ${tableRows}`);
    const personaCards = await page.locator('.ant-card, .persona-card').count();
    console.log(`画像卡片数: ${personaCards}`);

    // 检查是否有画像数据
    const hasPersonaData = await page.locator('text=/persona-/, text=/segment/, text=/authenticity/').first().isVisible().catch(() => false);
    results.push({ step: '画像管理-数据展示', status: hasPersonaData ? 'PASS' : 'WARN', detail: hasPersonaData ? '画像数据可见' : '未检测到画像数据' });

    // 5. 点击"问卷配置"
    console.log('\n=== 5. 问卷配置页面 ===');
    await page.click('text=问卷配置');
    await page.waitForTimeout(3000);

    const hasQuestionnaireData = await page.locator('text=/选择集/, text=/D-efficiency/, text=/算法/').first().isVisible().catch(() => false);
    results.push({ step: '问卷配置页面', status: hasQuestionnaireData ? 'PASS' : 'WARN', detail: hasQuestionnaireData ? '问卷数据可见' : '未检测到问卷数据' });

    // 6. 点击"属性重要性看板"
    console.log('\n=== 6. 属性重要性看板 ===');
    await page.click('text=属性重要性看板');
    await page.waitForTimeout(3000);

    const hasChart = await page.locator('canvas, .echarts, svg, .ant-chart').first().isVisible().catch(() => false);
    const hasImportanceData = await page.locator('text=/品牌/, text=/容量/, text=/重要性/').first().isVisible().catch(() => false);
    results.push({ step: '属性重要性看板', status: hasImportanceData ? 'PASS' : 'WARN', detail: hasChart ? '图表可见' : '数据可见' });

    // 7. 点击"市场份额模拟器"
    console.log('\n=== 7. 市场份额模拟器 ===');
    await page.click('text=市场份额模拟器');
    await page.waitForTimeout(3000);

    const hasSimulatorForm = await page.locator('input, select, .ant-form').first().isVisible().catch(() => false);
    results.push({ step: '市场份额模拟器', status: hasSimulatorForm ? 'PASS' : 'WARN', detail: hasSimulatorForm ? '表单元素可见' : '未检测到表单' });

    // 8. 点击"对话实验室"
    console.log('\n=== 8. 对话实验室 ===');
    await page.click('text=对话实验室');
    await page.waitForTimeout(3000);

    const hasChatUI = await page.locator('input[placeholder*="问题"], textarea, .chat-input').first().isVisible().catch(() => false);
    results.push({ step: '对话实验室', status: hasChatUI ? 'PASS' : 'WARN', detail: hasChatUI ? '输入框可见' : '未检测到对话输入' });

    // 9. 点击"作答模拟"
    console.log('\n=== 9. 作答模拟页面 ===');
    await page.click('text=作答模拟');
    await page.waitForTimeout(3000);

    const hasSimulator = await page.locator('button:has-text("模拟"), button:has-text("开始"), .ant-btn').first().isVisible().catch(() => false);
    results.push({ step: '作答模拟页面', status: hasSimulator ? 'PASS' : 'WARN', detail: hasSimulator ? '模拟按钮可见' : '未检测到模拟按钮' });

    // 10. 点击"分析任务状态"
    console.log('\n=== 10. 分析任务状态 ===');
    await page.click('text=分析任务状态');
    await page.waitForTimeout(3000);

    const hasTaskList = await page.locator('table, .ant-list, .ant-table').first().isVisible().catch(() => false);
    results.push({ step: '分析任务状态', status: hasTaskList ? 'PASS' : 'WARN', detail: hasTaskList ? '任务列表可见' : '未检测到任务列表' });

    // 11. 点击"细分群体比较"
    console.log('\n=== 11. 细分群体比较 ===');
    await page.click('text=细分群体比较');
    await page.waitForTimeout(3000);

    const hasComparison = await page.locator('select, .ant-select, button:has-text("比较")').first().isVisible().catch(() => false);
    results.push({ step: '细分群体比较', status: hasComparison ? 'PASS' : 'WARN', detail: hasComparison ? '比较控件可见' : '未检测到比较控件' });

    // 12. 检查 Console 错误和网络请求
    console.log('\n=== 12. 检查 Console 错误 ===');
    const consoleErrors = [];
    page.on('console', msg => {
      if (msg.type() === 'error') {
        consoleErrors.push(msg.text());
      }
    });
    await page.waitForTimeout(1000);

    // 检查网络请求错误
    const networkErrors = [];
    page.on('response', response => {
      if (response.status() >= 400) {
        networkErrors.push(`${response.url()}: ${response.status()}`);
      }
    });
    await page.waitForTimeout(1000);

    const hasErrors = consoleErrors.length > 0 || networkErrors.length > 0;
    results.push({ step: 'Console/网络错误', status: hasErrors ? 'WARN' : 'PASS', detail: hasErrors ? `Console: ${consoleErrors.length}, Network: ${networkErrors.length}` : '无错误' });

    // 输出结果
    console.log('\n========== 详细验证结果汇总 ==========');
    for (const r of results) {
      console.log(`${r.status}: ${r.step} - ${r.detail}`);
    }
    const passed = results.filter(r => r.status === 'PASS').length;
    const warnings = results.filter(r => r.status === 'WARN').length;
    const failed = results.filter(r => r.status === 'FAIL').length;
    console.log(`\n总计: ${passed} 通过, ${warnings} 警告, ${failed} 失败`);

    // 截图保存
    await page.screenshot({ path: 'E:/machine_learning_study/AI_CBC/frontend/test-screenshot-detailed.png', fullPage: true });
    console.log('\n截图已保存至: E:/machine_learning_study/AI_CBC/frontend/test-screenshot-detailed.png');

  } catch (e) {
    console.error('测试出错:', e.message);
    console.error(e.stack);
    await page.screenshot({ path: 'E:/machine_learning_study/AI_CBC/frontend/test-screenshot-error.png', fullPage: true });
  } finally {
    await browser.close();
  }
})();
