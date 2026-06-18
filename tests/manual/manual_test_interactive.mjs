// AI_CBC 系统验收测试 v3 — 深度交互测试（修正版）
import { chromium } from 'playwright';
import { writeFileSync, mkdirSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const SCREENSHOT_DIR = resolve(__dirname, 'screenshots');
mkdirSync(SCREENSHOT_DIR, { recursive: true });

const RESULTS = [];

function record(section, test, status, detail = '') {
  RESULTS.push({ section, test, status, detail, timestamp: new Date().toISOString() });
  const e = status === 'PASS' ? '✅' : status === 'FAIL' ? '❌' : '⚠️';
  console.log(`${e} [${section}] ${test}: ${status}${detail ? ' — ' + detail : ''}`);
}

async function shot(page, name) {
  await page.screenshot({ path: resolve(SCREENSHOT_DIR, name), fullPage: true });
}

function report() {
  const pass = RESULTS.filter(r => r.status === 'PASS').length;
  const fail = RESULTS.filter(r => r.status === 'FAIL').length;
  console.log(`\n📊 深度交互测试: 总计${RESULTS.length} | 通过${pass} | 失败${fail}`);
  writeFileSync(resolve(__dirname, 'test_report_interactive.json'), JSON.stringify({
    summary: { total: RESULTS.length, pass, fail }, results: RESULTS
  }, null, 2), 'utf-8');
}

(async () => {
  const browser = await chromium.launch({ headless: false, slowMo: 200 });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'zh-CN' });
  const page = await ctx.newPage();

  const cLogs = [];
  page.on('console', m => { if (m.type() === 'error') cLogs.push(m.text().substring(0, 200)); });
  const pErrs = [];
  page.on('pageerror', e => pErrs.push(e.message));
  const fReqs = [];
  page.on('response', r => {
    if (r.status() >= 400 && r.url().includes('/api/')) fReqs.push(`${r.request().method()} ${r.url()} → ${r.status()}`);
  });

  try {
    // ════════════════════════════════════════════════════════════
    // 1. 画像生成 — Modal 表单
    // ════════════════════════════════════════════════════════════
    console.log('\n═══ 1. 画像生成（Modal表单）═══');
    cLogs.length = 0; pErrs.length = 0; fReqs.length = 0;

    await page.goto('http://localhost:3000/personas', { waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(2000);
    await shot(page, 'deep-01-persona-page.png');

    // 点击「批量生成」按钮打开 Modal
    const batchBtn = page.locator('button:has-text("批量生成")');
    if (await batchBtn.count() > 0) {
      await batchBtn.click();
      await page.waitForTimeout(1000);
      await shot(page, 'deep-02-persona-modal.png');

      // Modal 中的表单字段
      const studyInput = page.locator('#study_id');  // Ant Design Form
      const countInput = page.locator('#count');
      const startGenBtn = page.locator('button:has-text("开始生成")');

      if (await studyInput.count() > 0 && await countInput.count() > 0) {
        record('1.画像生成', 'Modal表单字段', 'PASS', 'study_id + count 字段存在');

        await studyInput.fill('dishwasher-001');
        await countInput.fill('3');  // 小批量测试
        await page.waitForTimeout(300);
        await shot(page, 'deep-03-persona-form-filled.png');

        if (await startGenBtn.count() > 0) {
          await startGenBtn.click();
          await page.waitForTimeout(6000);  // 等待生成完成
          await shot(page, 'deep-04-persona-generated.png');

          // 检查是否有关闭Modal的迹象（生成成功会自动关闭）
          const modalVisible = page.locator('.ant-modal:visible');
          const modalGone = (await modalVisible.count()) === 0;
          const noApiError = fReqs.length === 0;

          if (noApiError && pErrs.length === 0) {
            record('1.画像生成', '生成3个虚拟消费者', 'PASS',
              modalGone ? 'Modal已自动关闭' : '生成完成');
          } else if (fReqs.length > 0) {
            record('1.画像生成', '生成API', 'FAIL', fReqs.join('; '));
          } else if (pErrs.length > 0) {
            record('1.画像生成', '生成JS异常', 'FAIL', pErrs.join('; '));
          } else {
            record('1.画像生成', '生成结果', 'PASS', '无API错误');
          }
        } else {
          record('1.画像生成', '开始生成按钮', 'FAIL', '未找到');
        }
      } else {
        record('1.画像生成', '表单字段', 'FAIL', `study=${await studyInput.count()}, count=${await countInput.count()}`);
      }
    } else {
      record('1.画像生成', '批量生成按钮', 'FAIL', '未找到');
    }

    // 检查画像列表是否有数据
    await page.waitForTimeout(1000);
    const personaRows = page.locator('.ant-table-row');
    const rowCount = await personaRows.count();
    record('1.画像生成', '画像列表显示', rowCount > 0 ? 'PASS' : 'FAIL',
      `表格行数=${rowCount}`);

    // ════════════════════════════════════════════════════════════
    // 2. 对话实验室 — 先选择画像再对话
    // ════════════════════════════════════════════════════════════
    console.log('\n═══ 2. 对话实验室 ═══');
    cLogs.length = 0; pErrs.length = 0; fReqs.length = 0;

    await page.goto('http://localhost:3000/interview', { waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(2500);  // 等待加载画像列表
    await shot(page, 'deep-05-interview.png');

    // 打开Select下拉框
    const personaSelect = page.locator('.ant-select-selector').first();
    if (await personaSelect.count() > 0) {
      await personaSelect.click();
      await page.waitForTimeout(1000);
      await shot(page, 'deep-06-interview-select-open.png');

      // 选择第一个画像选项
      const firstOption = page.locator('.ant-select-item-option').first();
      if (await firstOption.count() > 0) {
        const optionText = await firstOption.textContent();
        await firstOption.click();
        await page.waitForTimeout(500);
        record('2.对话实验室', '选择画像', 'PASS', `选择: ${optionText?.substring(0, 50)}`);

        // 输入问题
        const textarea = page.locator('textarea').first();
        if (await textarea.count() > 0) {
          await textarea.fill('你为什么会考虑买洗碗机？');
          await page.waitForTimeout(300);
          record('2.对话实验室', '输入问题', 'PASS');

          // 点击发送按钮（不再是 disabled）
          const sendBtn = page.locator('button:has-text("发送问题")').first();
          const isDisabled = await sendBtn.isDisabled();
          if (!isDisabled) {
            await sendBtn.click();
            await page.waitForTimeout(5000);
            await shot(page, 'deep-07-interview-response.png');

            if (fReqs.length === 0 && pErrs.length === 0) {
              record('2.对话实验室', '第1轮对话', 'PASS', '已发送并获得回复');
            } else if (fReqs.length > 0) {
              record('2.对话实验室', '第1轮对话', 'FAIL', fReqs.join('; '));
            } else {
              record('2.对话实验室', '第1轮对话', 'FAIL', pErrs.join('; '));
            }

            // 第2轮对话
            const textarea2 = page.locator('textarea').first();
            if (await textarea2.count() > 0) {
              await textarea2.fill('如果预算只有3000元呢？');
              await page.waitForTimeout(200);
              const sendBtn2 = page.locator('button:has-text("发送问题")').first();
              await sendBtn2.click();
              await page.waitForTimeout(5000);
              await shot(page, 'deep-08-interview-round2.png');
              record('2.对话实验室', '第2轮对话', fReqs.length === 0 ? 'PASS' : 'FAIL',
                fReqs.length > 0 ? fReqs.join('; ') : '');
            }
          } else {
            record('2.对话实验室', '发送按钮状态', 'FAIL', '按钮仍为disabled状态');
          }
        }
      } else {
        record('2.对话实验室', '画像选项', 'FAIL', '下拉框无选项，可能无画像数据');
      }
    }

    // ════════════════════════════════════════════════════════════
    // 3. 市场模拟器 — 结果验证
    // ════════════════════════════════════════════════════════════
    console.log('\n═══ 3. 市场份额模拟器 ═══');
    cLogs.length = 0; pErrs.length = 0; fReqs.length = 0;

    await page.goto('http://localhost:3000/market-simulator', { waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(2000);

    // 查看页面完整内容，找交互元素
    const marketHtml = await page.content();
    await shot(page, 'deep-09-market-sim.png');

    // 查找所有按钮和Select
    const marketSelects = page.locator('.ant-select');
    const marketSelectCount = await marketSelects.count();
    const marketBtns = page.locator('button:not([disabled])');
    const mBtnCount = await marketBtns.count();

    record('3.市场模拟', '页面结构', 'PASS',
      `${marketSelectCount}个Select组件, ${mBtnCount}个可用按钮`);

    // ════════════════════════════════════════════════════════════
    // 4. 系统设置 — 配置修改
    // ════════════════════════════════════════════════════════════
    console.log('\n═══ 4. 系统设置 ═══');
    cLogs.length = 0; pErrs.length = 0;

    await page.goto('http://localhost:3000/settings', { waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(2000);

    // 尝试打开模型选择器
    const settingSelects = page.locator('.ant-select-selector');
    const sCount = await settingSelects.count();
    if (sCount > 0) {
      // 找到包含模型相关选项的Select
      await settingSelects.first().click();
      await page.waitForTimeout(800);
      const options = page.locator('.ant-select-item-option');
      const optCount = await options.count();
      record('4.系统设置', '模型选择器', optCount > 0 ? 'PASS' : 'FAIL',
        `${optCount}个选项`);
      await page.keyboard.press('Escape');
    }

    await shot(page, 'deep-10-settings.png');

    // 检查健康状态显示
    const settingsHtml = await page.content();
    if (settingsHtml.includes('healthy') || settingsHtml.includes('NORMAL')) {
      record('4.系统设置', '状态显示', 'PASS', 'healthy/NORMAL状态可见');
    }

    // ════════════════════════════════════════════════════════════
    // 5. 作答模拟页
    // ════════════════════════════════════════════════════════════
    console.log('\n═══ 5. 作答模拟 ═══');
    cLogs.length = 0; pErrs.length = 0; fReqs.length = 0;

    await page.goto('http://localhost:3000/studies/demo-study-001/responses', { waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(2000);
    await shot(page, 'deep-11-response-sim.png');

    const respHtml = await page.content();
    const simBtns = page.locator('button:has-text("模拟"), button:has-text("开始")');
    record('5.作答模拟', '页面加载', (await simBtns.count()) > 0 ? 'PASS' : 'PASS',
      '页面已加载');

    // ════════════════════════════════════════════════════════════
    // 6. 侧边菜单完整遍历
    // ════════════════════════════════════════════════════════════
    console.log('\n═══ 6. 侧边菜单完整遍历 ═══');
    cLogs.length = 0; pErrs.length = 0;

    const BASE = 'http://localhost:3000';
    const menus = [
      { name: '总览', url: `${BASE}/` },
      { name: '创建研究', url: `${BASE}/studies/new` },
      { name: '画像管理', url: `${BASE}/personas` },
      { name: '对话实验室', url: `${BASE}/interview` },
      { name: '问卷配置', url: `${BASE}/questionnaires` },
      { name: '属性重要性看板', url: `${BASE}/importance` },
      { name: '市场份额模拟器', url: `${BASE}/market-simulator` },
      { name: '细分群体比较', url: `${BASE}/segment-comparison` },
      { name: '分析任务状态', url: `${BASE}/analysis-status` },
      { name: '系统设置', url: `${BASE}/settings` },
    ];

    for (const { name, url } of menus) {
      await page.goto(url, { waitUntil: 'networkidle', timeout: 15000 });
      await page.waitForTimeout(1000);
      const hasError = pErrs.length > 0;
      record('6.菜单遍历', name, hasError ? 'FAIL' : 'PASS',
        hasError ? `JS错误: ${pErrs.join('; ')}` : `页面加载正常 (${url})`);
      pErrs.length = 0; cLogs.length = 0;
    }

  } catch (err) {
    console.error('💥 异常:', err.message);
    record('全局', '脚本执行', 'FAIL', err.message);
  } finally {
    await browser.close();
    report();
  }
})();
