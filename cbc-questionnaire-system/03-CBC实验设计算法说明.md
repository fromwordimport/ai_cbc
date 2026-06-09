# CBC实验设计算法说明

> **版本**：v1.0  
> **定位**：CBC问卷生成系统的核心算法说明，涵盖实验设计原理、算法实现、效率评估  
> **前置知识**：需要了解基础统计学和Logit模型概念  
> **配套文档**：`01-CBC系统架构与解决方案.md`、`02-CBC问卷生成输入规范.md`

---

## 一、实验设计的核心问题

### 1.1 为什么需要专门的实验设计？

CBC问卷不是随机出题，而是需要**在有限的题目数量下，最大化统计效率**。

**全因子设计的困境**：
- 假设有 5 个属性，每个 3 个水平
- 全因子设计 = 3⁵ = **243 种产品配置**
- 每题展示 3 个选项，需要展示的组合数 = C(243, 3) ≈ **234万种选择集**
- 显然不可能让受访者回答这么多题

**实验设计的目标**：
> 从海量可能的组合中，选出**少量但信息丰富**的选择集，使得能用统计模型反推出各属性的效用值。

### 1.2 信息矩阵与设计效率

CBC分析通常使用 **条件Logit模型**（Conditional Logit）：

```
P(选择 j | 选择集 S) = exp(U_j) / Σ exp(U_k)

其中 U_j = β₁X_j₁ + β₂X_j₂ + ... + βₙX_jₙ
```

**信息矩阵（Information Matrix）**：
- 衡量设计能提供多少关于参数 β 的信息
- 信息矩阵越大（行列式越大），参数估计越精确

**D-efficiency**：
```
D-efficiency = |X'WX|^(1/p) / N

其中：
- X 是设计矩阵
- W 是权重矩阵（与选择概率相关）
- p 是参数数量
- N 是选择集数量
```

D-efficiency 取值 0~1，越接近 1 越好。一般来说：
- D-efficiency ≥ 0.85 → 优秀（设计目标）
- D-efficiency 0.80~0.85 → 良好（可接受）
- D-efficiency 0.60~0.80 → 一般（建议优化）
- D-efficiency < 0.50 → 较差，需要增加题目或调整属性

---

## 二、算法总览

```
┌─────────────────────────────────────────────────────────────────┐
│                      实验设计算法选择                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐     │
│  │  正交设计     │    │  D-最优设计   │    │  自适应设计   │     │
│  │  Orthogonal  │    │  D-Optimal   │    │  Adaptive    │     │
│  │              │    │              │    │              │     │
│  │ • 属性水平    │    │ • 最大化     │    │ • 动态更新   │     │
│  │   平衡出现    │    │   信息矩阵   │    │   先验分布   │     │
│  │ • 实现简单    │    │ • 统计效率   │    │ • 逐步聚焦   │     │
│  │ • 效率一般    │    │   最高       │    │   关键属性   │     │
│  │              │    │ • 计算量大   │    │ • 大样本在线  │     │
│  │ 适用：快速    │    │              │    │              │     │
│  │       原型    │    │ 适用：正式   │    │ 适用：在线   │     │
│  │              │    │       研究   │    │       调研   │     │
│  └──────────────┘    └──────────────┘    └──────────────┘     │
│                                                                  │
│  推荐：本系统默认使用 D-Optimal 设计                            │
└─────────────────────────────────────────────────────────────────┘
```

---

## 三、正交设计（Orthogonal Design）

### 3.1 核心思想

**每个属性的每个水平在所有选择集中出现的次数尽量相等，且与其他属性的水平组合均匀分布**。

### 3.2 示例

```
属性：品牌(3) × 价格(3) × 存储(2) = 18种配置

正交表选择：
┌─────────┬───────┬───────┬──────────┐
│ 题目    │ 品牌   │ 价格   │ 存储     │
├─────────┼───────┼───────┼──────────┤
│ 1-A     │ 华为   │ 2999  │ 128GB   │
│ 1-B     │ 小米   │ 3999  │ 256GB   │
│ 1-C     │ 苹果   │ 5999  │ 128GB   │
├─────────┼───────┼───────┼──────────┤
│ 2-A     │ 小米   │ 2999  │ 256GB   │
│ 2-B     │ 苹果   │ 3999  │ 128GB   │
│ 2-C     │ 华为   │ 5999  │ 256GB   │
│ ...     │ ...   │ ...   │ ...     │
└─────────┴───────┴───────┴──────────┘

验证：
- 华为出现 4 次，小米 4 次，苹果 4 次 ✓
- 2999 出现 3 次，3999 3 次，5999 3 次 ✓
- 每个品牌与每个价格的组合出现 1 次 ✓
```

### 3.3 实现方法

```python
def generate_orthogonal_design(attributes, levels, num_sets, alts_per_set):
    """
    生成正交设计
    
    参数：
        attributes: 属性列表
        levels: 每个属性的水平数
        num_sets: 选择集数量
        alts_per_set: 每集选项数
    
    返回：
        design: 选择集列表
    """
    # 1. 计算全因子空间大小
    full_factorial_size = np.prod(levels)
    
    # 2. 生成全因子设计矩阵
    full_design = generate_full_factorial(attributes, levels)
    
    # 3. 从中选择正交子集
    # 方法A：使用已有的正交表（Taguchi方法）
    # 方法B：贪婪算法，逐步选择使相关性最小的配置
    orthogonal_subset = select_orthogonal_subset(
        full_design, 
        target_size=num_sets * alts_per_set
    )
    
    # 4. 将配置分配到选择集中
    choice_sets = distribute_to_sets(orthogonal_subset, num_sets, alts_per_set)
    
    # 5. 校验正交性
    orthogonality_score = check_orthogonality(choice_sets, attributes)
    
    return {
        'design': choice_sets,
        'orthogonality_score': orthogonality_score,
        'd_efficiency': calculate_d_efficiency(choice_sets)
    }
```

### 3.4 优缺点

| 优点 | 缺点 |
|------|------|
| 实现简单，计算快 | 统计效率不是最优的 |
| 属性水平平衡 | 无法处理约束条件（禁止组合） |
| 直观易懂 | 不考虑参数估计的方差 |
| 适合快速原型 | 相同水平的属性可能高度相关 |

---

## 四、D-最优设计（D-Optimal Design）⭐ 推荐

### 4.1 核心思想

**最大化信息矩阵的行列式**，等价于**最小化参数估计的联合置信体积**。

```
D-最优准则：
最大化 det(X'WX)

等价于：
最小化 |Cov(β̂)| = |X'WX|⁻¹
```

### 4.2 为什么D-最优更适合CBC？

1. **考虑选择模型**：D-最优基于Logit模型的信息矩阵，而非线性回归
2. **处理非平衡水平**：某些属性水平更重要，可以让它们出现更频繁
3. **处理约束**：可以通过候选集筛选处理禁止组合
4. **统计效率最高**：在相同题目数量下，参数估计最精确

### 4.3 算法实现：候选集 + 交换算法

#### 步骤1：生成候选集

```python
def generate_candidate_set(attributes, levels, constraints=None):
    """
    生成所有合法的产品配置候选集
    
    处理约束条件（禁止组合）
    """
    # 1. 生成全因子配置
    all_profiles = generate_full_factorial(attributes, levels)
    
    # 2. 应用禁止组合过滤
    if constraints and constraints.prohibited_combinations:
        legal_profiles = []
        for profile in all_profiles:
            if not is_prohibited(profile, constraints.prohibited_combinations):
                legal_profiles.append(profile)
    else:
        legal_profiles = all_profiles
    
    # 3. 验证候选集足够大
    min_candidates = max(100, len(attributes) * np.prod(levels) // 2)
    if len(legal_profiles) < min_candidates:
        logger.warning(f"候选集过小: {len(legal_profiles)}, 可能影响设计质量")
    
    return legal_profiles
```

#### 步骤2：设计矩阵编码

```python
def encode_design_matrix(profiles, attributes):
    """
    将产品配置编码为设计矩阵X
    
    效果编码（Effects Coding）示例：
    品牌: 华为=[1,0], 小米=[0,1], 苹果=[-1,-1]
    
    价格（连续变量）: 直接编码为价格值
    """
    X = []
    for profile in profiles:
        row = []
        for attr in attributes:
            value = profile[attr.id]
            
            if attr.type == 'categorical' or attr.type == 'price':
                # 使用效果编码（Effects Coding）
                # 假设有k个水平，编码为k-1个虚拟变量
                encoded = effects_coding(value, attr.levels)
                row.extend(encoded)
            
            elif attr.type == 'continuous':
                # 连续变量直接编码（可标准化）
                row.append(value)
            
            elif attr.type == 'ordinal':
                # 有序变量可编码为整数或效果编码
                encoded = ordinal_coding(value, attr.levels)
                row.extend(encoded)
        
        X.append(row)
    
    return np.array(X)
```

#### 步骤3：计算信息矩阵

```python
def calculate_information_matrix(X, beta_prior=None):
    """
    计算Logit模型的信息矩阵
    
    条件Logit的信息矩阵：
    I(β) = X' P X - X' p p' X
    
    其中 P 是对角矩阵，对角线元素为 P_ij(1-P_ij)
          p 是选择概率向量
    """
    if beta_prior is None:
        # 使用零先验（所有效用相等）
        beta_prior = np.zeros(X.shape[1])
    
    # 计算效用值
    utilities = X @ beta_prior
    
    # 计算选择概率（假设每个选择集有相同数量的选项）
    # 这里简化处理，实际需要按选择集分组计算
    exp_utils = np.exp(utilities - np.max(utilities))  # 数值稳定性
    probabilities = exp_utils / np.sum(exp_utils)
    
    # 信息矩阵近似
    W = np.diag(probabilities * (1 - probabilities))
    info_matrix = X.T @ W @ X
    
    return info_matrix
```

#### 步骤4：D-最优交换算法

```python
def d_optimal_design(candidate_set, num_sets, alts_per_set, attributes, 
                     max_iterations=1000, convergence_threshold=1e-6):
    """
    D-最优设计的交换算法实现
    
    算法：
    1. 随机初始化设计（从候选集中选择）
    2. 重复直到收敛：
       a. 对设计中的每一个位置
       b. 尝试用候选集中的每个其他配置替换
       c. 如果替换能提高D-efficiency，则执行替换
    3. 返回最优设计
    """
    
    # 1. 随机初始化
    current_design = random_initialize(candidate_set, num_sets, alts_per_set)
    X_current = encode_design_matrix(current_design, attributes)
    
    # 2. 计算当前D值
    info_matrix = calculate_information_matrix(X_current)
    current_d_value = np.linalg.det(info_matrix)
    
    iteration = 0
    improved = True
    
    while improved and iteration < max_iterations:
        improved = False
        iteration += 1
        
        # 遍历设计中的每个位置
        for set_idx in range(num_sets):
            for alt_idx in range(alts_per_set):
                current_position = set_idx * alts_per_set + alt_idx
                current_profile = current_design[current_position]
                
                # 尝试用候选集中的每个配置替换
                best_replacement = None
                best_d_value = current_d_value
                
                for candidate in candidate_set:
                    if candidate == current_profile:
                        continue
                    
                    # 创建新设计
                    new_design = current_design.copy()
                    new_design[current_position] = candidate
                    
                    # 检查同一选择集内是否有重复配置
                    set_start = set_idx * alts_per_set
                    set_end = set_start + alts_per_set
                    current_set = new_design[set_start:set_end]
                    if has_duplicates(current_set):
                        continue
                    
                    # 计算新D值
                    X_new = encode_design_matrix(new_design, attributes)
                    info_matrix_new = calculate_information_matrix(X_new)
                    new_d_value = np.linalg.det(info_matrix_new)
                    
                    if new_d_value > best_d_value:
                        best_d_value = new_d_value
                        best_replacement = candidate
                
                # 执行最佳替换
                if best_replacement is not None:
                    current_design[current_position] = best_replacement
                    current_d_value = best_d_value
                    improved = True
                    
                    logger.debug(f"迭代 {iteration}: 替换位置 ({set_idx},{alt_idx}), "
                               f"D值: {current_d_value:.6f}")
        
        # 检查收敛
        if not improved:
            logger.info(f"算法收敛于迭代 {iteration}")
            break
    
    # 3. 将设计转换为选择集格式
    choice_sets = []
    for i in range(num_sets):
        start = i * alts_per_set
        end = start + alts_per_set
        choice_sets.append({
            'set_id': i + 1,
            'alternatives': current_design[start:end]
        })
    
    # 4. 计算最终效率指标
    X_final = encode_design_matrix(current_design, attributes)
    final_info = calculate_information_matrix(X_final)
    
    d_efficiency = calculate_d_efficiency(X_final, attributes)
    a_efficiency = calculate_a_efficiency(final_info)
    
    return {
        'design': choice_sets,
        'd_value': current_d_value,
        'd_efficiency': d_efficiency,
        'a_efficiency': a_efficiency,
        'iterations': iteration
    }
```

### 4.4 处理固定选项

当需要包含固定基准选项时：

```python
def d_optimal_with_fixed(candidate_set, num_sets, alts_per_set, 
                         fixed_profile, fixed_position,
                         attributes, **kwargs):
    """
    包含固定选项的D-最优设计
    
    方法：
    1. 将固定选项固定在每个选择集的指定位置
    2. 只对其他位置进行D-最优优化
    3. 信息矩阵计算时包含固定选项的效应
    """
    
    # 1. 从候选集中移除固定选项（避免重复）
    candidate_set_filtered = [c for c in candidate_set if c != fixed_profile]
    
    # 2. 初始化：每个选择集包含固定选项
    design = []
    for i in range(num_sets):
        for j in range(alts_per_set):
            if j == fixed_position:
                design.append(fixed_profile)
            else:
                design.append(random.choice(candidate_set_filtered))
    
    # 3. 运行D-最优优化（跳过固定位置）
    # ... 修改交换算法，固定位置不可交换
    
    return optimized_design
```

### 4.5 处理必须包含组合

```python
def ensure_required_combinations(design, required_combinations, num_sets, alts_per_set):
    """
    确保必须包含的组合在问卷中出现足够次数
    
    方法：
    1. 在D-最优优化后，检查必须组合的出现次数
    2. 如果不足，用必须组合替换非关键位置上的配置
    3. 替换后可能需要局部重新优化
    """
    
    for req in required_combinations:
        profile = req['profile']
        min_count = req['min_appearances']
        max_count = req.get('max_appearances', num_sets * alts_per_set)
        
        # 计算当前出现次数
        current_count = sum(1 for p in design if p == profile)
        
        # 如果不足，替换其他配置
        while current_count < min_count:
            # 找到最适合替换的位置（对D-efficiency影响最小）
            best_replace_idx = find_least_important_position(design, profile)
            design[best_replace_idx] = profile
            current_count += 1
        
        # 如果超过最大次数，移除多余
        while current_count > max_count:
            # 找到最适合移除的位置
            best_remove_idx = find_redundant_position(design, profile)
            # 用候选集中的其他配置替换
            design[best_remove_idx] = select_alternative_profile(design, profile)
            current_count -= 1
    
    return design
```

---

## 五、效率评估指标

### 5.1 D-efficiency

```python
def calculate_d_efficiency(X, attributes):
    """
    计算D-efficiency
    
    D-efficiency = |X'X|^(1/p) / N
    
    其中 p 是参数数量，N 是观测数量
    """
    p = X.shape[1]  # 参数数量
    N = X.shape[0]  # 观测数量（选择集数 × 每集选项数）
    
    info_matrix = X.T @ X
    
    # 防止奇异矩阵
    if np.linalg.det(info_matrix) <= 0:
        return 0.0
    
    d_efficiency = np.power(np.linalg.det(info_matrix), 1/p) / N
    
    # 归一化到 0-1 范围（相对于正交设计的效率）
    # 或者使用理论最优值归一化
    
    return min(d_efficiency, 1.0)
```

### 5.2 A-efficiency

```python
def calculate_a_efficiency(info_matrix):
    """
    计算A-efficiency
    
    A-efficiency ∝ 1 / trace(X'X)⁻¹
    
    等价于最小化参数估计方差的平均
    """
    try:
        cov_matrix = np.linalg.inv(info_matrix)
        a_efficiency = len(info_matrix) / np.trace(cov_matrix)
        return min(a_efficiency, 1.0)
    except np.linalg.LinAlgError:
        return 0.0
```

### 5.3 标准误预测

```python
def predict_standard_errors(design, attributes, expected_sample_size):
    """
    预测每个参数估计的标准误
    
    帮助研究者判断设计是否足够精确
    """
    X = encode_design_matrix(design, attributes)
    info_matrix = calculate_information_matrix(X)
    
    try:
        cov_matrix = np.linalg.inv(info_matrix) / expected_sample_size
        standard_errors = np.sqrt(np.diag(cov_matrix))
        
        return {
            'standard_errors': standard_errors,
            'max_se': np.max(standard_errors),
            'mean_se': np.mean(standard_errors),
            'acceptable': np.max(standard_errors) < 0.5  # 经验阈值
        }
    except np.linalg.LinAlgError:
        return {'error': '信息矩阵奇异，设计可能有缺陷'}
```

### 5.4 效率指标解读

| 指标 | 含义 | 优秀标准 | 关注阈值 |
|------|------|---------|---------|
| **D-efficiency** | 参数联合估计精度 | ≥ 0.85 | < 0.50 |
| **A-efficiency** | 参数平均估计精度 | ≥ 0.75 | < 0.50 |
| **标准误** | 单个参数的估计精度 | ≤ 0.3 | > 0.5 |
| **条件数** | 设计的病态程度 | < 10 | > 30 |

---

## 六、自适应设计（Adaptive Design）

### 6.1 核心思想

**根据前期受访者的回答，动态更新参数先验分布，生成更聚焦后续选择集**。

适合场景：
- 大样本在线研究
- 需要极高精度的参数估计
- 长问卷（20+选择集）

### 6.2 贝叶斯自适应算法

```python
class AdaptiveCBCDesign:
    """
    贝叶斯自适应CBC设计
    
    核心流程：
    1. 使用非信息先验（β ~ N(0, I)）初始化
    2. 每收集一批回答，更新后验分布
    3. 基于当前后验，生成下一批最优选择集
    4. 重复直到达到目标题目数
    """
    
    def __init__(self, attributes, levels, candidate_set):
        self.attributes = attributes
        self.levels = levels
        self.candidate_set = candidate_set
        
        # 初始化先验
        num_params = sum(len(attr.levels) - 1 for attr in attributes)
        self.beta_prior = np.zeros(num_params)
        self.prior_cov = np.eye(num_params) * 10  # 大方差 = 弱先验
        
        self.responses = []
    
    def generate_next_choice_set(self, num_alts=3):
        """
        基于当前后验分布，生成下一个最优选择集
        
        准则：最大化期望信息增益
        """
        # 1. 从后验分布采样
        beta_samples = np.random.multivariate_normal(
            self.beta_prior, 
            self.prior_cov, 
            size=100
        )
        
        # 2. 评估所有可能的选择集
        best_set = None
        best_info_gain = -np.inf
        
        # 从候选集中随机抽样评估（降低计算量）
        candidate_subsets = random.sample(
            list(combinations(self.candidate_set, num_alts)), 
            min(1000, len(self.candidate_set))
        )
        
        for alt_set in candidate_subsets:
            # 计算期望信息增益
            expected_info_gain = self.calculate_expected_info_gain(
                alt_set, beta_samples
            )
            
            if expected_info_gain > best_info_gain:
                best_info_gain = expected_info_gain
                best_set = alt_set
        
        return list(best_set)
    
    def calculate_expected_info_gain(self, choice_set, beta_samples):
        """
        计算选择集的期望信息增益
        
        E[IG] = Σ P(选择j|β) × [H(β) - H(β|选择j)]
        """
        X_set = encode_design_matrix(choice_set, self.attributes)
        
        total_info_gain = 0
        
        for beta in beta_samples:
            utilities = X_set @ beta
            probs = softmax(utilities)
            
            for j, prob in enumerate(probs):
                if prob > 0.01:  # 忽略极小概率选择
                    # 假设选择j后的后验信息矩阵
                    info_gain = self.approximate_info_gain(X_set[j], beta)
                    total_info_gain += prob * info_gain
        
        return total_info_gain / len(beta_samples)
    
    def update_posterior(self, choice_set, chosen_alt_idx):
        """
        根据新的选择更新后验分布
        
        使用Laplace近似或MCMC
        """
        self.responses.append({
            'choice_set': choice_set,
            'chosen': chosen_alt_idx
        })
        
        # 使用最大后验估计（MAP）更新
        # 简化版：使用Laplace近似
        
        # 1. 找到MAP估计
        beta_map = self.find_map_estimate()
        
        # 2. 计算Hessian矩阵近似协方差
        hessian = self.calculate_hessian(beta_map)
        
        self.beta_prior = beta_map
        self.prior_cov = np.linalg.inv(hessian)
    
    def find_map_estimate(self):
        """找到最大后验估计"""
        from scipy.optimize import minimize
        
        def negative_log_posterior(beta):
            # 对数似然
            log_likelihood = 0
            for resp in self.responses:
                X_set = encode_design_matrix(resp['choice_set'], self.attributes)
                utilities = X_set @ beta
                log_likelihood += utilities[resp['chosen']] - logsumexp(utilities)
            
            # 对数先验
            log_prior = -0.5 * np.sum(beta ** 2 / 10)
            
            return -(log_likelihood + log_prior)
        
        result = minimize(negative_log_posterior, self.beta_prior, method='BFGS')
        return result.x
```

### 6.3 自适应 vs 固定设计对比

| 维度 | 固定设计（D-Optimal） | 自适应设计 |
|------|----------------------|-----------|
| **适用场景** | 模拟消费者Agent批量执行 | 真人受访者在线填写 |
| **题目数量** | 需要更多题目（12-20） | 可用更少题目（8-12） |
| **实现复杂度** | 简单，一次性生成 | 复杂，需要在线更新 |
| **与画像系统配合** | ⭐ 更适合（批量执行） | 需要逐个执行 |
| **统计效率** | 良好 | 优秀 |
| **计算成本** | 低（一次性） | 高（每题都需计算） |

**推荐**：对于模拟消费者Agent系统，使用 **固定D-Optimal设计** 即可，因为：
1. 模拟消费者可以批量并行执行
2. 不需要节省真人受访者的时间
3. 实现更简单，结果可复现

---

## 七、多版本设计（Versioning）

### 7.1 为什么需要多版本？

- **减少顺序效应**：不同受访者看到不同的题目顺序和组合
- **增加设计多样性**：提高总体信息矩阵的稳健性
- **测试设计稳定性**：如果不同版本结果一致，说明结论可靠

### 7.2 多版本生成策略

```python
def generate_multiple_versions(candidate_set, num_sets, alts_per_set, 
                               attributes, num_versions=4):
    """
    生成多个设计版本
    
    策略：
    1. 每个版本独立运行D-最优算法
    2. 确保版本间有足够的差异（汉明距离）
    3. 平衡每个版本的设计效率
    """
    versions = []
    
    for v in range(num_versions):
        # 使用不同的随机种子初始化
        seed = v * 1000 + 42
        np.random.seed(seed)
        
        # 运行D-最优设计
        version = d_optimal_design(
            candidate_set, num_sets, alts_per_set, attributes
        )
        
        versions.append(version)
    
    # 验证版本间差异度
    diversity_scores = calculate_version_diversity(versions)
    
    return {
        'versions': versions,
        'diversity_scores': diversity_scores,
        'min_efficiency': min(v['d_efficiency'] for v in versions)
    }
```

---

## 八、完整算法流程图

```
输入：产品属性、水平、约束条件、设计参数
  │
  ▼
┌─────────────────────────────────────┐
│ 1. 生成候选集                        │
│    - 全因子生成                      │
│    - 应用禁止组合过滤                │
└─────────────┬───────────────────────┘
              │
              ▼
┌─────────────────────────────────────┐
│ 2. 检查固定选项                      │
│    - 如有，从候选集移除固定配置      │
│    - 预留固定位置                    │
└─────────────┬───────────────────────┘
              │
              ▼
┌─────────────────────────────────────┐
│ 3. 随机初始化设计                    │
│    - 从候选集中随机选择              │
│    - 确保选择集内无重复              │
└─────────────┬───────────────────────┘
              │
              ▼
┌─────────────────────────────────────┐
│ 4. D-最优交换优化（核心）            │
│    ┌─────────────────────────────┐  │
│    │ 重复直到收敛：               │  │
│    │   对每个位置：               │  │
│    │     尝试所有候选替换         │  │
│    │     保留提高D值的替换        │  │
│    └─────────────────────────────┘  │
└─────────────┬───────────────────────┘
              │
              ▼
┌─────────────────────────────────────┐
│ 5. 应用必须包含组合                  │
│    - 检查出现次数                    │
│    - 不足则替换（最小效率损失）      │
└─────────────┬───────────────────────┘
              │
              ▼
┌─────────────────────────────────────┐
│ 6. 计算效率指标                      │
│    - D-efficiency                    │
│    - A-efficiency                    │
│    - 标准误预测                      │
└─────────────┬───────────────────────┘
              │
              ▼
┌─────────────────────────────────────┐
│ 7. 质量判断                          │
│    D-efficiency ≥ 0.85?              │
│    ├─ 是 → 输出设计                  │
│    └─ 否 → 增加题目数或调整水平      │
└─────────────────────────────────────┘
```

---

## 九、Python实现参考

### 9.1 核心类设计

```python
from dataclasses import dataclass
from typing import List, Dict, Optional
import numpy as np
from scipy.optimize import minimize
from itertools import product, combinations
import random

@dataclass
class Attribute:
    id: str
    name: str
    type: str  # 'categorical', 'continuous', 'ordinal', 'price'
    levels: List[Dict]  # [{'value': ..., 'label': ...}, ...]

@dataclass
class DesignConstraint:
    prohibited_combinations: List[Dict] = None
    required_combinations: List[Dict] = None
    fixed_alternative: Dict = None

class CBCDesignEngine:
    """
    CBC实验设计引擎
    
    支持：
    - 正交设计
    - D-最优设计（默认）
    - 自适应设计
    - 约束处理
    """
    
    def __init__(self, attributes: List[Attribute], 
                 design_method: str = 'd_optimal'):
        self.attributes = attributes
        self.design_method = design_method
        self.candidate_set = None
        
    def generate_design(self, num_sets: int, alts_per_set: int,
                       constraints: Optional[DesignConstraint] = None,
                       **kwargs) -> Dict:
        """
        生成CBC实验设计
        
        参数：
            num_sets: 选择集数量
            alts_per_set: 每集选项数
            constraints: 约束条件
            
        返回：
            包含设计矩阵和效率指标的字典
        """
        # 1. 生成候选集
        self.candidate_set = self._generate_candidate_set(constraints)
        
        # 2. 根据设计方法生成
        if self.design_method == 'orthogonal':
            result = self._orthogonal_design(num_sets, alts_per_set)
        elif self.design_method == 'd_optimal':
            result = self._d_optimal_design(num_sets, alts_per_set, constraints, **kwargs)
        elif self.design_method == 'adaptive':
            result = self._adaptive_design(num_sets, alts_per_set)
        else:
            raise ValueError(f"未知设计方法: {self.design_method}")
        
        # 3. 计算效率指标
        result['efficiency_metrics'] = self._calculate_efficiency_metrics(
            result['design']
        )
        
        return result
    
    def _generate_candidate_set(self, constraints: Optional[DesignConstraint]) -> List[Dict]:
        """生成所有合法的产品配置候选"""
        # 生成全因子
        level_values = []
        for attr in self.attributes:
            level_values.append([l['value'] for l in attr.levels])
        
        all_combinations = list(product(*level_values))
        
        # 构建配置字典
        profiles = []
        for combo in all_combinations:
            profile = {}
            for i, attr in enumerate(self.attributes):
                profile[attr.id] = combo[i]
            profiles.append(profile)
        
        # 应用禁止组合
        if constraints and constraints.prohibited_combinations:
            legal_profiles = []
            for profile in profiles:
                if not self._is_prohibited(profile, constraints.prohibited_combinations):
                    legal_profiles.append(profile)
            profiles = legal_profiles
        
        return profiles
    
    def _is_prohibited(self, profile: Dict, prohibited: List[Dict]) -> bool:
        """检查配置是否在禁止组合列表中"""
        for p in prohibited:
            match = True
            for attr_id, forbidden_values in p['conditions'].items():
                if profile.get(attr_id) not in forbidden_values:
                    match = False
                    break
            if match:
                return True
        return False
    
    def _encode_profile(self, profile: Dict) -> np.ndarray:
        """将产品配置编码为设计向量"""
        vector = []
        for attr in self.attributes:
            value = profile[attr.id]
            
            if attr.type in ('categorical', 'price', 'ordinal'):
                # 效果编码
                level_values = [l['value'] for l in attr.levels]
                num_levels = len(level_values)
                
                # 效果编码：k个水平编码为k-1个变量
                encoded = np.zeros(num_levels - 1)
                if value in level_values:
                    idx = level_values.index(value)
                    if idx < num_levels - 1:
                        encoded[idx] = 1
                    else:
                        # 最后一个水平编码为 [-1, -1, ..., -1]
                        encoded = np.full(num_levels - 1, -1)
                vector.extend(encoded)
            
            elif attr.type == 'continuous':
                # 连续变量直接编码
                vector.append(float(value))
        
        return np.array(vector)
    
    def _d_optimal_design(self, num_sets: int, alts_per_set: int,
                         constraints: Optional[DesignConstraint],
                         max_iterations: int = 1000) -> Dict:
        """D-最优设计实现"""
        
        total_positions = num_sets * alts_per_set
        
        # 处理固定选项
        fixed_positions = set()
        fixed_profiles = {}
        if constraints and constraints.fixed_alternative and constraints.fixed_alternative.get('enabled'):
            fixed_alt = constraints.fixed_alternative
            fixed_profile = fixed_alt['profile']
            position = fixed_alt.get('position', 'random')
            
            if position == 'first':
                for i in range(num_sets):
                    fixed_positions.add(i * alts_per_set)
                    fixed_profiles[i * alts_per_set] = fixed_profile
            elif position == 'last':
                for i in range(num_sets):
                    fixed_positions.add(i * alts_per_set + alts_per_set - 1)
                    fixed_profiles[i * alts_per_set + alts_per_set - 1] = fixed_profile
            else:  # random
                import random
                for i in range(num_sets):
                    pos = i * alts_per_set + random.randint(0, alts_per_set - 1)
                    fixed_positions.add(pos)
                    fixed_profiles[pos] = fixed_profile
        
        # 随机初始化
        current_design = []
        available_candidates = [c for c in self.candidate_set 
                               if c not in fixed_profiles.values()]
        
        for i in range(total_positions):
            if i in fixed_positions:
                current_design.append(fixed_profiles[i])
            else:
                current_design.append(random.choice(available_candidates))
        
        # 计算初始D值
        X = np.array([self._encode_profile(p) for p in current_design])
        current_d = self._calculate_d_value(X)
        
        # 交换优化
        iteration = 0
        improved = True
        
        while improved and iteration < max_iterations:
            improved = False
            iteration += 1
            
            for pos in range(total_positions):
                if pos in fixed_positions:
                    continue
                
                best_d = current_d
                best_candidate = None
                
                for candidate in available_candidates:
                    if candidate == current_design[pos]:
                        continue
                    
                    # 检查同一选择集内是否重复
                    set_start = (pos // alts_per_set) * alts_per_set
                    set_end = set_start + alts_per_set
                    
                    new_design = current_design.copy()
                    new_design[pos] = candidate
                    
                    if self._has_duplicate_in_set(new_design, set_start, set_end):
                        continue
                    
                    # 计算新D值
                    X_new = np.array([self._encode_profile(p) for p in new_design])
                    new_d = self._calculate_d_value(X_new)
                    
                    if new_d > best_d:
                        best_d = new_d
                        best_candidate = candidate
                
                if best_candidate is not None:
                    current_design[pos] = best_candidate
                    current_d = best_d
                    improved = True
        
        # 应用必须包含组合
        if constraints and constraints.required_combinations:
            current_design = self._ensure_required_combinations(
                current_design, constraints.required_combinations, 
                num_sets, alts_per_set
            )
        
        # 转换为选择集格式
        choice_sets = []
        for i in range(num_sets):
            start = i * alts_per_set
            alts = current_design[start:start + alts_per_set]
            choice_sets.append({
                'set_id': i + 1,
                'alternatives': alts
            })
        
        return {
            'design': choice_sets,
            'd_value': current_d,
            'iterations': iteration
        }
    
    def _calculate_d_value(self, X: np.ndarray) -> float:
        """计算信息矩阵的行列式（D值）"""
        # 简化版：使用 X'X 近似
        info = X.T @ X
        
        # 添加正则化防止奇异
        info += np.eye(info.shape[0]) * 1e-6
        
        try:
            return np.linalg.det(info)
        except:
            return 0.0
    
    def _has_duplicate_in_set(self, design: List[Dict], start: int, end: int) -> bool:
        """检查选择集中是否有重复配置"""
        profiles = design[start:end]
        seen = []
        for p in profiles:
            p_tuple = tuple(sorted(p.items()))
            if p_tuple in seen:
                return True
            seen.append(p_tuple)
        return False
    
    def _calculate_efficiency_metrics(self, design: List[Dict]) -> Dict:
        """计算设计效率指标"""
        all_profiles = []
        for cs in design:
            all_profiles.extend(cs['alternatives'])
        
        X = np.array([self._encode_profile(p) for p in all_profiles])
        
        # D-efficiency
        p = X.shape[1]
        N = X.shape[0]
        info = X.T @ X + np.eye(p) * 1e-6
        d_eff = np.power(np.abs(np.linalg.det(info)), 1/p) / N
        
        # A-efficiency
        try:
            cov = np.linalg.inv(info)
            a_eff = p / np.trace(cov)
        except:
            a_eff = 0.0
        
        return {
            'd_efficiency': min(d_eff, 1.0),
            'a_efficiency': min(a_eff, 1.0),
            'condition_number': np.linalg.cond(info)
        }
```

---

## 十、推荐配置速查表

### 10.1 根据研究目标选择设计参数

| 研究目标 | 选择集数 | 每集选项 | 设计方法 | 是否包含"都不选" |
|---------|---------|---------|---------|----------------|
| 快速概念验证 | 8 | 2 | 正交设计 | 否 |
| 标准属性重要性 | 12 | 3 | D-最优 | 是 |
| 精确价格敏感度 | 16 | 3 | D-最优 | 是 |
| 市场份额预测 | 16 | 3-4 | D-最优 | **必须** |
| 新品概念测试 | 12 | 3 | D-最优 + 固定选项 | 是 |
| 细分人群对比 | 12×N组 | 3 | D-最优 + 分组 | 是 |

### 10.2 样本量建议

```
最小样本量 = 总参数数 × 5 / 选择集数

示例：
- 5个属性，各3个水平 → 总参数 = (3-1)×5 = 10
- 12个选择集 → 最小样本 = 10 × 5 / 12 ≈ 5 人/组
- 建议样本 = 最小样本 × 3 = 15 人/组（考虑异质性）

对于模拟消费者Agent：
- 每个画像至少执行 1 次
- 建议每个细分群体 10-50 个画像
- 总样本量 50-200 个模拟消费者
```

---

## 十一、常见问题排查

| 问题 | 可能原因 | 解决方案 |
|------|---------|---------|
| D-efficiency < 0.5 | 属性过多或水平过多 | 减少属性或增加选择集数量 |
| 信息矩阵奇异 | 属性间高度相关 | 删除相关属性或合并水平 |
| 候选集过小 | 禁止组合过滤太严格 | 放宽约束或增加水平数 |
| 算法不收敛 | 设计空间太复杂 | 减少属性数量，简化约束 |
| 某属性水平从不出现 | 该水平被D-最优认为信息价值低 | 检查水平设置是否合理 |
| 固定选项导致效率低 | 固定选项占用了信息丰富的位置 | 调整固定位置或增加题目 |

---

*本文档与以下文件配套使用：*
- `01-CBC系统架构与解决方案.md`（整体方案）
- `02-CBC问卷生成输入规范.md`（输入字段定义）
- `04-CBC与模拟消费者集成方案.md`（与模拟消费者Agent的集成）