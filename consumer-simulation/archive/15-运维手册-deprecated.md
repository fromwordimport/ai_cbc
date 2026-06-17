# 运维手册

> **版本**：v1.0  
> **定位**：消费者模拟系统生产环境的部署、监控、告警、故障排查和日常运维指南  
> **使用说明**：运维人员、SRE、以及需要自行部署系统的开发团队参考

---

## 一、部署架构

```
                        ┌─────────────┐
                        │   负载均衡   │
                        │  (Nginx/ALB)│
                        └──────┬──────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
        ┌─────▼─────┐    ┌─────▼─────┐    ┌─────▼─────┐
        │ API服务-1  │    │ API服务-2  │    │ API服务-3  │
        │  (FastAPI) │    │  (FastAPI) │    │  (FastAPI) │
        └─────┬─────┘    └─────┬─────┘    └─────┬─────┘
              │                │                │
              └────────────────┼────────────────┘
                               │
        ┌──────────────────────┼──────────────────────┐
        │                      │                      │
   ┌────▼────┐           ┌─────▼─────┐          ┌────▼────┐
   │  Redis  │           │   Kafka   │          │MongoDB  │
   │ Cluster │           │  Cluster  │          │Cluster  │
   │ (缓存)  │           │  (消息队列)│          │(主存储) │
   └─────────┘           └───────────┘          └─────────┘
        │                                              │
        │                      ┌───────────────────────┘
        │                      │
   ┌────▼──────────────────────▼────┐
   │         S3 / MinIO            │
   │        (对象存储/归档)         │
   └───────────────────────────────┘
```

---

## 二、环境要求

### 2.1 生产环境最低配置

| 组件 | 实例数 | CPU | 内存 | 存储 | 网络 |
|------|--------|-----|------|------|------|
| API服务 | 3 | 4核 | 8GB | 50GB SSD | 内网 |
| Redis | 6（3主3从） | 4核 | 64GB | 100GB SSD | 内网 |
| MongoDB | 9（3分片×3副本） | 8核 | 32GB | 2TB SSD | 内网 |
| Kafka | 3 | 4核 | 16GB | 500GB SSD | 内网 |
| S3/MinIO | 3 | 4核 | 16GB | 10TB HDD | 内网 |

### 2.2 依赖软件版本

```yaml
runtime:
  python: ">=3.10"
  nodejs: ">=18"  # 如果需要前端管理界面

middleware:
  redis: "7.x"
  mongodb: "6.x"
  kafka: "3.x"

optional:
  nginx: "1.24+"
  docker: "24.x"
  kubernetes: "1.28+"
```

### 2.3 网络要求

```
内部通信：
- API → Redis：6379
- API → MongoDB：27017
- API → Kafka：9092
- API → S3：9000

外部暴露：
- API入口：443（HTTPS）
- 管理后台：443（HTTPS，可选）
- 监控面板：3000（Grafana，内网VPN访问）
```

---

## 三、部署步骤

### 3.1 使用 Docker Compose 快速部署（开发/测试环境）

```yaml
# docker-compose.yml
version: '3.8'

services:
  api:
    image: consumer-sim-api:latest
    build: .
    ports:
      - "8000:8000"
    environment:
      - REDIS_URL=redis://redis:6379
      - MONGODB_URL=mongodb://mongo:27017/consumer_sim
      - KAFKA_BOOTSTRAP=kafka:9092
    depends_on:
      - redis
      - mongo
      - kafka
    deploy:
      replicas: 2

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

  mongo:
    image: mongo:6
    ports:
      - "27017:27017"
    volumes:
      - mongo_data:/data/db

  kafka:
    image: confluentinc/cp-kafka:7.5
    ports:
      - "9092:9092"
    environment:
      KAFKA_BROKER_ID: 1
      KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://localhost:9092

  zookeeper:
    image: confluentinc/cp-zookeeper:7.5
    environment:
      ZOOKEEPER_CLIENT_PORT: 2181

  minio:
    image: minio/minio:latest
    command: server /data --console-address ":9001"
    ports:
      - "9000:9000"
      - "9001:9001"
    volumes:
      - minio_data:/data

volumes:
  redis_data:
  mongo_data:
  minio_data:
```

**部署命令**：

```bash
# 1. 克隆代码
git clone https://github.com/your-org/consumer-simulation.git
cd consumer-simulation

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 填入LLM API密钥等

# 3. 启动服务
docker-compose up -d

# 4. 检查健康状态
curl http://localhost:8000/health
```

### 3.2 使用 Kubernetes 生产部署

```yaml
# k8s-deployment.yml 示例
apiVersion: apps/v1
kind: Deployment
metadata:
  name: consumer-sim-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: consumer-sim-api
  template:
    metadata:
      labels:
        app: consumer-sim-api
    spec:
      containers:
      - name: api
        image: consumer-sim-api:v1.0.0
        ports:
        - containerPort: 8000
        env:
        - name: REDIS_URL
          valueFrom:
            secretKeyRef:
              name: app-secrets
              key: redis-url
        - name: MONGODB_URL
          valueFrom:
            secretKeyRef:
              name: app-secrets
              key: mongodb-url
        resources:
          requests:
            memory: "4Gi"
            cpu: "2"
          limits:
            memory: "8Gi"
            cpu: "4"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /ready
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
```

**部署命令**：

```bash
# 1. 创建命名空间
kubectl create namespace consumer-sim

# 2. 应用配置
kubectl apply -f k8s/ -n consumer-sim

# 3. 检查状态
kubectl get pods -n consumer-sim
kubectl get svc -n consumer-sim
```

---

## 四、监控指标

### 4.1 业务指标（Business Metrics）

| 指标名 | 类型 | 说明 | 采集方式 |
|--------|------|------|---------|
| `persona_generated_total` | Counter | 累计生成画像数 | API埋点 |
| `persona_passed_rate` | Gauge | 画像通过率 | 定时计算 |
| `persona_avg_authenticity_score` | Gauge | 平均真实感评分 | 定时计算 |
| `simulation_generated_total` | Counter | 累计模拟记录数 | API埋点 |
| `simulation_avg_score` | Gauge | 模拟记录平均评分 | 定时计算 |
| `human_review_queue_size` | Gauge | 人工审核队列长度 | 定时采集 |
| `bias_flagged_total` | Counter | 偏见标记次数 | API埋点 |

### 4.2 系统指标（System Metrics）

| 指标名 | 类型 | 说明 | 来源 |
|--------|------|------|------|
| `api_request_duration_seconds` | Histogram | API请求耗时 | 应用埋点 |
| `api_request_total` | Counter | API请求数（按状态码分类） | 应用埋点 |
| `llm_request_duration_seconds` | Histogram | LLM调用耗时 | 应用埋点 |
| `llm_request_total` | Counter | LLM调用次数（按模型分类） | 应用埋点 |
| `redis_operation_duration_seconds` | Histogram | Redis操作耗时 | 应用埋点 |
| `mongodb_operation_duration_seconds` | Histogram | MongoDB操作耗时 | 应用埋点 |
| `kafka_consumer_lag` | Gauge | Kafka消费延迟 | Kafka Exporter |

### 4.3 健康检查端点

```python
# /health - 存活检查
{
  "status": "healthy",
  "timestamp": "2026-06-08T14:30:00Z",
  "version": "1.0.0"
}

# /ready - 就绪检查（检查依赖服务）
{
  "status": "ready",
  "checks": {
    "redis": "ok",
    "mongodb": "ok",
    "kafka": "ok"
  }
}

# /metrics - Prometheus指标
# 返回Prometheus格式的指标数据
```

---

## 五、告警规则

### 5.1 关键告警

| 告警名 | 触发条件 | 级别 | 通知方式 | 处理SOP |
|--------|---------|------|---------|---------|
| API错误率过高 | 5分钟内错误率 > 5% | P1 | 电话+钉钉 | 查看日志，定位错误模块 |
| API延迟过高 | P95延迟 > 30s 持续5分钟 | P1 | 电话+钉钉 | 检查LLM API状态，扩容 |
| LLM调用失败 | 10分钟内失败 > 20次 | P1 | 电话+钉钉 | 切换备用模型，检查配额 |
| MongoDB连接失败 | 连续3次健康检查失败 | P1 | 电话+钉钉 | 检查MongoDB集群状态 |
| Redis连接失败 | 连续3次健康检查失败 | P1 | 电话+钉钉 | 检查Redis集群状态 |
| Kafka消费堆积 | 消费延迟 > 1000 持续10分钟 | P2 | 钉钉 | 扩容消费者，检查处理速度 |
| 人工审核队列过长 | 队列长度 > 50 持续1小时 | P2 | 钉钉 | 通知审核人员处理 |
| 画像通过率过低 | 单日通过率 < 50% | P2 | 钉钉 | 检查Prompt和校验规则 |
| 存储容量预警 | 磁盘使用 > 80% | P2 | 钉钉 | 清理日志，扩展存储 |
| 偏见检测高危 | 单日高危标记 > 10次 | P3 | 邮件 | 检查生成策略，调整偏见库 |

### 5.2 Prometheus告警规则示例

```yaml
# alert_rules.yml
groups:
  - name: consumer_sim_alerts
    rules:
      - alert: HighAPIErrorRate
        expr: |
          (
            sum(rate(api_request_total{status=~"5.."}[5m]))
            /
            sum(rate(api_request_total[5m]))
          ) > 0.05
        for: 2m
        labels:
          severity: p1
        annotations:
          summary: "API错误率过高"
          description: "5分钟内错误率超过5%"

      - alert: HighAPILatency
        expr: histogram_quantile(0.95, rate(api_request_duration_seconds_bucket[5m])) > 30
        for: 5m
        labels:
          severity: p1
        annotations:
          summary: "API P95延迟过高"
          description: "P95延迟超过30秒"

      - alert: LLMCallFailures
        expr: increase(llm_request_total{status="error"}[10m]) > 20
        for: 1m
        labels:
          severity: p1
        annotations:
          summary: "LLM调用频繁失败"
          description: "10分钟内失败超过20次"

      - alert: KafkaConsumerLag
        expr: kafka_consumer_group_lag > 1000
        for: 10m
        labels:
          severity: p2
        annotations:
          summary: "Kafka消费延迟"
          description: "消费延迟超过1000条"
```

---

## 六、故障排查SOP

### 6.1 API服务无响应

```markdown
1. 检查Pod状态
   kubectl get pods -n consumer-sim
   → 如果 Pod 不在 Running 状态，查看事件
   kubectl describe pod {pod_name} -n consumer-sim

2. 检查依赖服务
   curl http://localhost:8000/ready
   → 如果 redis/mongodb/kafka 检查失败，定位具体依赖

3. 查看应用日志
   kubectl logs -f deployment/consumer-sim-api -n consumer-sim
   → 搜索 ERROR / FATAL 关键字

4. 检查资源使用
   kubectl top pods -n consumer-sim
   → CPU/内存是否触顶，是否需要扩容

5. 检查LLM API状态
   → 测试直接调用LLM API是否可用
   → 检查API配额是否耗尽
```

### 6.2 画像生成大量失败

```markdown
1. 查看失败类型分布
   → Schema失败？Logic失败？Bias失败？LLM失败？

2. 如果是Schema失败
   → 检查LLM输出格式是否稳定
   → 考虑降低生成温度，或增强Prompt格式约束

3. 如果是Logic失败
   → 检查种子组合是否过于极端
   → 调整张力阈值或放宽部分规则

4. 如果是Bias失败
   → 检查刻板印象模式库是否需要更新
   → 检查采样是否过于集中

5. 如果是LLM失败
   → 切换备用模型
   → 检查API配额和限流
```

### 6.3 数据库性能下降

```markdown
1. 检查慢查询
   db.currentOp({"secs_running": {$gt: 5}})

2. 检查索引使用情况
   db.simulations.explain("executionStats").find({persona_id: "xxx"})
   → 如果 COLLSCAN，需要创建索引

3. 检查连接数
   db.serverStatus().connections
   → 当前连接 / 可用连接

4. 检查存储空间
   db.stats()
   → 如果接近上限，启动归档任务

5. 检查副本集状态
   rs.status()
   → 确保Primary选举正常
```

### 6.4 Redis缓存命中率低

```markdown
1. 查看命中率
   redis-cli INFO stats
   → keyspace_hits / (keyspace_hits + keyspace_misses)

2. 如果命中率 < 80%
   → 检查缓存Key设计是否合理
   → 检查TTL设置是否过短
   → 检查是否频繁出现缓存穿透

3. 检查内存使用
   redis-cli INFO memory
   → used_memory / maxmemory
   → 如果接近上限，考虑扩容或调整淘汰策略

4. 检查大Key
   redis-cli --bigkeys
   → 是否存在异常大的Key影响性能
```

### 6.5 Kafka消费延迟

```markdown
1. 查看消费者组状态
   kafka-consumer-groups.sh --bootstrap-server kafka:9092 --describe --group sim_consumers

2. 查看Topic堆积情况
   kafka-run-class.sh kafka.tools.GetOffsetShell --broker-list kafka:9092 --topic simulation_records

3. 如果LAG持续增长
   → 扩容消费者实例
   → 检查消费者处理逻辑是否阻塞
   → 检查是否有消费者实例崩溃

4. 如果是突发流量
   → 临时增加Partition数
   → 启动更多消费者Pod
```

---

## 七、日常运维任务

### 7.1 每日检查清单

```markdown
□ 查看告警面板（Grafana），确认无未处理P1/P2告警
□ 检查API服务健康状态（/health /ready）
□ 检查Kafka消费者LAG是否正常
□ 检查人工审核队列长度
□ 查看昨日业务指标（生成量、通过率、平均分）
□ 查看LLM API调用量和费用

预计耗时：15分钟
```

### 7.2 每周检查清单

```markdown
□ 查看存储使用情况，预测扩容需求
□ 检查慢查询TOP10，优化索引
□ 检查Redis缓存命中率趋势
□ 审查偏见检测高危案例
□ 更新刻板印象模式库（如有需要）
□ 检查备份任务是否成功执行
□ 审查安全日志，检查异常访问

预计耗时：1小时
```

### 7.3 每月检查清单

```markdown
□ 生成画像资产月报
□ 归档超过90天的模拟记录
□ 清理超过30天的应用日志
□ 评估是否需要扩容（QPS、存储）
□ 检查证书到期时间（HTTPS等）
□ 执行灾难恢复演练
□ 审查并更新告警阈值
□ 更新依赖组件到最新稳定版（测试环境先验证）

预计耗时：半天
```

---

## 八、备份与恢复

### 8.1 备份策略

| 数据 | 备份频率 | 保留期 | 方式 |
|------|---------|--------|------|
| MongoDB | 每日凌晨2点 | 30天 | mongodump + 压缩上传S3 |
| Redis | 每小时RDB | 7天 | Redis RDB + AOF |
| 配置文件 | 每次变更 | 永久 | Git版本控制 |
| S3对象 | 每周 | 90天 | 跨区域复制 |

### 8.2 MongoDB备份脚本

```bash
#!/bin/bash
# backup_mongodb.sh

DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/backup/mongodb/$DATE"
S3_BUCKET="s3://consumer-sim-backups/mongodb/"

# 执行备份
mongodump --uri="$MONGODB_URL" --out="$BACKUP_DIR"

# 压缩
tar -czf "$BACKUP_DIR.tar.gz" -C "$BACKUP_DIR" .

# 上传S3
aws s3 cp "$BACKUP_DIR.tar.gz" "$S3_BUCKET"

# 清理本地文件
rm -rf "$BACKUP_DIR" "$BACKUP_DIR.tar.gz"

# 清理旧备份（保留30天）
aws s3 ls "$S3_BUCKET" | awk '{print $4}' | sort -r | tail -n +31 | \
  xargs -I {} aws s3 rm "$S3_BUCKET{}"
```

### 8.3 灾难恢复流程

```markdown
场景：MongoDB集群完全不可用

1. 确认故障范围
   - 是单个节点还是整个集群？
   - 是否有可用的Secondary可以提升为Primary？

2. 如果集群可恢复
   - 修复故障节点
   - 重新加入集群
   - 等待数据同步完成

3. 如果集群不可恢复
   - 从S3下载最新备份
   - 在新集群上执行 mongorestore
   - 验证数据完整性
   - 更新应用连接字符串
   - 逐步恢复服务

4. 事后复盘
   - 记录故障原因
   - 评估RTO/RPO是否达标
   - 更新应急预案
```

---

## 九、扩容指南

### 9.1 水平扩容API服务

```bash
# Kubernetes
kubectl scale deployment consumer-sim-api --replicas=5 -n consumer-sim

# Docker Compose
docker-compose up -d --scale api=5
```

### 9.2 Redis扩容

```bash
# 增加新的Redis节点
redis-cli --cluster add-node new_redis:6379 existing_redis:6379

# 重新分配slot
redis-cli --cluster reshard existing_redis:6379
```

### 9.3 MongoDB扩容

```bash
# 增加新的分片
mongosh --eval "sh.addShard('shard3rs/mongo-shard3a:27017')"

# 重新平衡数据
mongosh --eval "shBalancerStatus()"
```

### 9.4 扩容触发条件

| 指标 | 当前值 | 触发扩容 | 扩容动作 |
|------|--------|---------|---------|
| API平均CPU | > 70% 持续10分钟 | 增加API实例 | +2 replicas |
| API P95延迟 | > 20s 持续5分钟 | 增加API实例 | +2 replicas |
| Redis内存使用 | > 80% | 增加Redis节点 | +1 master + 1 slave |
| MongoDB存储 | > 75% | 增加存储/分片 | +1 shard 或扩容磁盘 |
| Kafka消费LAG | > 5000 持续15分钟 | 增加消费者 | +2 consumer pods |

---

## 十、安全运维

### 10.1 密钥管理

```markdown
- LLM API Key：存储在K8s Secret或Vault中，定期轮换（90天）
- 数据库密码：使用强密码，存储在K8s Secret中
- S3访问密钥：使用IAM Role（K8s中通过ServiceAccount绑定）
- 证书：使用Let's Encrypt自动续期，提前30天告警
```

### 10.2 访问控制

```markdown
- API入口：使用API Key或JWT认证
- 管理后台：SSO + RBAC
- 数据库：只开放内网访问，禁止公网暴露
- Redis：启用AUTH，绑定内网IP
- Kafka：启用SASL认证
```

### 10.3 审计日志

```markdown
必须记录的操作：
- 画像的创建、修改、发布、废弃
- 模拟任务的创建和执行
- 人工审核的通过/拒绝
- 配置的变更
- 用户的登录/登出

日志保留期：180天
日志存储：Elasticsearch或Loki
```

## 十一、运维风险清单

### 11.1 生产环境典型故障模式

| 故障 | 根因 | 预防 | 恢复时间 |
|------|------|------|---------|
| **LLM API配额耗尽** | 突发流量或预算不足 | ①监控配额使用率 ②设置80%告警 ③多模型备用 | 10分钟（切换模型） |
| **MongoDB Primary宕机** | 节点故障或网络分区 | ③副本集+仲裁节点 ②定期故障演练 | 30秒（自动选举） |
| **Redis集群脑裂** | 网络分区导致多主 | ①min-slaves配置 ②sentinel监控 ③手动介入预案 | 5分钟 |
| **Kafka磁盘满** | 消息堆积未清理 | ① retention.ms设置 ②磁盘使用率告警 ③定期清理 | 10分钟（清理后恢复） |
| **证书过期** | Let's Encrypt续期失败 | ①提前30天告警 ②自动续期脚本 ③备用证书 | 30分钟（手动替换） |
| **DDoS攻击** | API被恶意调用 | ①Rate Limiting ②WAF ③IP黑名单 | 即时（限流生效） |

### 11.2 容量规划风险

| 指标 | 当前 | 3个月预期 | 风险 |
|------|------|----------|------|
| 画像数 | 1,000 | 5,000 | MongoDB单分片可能不足 |
| 模拟记录 | 10万 | 50万 | 索引膨胀，查询变慢 |
| 日生成量 | 100 | 500 | LLM费用×5 |
| 并发用户 | 10 | 50 | API服务需扩容 |

**建议**：每月评估一次容量，提前2周触发扩容流程。

### 11.3 数据安全风险

| 风险 | 等级 | 措施 |
|------|------|------|
| 画像数据泄露 | 高 | ①传输TLS ②存储加密 ③访问日志 ④定期审计 |
| LLM API Key泄露 | 高 | ①Vault管理 ②定期轮换 ③最小权限 ④异常调用监控 |
| 模拟记录被篡改 | 中 | ①写后只读 ②版本控制 ③操作审计 |
| 内部人员越权 | 中 | ①RBAC ②最小权限 ③定期权限审查 |

---

*本手册与以下文件配套使用：*
- [`13-实现参考与接口定义.md`](./13-实现参考与接口定义.md)（系统组件的实现细节）
- [`14-测试规范.md`](./14-测试规范.md)（部署后的验证测试）
- [`09-Agent输出信息规范.md`](./09-Agent输出信息规范.md)（存储层设计，第9章）
