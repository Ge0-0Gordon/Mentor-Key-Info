# Semantic Local New Unknowns Labeling Report

## Summary

- total rows labeled: 21
- good: 11
- acceptable: 7
- bad: 3

这些标签用于补充 BGE-M3 local semantic 新引入的 unknown 导师，标注口径与第一轮一致：good 表示明显适合，acceptable 表示可作为备选，bad 表示不建议进入该 case 的 Top 推荐。

## Case-level Label Counts

| case_id | description | good | acceptable | bad |
|---|---|---:|---:|---:|
| case_002 | 应届生想做产品运营或增长产品，关注小红书、B站、抖音 | 0 | 1 | 0 |
| case_005 | 想做经营分析、BI或商业分析，希望导师懂数据体系搭建 | 1 | 0 | 0 |
| case_011 | 想找管理咨询、四大或战略咨询导师，准备秋招 | 0 | 1 | 0 |
| case_014 | 关注人才发展、培训体系、绩效和OKR，希望找企业组织管理导师 | 1 | 0 | 0 |
| case_015 | 想转HR或人力资源方向，需要从零定位和简历修改 | 1 | 0 | 0 |
| case_020 | 想做AIGC、数据产品或大模型应用方向，关注产品和数据结合 | 0 | 1 | 1 |
| case_021 | 技术岗、算法或AI行业求职，希望导师懂技术转商业表达 | 1 | 2 | 0 |
| case_022 | 不知道做什么，只想做职业规划和方向探索 | 6 | 1 | 0 |
| case_023 | 简历很弱，需要定位、经历梳理和求职路径设计 | 1 | 0 | 0 |
| case_025 | 希望找上海的资深女性导师，偏管理层或负责人背景，做职业规划 | 0 | 1 | 2 |

## Row-level Rationale

### 1. case_002 / rank 8 / service_mentor:1 / 刘永成

- case: 应届生想做产品运营或增长产品，关注小红书、B站、抖音
- label: **acceptable**
- score snapshot: final=42.66, semantic=76.61, company=40.0, role=0.0, skill=45.0, industry=50.0, stage=75.0
- key fields: industries=互联网；IT；新能源汽车；快消品; companies=阿里；字节；蔚来汽车；高合；百事；职优越; roles=阿里HRG；字节线下全国业务HRBP Leader；蔚来汽车区域HRBP Head；高合全国营销COE专家；百事东北区域TD/LD；职优越品牌创始人；企业管理咨询顾问；中高阶人才培养导师；猎聘特邀职业辅导讲师; skills=招聘体系搭建；人才发展；面试官培养；背调；高管教练；职业规划；大厂用人体系搭建；面试官赋能；职业生命周期规划; target_mentees=P7专家；P5-P6专员级；P8以上总监；应届生/留学生
- rationale: 有字节/互联网及招聘管理视角，可帮助理解企业筛选逻辑和应届生求职；但核心经历偏HRBP/人才体系，不是产品运营或增长产品，且未命中小红书/B站/抖音。

### 2. case_005 / rank 10 / service_mentor:118 / 彭丹丹

- case: 想做经营分析、BI或商业分析，希望导师懂数据体系搭建
- label: **good**
- score snapshot: final=34.74, semantic=78.86, company=0.0, role=23.33, skill=25.0, industry=50.0, stage=0.0
- key fields: industries=互联网; companies=京东；携程；BOSS直聘; roles=; skills=Python；SQL；BI；数据分析；数据可视化；HR全模块；数字化项目; target_mentees=应届生/留学生；P5-P6专员级
- rationale: 直接具备Python、SQL、BI、数据分析和数据可视化能力，也有数据看板与自动化报表项目经验，和BI/数据体系搭建需求强相关；不足是业务场景偏HR数字化。

### 3. case_011 / rank 10 / service_mentor:69 / 邓海毅（Daisy）

- case: 想找管理咨询、四大或战略咨询导师，准备秋招
- label: **acceptable**
- score snapshot: final=43.3, semantic=77.99, company=0.0, role=35.0, skill=50.0, industry=75.0, stage=75.0
- key fields: industries=资产管理；网络科技；咨询顾问；金融服务；通信; companies=松下通信；泛华金融；北京易才集团; roles=综合管理部经理；华南区人事行政经理；人事负责人; skills=招聘配置；薪酬绩效；员工关系；组织变革；简历优化；职业规划；面试辅导；心理测量; target_mentees=应届生/留学生；P5-P6专员级；P7专家；P8以上总监
- rationale: 有咨询顾问/金融服务等行业信号，也能提供简历、职业规划和面试辅导；但核心履历偏人力资源和组织管理，不是管理咨询/战略咨询或四大方向。

### 4. case_014 / rank 10 / service_mentor:19 / 于丽（Chelsea）

- case: 关注人才发展、培训体系、绩效和OKR，希望找企业组织管理导师
- label: **good**
- score snapshot: final=41.01, semantic=77.54, company=0.0, role=35.0, skill=37.5, industry=35.0, stage=0.0
- key fields: industries=医药；生物制药；软件技术行业; companies=; roles=HR负责人；招聘负责人；高端人才猎头；MBA面试辅导师；学生就业指导师; skills=人才画像；人才识别；潜力挖掘；招聘计划；培训体系搭建；领导力培训；职业规划；面试辅导；人才匹配；战略人力规划；猎头; target_mentees=应届生/留学生；P5-P6专员级；P7专家
- rationale: 长期HRD和人才发展背景，覆盖招聘计划、培训体系、领导力培训、员工职业发展体系，和人才发展/培训体系/组织管理需求高度匹配。

### 5. case_015 / rank 8 / service_mentor:47 / 田畅（Tina）

- case: 想转HR或人力资源方向，需要从零定位和简历修改
- label: **good**
- score snapshot: final=47.87, semantic=79.01, company=0.0, role=35.0, skill=45.0, industry=70.0, stage=0.0
- key fields: industries=IT；互联网；咨询服务; companies=IBM；华为; roles=招聘专家；生涯规划师；猎头; skills=企业端人才配置；职业定位；简历优化；面试技巧指导；人才寻访；招聘管理; target_mentees=应届生/留学生
- rationale: 招聘专家和生涯规划师背景，擅长职业定位、简历优化、面试技巧指导，适合想转HR/人力资源方向并需要从零定位的人；不足是可辅导阶段主要偏应届生。

### 6. case_020 / rank 9 / service_mentor:84 / 李佳霖

- case: 想做AIGC、数据产品或大模型应用方向，关注产品和数据结合
- label: **acceptable**
- score snapshot: final=21.83, semantic=78.69, company=0.0, role=0.0, skill=0.0, industry=35.0, stage=0.0
- key fields: industries=互联网；咨询服务；数科；职场辅导; companies=安永咨询；字节跳动；华润数科; roles=咨询顾问；运营分析；PMO；创业者；职业规划师; skills=项目管理；经营分析；数据搭建；数据可视化；求职辅导；职业规划；自媒体运营；逻辑分析；数据分析; target_mentees=应届生；留学生；P5-P6专员
- rationale: 有经营分析、数据搭建、数据可视化和项目管理经验，能覆盖数据产品的一部分能力；但缺少AIGC/大模型/AI产品明确经历，因此不标good。

### 7. case_020 / rank 10 / service_mentor:48 / 程镱（Charlie）

- case: 想做AIGC、数据产品或大模型应用方向，关注产品和数据结合
- label: **bad**
- score snapshot: final=21.75, semantic=78.16, company=0.0, role=0.0, skill=0.0, industry=35.0, stage=0.0
- key fields: industries=金融；证券; companies=; roles=首席分析师；职业规划导师; skills=投研分析；行业分析；标的研判；投研报告撰写；职业规划；简历修改；面试辅导；职业晋升指导；数据分析；行业洞察; target_mentees=应届生/留学生
- rationale: 核心背景在金融投研和金融求职辅导，虽有数据分析/行业分析能力，但与AIGC、数据产品、大模型应用方向差距较大。

### 8. case_021 / rank 7 / service_mentor:24 / Mia（吉延霞）

- case: 技术岗、算法或AI行业求职，希望导师懂技术转商业表达
- label: **acceptable**
- score snapshot: final=24.86, semantic=80.22, company=33.33, role=0.0, skill=0.0, industry=50.0, stage=0.0
- key fields: industries=互联网; companies=字节跳动; roles=HRBP；人才招聘体系负责人；面试官培训体系负责人; skills=招聘；面试官培训；职业规划；人才管理; target_mentees=应届生/留学生；P5-P6专员级
- rationale: 有字节招聘、面试官培训和应届生求职指导视角，可帮助理解大厂招聘标准；但缺少技术岗、算法或AI工程师实战背景。

### 9. case_021 / rank 9 / service_mentor:45 / 金思宇（Charles）

- case: 技术岗、算法或AI行业求职，希望导师懂技术转商业表达
- label: **good**
- score snapshot: final=24.7, semantic=78.71, company=33.33, role=0.0, skill=0.0, industry=50.0, stage=0.0
- key fields: industries=互联网；游戏; companies=腾讯; roles=腾讯11级高级工程师；项目主程序负责人；腾讯面试官；腾讯优秀导师; skills=研发全流程管理；技术难点攻克；新人培养；面试官技能；人才需求标准把握; target_mentees=应届生；留学生；新人；P5-P6专员；P7专家
- rationale: 腾讯高级工程师、项目主程序负责人和面试官背景，直接匹配技术岗/算法/AI行业求职及技术表达需求。

### 10. case_021 / rank 10 / service_mentor:84 / 李佳霖

- case: 技术岗、算法或AI行业求职，希望导师懂技术转商业表达
- label: **acceptable**
- score snapshot: final=24.66, semantic=78.29, company=33.33, role=0.0, skill=0.0, industry=50.0, stage=0.0
- key fields: industries=互联网；咨询服务；数科；职场辅导; companies=安永咨询；字节跳动；华润数科; roles=咨询顾问；运营分析；PMO；创业者；职业规划师; skills=项目管理；经营分析；数据搭建；数据可视化；求职辅导；职业规划；自媒体运营；逻辑分析；数据分析; target_mentees=应届生；留学生；P5-P6专员
- rationale: 具备互联网、数据分析、经营分析和求职辅导能力，可辅助技术转商业表达；但没有算法/技术岗实战和技术面试信号。

### 11. case_022 / rank 2 / service_mentor:120 / 刘斐

- case: 不知道做什么，只想做职业规划和方向探索
- label: **good**
- score snapshot: final=47.57, semantic=79.07, company=0.0, role=0.0, skill=50.0, industry=0.0, stage=0.0
- key fields: industries=机械制造；建筑工程; companies=昆明中铁大型养路机械集团；建筑工程公司; roles=副总经理; skills=一对一深度沟通；问题拆解；方案定制；职业规划; target_mentees=应届生/留学生；P5-P6专员级；P7专家；P8以上总监
- rationale: 具备GCDF/BCC和心理咨询师资质，擅长深度沟通、问题拆解、方案定制和职业规划，适合方向探索型需求。

### 12. case_022 / rank 3 / service_mentor:48 / 程镱（Charlie）

- case: 不知道做什么，只想做职业规划和方向探索
- label: **acceptable**
- score snapshot: final=47.41, semantic=78.33, company=0.0, role=0.0, skill=50.0, industry=0.0, stage=0.0
- key fields: industries=金融；证券; companies=; roles=首席分析师；职业规划导师; skills=投研分析；行业分析；标的研判；投研报告撰写；职业规划；简历修改；面试辅导；职业晋升指导；数据分析；行业洞察; target_mentees=应届生/留学生
- rationale: 有职业规划、简历修改和面试辅导经验，但更偏金融投研领域，对完全开放的方向探索有一定帮助但不够通用。

### 13. case_022 / rank 4 / service_mentor:77 / 徐莉

- case: 不知道做什么，只想做职业规划和方向探索
- label: **good**
- score snapshot: final=47.33, semantic=77.98, company=0.0, role=0.0, skill=50.0, industry=0.0, stage=0.0
- key fields: industries=多行业; companies=; roles=; skills=招聘配置；员工关系；绩效管理；组织发展；职业规划；求职辅导；人才评估; target_mentees=应届生/留学生；P5-P6专员级
- rationale: 认证职业规划师和求职辅导教练，擅长人才评估、优势挖掘、人岗匹配和职业规划，适合迷茫期方向探索。

### 14. case_022 / rank 6 / service_mentor:51 / 赵磊

- case: 不知道做什么，只想做职业规划和方向探索
- label: **good**
- score snapshot: final=47.14, semantic=77.12, company=0.0, role=0.0, skill=50.0, industry=0.0, stage=0.0
- key fields: industries=通信；金融；科技；地产；文化；央国企；运输; companies=; roles=人力资源专家；企业高管；培训师；职业生涯规划师; skills=招聘面试；人才选拔；简历优化；面试指导；职业规划；学业规划；全周期咨询；用人标准制定; target_mentees=应届生/留学生；P5-P6专员级；P7专家；P8以上总监
- rationale: 高年限HR和职业生涯规划师背景，能从企业招聘方视角提供学业规划、求职辅导和职业发展方案，适合开放式职业规划。

### 15. case_022 / rank 7 / service_mentor:62 / 任丽萍

- case: 不知道做什么，只想做职业规划和方向探索
- label: **good**
- score snapshot: final=47.02, semantic=76.61, company=0.0, role=0.0, skill=50.0, industry=0.0, stage=0.0
- key fields: industries=互联网；环保；自动售货机；快消；广告; companies=华润超市；慧聪网；友宝集团；北京绿橄榄环保；智联招聘；BOSS直聘; roles=招聘主管；HRBP；人事经理；资深导师；职业规划讲师；职场导师; skills=人力全模块运营；团队管理；招聘；职业规划；简历优化；面试辅导；求职陪跑；授课；心理咨询; target_mentees=应届生；留学生；P5-P6专员级；P7专家；P8以上总监
- rationale: GCDF生涯规划师、长期职业规划讲师和职场导师，擅长职业定位、简历优化、面试辅导与求职陪跑，和方向探索高度匹配。

### 16. case_022 / rank 8 / service_mentor:74 / 张金花

- case: 不知道做什么，只想做职业规划和方向探索
- label: **good**
- score snapshot: final=47.0, semantic=76.51, company=0.0, role=0.0, skill=50.0, industry=0.0, stage=0.0
- key fields: industries=制药；保健品；IVD; companies=; roles=人力资源总监；猎头; skills=人才招聘；人才培养；中高端人才寻访；求职就业实训；职业规划；简历辅导；面试辅导; target_mentees=应届生/留学生；P5-P6专员级；P7专家；P8以上总监
- rationale: 有职业规划、求职就业能力提升、简历面试辅导个案经验，虽行业偏医药，但对无明确方向的职业规划仍有较强适配度。

### 17. case_022 / rank 10 / service_mentor:107 / 张杰（Jack）

- case: 不知道做什么，只想做职业规划和方向探索
- label: **good**
- score snapshot: final=46.93, semantic=76.19, company=0.0, role=0.0, skill=50.0, industry=0.0, stage=0.0
- key fields: industries=生物科技；互联网；咨询行业; companies=广东银禧科技；深圳刷新生物；和君咨询；杰特咨询; roles=高级人力资源经理；人力资源总监；培训经理；猎头部总监；副总；面试专家; skills=人力资源全模块；猎头；管理咨询；面试甄选；职业规划；人才辅导；BEI面试法；招聘；简历精修；offer谈判; target_mentees=应届生/留学生；P5-P6专员级；P7专家；P8以上总监
- rationale: 长期HR、管理咨询和面试专家背景，辅导人群广，覆盖求职、面试和职业规划，适合迷茫期方向探索。

### 18. case_023 / rank 10 / service_mentor:47 / 田畅（Tina）

- case: 简历很弱，需要定位、经历梳理和求职路径设计
- label: **good**
- score snapshot: final=57.34, semantic=81.35, company=0.0, role=0.0, skill=33.33, industry=0.0, stage=75.0
- key fields: industries=IT；互联网；咨询服务; companies=IBM；华为; roles=招聘专家；生涯规划师；猎头; skills=企业端人才配置；职业定位；简历优化；面试技巧指导；人才寻访；招聘管理; target_mentees=应届生/留学生
- rationale: 招聘专家与生涯规划师背景，明确覆盖职业定位、简历优化和面试技巧，且可辅导应届生，适合简历弱和求职路径设计场景。

### 19. case_025 / rank 6 / service_mentor:70 / 古文丽（Lisa）

- case: 希望找上海的资深女性导师，偏管理层或负责人背景，做职业规划
- label: **bad**
- score snapshot: final=46.8, semantic=79.2, company=0.0, role=37.5, skill=50.0, industry=0.0, stage=0.0
- key fields: industries=科技；新能源；教育；咨询; companies=; roles=培训经理；HRBP；公关负责人；企业合伙人；职业成长促动师; skills=培训体系搭建；人才招聘；组织发展；职业规划；课程开发；就业辅导；商业模式咨询; target_mentees=应届生/留学生；P5-P6专员级；P7专家
- rationale: 资深女性且有HRBP/培训/合伙人背景，但城市为珠海，和上海约束不匹配；若城市为硬约束，不应进入优先推荐。

### 20. case_025 / rank 9 / service_mentor:50 / 张碧妹（Sukey）

- case: 希望找上海的资深女性导师，偏管理层或负责人背景，做职业规划
- label: **bad**
- score snapshot: final=46.67, semantic=78.38, company=0.0, role=37.5, skill=50.0, industry=0.0, stage=0.0
- key fields: industries=投资；互联网科技；电商；咨询服务; companies=; roles=人力资源负责人；生涯规划师; skills=招聘；团队搭建；制度落地；人才选拔；职业规划；简历优化；面试策略；多岗位能力模型洞察; target_mentees=应届生/留学生；P5-P6专员级
- rationale: 资深女性且有人力负责人和职业规划能力，但城市为广州，和上海约束不匹配；若城市为硬约束，不应进入优先推荐。

### 21. case_025 / rank 10 / service_mentor:85 / 王瑜婧（Yvonne）

- case: 希望找上海的资深女性导师，偏管理层或负责人背景，做职业规划
- label: **acceptable**
- score snapshot: final=46.58, semantic=77.76, company=0.0, role=37.5, skill=50.0, industry=0.0, stage=0.0
- key fields: industries=半导体；智能硬件; companies=字节跳动；乐鑫科技；汝原科技；博维逻辑; roles=HR；招聘负责人；职业规划师; skills=全周期招聘；人才库储备；难招岗位攻克；校招；社招；雇主品牌搭建；跨文化交际；数据分析；职业规划; target_mentees=应届生；留学生；P5-P6专员
- rationale: 城市为上海且为女性导师，具备招聘和职业规划能力；但年限和管理层/负责人信号较弱，更适合作为可接受备选而不是强推荐。

## Suggested Next Step

将 `gold_labels_filled_v2.jsonl` 放回 `eval/gold/`，用同一批 case 重新跑 semantic local BGE-M3，再和 semantic none baseline 做对比。重点观察 NDCG@10、bad_in_top10_count、unknown_in_top10_count 是否改善。