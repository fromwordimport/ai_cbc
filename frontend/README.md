# AI_CBC Frontend

AI_CBC 虚拟消费者联合分析平台的前端应用。

## 技术栈

- **框架**: React 18 + TypeScript
- **构建工具**: Vite 5
- **UI 组件库**: Ant Design 5
- **图表库**: ECharts 5 (echarts-for-react)
- **状态管理**: Zustand
- **路由**: React Router 6
- **HTTP 客户端**: Axios

## 开发环境

```bash
# 安装依赖
npm install

# 启动开发服务器（代理到后端 localhost:8000）
npm run dev

# 构建生产版本
npm run build

# 预览生产构建
npm run preview
```

## 页面说明

| 页面 | 路径 | 功能 |
|------|------|------|
| 总览 | `/` | 研究项目、虚拟消费者统计 |
| 属性重要性看板 | `/importance` | 属性重要性可视化、收敛诊断、WTP |
| 市场份额模拟器 | `/market-simulator` | 交互式产品配置、市场份额预测 |

## API 代理

开发服务器配置 Vite proxy，将 `/api` 请求转发到后端 `http://localhost:8000`。
