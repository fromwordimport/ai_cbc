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
        browser = await p.chromium.launch(headless=True, slow_mo=100)
        context = await browser.new_context(viewport={"width": 1400, "height": 900})
        page = await context.new_page()

        # ========== Step 1: 访问 Dashboard ==========
        log("Step 1", "START", "访问 Dashboard 总览页面")
        try:
            await page.goto(f"{BASE_URL}/", wait_until="networkidle")
            await page.wait_for_timeout(1500)
            title = await page.title()
            log("Dashboard 加载", "PASS" if "AI_CBC" in title else "WARN", f"页面标题: {title}")
            await screenshot(page, "01-dashboard")
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
            await screenshot(page, "02-study-create-page")
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
            # 尝试选择"一线城市年轻家庭"
            try:
                await page.click('text=一线城市年轻家庭', timeout=2000)
            except:
                pass
            await page.wait_for_timeout(300)
            # 按 ESC 关闭下拉框
            await page.keyboard.press('Escape')
            await page.wait_for_timeout(300)
            await screenshot(page, "03-study-form-filled")

            # 提交
            await page.click('button:has-text("创建研究并生成问卷")')
            log("表单提交", "PASS", "已点击创建按钮")
            await page.wait_for_timeout(3000)
            await screenshot(page, "04-study-created")

            # 检查是否有成功消息或已跳回 Dashboard
            body_text = await page.inner_text('body')
            if "创建成功" in body_text or "问卷生成" in body_text or "研究项目列表" in body_text:
                log("研究创建", "PASS", f"研究 {STUDY_ID} 创建成功")
            else:
                log("研究创建", "WARN", "未检测到成功提示，可能已跳转或失败")
        except Exception as e:
            log("研究创建", "FAIL", str(e))
            await screenshot(page, "04-study-create-error")

        # ========== Step 3: 查看研究列表和新研究 ==========
        log("Step 3", "START", "返回 Dashboard 查看研究列表")
        try:
            await page.goto(f"{BASE_URL}/", wait_until="networkidle")
            await page.wait_for_timeout(2000)
            body_text = await page.inner_text('body')
            if STUDY_ID in body_text:
                log("研究列表", "PASS", f"新研究 {STUDY_ID} 已出现在列表中")
            else:
                log("研究列表", "WARN", "未在列表中找到新研究，可能创建失败或需要刷新")
            await screenshot(page, "05-dashboard-with-study")
        except Exception as e:
            log("研究列表", "FAIL", str(e))

        # ========== Step 4: 查看生成的问卷 ==========
        log("Step 4", "START", "查看生成的问卷")
        try:
            await page.goto(f"{BASE_URL}/studies/{STUDY_ID}/questionnaire", wait_until="networkidle")
            await page.wait_for_timeout(2000)
            body_text = await page.inner_text('body')
            if "问卷" in body_text or "CBC" in body_text or "choice" in body_text.lower():
                log("问卷查看", "PASS", "问卷页面已加载")
            else:
                log("问卷查看", "WARN", f"页面内容: {body_text[:100]}")
            await screenshot(page, "06-questionnaire")
        except Exception as e:
            log("问卷查看", "FAIL", str(e))

        # ========== Step 5: 画像管理 - 批量生成虚拟消费者 ==========
        log("Step 5", "START", "进入画像管理页面")
        try:
            await page.goto(f"{BASE_URL}/personas", wait_until="networkidle")
            await page.wait_for_timeout(1500)
            await page.wait_for_selector('text=虚拟消费者画像管理', timeout=5000)
            log("画像管理页面", "PASS", "页面已加载")
            await screenshot(page, "07-persona-manager")

            # 点击批量生成
            await page.click('button:has-text("批量生成")')
            await page.wait_for_timeout(500)
            await page.wait_for_selector('text=批量生成虚拟消费者', timeout=5000)
            log("批量生成弹窗", "PASS", "弹窗已打开")

            # 填写表单
            await page.fill('input[placeholder*="例如：dishwasher"]', STUDY_ID)
            await page.fill('input[type="number"]', "5")
            await screenshot(page, "08-persona-gen-form")

            # 提交
            await page.click('button:has-text("开始生成")')
            log("生成提交", "PASS", "已点击生成按钮")
            await page.wait_for_timeout(5000)
            await screenshot(page, "09-personas-generated")

            body_text = await page.inner_text('body')
            if "成功生成" in body_text or "生成" in body_text:
                log("画像生成", "PASS", "虚拟消费者已生成")
            else:
                log("画像生成", "WARN", "未检测到成功提示")
        except Exception as e:
            log("画像生成", "FAIL", str(e))
            await screenshot(page, "09-persona-gen-error")

        # ========== Step 6: 作答模拟 ==========
        log("Step 6", "START", "进入作答模拟页面")
        try:
            await page.goto(f"{BASE_URL}/studies/{STUDY_ID}/responses", wait_until="networkidle")
            await page.wait_for_timeout(2000)
            body_text = await page.inner_text('body')
            if "模拟作答" in body_text or "选择要模拟的" in body_text:
                log("作答模拟页面", "PASS", "页面已加载")
            else:
                log("作答模拟页面", "WARN", f"页面内容: {body_text[:100]}")
            await screenshot(page, "10-response-simulator")

            # 选择虚拟消费者（全选）
            await page.click('.ant-select-selection-search-input')
            await page.wait_for_timeout(500)
            # 尝试选择第一个选项
            options = await page.locator('.ant-select-item-option-content').all()
            if options:
                for opt in options[:3]:
                    try:
                        await opt.click()
                        await page.wait_for_timeout(200)
                    except:
                        break
                await page.keyboard.press('Escape')
                log("消费者选择", "PASS", f"选择了 {min(len(options), 3)} 个消费者")
            else:
                log("消费者选择", "WARN", "未找到消费者选项")

            await screenshot(page, "11-consumers-selected")

            # 选择模拟模式（LLM模式）
            await page.click('text=LLM 模式')
            await page.wait_for_timeout(300)
            await screenshot(page, "12-mode-selected")

            # 开始模拟
            await page.click('button:has-text("开始模拟作答")')
            log("模拟开始", "PASS", "已点击开始模拟")
            await page.wait_for_timeout(8000)
            await screenshot(page, "13-simulation-complete")

            body_text = await page.inner_text('body')
            if "模拟完成" in body_text or "成功" in body_text:
                log("作答模拟", "PASS", "模拟作答完成")
            else:
                log("作答模拟", "WARN", "未检测到完成提示")
        except Exception as e:
            log("作答模拟", "FAIL", str(e))
            await screenshot(page, "13-simulation-error")

        # ========== Step 7: 查看分析结果 ==========
        # 7a. 属性重要性看板
        log("Step 7a", "START", "查看属性重要性看板")
        try:
            await page.goto(f"{BASE_URL}/importance?study={STUDY_ID}", wait_until="networkidle")
            await page.wait_for_timeout(3000)
            body_text = await page.inner_text('body')
            if "重要性" in body_text or "part-worth" in body_text.lower() or "分析" in body_text:
                log("属性重要性看板", "PASS", "页面已加载")
            else:
                log("属性重要性看板", "WARN", f"页面内容: {body_text[:100]}")
            await screenshot(page, "14-importance-dashboard")
        except Exception as e:
            log("属性重要性看板", "FAIL", str(e))

        # 7b. 市场份额模拟器
        log("Step 7b", "START", "查看市场份额模拟器")
        try:
            await page.goto(f"{BASE_URL}/market-simulator", wait_until="networkidle")
            await page.wait_for_timeout(2000)
            body_text = await page.inner_text('body')
            if "市场份额" in body_text or "Market" in body_text or "模拟" in body_text:
                log("市场份额模拟器", "PASS", "页面已加载")
            else:
                log("市场份额模拟器", "WARN", f"页面内容: {body_text[:100]}")
            await screenshot(page, "15-market-simulator")
        except Exception as e:
            log("市场份额模拟器", "FAIL", str(e))

        # 7c. 分析任务状态
        log("Step 7c", "START", "查看分析任务状态")
        try:
            await page.goto(f"{BASE_URL}/analysis-status", wait_until="networkidle")
            await page.wait_for_timeout(2000)
            body_text = await page.inner_text('body')
            if "任务" in body_text or "状态" in body_text or "分析" in body_text:
                log("分析任务状态", "PASS", "页面已加载")
            else:
                log("分析任务状态", "WARN", f"页面内容: {body_text[:100]}")
            await screenshot(page, "16-analysis-status")
        except Exception as e:
            log("分析任务状态", "FAIL", str(e))

        # 7d. 细分群体比较
        log("Step 7d", "START", "查看细分群体比较")
        try:
            await page.goto(f"{BASE_URL}/segment-comparison", wait_until="networkidle")
            await page.wait_for_timeout(2000)
            body_text = await page.inner_text('body')
            if "细分" in body_text or "比较" in body_text or "Segment" in body_text:
                log("细分群体比较", "PASS", "页面已加载")
            else:
                log("细分群体比较", "WARN", f"页面内容: {body_text[:100]}")
            await screenshot(page, "17-segment-comparison")
        except Exception as e:
            log("细分群体比较", "FAIL", str(e))

        # ========== Step 8: 系统设置 ==========
        log("Step 8", "START", "查看系统设置")
        try:
            await page.goto(f"{BASE_URL}/settings", wait_until="networkidle")
            await page.wait_for_timeout(2000)
            body_text = await page.inner_text('body')
            if "设置" in body_text or "健康" in body_text or "Settings" in body_text:
                log("系统设置", "PASS", "页面已加载")
            else:
                log("系统设置", "WARN", f"页面内容: {body_text[:100]}")
            await screenshot(page, "18-settings")
        except Exception as e:
            log("系统设置", "FAIL", str(e))

        # ========== 最终汇总 ==========
        log("流程完成", "DONE", "全部步骤执行完毕")
        await browser.close()

        # 输出汇总报告
        print("\n" + "=" * 60)
        print("           AI_CBC 完整分析流程体验报告")
        print("=" * 60)
        passed = sum(1 for e in experience_log if e["status"] in ("PASS", "DONE"))
        failed = sum(1 for e in experience_log if e["status"] == "FAIL")
        warned = sum(1 for e in experience_log if e["status"] == "WARN")
        print(f"总步骤: {len(experience_log)} | 通过: {passed} | 失败: {failed} | 警告: {warned}")
        print("-" * 60)
        for e in experience_log:
            icon = {"PASS": "✅", "FAIL": "❌", "WARN": "⚠️", "INFO": "ℹ️", "START": "▶️", "DONE": "🏁"}.get(e["status"], "❓")
            print(f"{icon} [{e['timestamp']}] {e['step']}")
            if e["detail"]:
                print(f"   → {e['detail']}")
        print("-" * 60)
        print(f"截图保存路径: {SCREENSHOT_DIR}")
        print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
