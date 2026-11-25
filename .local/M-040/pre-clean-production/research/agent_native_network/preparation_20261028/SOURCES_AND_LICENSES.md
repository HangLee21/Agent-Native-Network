# 执行入口的来源、版本与许可

2026-10-28，D-010首阶段。先冻结SmolVLM来源供M检查点使用；E1负责硬件、环境和A0兼容，E2负责网络入口。这里只核来源与小型文本元数据，不下载模型权重或数据，不运行模型/仿真。机器可读记录见[SOURCE_LOCK.json](SOURCE_LOCK.json)。

## 1. SmolVLM2-500M：已锁定，可交A0来源检查点

| 项目 | 核查结果与一手来源 |
|---|---|
| 官方模型 | `HuggingFaceTB/SmolVLM2-500M-Video-Instruct`，[固定revision目录](https://huggingface.co/HuggingFaceTB/SmolVLM2-500M-Video-Instruct/tree/7b375e1b73b11138ff12fe22c8f2822d8fe03467) |
| 不可变revision | `7b375e1b73b11138ff12fe22c8f2822d8fe03467`；[官方commit](https://huggingface.co/HuggingFaceTB/SmolVLM2-500M-Video-Instruct/commit/7b375e1b73b11138ff12fe22c8f2822d8fe03467)，API lastModified为2025-04-08T07:25:40Z |
| 访问 | 官方API返回`private=false, gated=false`，本轮无账户/token取得公开配置和卡片；权重下载链路及传输耗时未测 |
| 权重 | `model.safetensors`，**2,029,990,624 byte**；远端LFS SHA-256 `b9bfd456c9472c0acd5719d6e514c4b859891af205ee1a736552fd3497b8b0c3`，[文件页](https://huggingface.co/HuggingFaceTB/SmolVLM2-500M-Video-Instruct/blob/7b375e1b73b11138ff12fe22c8f2822d8fe03467/model.safetensors)。这是发布方摘要，尚无本地权重文件供D复算 |
| 许可声明 | [固定模型卡](https://huggingface.co/HuggingFaceTB/SmolVLM2-500M-Video-Instruct/raw/7b375e1b73b11138ff12fe22c8f2822d8fe03467/README.md)的YAML、Model Summary及License节一致声明Apache-2.0，License节明确适用于SmolVLM2 checkpoints |
| 独立LICENSE | 完整revision文件列表中没有LICENSE/NOTICE；固定revision的`resolve/.../LICENSE`实测404。标准全文取自[Apache官方](https://www.apache.org/licenses/LICENSE-2.0.txt)。没有独立LICENSE文件与没有许可声明分开记录，不因此自动阻断依官方checkpoint声明进行本地研究推理 |
| 取得层级 | 已定位官方源；小型配置/模型卡已通过HTTP取入内存并计算哈希，摘要写入lock；未另外保存原文件；权重未取得、模型环境未由D运行、结果未复现 |

Apache-2.0允许按条款使用、修改和分发；分发时保留许可与适用声明、说明修改，存在NOTICE时按条款处理。模型卡另列能力与使用边界，应随模型记录保存。该模型声明不授予nuScenes、WILDTRACK或训练数据的使用/再分发权，也不将上游资料未核的条款猜填为已核。本文是来源条款记录，不为特定再分发包作合规验收。

### 1.1 最小文件集与总量

为减少运行时因tokenizer回退缺文件而返工，**建议13文件的保守根目录白名单**。排除整个`onnx/`和`.gitattributes`；整仓页面约7.92GB，不能直接整仓下载。

| 文件 | 官方API size，byte | 用途/本轮证据 |
|---|---:|---|
| model.safetensors | 2,029,990,624 | 唯一PyTorch权重；发布方SHA-256已锁，未下载 |
| config.json | 3,767 | 架构与配置，已取小文件并复算SHA-256 |
| generation_config.json | 136 | 默认生成配置，已取并复算 |
| preprocessor_config.json | 599 | 图像处理参数，已取并复算 |
| processor_config.json | 67 | Processor类型/图像序列参数，已取并复算 |
| tokenizer.json | 3,548,256 | fast tokenizer；仅核API大小及Git blob ID |
| tokenizer_config.json | 28,626 | tokenizer配置，已取并复算 |
| special_tokens_map.json | 868 | 仅核API大小及Git blob ID |
| added_tokens.json | 4,739 | 仅核API大小及Git blob ID |
| chat_template.json | 430 | 对话模板，已取并复算 |
| merges.txt | 466,391 | tokenizer回退文件；仅核API大小及Git blob ID |
| vocab.json | 800,662 | tokenizer回退文件；仅核API大小及Git blob ID |
| README.md | 10,865 | 版本化checkpoint许可声明，已取并复算 |
| **推荐合计** | **2,034,856,030** | **2.034856030 GB（十进制），约1.895 GiB** |

若只保留权重、配置、处理器、fast tokenizer及特殊token等10文件，去掉README/merges/vocab，候选最小量为**2,033,578,112 byte**。这一集合尚未经过本机加载验证；13文件仅多1,277,918 byte，故建议保留回退与许可说明，不声称10文件已被运行证明足够。

E1卡的模型与依赖合计上限2.5GB，按保守十进制2,500,000,000 byte解释时，推荐模型集合后仅余**465,143,970 byte**供依赖。包体积、缓存与所需增量由E1实测，不在D处假定已经满足。离线转换为bf16不会减少原始权重的下载量；锁定config顶层`torch_dtype=float32`，模型卡示例加载dtype为bf16，两者分列。

### 1.2 执行者使用约束

下载时固定完整revision和白名单，不使用`main`，下载后核每项size和权重SHA-256；lock中的Git blob SHA-1与文件内容SHA-256字段不混用。未由D获取内容的tokenizer文件，其SHA-256保持null，执行者取得后补进自己的manifest。可按`resolve_base_url + path`构造每项地址，地址均为公开官方源。

加载使用同一个本地目录的Processor与Model，记录实际包版本、设备、dtype和attention实现。config保存的`transformers_version=4.47.1`不是本机支持性的证明；[官方4.51.3 SmolVLM文档](https://huggingface.co/docs/transformers/v4.51.3/en/model_doc/smolvlm)提供内置架构入口，具体使用E1已核的隔离环境，不为追新改共享环境。仓库无模型自带Python文件；不需要因该checkpoint开启远端代码执行。

预处理默认`size.longest_edge=2048`、patch最长边512、开启image splitting，视频最多64帧。这些是默认配置，不是A0应使用的负载；E1若改成单张较小合成图，应固定配置并保存实际张量尺寸。模型卡的显存说明不作为本机资源保证。D锁定来源后，真实A0仍由M按E1-010同卡检查点发放，最多4次前向/每次128输出token等以该卡最新预算为准。

## 2. ns-3版本与构建：已核来源，执行仍由E2负责

[官方3.46发布页](https://www.nsnam.org/releases/ns-3-46/)列出3.46及3.46.1补丁，建议后者；本次按原计划首先锁3.46，不默默替执行者换版本。官方tag API的annotated tag object与commit分别为：

| 版本 | tag object | 实际commit |
|---|---|---|
| ns-3.46 | e21d6dcbdf8239783fb7b39b54f2f5d3882409b0 | ea50b72ab79b1ec5912c66d5b384effa829f18bc |
| ns-3.46.1 | d13fc6d66c77a493bce9864ffe1d58c5f94e758f | 51387bce7e5f5c57aa080612a4ed690bf33d0c92 |

可复核[3.46 GitLab tag API](https://gitlab.com/api/v4/projects/nsnam%2Fns-3-dev/repository/tags/ns-3.46)、[3.46.1 API](https://gitlab.com/api/v4/projects/nsnam%2Fns-3-dev/repository/tags/ns-3.46.1)。[固定commit README](https://raw.githubusercontent.com/nsnam/ns-3-dev-git/ea50b72ab79b1ec5912c66d5b384effa829f18bc/README.md)声明GPL-2.0-only；[LICENSE](https://raw.githubusercontent.com/nsnam/ns-3-dev-git/ea50b72ab79b1ec5912c66d5b384effa829f18bc/LICENSE)的SHA-256为`ab15fd526bd8dd18a9e77ebc139656bf4d33e97fc7238cd11bf60e2b9b8666c6`。按条款保留来源、修改和分发所需源代码，具体文件的其他适用声明另保留；不把网站页脚的CC许可当作模拟器许可。

**构建要求须以固定源码检查为准。** 官方3.46安装指南quick-start仍显示较旧的最低版本，而本次固定commit的CMake声明为CMake≥3.20、GNU≥11、Clang≥17、AppleClang≥15；`ns3`包装器要求Python≥3.9。本次读取的`build-support/macros-and-definitions.cmake`声明最低C++23并排除C++20，已通过GitLab主仓文件API和GitHub镜像同commit交叉核对，二者blob为`fc7a5731a10ee2ad8e052aed27c685cc8f2c52dd`、SHA-256均为`bde58db7b9a9ed9e0fef70bcd7d2f185b1de4c3fd3b1c5e8e2585f3c5a484558`。执行者需保存所取源码hash与实际configure诊断；不能仅用网上的C++20通用说明推定本机可构建。

Windows并非必须转Linux：[官方安装指南Windows节](https://www.nsnam.org/docs/release/3.46/installation/singlehtml/index.html#windows)列WSL或MSYS2/MinGW64两条路径。已有Windows工具链可在E2卡的同一预算下验证；本卡不安装工具/驱动、不改系统或共享环境。以上是来源/构建声明核查，D未构建或运行ns-3。

## 3. 数据：条款核查与A0输入分开

### nuScenes mini

原[条款入口](https://www.nuscenes.org/terms-of-use)静态正文只显示需JavaScript。本轮进一步只读其HTML明确引用的[官网TermsOfUseNonCommercial组件](https://www.nuscenes.org/static/js/TermsOfUseNonCommercial.d9d49b0c.chunk.js)，未执行脚本或登录；文本取得并计算SHA-256为`16004e67a806af07ef913d269de0f2a835476b25fa1c585642f1fa1fe1bfeedf`。组件声明条款更新日2021-11-16，许可为**CC BY-NC-SA 4.0及该站附加Dataset Terms**，冲突时附加条款优先，第三方数据还可能有单独条件。[官网NuScenes组件](https://www.nuscenes.org/static/js/NuScenes.8e147369.chunk.js)也明确非商业使用范围，SHA-256为`7c72d580670e968975d0552e7c9bc8a1eca7a12a31696a8c1461ca27c79e80d0`。

研究使用与再分发需按这些实际数据条款处理：保留归属/许可及修改说明，非商业与相同方式共享要求适用于许可涵盖的范围，另核第三方标记、隐私及附加条款；不据模型Apache许可或[devkit](https://github.com/nutonomy/nuscenes-devkit)代码许可推定数据可任意再分发。mini的实际下载包、精确size/hash、当前账户/条款接受流程及数据文件内标记，本轮均未执行/未核到最终包，不填已可下载或已同意。后续从官方页面取得并保存当时条款和文件hash；不以第三方镜像绕开流程。

这不阻塞当前A0：E1可使用自生成合成图验证视觉加载与接口，不能据此声称真实场景自主协作。nuScenes同车多视角的用途和几何边界沿已冻结验证方案。

### WILDTRACK

[EPFL官方页面](https://www.epfl.ch/labs/cvlab/data/data-wildtrack/)提供标注帧ZIP直接链接、7路视频入口、标定和同步说明；页面本身未列完整数据许可、再分发和衍生数据条款。**公开链接已定位，完整许可unknown**，不从研究论文或其他代码仓的许可补填。未点取ZIP/视频、未测试包大小/匿名下载成功、不重分发；后续需取得正式条款或权利人明确授权。A0不依赖该数据。

## 4. AgenticDTN：精确论文与作者入口缺口

准确题目为 *Agentic-AI Digital Twin Network for Autonomous Optimization of Wireless Mesh Networks*，DOI `10.1109/RADIOELEKTRONIKA71189.2026.11726473`。[IEEE官方摘要](https://ieeexplore.ieee.org/abstract/document/11726473)仍是本轮能直接核对的方法证据。出版方提交的[Crossref记录](https://api.crossref.org/works/10.1109%2FRADIOELEKTRONIKA71189.2026.11726473)确认作者Rami Khaldi、Armin Lehmann、Bogdan Ghita、Ulrich Trick及机构，资源入口指IEEE。

有界检索采用准确题目、AgenticDTN+GitHub/arXiv、题目+Khaldi+pdf，以及作者机构域。定位到[作者研究组介绍](https://www.e-technik.org/forschung/trick_frankfurt_university.pdf)和[会议程序](https://radioelektronika.uniza.sk/confprogram?id_conference=30&ra%5Bid_conference%5D=30&rp=%2Fhome.php)，但没有据此取得该篇公开全文或代码。Crossref的PDF项标为similarity-checking，不能把它当公开全文访问授权。

检索另命中同作者的 *Agentic-AI Framework for Integrated Design, Implementation, Testing, and Operation of Digital Twin Networks*，DOI `10.1109/OJCOMS.2026.3686199`，是另一篇文章；不拿其核心网实验、作者稿或许可填到本篇Mesh论文。当前直接可用结论仍限原摘要的16节点双射频802.11s、3UDP流及数字孪生验证后调信道/路由。模型驻留、移动/churn、控制收费、源码与可复现实验参数继续unknown；全文访问不阻塞SmolVLM来源交接。

## 5. 复核与交接

机器锁定记录保留每项size、Git blob和已取小文件的SHA-256，未取字段为null；全文和权重访问不混写。只读HTTP命令形态为`Invoke-RestMethod -Uri <official API> -TimeoutSec 30`及`Invoke-WebRequest -Uri <pinned small metadata URL> -TimeoutSec 30`；内容在内存解析/哈希，不调用模型、不保存未获分配的源文件。普通sandbox socket请求失败一次后，改用获准的只读元数据请求成功；`LICENSE`404与无权重下载均记录。

首阶段交M冻结来源后即停写，等待同卡后续整合指令；PREPARATION总报告和NEXT_STEPS的执行状态须在E1/E2冻结后按实际证据更新。本卡不把来源锁定等同A0通过。
