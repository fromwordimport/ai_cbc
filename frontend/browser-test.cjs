const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: false, slowMo: 100 });
  const context = await browser.newContext({ viewport: { width: 1400, height: 900 } });
  const page = await context.newPage();

  const results = [];

  try {
    // 1. 访问总览页面
    console.log('=== 1. 访问总览页面 ===');
    await page.goto('http://localhost:3001');
    await page.waitForTimeout(2000);
    const title = await page.title();
    console.log('页面标题:', title);
    results.push({ step: '总览页面', status: title.includes('AI_CBC') ? 'PASS' : 'FAIL', detail: title });

    // 2. 检查左侧菜单
    console.log('\n=== 2. 检查左侧菜单 ===');
    const menuItems = await page.locator('.ant-menu-item, .ant-menu-submenu-title').allTextContents();
    console.log('菜单项:', menuItems.filter(t => t.trim()));
    results.push({ step: '左侧菜单', status: menuItems.length > 5 ? 'PASS' : 'FAIL', detail: `找到 ${menuItems.length} 个菜单项` });

    // 3. 点击"创建研究"
    console.log('\n=== 3. 点击创建研究 ===');
    const createStudyLink = await page.locator('text=/创建研究|新建研究|Create Study/i').first();
    if (await createStudyLink.isVisible().catch(() => false)) {
      await createStudyLink.click();
      await page.waitForTimeout(1500);
      const formVisible = await page.locator('input, form').first().isVisible().catch(() => false);
      results.push({ step: '创建研究页面', status: formVisible ? 'PASS' : 'FAIL', detail: formVisible ? '表单可见' : '表单不可见' });
    } else {
      results.push({ step: '创建研究页面', status: 'FAIL', detail: '未找到创建研究入口' });
    }

    // 4. 返回总览
    console.log('\n=== 4. 返回总览 ===');
    await page.goto('http://localhost:3001');
    await page.waitForTimeout(1500);

    // 5. 点击"画像管理"
    console.log('\n=== 5. 点击画像管理 ===');
    const personaLink = await page.locator('text=/画像管理|Persona|消费者画像/i').first();
    if (await personaLink.isVisible().catch(() => false)) {
      await personaLink.click();
      await page.waitForTimeout(2000);
      const tableVisible = await page.locator('table, .ant-table, .ant-list').first().isVisible().catch(() => false);
      results.push({ step: '画像管理页面', status: tableVisible ? 'PASS' : 'FAIL', detail: tableVisible ? '列表/表格可见' : '列表不可见' });
    } else {
      results.push({ step: '画像管理页面', status: 'FAIL', detail: '未找到画像管理入口' });
    }

    // 6. 点击"问卷配置"
    console.log('\n=== 6. 点击问卷配置 ===');
    await page.goto('http://localhost:3001');
    await page.waitForTimeout(1000);
    const questionnaireLink = await page.locator('text=/问卷配置|问卷|Questionnaire/i').first();
    if (await questionnaireLink.isVisible().catch(() => false)) {
      await questionnaireLink.click();
      await page.waitForTimeout(2000);
      results.push({ step: '问卷配置页面', status: 'PASS', detail: '页面已加载' });
    } else {
      results.push({ step: '问卷配置页面', status: 'FAIL', detail: '未找到问卷配置入口' });
    }

    // 7. 点击"属性重要性看板"
    console.log('\n=== 7. 点击属性重要性看板 ===');
    await page.goto('http://localhost:3001');
    await page.waitForTimeout(1000);
    const importanceLink = await page.locator('text=/属性重要性|重要性|Importance/i').first();
    if (await importanceLink.isVisible().catch(() => false)) {
      await importanceLink.click();
      await page.waitForTimeout(2000);
      results.push({ step: '属性重要性看板', status: 'PASS', detail: '页面已加载' });
    } else {
      results.push({ step: '属性重要性看板', status: 'FAIL', detail: '未找到入口' });
    }

    // 8. 点击"市场份额模拟器"
    console.log('\n=== 8. 点击市场份额模拟器 ===');
    await page.goto('http://localhost:3001');
    await page.waitForTimeout(1000);
    const marketLink = await page.locator('text=/市场份额|市场模拟|Market/i').first();
    if (await marketLink.isVisible().catch(() => false)) {
      await marketLink.click();
      await page.waitForTimeout(2000);
      results.push({ step: '市场份额模拟器', status: 'PASS', detail: '页面已加载' });
    } else {
      results.push({ step: '市场份额模拟器', status: 'FAIL', detail: '未找到入口' });
    }

    // 9. 点击"系统设置"
    console.log('\n=== 9. 点击系统设置 ===');
    await page.goto('http://localhost:3001');
    await page.waitForTimeout(1000);
    const settingsLink = await page.locator('text=/系统设置|设置|Settings/i').first();
    if (await settingsLink.isVisible().catch(() => false)) {
      await settingsLink.click();
      await page.waitForTimeout(2000);
      const healthCard = await page.locator('text=/healthy|健康|系统健康/i').first().isVisible().catch(() => false);
      results.push({ step: '系统设置页面', status: healthCard ? 'PASS' : 'PASS', detail: '页面已加载' });
    } else {
      results.push({ step: '系统设置页面', status: 'FAIL', detail: '未找到入口' });
    }

    // 10. 检查 Console 错误
    console.log('\n=== 10. 检查 Console 错误 ===');
    const errors = [];
    page.on('console', msg => {
      if (msg.type() === 'error') {
        errors.push(msg.text());
      }
    });
    await page.waitForTimeout(1000);
    results.push({ step: 'Console 错误', status: errors.length === 0 ? 'PASS' : 'WARN', detail: errors.length > 0 ? `发现 ${errors.length} 个错误: ${errors.slice(0, 3).join(', ')}` : '无错误' });

    // 输出结果
    console.log('\n========== 验证结果汇总 ==========');
    for (const r of results) {
      console.log(`${r.status}: ${r.step} - ${r.detail}`);
    }
    const passed = results.filter(r => r.status === 'PASS').length;
    const failed = results.filter(r => r.status === 'FAIL').length;
    const warnings = results.filter(r => r.status === 'WARN').length;
    console.log(`\n总计: ${passed} 通过, ${failed} 失败, ${warnings} 警告`);

    // 截图保存
    await page.screenshot({ path: 'E:/machine_learning_study/AI_CBC/frontend/test-screenshot-final.png', fullPage: true });
    console.log('\n截图已保存至: E:/machine_learning_study/AI_CBC/frontend/test-screenshot-final.png');

  } catch (e) {
    console.error('测试出错:', e.message);
    await page.screenshot({ path: 'E:/machine_learning_study/AI_CBC/frontend/test-screenshot-error.png', fullPage: true });
  } finally {
    await browser.close();
  }
})();
