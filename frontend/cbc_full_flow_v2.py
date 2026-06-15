import asyncio
import os
import time
from datetime import datetime

from playwright.async_api import async_playwright

BASE_URL = "http://localhost:3000"
API_URL = "http://localhost:8000/api/v1"
SCREENSHOT_DIR = r"E:\machine_learning_study\AI_CBC\frontend\screenshots"
STUDY_ID = f"test-study-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

os.makedirs(SCREENSHOT_DIR, exist_ok=True)

experience_log = []

def log(step, status, detail=""):
    entry = {
        "timestamp": datetime.now().strftime("%H:%M:%S"),
        "step": step,
        "status": status,
        "detail": detail,
    }
    experience_log.append(entry)
    print(f"[{entry['timestamp']}] [{status}] {step}: {detail}")

async def screenshot(page, name):
    path = os.path.join(SCREENSHOT_DIR, f"{name}.png")
    await page.screenshot(path=path, full_page=True)
    log(f"截图: {name}", "INFO", f"已保存到 {path}")
    return path

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, slow_mo=150)
        context = await browser.new_context(viewport={"width": 1400, "height": 900})
        page = await context.new_page()

        # ========== Step 1: 访问 Dashboard ==========
        log("Step 1", "START", "访问 Dashboard 总览页面")
        try:
            await page.goto(f"{BASE_URL}/", wait_until="networkidle")
            await page.wait_for_timeout(1500)
            title = await page.title()
            log("Dashboard 加载", "PASS" if "AI_CBC" in title else "WARN", f"页面标题: {title}")
            await screenshot(page, "v2-01-dashboard")
        except Exception as e:
            log("Dashboard 加载", "FAIL", str(e))
            await browser.close()
            return

        # ========== Step 2: 创建新研究 ==========
        log("Step 2", "START", "点击左侧菜单「创建研究」")
        try:
            await page.click('li:has-text("创建研究")')
            await page.wait_for_timeout(1500)
            await page.wait_for_selector('text=创建新研究', timeout=5000)
            log("创建研究页面", "PASS", "表单已加载")
            await screenshot(page, "v2-02-study-create-page")
        except Exception as e:
            log("创建研究页面", "FAIL", str(e))

        # 填写表单
        log("Step 2b", "START", "填写研究表单")
        try:
            await page.fill('input[placeholder*="例如：dishwasher"]', STUDY_ID)
            await page.fill('input[placeholder*="洗碗机、扫地机器人"]', "智能音箱")
            await page.fill('textarea[placeholder*="评估消费者对"]', "评估消费者对智能音箱各属性水平的偏好，指导新品定价与功能配置")
            # 目标人群 - 选择标签
            await page.click('.ant-select-selection-search-input')
            await page.wait_for_timeout(300)
            try:
                await page.click('text=一线城市年轻家庭', timeout=2000)
            except:
                pass
            await page.wait_for_timeout(300)
            await page.keyboard.press('Escape')
            await page.wait_for_timeout(300)
            await screenshot(page, "v2-03-study-form-filled")

            # 提交
            await page.click('button:has-text("创建研究并生成问卷")')
            log("表单提交", "PASS", "已点击创建按钮")
            await page.wait_for_timeout(3000)
            await screenshot(page, "v2-04-study-created")

            body_text = await page.inner_text('body')
            if "创建成功" in body_text or "问卷生成" in body_text or "研究项目列表" in body_text:
                log("研究创建", "PASS", f"研究 {STUDY_ID} 创建成功")
            else:
                log("研究创建", "WARN", "未检测到成功提示")
        except Exception as e:
            log("研究创建", "FAIL", str(e))
            await screenshot(page, "v2-04-study-create-error")

        # ========== Step 3: 批量生成虚拟消费者 ==========
        log("Step 3", "START", "进入画像管理并批量生成消费者")
        try:
            await page.goto(f"{BASE_URL}/personas", wait_until="networkidle")
            await page.wait_for_timeout(1500)
            await page.wait_for_selector('text=虚拟消费者画像管理', timeout=5000)
            await screenshot(page, "v2-05-persona-manager")

            await page.click('button:has-text("批量生成")')
            await page.wait_for_timeout(500)
            await page.wait_for_selector('text=批量生成虚拟消费者', timeout=5000)
            await page.fill('input[placeholder*="例如：dishwasher"]', STUDY_ID)
            await page.fill('input[type="number"]', "5")
            await screenshot(page, "v2-06-persona-gen-form")

            await page.click('button:has-text("开始生成")')
            log("生成提交", "PASS", "已点击生成按钮")
            await page.wait_for_timeout(6000)
            await screenshot(page, "v2-07-personas-generated")

            body_text = await page.inner_text('body')
            if "成功生成" in body_text:
                log("画像生成", "PASS", "虚拟消费者已生成")
            else:
                log("画像生成", "WARN", "未检测到成功提示")
        except Exception as e:
            log("画像生成", "FAIL", str(e))

        # ========== Step 4: 作答模拟（使用随机模式） ==========
        log("Step 4", "START", "进入作答模拟页面并执行模拟")
        try:
            await page.goto(f"{BASE_URL}/studies/{STUDY_ID}/responses", wait_until="networkidle")
            await page.wait_for_timeout(2000)
            await screenshot(page, "v2-08-response-simulator")

            # 选择虚拟消费者 - 点击多选框
            await page.click('.ant-select-selection-search-input')
            await page.wait_for_timeout(800)
            
            # 获取所有选项并选择前3个
            options = await page.locator('.ant-select-item-option-content').all()
            selected_count = 0
            for opt in options[:3]:
                try:
                    await opt.click()
                    await page.wait_for_timeout(300)
                    selected_count += 1
                except:
                    break
            await page.keyboard.press('Escape')
            log("消费者选择", "PASS", f"选择了 {selected_count} 个消费者")
            await screenshot(page, "v2-09-consumers-selected")

            # 使用默认随机模式（不做LLM切换，避免超时问题）
            log("模拟模式", "INFO", "使用默认随机模式(stochastic)")
            await screenshot(page, "v2-10-mode-selected")

            # 开始模拟
            await page.click('button:has-text("开始模拟作答")')
            log("模拟开始", "PASS", "已点击开始模拟")
            await page.wait_for_timeout(10000)
            await screenshot(page, "v2-11-simulation-complete")

            body_text = await page.inner_text('body')
            if "模拟完成" in body_text or "成功" in body_text:
                log("作答模拟", "PASS", "模拟作答完成")
            else:
                log("作答模拟", "WARN", "未检测到完成提示")
        except Exception as e:
            log("作答模拟", "FAIL", str(e))
            await screenshot(page, "v2-11-simulation-error")

        # ========== Step 5: 运行 HB 分析 ==========
        log("Step 5", "START", "在属性重要性看板运行HB分析")
        try:
            await page.goto(f"{BASE_URL}/importance?study={STUDY_ID}", wait_until="networkidle")
            await page.wait_for_timeout(2000)
            await screenshot(page, "v2-12-importance-before")
            
            # 点击运行 HB 分析按钮
            hb_button = await page.locator('button:has-text("运行 HB 分析")').first()
            if await hb_button.is_visible().catch(lambda: False):
                await hb_button.click()
                log("HB 分析", "PASS", "已点击运行 HB 分析")
                await page.wait_for_timeout(5000)
            else:
                log("HB 分析", "WARN", "未找到运行 HB 分析按钮")
            await screenshot(page, "v2-13-importance-after")
        except Exception as e:
            log("HB 分析", "FAIL", str(e))

        # ========== Step 6: 查看市场份额模拟器 ==========
        log("Step 6", "START", "查看市场份额模拟器")
        try:
            await page.goto(f"{BASE_URL}/market-simulator", wait_until="networkidle")
            await page.wait_for_timeout(2000)
            await screenshot(page, "v2-14-market-simulator")
            log("市场份额模拟器", "PASS", "页面已加载")
        except Exception as e:
            log("市场份额模拟器", "FAIL", str(e))

        # ========== Step 7: 查看分析任务状态 ==========
        log("Step 7", "START", "查看分析任务状态")
        try:
            await page.goto(f"{BASE_URL}/analysis-status", wait_until="networkidle")
            await page.wait_for_timeout(2000)
            await screenshot(page, "v2-15-analysis-status")
            log("分析任务状态", "PASS", "页面已加载")
        except Exception as e:
            log("分析任务状态", "FAIL", str(e))

        # ========== 最终汇总 ==========
        log("流程完成", "DONE", "全部步骤执行完毕")
        await browser.close()

        # 输出汇总报告（使用 ASCII 兼容字符）
        print("\n" + "=" * 60)
        print("           AI_CBC 完整分析流程体验报告")
        print("=" * 60)
        passed = sum(1 for e in experience_log if e["status"] in ("PASS", "DONE"))
        failed = sum(1 for e in experience_log if e["status"] == "FAIL")
        warned = sum(1 for e in experience_log if e["status"] == "WARN")
        print(f"总步骤: {len(experience_log)} | 通过: {passed} | 失败: {failed} | 警告: {warned}")
        print("-" * 60)
        for e in experience_log:
            icon = {"PASS": "[OK]", "FAIL": "[NG]", "WARN": "[!!]", "INFO": "[i]", "START": "[>]", "DONE": "[*]"}.get(e["status"], "[?]")
            print(f"{icon} [{e['timestamp']}] {e['step']}")
            if e["detail"]:
                print(f"   -> {e['detail']}")
        print("-" * 60)
        print(f"截图保存路径: {SCREENSHOT_DIR}")
        print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
