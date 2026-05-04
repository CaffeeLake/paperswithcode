// Domain tags with muted academic colors (all oklch chroma ~0.06)
const DOMAINS = [
  { id: "language-modeling", label: "language modeling", count: 1284, hue: 250 },
  { id: "reinforcement-learning", label: "reinforcement learning", count: 612, hue: 30 },
  { id: "image-classification", label: "image classification", count: 891, hue: 145 },
  { id: "robotics", label: "robotics", count: 287, hue: 20 },
  { id: "diffusion-models", label: "diffusion models", count: 543, hue: 310 },
  { id: "multimodal", label: "multimodal", count: 478, hue: 195 },
  { id: "agents", label: "agents", count: 401, hue: 80 },
  { id: "speech-recognition", label: "speech recognition", count: 156, hue: 175 },
  { id: "graph-neural-networks", label: "graph neural networks", count: 189, hue: 280 },
  { id: "interpretability", label: "interpretability", count: 234, hue: 50 },
  { id: "video-generation", label: "video generation", count: 167, hue: 340 },
  { id: "code-generation", label: "code generation", count: 298, hue: 220 },
  { id: "medical-imaging", label: "medical imaging", count: 134, hue: 110 },
  { id: "3d-reconstruction", label: "3d reconstruction", count: 198, hue: 165 },
  { id: "alignment", label: "alignment", count: 312, hue: 10 },
  { id: "object-detection", label: "object detection", count: 267, hue: 130 },
  { id: "time-series", label: "time series", count: 145, hue: 260 },
  { id: "evaluation", label: "evaluation", count: 223, hue: 70 },
];

const PAPERS = [
  {
    id: "2604.18221",
    title: "Sparse Mixture-of-Specialists: Routing Capacity Beyond the Dense Frontier",
    authors: ["Wei Zhang", "Maya Krishnan", "Henrik Lund", "Akira Tanaka", "+8 authors"],
    institution: "Stanford NLP Group",
    abstract: "We introduce Sparse Mixture-of-Specialists (SMoS), a routing architecture that activates a small subset of expert subnetworks per token while maintaining gradient flow through unused experts via auxiliary distillation. SMoS achieves a 3.2× compute reduction over dense baselines at equivalent perplexity on language modeling benchmarks, and we demonstrate that specialist routing emerges interpretable domain structure without explicit supervision.",
    tags: ["language-modeling", "interpretability"],
    upvotes: 312,
    citations: 47,
    date: "Apr 26",
    submitter: "wzhang",
    github: 4200,
    project: "https://smos.stanford.edu/",
    pdfPages: 24,
  },
  {
    id: "2604.17889",
    title: "DiffPolicy: Closed-Loop Robotic Manipulation via Conditional Score Distillation",
    authors: ["Carlos Mendoza", "Priya Raman", "Jin-Soo Park", "Eleanor Hayes"],
    institution: "MIT CSAIL",
    abstract: "DiffPolicy formulates robotic manipulation as iterative score-based denoising over action trajectories, conditioned on multi-view RGB-D observations. By distilling a teacher diffusion policy into a single-step student, we achieve real-time control at 50Hz while preserving multimodal action distributions. Across 22 manipulation tasks, DiffPolicy outperforms prior methods by 18.4% absolute success rate.",
    tags: ["robotics", "diffusion-models"],
    upvotes: 244,
    citations: 31,
    date: "Apr 26",
    submitter: "cmendoza",
    github: 1800,
    project: "https://diffpolicy.csail.mit.edu/",
    pdfPages: 19,
  },
  {
    id: "2604.17654",
    title: "Reasoning Traces Are All You Need: Process Reward Models from Implicit Supervision",
    authors: ["Liam O'Connor", "Saanvi Gupta", "Yuki Watanabe", "+12 authors"],
    institution: "DeepMind",
    abstract: "We show that process reward models (PRMs) can be trained without per-step human annotation by leveraging the implicit signal in successful reasoning traces. Our method, ImplicitPRM, derives stepwise rewards from final answer correctness via a learned credit assignment objective, matching annotated baselines on MATH and GSM8K while using 0% labeled intermediate steps.",
    tags: ["reinforcement-learning", "language-modeling", "alignment"],
    upvotes: 198,
    citations: 22,
    date: "Apr 25",
    submitter: "loconnor",
    github: 980,
    pdfPages: 31,
  },
  {
    id: "2604.17321",
    title: "Holographic Scene Fields: Compositional 3D Generation via Latent Volumetric Primitives",
    authors: ["Anya Volkov", "Tobias Reinhardt", "Mei Lin", "Jacob Steiner"],
    institution: "ETH Zürich",
    abstract: "We propose Holographic Scene Fields, a generative model that composes 3D scenes from a vocabulary of latent volumetric primitives. Each primitive encodes geometry and appearance in a 64-dim latent that decodes to a neural radiance field. Our model supports interactive editing, scene composition, and outperforms text-to-3D baselines by 12.7 CLIP-similarity points.",
    tags: ["3d-reconstruction", "diffusion-models"],
    upvotes: 167,
    citations: 14,
    date: "Apr 25",
    submitter: "avolkov",
    github: 720,
    project: "https://holoscene.ethz.ch/",
    pdfPages: 22,
  },
  {
    id: "2604.16998",
    title: "Long-Context Attention Without Quadratic Memory: Recurrent Compression with Verifiable Recall",
    authors: ["Ravi Subramanian", "Hannah Ng", "Pierre Boucher"],
    institution: "Cornell University",
    abstract: "We present RCVR, a hybrid attention mechanism combining recurrent state compression with sparse verifiable retrieval. Unlike pure linear attention, RCVR provides certified recall guarantees on a learned subset of tokens. We process 1M token contexts at 4× the throughput of FlashAttention-2 while matching dense baseline accuracy on RULER and InfiniteBench.",
    tags: ["language-modeling"],
    upvotes: 156,
    citations: 19,
    date: "Apr 24",
    submitter: "rsubra",
    github: 612,
    pdfPages: 18,
  },
  {
    id: "2604.16772",
    title: "VisionLM-7B: Compute-Optimal Scaling Laws for Multimodal Pretraining",
    authors: ["Sofia Esposito", "Daniel Park", "Aisha Mohammed", "+6 authors"],
    institution: "Allen Institute for AI",
    abstract: "We derive empirical scaling laws for multimodal pretraining across image-text, video-text, and audio-text modalities. Contrary to prior work, we find optimal vision-language compute splits depend strongly on downstream evaluation distribution. VisionLM-7B, trained at our derived optimum, matches 13B baselines on 11 of 14 benchmarks.",
    tags: ["multimodal", "language-modeling"],
    upvotes: 142,
    citations: 11,
    date: "Apr 24",
    submitter: "sesposito",
    github: 2100,
    project: "https://allenai.org/visionlm-7b",
    pdfPages: 28,
  },
  {
    id: "2604.16443",
    title: "Self-Verifying Code Agents: Iterative Refinement Through Test Synthesis",
    authors: ["Marcus Wei", "Lina Petrov", "Hassan Al-Rashid", "+4 authors"],
    institution: "UC Berkeley",
    abstract: "Self-verifying code agents synthesize executable test cases alongside candidate solutions, using test pass rates as an internal reward signal for iterative refinement. On SWE-bench Verified, our agent achieves 64.3% solve rate using only open-weight models, surpassing prior open-source approaches by 11.2 points.",
    tags: ["code-generation", "agents"],
    upvotes: 134,
    citations: 8,
    date: "Apr 23",
    submitter: "mwei",
    github: 3400,
    project: "https://selfverify.berkeley.edu/",
    pdfPages: 17,
  },
  {
    id: "2604.16201",
    title: "Probing the Geometry of Refusal: A Mechanistic Account of Safety Training",
    authors: ["Olivia Chen", "Ben Yamamoto", "Fatima Khalil"],
    institution: "Anthropic",
    abstract: "We identify a low-rank refusal direction in the residual stream of safety-trained language models and show it can be ablated to reverse refusal behavior. More importantly, we characterize the geometry of how refusal interacts with helpfulness, finding that they occupy nearly orthogonal subspaces in early layers but entangle in later ones.",
    tags: ["interpretability", "alignment"],
    upvotes: 121,
    citations: 16,
    date: "Apr 23",
    submitter: "ochen",
    github: 540,
    pdfPages: 23,
  },
  {
    id: "2604.15998",
    title: "EquiDiff: SE(3)-Equivariant Diffusion for Molecular Conformer Generation",
    authors: ["Niko Halonen", "Aarav Mehta", "Clara Dubois", "+3 authors"],
    institution: "EPFL",
    abstract: "EquiDiff enforces SE(3) equivariance throughout a denoising diffusion process for 3D molecular conformer generation. We introduce a novel tensor-product attention layer that maintains exact equivariance while being 2.3× faster than prior equivariant networks. EquiDiff sets new state-of-the-art on GEOM-Drugs.",
    tags: ["diffusion-models", "graph-neural-networks"],
    upvotes: 98,
    citations: 9,
    date: "Apr 22",
    submitter: "nhalonen",
    github: 410,
    pdfPages: 16,
  },
  {
    id: "2604.15772",
    title: "FlowVideo: Long-Form Video Generation via Trajectory-Conditioned Flow Matching",
    authors: ["Yuhan Zhao", "Marco Bianchi", "Selin Aydın", "+5 authors"],
    institution: "Tsinghua University",
    abstract: "FlowVideo generates 60-second coherent videos at 720p resolution by conditioning a flow-matching model on dense optical-flow trajectories. We introduce trajectory consistency loss that maintains object identity across long horizons. Outperforms prior methods by 8.3 FVD points on UCF-101.",
    tags: ["video-generation", "diffusion-models"],
    upvotes: 89,
    citations: 6,
    date: "Apr 22",
    submitter: "yzhao",
    github: 890,
    project: "https://flowvideo.ai/",
    pdfPages: 21,
  },
  {
    id: "2604.15443",
    title: "BenchmarkRot: How Quickly Do LLM Benchmarks Saturate, and Why?",
    authors: ["Theodore Adams", "Ines Romero", "Kenji Sato"],
    institution: "Princeton University",
    abstract: "We track 47 popular LLM benchmarks over 30 months and find median time-to-saturation of 14.2 months. Benchmark rot correlates with task ambiguity and training data leakage. We propose BenchmarkRot, a meta-evaluation framework that predicts benchmark longevity from task design features.",
    tags: ["evaluation", "language-modeling"],
    upvotes: 78,
    citations: 12,
    date: "Apr 21",
    submitter: "tadams",
    github: 230,
    pdfPages: 15,
  },
  {
    id: "2604.15201",
    title: "Sample-Efficient World Models for Sparse-Reward Manipulation",
    authors: ["Lukas Berger", "Pooja Iyer", "Daniel Costa"],
    institution: "Carnegie Mellon",
    abstract: "We learn world models from 50 demonstrations plus 2 hours of online interaction, enabling sample-efficient policy learning on contact-rich manipulation tasks with sparse rewards. Our approach, WMSparse, combines latent dynamics learning with goal-conditioned exploration, achieving 73% success on a real Franka arm across 9 tasks.",
    tags: ["robotics", "reinforcement-learning"],
    upvotes: 67,
    citations: 4,
    date: "Apr 21",
    submitter: "lberger",
    github: 320,
    project: "https://wmsparse.cmu.edu/",
    pdfPages: 19,
  },
];

// Helper: get domain by id
function getDomain(id) {
  return DOMAINS.find(d => d.id === id);
}

// Helper: get papers filtered by tag
function getPapersByTag(tagId) {
  return PAPERS.filter(p => p.tags.includes(tagId));
}

// Methods — common AI techniques. Grouped by category.
const METHODS = [
  // Attention / transformer family
  { id: "transformer", label: "Transformer", category: "architectures", count: 4821, blurb: "An encoder–decoder architecture built on multi-head self-attention, replacing recurrence with parallel sequence modeling.", year: 2017, source: { title: "Attention Is All You Need", authors: "Vaswani et al.", arxivId: "1706.03762" } },
  { id: "attention", label: "Attention", category: "architectures", count: 6210, blurb: "A learned weighting mechanism that computes context-dependent representations by attending over a set of keys and values.", year: 2014, source: { title: "Neural Machine Translation by Jointly Learning to Align and Translate", authors: "Bahdanau et al.", arxivId: "1409.0473" } },
  { id: "self-attention", label: "Self-Attention", category: "architectures", count: 3104, blurb: "Attention applied within a single sequence so each token can attend to every other token.", year: 2017, source: { title: "Attention Is All You Need", authors: "Vaswani et al.", arxivId: "1706.03762" } },
  { id: "rope", label: "RoPE", category: "architectures", count: 612, blurb: "Rotary Position Embeddings — encodes absolute position by rotating query and key vectors in 2D subspaces.", year: 2021, source: { title: "RoFormer: Enhanced Transformer with Rotary Position Embedding", authors: "Su et al.", arxivId: "2104.09864" } },
  { id: "flashattn", label: "FlashAttention", category: "architectures", count: 489, blurb: "An IO-aware exact attention algorithm that tiles computation to fit GPU SRAM, reducing memory and wall-clock time.", year: 2022, source: { title: "FlashAttention: Fast and Memory-Efficient Exact Attention with IO-Awareness", authors: "Dao et al.", arxivId: "2205.14135" } },
  { id: "moe", label: "Mixture of Experts", category: "architectures", count: 412, blurb: "Sparse routing of inputs to a small subset of expert subnetworks per forward pass.", year: 1991, source: { title: "Adaptive Mixtures of Local Experts", authors: "Jacobs, Jordan, Nowlan & Hinton", arxivId: null } },
  { id: "cnn", label: "Convolutional Network", category: "architectures", count: 7102, blurb: "Networks built from learned convolutional filters that exploit translation equivariance.", year: 1989, source: { title: "Backpropagation Applied to Handwritten Zip Code Recognition", authors: "LeCun et al.", arxivId: null } },
  { id: "u-net", label: "U-Net", category: "architectures", count: 1843, blurb: "An encoder–decoder with skip connections at matching resolutions, widely used for dense prediction and diffusion.", year: 2015, source: { title: "U-Net: Convolutional Networks for Biomedical Image Segmentation", authors: "Ronneberger, Fischer & Brox", arxivId: "1505.04597" } },
  { id: "vit", label: "Vision Transformer", category: "architectures", count: 1521, blurb: "Applies the Transformer encoder directly to sequences of image patches.", year: 2020, source: { title: "An Image is Worth 16×16 Words: Transformers for Image Recognition at Scale", authors: "Dosovitskiy et al.", arxivId: "2010.11929" } },

  // Normalization
  { id: "layernorm", label: "LayerNorm", category: "normalization", count: 3102, blurb: "Normalizes activations across the feature dimension within each token, stabilizing training of deep transformers.", year: 2016, source: { title: "Layer Normalization", authors: "Ba, Kiros & Hinton", arxivId: "1607.06450" } },
  { id: "batchnorm", label: "BatchNorm", category: "normalization", count: 4421, blurb: "Normalizes activations across a mini-batch per feature channel; widely used in convolutional networks.", year: 2015, source: { title: "Batch Normalization: Accelerating Deep Network Training by Reducing Internal Covariate Shift", authors: "Ioffe & Szegedy", arxivId: "1502.03167" } },
  { id: "rmsnorm", label: "RMSNorm", category: "normalization", count: 521, blurb: "A simpler variant of LayerNorm that skips the mean centering step.", year: 2019, source: { title: "Root Mean Square Layer Normalization", authors: "Zhang & Sennrich", arxivId: "1910.07467" } },

  // Optimizers
  { id: "adamw", label: "AdamW", category: "optimization", count: 3812, blurb: "Adam with decoupled weight decay; the default optimizer for most modern transformer training runs.", year: 2017, source: { title: "Decoupled Weight Decay Regularization", authors: "Loshchilov & Hutter", arxivId: "1711.05101" } },
  { id: "adam", label: "Adam", category: "optimization", count: 6921, blurb: "Adaptive moment estimation — combines first and second moment estimates of gradients.", year: 2014, source: { title: "Adam: A Method for Stochastic Optimization", authors: "Kingma & Ba", arxivId: "1412.6980" } },
  { id: "sgd", label: "SGD with Momentum", category: "optimization", count: 5432, blurb: "Stochastic gradient descent with a velocity term that accumulates past gradients.", year: 1986, source: { title: "Learning representations by back-propagating errors", authors: "Rumelhart, Hinton & Williams", arxivId: null } },
  { id: "cosine-schedule", label: "Cosine Schedule", category: "optimization", count: 1421, blurb: "A learning rate schedule that decays following a half-cosine curve to zero.", year: 2017, source: { title: "SGDR: Stochastic Gradient Descent with Warm Restarts", authors: "Loshchilov & Hutter", arxivId: "1608.03983" } },

  // Generative
  { id: "ddpm", label: "DDPM", category: "generative", count: 1212, blurb: "Denoising Diffusion Probabilistic Models — generative models trained to reverse a noising process.", year: 2020, source: { title: "Denoising Diffusion Probabilistic Models", authors: "Ho, Jain & Abbeel", arxivId: "2006.11239" } },
  { id: "flow-matching", label: "Flow Matching", category: "generative", count: 312, blurb: "Trains a continuous-time flow by regressing onto a target vector field, an alternative to score-based diffusion.", year: 2022, source: { title: "Flow Matching for Generative Modeling", authors: "Lipman et al.", arxivId: "2210.02747" } },
  { id: "vae", label: "VAE", category: "generative", count: 2410, blurb: "Variational Autoencoders — latent-variable generative models trained with an evidence lower bound.", year: 2013, source: { title: "Auto-Encoding Variational Bayes", authors: "Kingma & Welling", arxivId: "1312.6114" } },
  { id: "gan", label: "GAN", category: "generative", count: 5102, blurb: "Generative Adversarial Networks — pit a generator against a discriminator in a minimax game.", year: 2014, source: { title: "Generative Adversarial Networks", authors: "Goodfellow et al.", arxivId: "1406.2661" } },
  { id: "score-distillation", label: "Score Distillation", category: "generative", count: 187, blurb: "Distills a teacher score-based model into a faster student sampler, often single-step.", year: 2022, source: { title: "DreamFusion: Text-to-3D using 2D Diffusion", authors: "Poole et al.", arxivId: "2209.14988" } },

  // RL / training paradigms
  { id: "ppo", label: "PPO", category: "rl", count: 1923, blurb: "Proximal Policy Optimization — a clipped policy gradient method, the workhorse of policy learning.", year: 2017, source: { title: "Proximal Policy Optimization Algorithms", authors: "Schulman et al.", arxivId: "1707.06347" } },
  { id: "rlhf", label: "RLHF", category: "rl", count: 612, blurb: "Reinforcement Learning from Human Feedback — fine-tunes models against a learned reward model trained on human preferences.", year: 2017, source: { title: "Deep Reinforcement Learning from Human Preferences", authors: "Christiano et al.", arxivId: "1706.03741" } },
  { id: "dpo", label: "DPO", category: "rl", count: 423, blurb: "Direct Preference Optimization — fits a policy to preference data without a separate reward model.", year: 2023, source: { title: "Direct Preference Optimization: Your Language Model is Secretly a Reward Model", authors: "Rafailov et al.", arxivId: "2305.18290" } },

  // Audio / signal
  { id: "spectrogram", label: "Spectrogram", category: "signal", count: 1012, blurb: "A 2D time-frequency representation of an audio signal, commonly the input to audio neural networks.", year: 1947, source: { title: "Visible Speech", authors: "Potter, Kopp & Green", arxivId: null } },
  { id: "mel-spectrogram", label: "Mel-Spectrogram", category: "signal", count: 821, blurb: "A spectrogram on a perceptually-spaced mel-frequency axis, standard for speech recognition.", year: 1937, source: { title: "A Scale for the Measurement of the Psychological Magnitude Pitch", authors: "Stevens, Volkmann & Newman", arxivId: null } },

  // Regularization / techniques
  { id: "dropout", label: "Dropout", category: "regularization", count: 5821, blurb: "Randomly zeroes a fraction of activations during training to prevent co-adaptation.", year: 2012, source: { title: "Improving neural networks by preventing co-adaptation of feature detectors", authors: "Hinton et al.", arxivId: "1207.0580" } },
  { id: "lora", label: "LoRA", category: "regularization", count: 1421, blurb: "Low-Rank Adaptation — fine-tunes large models by injecting trainable low-rank matrices into frozen weights.", year: 2021, source: { title: "LoRA: Low-Rank Adaptation of Large Language Models", authors: "Hu et al.", arxivId: "2106.09685" } },
];

const METHOD_CATEGORIES = [
  { id: "architectures", label: "Architectures", blurb: "Building blocks and full networks." },
  { id: "normalization", label: "Normalization", blurb: "Activation re-scaling layers." },
  { id: "optimization", label: "Optimization", blurb: "Optimizers and learning-rate schedules." },
  { id: "generative", label: "Generative Modeling", blurb: "Methods for sampling from learned distributions." },
  { id: "rl", label: "Reinforcement Learning", blurb: "Policy optimization and preference learning." },
  { id: "signal", label: "Signal Representations", blurb: "Inputs derived from raw audio and other signals." },
  { id: "regularization", label: "Regularization & Adaptation", blurb: "Generalization and parameter-efficient tuning." },
];

// Tag papers with methods (paperId -> method ids)
const PAPER_METHODS = {
  "2604.18221": ["transformer", "moe", "layernorm", "adamw", "rope"],
  "2604.17889": ["ddpm", "u-net", "score-distillation", "adamw"],
  "2604.17654": ["transformer", "rlhf", "ppo", "adamw", "rope"],
  "2604.17321": ["ddpm", "vit", "u-net", "adamw"],
  "2604.16998": ["transformer", "flashattn", "rmsnorm", "adamw", "rope"],
  "2604.16772": ["vit", "transformer", "layernorm", "adamw", "cosine-schedule"],
  "2604.16443": ["transformer", "rlhf", "dpo", "adamw"],
  "2604.16201": ["transformer", "rmsnorm", "lora", "rope"],
  "2604.15998": ["ddpm", "transformer", "layernorm", "adamw"],
  "2604.15772": ["flow-matching", "u-net", "vit", "adamw", "cosine-schedule"],
  "2604.15443": ["transformer", "rope", "flashattn"],
  "2604.15201": ["ppo", "cnn", "adam", "batchnorm"],
};

// Benchmark results per paper (for the Results section)
const PAPER_RESULTS = {
  "2604.18221": [{ task: "language-modeling", benchmark: "C4 (validation)", metric: "PPL", value: "9.84", rank: 1 }, { task: "language-modeling", benchmark: "The Pile", metric: "PPL", value: "7.21", rank: 1 }],
  "2604.17889": [{ task: "robotics", benchmark: "RoboBench-22", metric: "Success Rate", value: "78.3%", rank: 1 }, { task: "robotics", benchmark: "Real Franka (9 tasks)", metric: "Success", value: "73%", rank: 2 }],
  "2604.17654": [{ task: "reinforcement-learning", benchmark: "MATH", metric: "Accuracy", value: "62.4%", rank: 3 }, { task: "reinforcement-learning", benchmark: "GSM8K", metric: "Accuracy", value: "89.1%", rank: 4 }],
  "2604.17321": [{ task: "3d-reconstruction", benchmark: "T3Bench", metric: "CLIP-Sim", value: "0.342", rank: 1 }],
  "2604.16998": [{ task: "language-modeling", benchmark: "RULER (1M ctx)", metric: "Recall", value: "94.2%", rank: 1 }, { task: "language-modeling", benchmark: "InfiniteBench", metric: "Avg", value: "61.8", rank: 2 }],
  "2604.16772": [{ task: "multimodal", benchmark: "MMMU", metric: "Accuracy", value: "58.2%", rank: 4 }, { task: "multimodal", benchmark: "DocVQA", metric: "ANLS", value: "0.892", rank: 3 }],
  "2604.16443": [{ task: "code-generation", benchmark: "SWE-bench Verified", metric: "Resolved", value: "64.3%", rank: 1 }, { task: "code-generation", benchmark: "HumanEval+", metric: "Pass@1", value: "91.4%", rank: 5 }],
  "2604.16201": [{ task: "interpretability", benchmark: "ToxicBench", metric: "ASR", value: "82%", rank: 2 }],
  "2604.15998": [{ task: "diffusion-models", benchmark: "GEOM-Drugs", metric: "AMR-MIN", value: "0.247", rank: 1 }],
  "2604.15772": [{ task: "video-generation", benchmark: "UCF-101", metric: "FVD", value: "212.4", rank: 1 }, { task: "video-generation", benchmark: "MSR-VTT", metric: "FVD", value: "184.1", rank: 2 }],
  "2604.15443": [{ task: "evaluation", benchmark: "BenchmarkRot-47", metric: "Rank-Corr", value: "0.71", rank: 1 }],
  "2604.15201": [{ task: "robotics", benchmark: "RLBench-9", metric: "Success", value: "73%", rank: 3 }],
};

function getMethod(id) { return METHODS.find(m => m.id === id); }
function getMethodCategory(id) { return METHOD_CATEGORIES.find(c => c.id === id); }
function getPapersByMethod(methodId) {
  return PAPERS.filter(p => (PAPER_METHODS[p.id] || []).includes(methodId));
}

// Foundational source papers — synthesized records for the papers that introduced
// each method. Looked up by arxivId; PaperDetailView falls back to these when the
// id isn't in the main PAPERS list.
const SOURCE_PAPERS = {
  "1706.03762": {
    id: "1706.03762",
    title: "Attention Is All You Need",
    authors: ["Ashish Vaswani", "Noam Shazeer", "Niki Parmar", "Jakob Uszkoreit", "Llion Jones", "Aidan N. Gomez", "Łukasz Kaiser", "Illia Polosukhin"],
    institution: "Google Brain · Google Research · University of Toronto",
    abstract: "The dominant sequence transduction models are based on complex recurrent or convolutional neural networks that include an encoder and a decoder. The best performing models also connect the encoder and decoder through an attention mechanism. We propose a new simple network architecture, the Transformer, based solely on attention mechanisms, dispensing with recurrence and convolutions entirely. Experiments on two machine translation tasks show these models to be superior in quality while being more parallelizable and requiring significantly less time to train.",
    tldr: "Replaces recurrence and convolutions with multi-head self-attention. Establishes the Transformer architecture that underpins essentially every modern language and multimodal model.",
    tags: ["language-modeling"],
    upvotes: 12480, citations: 132041, comments: 0,
    year: 2017, date: "Jun 12, 2017", venue: "NeurIPS 2017",
  },
  "1409.0473": {
    id: "1409.0473",
    title: "Neural Machine Translation by Jointly Learning to Align and Translate",
    authors: ["Dzmitry Bahdanau", "Kyunghyun Cho", "Yoshua Bengio"],
    institution: "Université de Montréal · Jacobs University Bremen",
    abstract: "Neural machine translation is a recently proposed approach to machine translation that aims to build a single neural network that can be jointly tuned to maximize translation performance. We conjecture that the use of a fixed-length vector is a bottleneck and propose extending the encoder–decoder model with a soft attention mechanism that learns to align and translate jointly. The proposed approach achieves a translation performance comparable to the existing state-of-the-art phrase-based system on English-to-French translation.",
    tldr: "Introduces the soft attention mechanism for sequence-to-sequence models, freeing the decoder from compressing the source into a single fixed vector.",
    tags: ["language-modeling"],
    upvotes: 8420, citations: 41203, comments: 0,
    year: 2014, date: "Sep 1, 2014", venue: "ICLR 2015",
  },
  "2104.09864": {
    id: "2104.09864",
    title: "RoFormer: Enhanced Transformer with Rotary Position Embedding",
    authors: ["Jianlin Su", "Yu Lu", "Shengfeng Pan", "Bo Wen", "Yunfeng Liu"],
    institution: "Zhuiyi Technology",
    abstract: "Position encoding has shown effective in the transformer architecture. We propose Rotary Position Embedding (RoPE) to encode absolute positional information with rotation matrices and naturally incorporate explicit relative position dependency in self-attention. RoPE has valuable properties such as flexibility of being expanded to any sequence lengths, decaying inter-token dependency with increasing relative distances, and the capability of equipping the linear self-attention with relative position encoding.",
    tldr: "Encodes position by rotating query/key vectors in 2D subspaces — became the standard positional scheme in modern LLMs.",
    tags: ["language-modeling"],
    upvotes: 1240, citations: 4870, comments: 0,
    year: 2021, date: "Apr 20, 2021", venue: "Neurocomputing 2024",
  },
  "2205.14135": {
    id: "2205.14135",
    title: "FlashAttention: Fast and Memory-Efficient Exact Attention with IO-Awareness",
    authors: ["Tri Dao", "Daniel Y. Fu", "Stefano Ermon", "Atri Rudra", "Christopher Ré"],
    institution: "Stanford University · University at Buffalo",
    abstract: "Transformers are slow and memory-hungry on long sequences, since the time and memory complexity of self-attention are quadratic in sequence length. We propose FlashAttention, an IO-aware exact attention algorithm that uses tiling to reduce the number of memory reads/writes between GPU HBM and on-chip SRAM. FlashAttention trains transformers faster than existing baselines and enables longer context.",
    tldr: "Reframes attention as an IO-bound problem and tiles the computation to fit GPU SRAM, yielding exact attention that is dramatically faster and more memory-efficient.",
    tags: ["language-modeling"],
    upvotes: 1840, citations: 3120, comments: 0,
    year: 2022, date: "May 27, 2022", venue: "NeurIPS 2022",
  },
  "1505.04597": {
    id: "1505.04597",
    title: "U-Net: Convolutional Networks for Biomedical Image Segmentation",
    authors: ["Olaf Ronneberger", "Philipp Fischer", "Thomas Brox"],
    institution: "University of Freiburg",
    abstract: "There is large consent that successful training of deep networks requires many thousand annotated training samples. We present a network and training strategy that relies on the strong use of data augmentation to use the available annotated samples more efficiently. The architecture consists of a contracting path to capture context and a symmetric expanding path that enables precise localization. We show that such a network can be trained end-to-end from very few images and outperforms the prior best method on the ISBI challenge for segmentation of neuronal structures in electron microscopic stacks.",
    tldr: "An encoder–decoder with skip connections at matching resolutions; the dense-prediction backbone behind nearly every modern diffusion model.",
    tags: ["computer-vision"],
    upvotes: 5210, citations: 75200, comments: 0,
    year: 2015, date: "May 18, 2015", venue: "MICCAI 2015",
  },
  "2010.11929": {
    id: "2010.11929",
    title: "An Image is Worth 16×16 Words: Transformers for Image Recognition at Scale",
    authors: ["Alexey Dosovitskiy", "Lucas Beyer", "Alexander Kolesnikov", "Dirk Weissenborn", "Xiaohua Zhai", "Thomas Unterthiner", "Mostafa Dehghani", "Matthias Minderer", "Georg Heigold", "Sylvain Gelly", "Jakob Uszkoreit", "Neil Houlsby"],
    institution: "Google Research, Brain Team",
    abstract: "While the Transformer architecture has become the de-facto standard for natural language processing tasks, its applications to computer vision remain limited. We show that this reliance on CNNs is not necessary and a pure transformer applied directly to sequences of image patches can perform very well on image classification tasks. When pre-trained on large amounts of data and transferred to multiple mid-sized or small image recognition benchmarks, Vision Transformer (ViT) attains excellent results compared to state-of-the-art convolutional networks while requiring substantially fewer computational resources to train.",
    tldr: "Treats an image as a sequence of patches and feeds it to a vanilla Transformer encoder. Shows attention-only models can match or beat CNNs at scale.",
    tags: ["computer-vision"],
    upvotes: 3920, citations: 38120, comments: 0,
    year: 2020, date: "Oct 22, 2020", venue: "ICLR 2021",
  },
  "1607.06450": {
    id: "1607.06450",
    title: "Layer Normalization",
    authors: ["Jimmy Lei Ba", "Jamie Ryan Kiros", "Geoffrey E. Hinton"],
    institution: "University of Toronto",
    abstract: "Training state-of-the-art, deep neural networks is computationally expensive. One way to reduce the training time is to normalize the activities of the neurons. We transpose batch normalization into layer normalization by computing the mean and variance used for normalization from all of the summed inputs to the neurons in a layer on a single training case. We show that layer normalization can substantially reduce the training time compared with previously published techniques.",
    tldr: "Normalizes across the feature dimension within a single example. Became the default normalization layer for transformers.",
    tags: ["language-modeling"],
    upvotes: 2120, citations: 11200, comments: 0,
    year: 2016, date: "Jul 21, 2016", venue: "arXiv 2016",
  },
  "1502.03167": {
    id: "1502.03167",
    title: "Batch Normalization: Accelerating Deep Network Training by Reducing Internal Covariate Shift",
    authors: ["Sergey Ioffe", "Christian Szegedy"],
    institution: "Google",
    abstract: "Training Deep Neural Networks is complicated by the fact that the distribution of each layer's inputs changes during training, as the parameters of the previous layers change. We refer to this phenomenon as internal covariate shift, and address it by normalizing layer inputs. Our method draws its strength from making normalization a part of the model architecture and performing the normalization for each training mini-batch. Batch Normalization allows us to use much higher learning rates and be less careful about initialization.",
    tldr: "Normalizes activations across the mini-batch per channel, allowing higher learning rates and reducing the importance of careful initialization.",
    tags: ["computer-vision"],
    upvotes: 4120, citations: 53400, comments: 0,
    year: 2015, date: "Feb 11, 2015", venue: "ICML 2015",
  },
  "1910.07467": {
    id: "1910.07467",
    title: "Root Mean Square Layer Normalization",
    authors: ["Biao Zhang", "Rico Sennrich"],
    institution: "University of Edinburgh · University of Zurich",
    abstract: "Layer normalization is a recently introduced technique for normalizing the distributions of intermediate layers in deep neural networks. Despite its empirical success, the role of LayerNorm is poorly understood. In this paper, we hypothesize that re-centering invariance in LayerNorm is dispensable, and propose Root Mean Square Layer Normalization (RMSNorm). RMSNorm regularizes the summed inputs to a neuron in one layer according to root mean square, giving the model re-scaling invariance and implicit learning-rate adaptation ability.",
    tldr: "Drops mean centering from LayerNorm; cheaper and equally effective. Adopted by Llama, T5, and most recent open LLMs.",
    tags: ["language-modeling"],
    upvotes: 612, citations: 1840, comments: 0,
    year: 2019, date: "Oct 16, 2019", venue: "NeurIPS 2019",
  },
  "1711.05101": {
    id: "1711.05101",
    title: "Decoupled Weight Decay Regularization",
    authors: ["Ilya Loshchilov", "Frank Hutter"],
    institution: "University of Freiburg",
    abstract: "L2 regularization and weight decay regularization are equivalent for standard stochastic gradient descent (when rescaled by the learning rate), but as we demonstrate this is not the case for adaptive gradient algorithms, such as Adam. We propose a simple modification to recover the original formulation of weight decay regularization by decoupling the weight decay from the optimization steps taken w.r.t. the loss function.",
    tldr: "Shows L2 and weight decay are not equivalent under Adam, and proposes decoupling them. The result, AdamW, is the default optimizer for nearly every modern transformer.",
    tags: ["language-modeling"],
    upvotes: 920, citations: 14820, comments: 0,
    year: 2017, date: "Nov 14, 2017", venue: "ICLR 2019",
  },
  "1412.6980": {
    id: "1412.6980",
    title: "Adam: A Method for Stochastic Optimization",
    authors: ["Diederik P. Kingma", "Jimmy Ba"],
    institution: "University of Amsterdam · University of Toronto",
    abstract: "We introduce Adam, an algorithm for first-order gradient-based optimization of stochastic objective functions, based on adaptive estimates of lower-order moments. The method is straightforward to implement, is computationally efficient, has little memory requirements, is invariant to diagonal rescaling of the gradients, and is well suited for problems that are large in terms of data and/or parameters.",
    tldr: "Combines first- and second-moment estimates of the gradient. Defined the modern adaptive optimizer landscape.",
    tags: ["language-modeling"],
    upvotes: 6210, citations: 184000, comments: 0,
    year: 2014, date: "Dec 22, 2014", venue: "ICLR 2015",
  },
  "1608.03983": {
    id: "1608.03983",
    title: "SGDR: Stochastic Gradient Descent with Warm Restarts",
    authors: ["Ilya Loshchilov", "Frank Hutter"],
    institution: "University of Freiburg",
    abstract: "Restart techniques are common in gradient-free optimization to deal with multimodal functions. Partial warm restarts are also gaining popularity in gradient-based optimization to improve the rate of convergence in accelerated gradient schemes. We propose a simple warm restart technique for stochastic gradient descent. We empirically study its performance on the CIFAR-10 and CIFAR-100 datasets.",
    tldr: "Introduces cosine annealing with warm restarts. The cosine schedule is now standard for transformer training.",
    tags: ["computer-vision"],
    upvotes: 412, citations: 4920, comments: 0,
    year: 2016, date: "Aug 13, 2016", venue: "ICLR 2017",
  },
  "2006.11239": {
    id: "2006.11239",
    title: "Denoising Diffusion Probabilistic Models",
    authors: ["Jonathan Ho", "Ajay Jain", "Pieter Abbeel"],
    institution: "UC Berkeley",
    abstract: "We present high quality image synthesis results using diffusion probabilistic models, a class of latent variable models inspired by considerations from nonequilibrium thermodynamics. Our best results are obtained by training on a weighted variational bound designed according to a novel connection between diffusion probabilistic models and denoising score matching with Langevin dynamics, and our models naturally admit a progressive lossy decompression scheme that can be interpreted as a generalization of autoregressive decoding.",
    tldr: "Reformulates diffusion models with a simple noise-prediction objective. Kicked off the modern diffusion era.",
    tags: ["diffusion-models", "computer-vision"],
    upvotes: 4820, citations: 18420, comments: 0,
    year: 2020, date: "Jun 19, 2020", venue: "NeurIPS 2020",
  },
  "2210.02747": {
    id: "2210.02747",
    title: "Flow Matching for Generative Modeling",
    authors: ["Yaron Lipman", "Ricky T. Q. Chen", "Heli Ben-Hamu", "Maximilian Nickel", "Matthew Le"],
    institution: "Meta AI · Weizmann Institute",
    abstract: "We introduce a new paradigm for generative modeling built on Continuous Normalizing Flows (CNFs), allowing us to train CNFs at unprecedented scale. Specifically, we present the notion of flow matching, a simulation-free approach for training CNFs based on regressing vector fields of fixed conditional probability paths.",
    tldr: "Trains continuous-time flows by regressing on a target velocity field. Simulation-free training and a strong alternative to score-based diffusion.",
    tags: ["diffusion-models"],
    upvotes: 412, citations: 920, comments: 0,
    year: 2022, date: "Oct 6, 2022", venue: "ICLR 2023",
  },
  "1312.6114": {
    id: "1312.6114",
    title: "Auto-Encoding Variational Bayes",
    authors: ["Diederik P. Kingma", "Max Welling"],
    institution: "University of Amsterdam",
    abstract: "How can we perform efficient inference and learning in directed probabilistic models, in the presence of continuous latent variables with intractable posterior distributions, and large datasets? We introduce a stochastic variational inference and learning algorithm that scales to large datasets and, under some mild differentiability conditions, even works in the intractable case.",
    tldr: "Introduces the VAE: a latent-variable model trained by maximizing an evidence lower bound, with the reparameterization trick enabling backprop through sampling.",
    tags: ["computer-vision"],
    upvotes: 4820, citations: 47200, comments: 0,
    year: 2013, date: "Dec 20, 2013", venue: "ICLR 2014",
  },
  "1406.2661": {
    id: "1406.2661",
    title: "Generative Adversarial Networks",
    authors: ["Ian J. Goodfellow", "Jean Pouget-Abadie", "Mehdi Mirza", "Bing Xu", "David Warde-Farley", "Sherjil Ozair", "Aaron Courville", "Yoshua Bengio"],
    institution: "Université de Montréal",
    abstract: "We propose a new framework for estimating generative models via an adversarial process, in which we simultaneously train two models: a generative model G that captures the data distribution, and a discriminative model D that estimates the probability that a sample came from the training data rather than G. The training procedure for G is to maximize the probability of D making a mistake.",
    tldr: "Frames generative modeling as a two-player minimax game between a generator and a discriminator.",
    tags: ["computer-vision"],
    upvotes: 7420, citations: 64900, comments: 0,
    year: 2014, date: "Jun 10, 2014", venue: "NeurIPS 2014",
  },
  "2209.14988": {
    id: "2209.14988",
    title: "DreamFusion: Text-to-3D using 2D Diffusion",
    authors: ["Ben Poole", "Ajay Jain", "Jonathan T. Barron", "Ben Mildenhall"],
    institution: "Google Research",
    abstract: "We use a pretrained 2D text-to-image diffusion model to perform text-to-3D synthesis. We introduce a loss based on probability density distillation that enables the use of a 2D diffusion model as a prior for optimization of a parametric image generator.",
    tldr: "Score Distillation Sampling — distills a 2D diffusion prior into an arbitrary differentiable renderer for text-to-3D.",
    tags: ["3d-reconstruction", "diffusion-models"],
    upvotes: 920, citations: 2840, comments: 0,
    year: 2022, date: "Sep 29, 2022", venue: "ICLR 2023",
  },
  "1707.06347": {
    id: "1707.06347",
    title: "Proximal Policy Optimization Algorithms",
    authors: ["John Schulman", "Filip Wolski", "Prafulla Dhariwal", "Alec Radford", "Oleg Klimov"],
    institution: "OpenAI",
    abstract: "We propose a new family of policy gradient methods for reinforcement learning, which alternate between sampling data through interaction with the environment, and optimizing a surrogate objective function using stochastic gradient ascent. Whereas standard policy gradient methods perform one gradient update per data sample, we propose a novel objective function that enables multiple epochs of minibatch updates.",
    tldr: "Clipped surrogate objective enabling multiple epochs over each rollout. The default RL algorithm, including for RLHF.",
    tags: ["reinforcement-learning"],
    upvotes: 3420, citations: 18420, comments: 0,
    year: 2017, date: "Jul 20, 2017", venue: "arXiv 2017",
  },
  "1706.03741": {
    id: "1706.03741",
    title: "Deep Reinforcement Learning from Human Preferences",
    authors: ["Paul Christiano", "Jan Leike", "Tom B. Brown", "Miljan Martic", "Shane Legg", "Dario Amodei"],
    institution: "OpenAI · DeepMind",
    abstract: "For sophisticated reinforcement learning systems to interact usefully with real-world environments, we need to communicate complex goals to these systems. We explore goals defined in terms of (non-expert) human preferences between pairs of trajectory segments. We show that this approach can effectively solve complex RL tasks without access to a reward function.",
    tldr: "Trains a reward model from pairwise human preferences and optimizes a policy against it. Foundation of modern RLHF.",
    tags: ["reinforcement-learning"],
    upvotes: 1820, citations: 4920, comments: 0,
    year: 2017, date: "Jun 12, 2017", venue: "NeurIPS 2017",
  },
  "2305.18290": {
    id: "2305.18290",
    title: "Direct Preference Optimization: Your Language Model is Secretly a Reward Model",
    authors: ["Rafael Rafailov", "Archit Sharma", "Eric Mitchell", "Stefano Ermon", "Christopher D. Manning", "Chelsea Finn"],
    institution: "Stanford University",
    abstract: "While large-scale unsupervised language models learn broad world knowledge and some reasoning skills, achieving precise control of their behavior is difficult due to the unsupervised nature of their training. We introduce Direct Preference Optimization (DPO), a parameterization of the reward model that enables extraction of the corresponding optimal policy in closed form, allowing us to solve the standard RLHF problem with only a simple classification loss.",
    tldr: "Eliminates the separate reward-model and PPO stages of RLHF. Optimizes the policy directly on preference pairs with a simple classification loss.",
    tags: ["language-modeling", "reinforcement-learning"],
    upvotes: 2210, citations: 3420, comments: 0,
    year: 2023, date: "May 29, 2023", venue: "NeurIPS 2023",
  },
  "1207.0580": {
    id: "1207.0580",
    title: "Improving neural networks by preventing co-adaptation of feature detectors",
    authors: ["Geoffrey E. Hinton", "Nitish Srivastava", "Alex Krizhevsky", "Ilya Sutskever", "Ruslan R. Salakhutdinov"],
    institution: "University of Toronto",
    abstract: "When a large feedforward neural network is trained on a small training set, it typically performs poorly on held-out test data. This 'overfitting' is greatly reduced by randomly omitting half of the feature detectors on each training case. This prevents complex co-adaptations in which a feature detector is only helpful in the context of several other specific feature detectors.",
    tldr: "Introduces dropout — randomly omitting feature detectors during training to prevent co-adaptation.",
    tags: ["computer-vision"],
    upvotes: 2820, citations: 9120, comments: 0,
    year: 2012, date: "Jul 3, 2012", venue: "arXiv 2012",
  },
  "2106.09685": {
    id: "2106.09685",
    title: "LoRA: Low-Rank Adaptation of Large Language Models",
    authors: ["Edward J. Hu", "Yelong Shen", "Phillip Wallis", "Zeyuan Allen-Zhu", "Yuanzhi Li", "Shean Wang", "Lu Wang", "Weizhu Chen"],
    institution: "Microsoft Research",
    abstract: "An important paradigm of natural language processing consists of large-scale pre-training on general domain data and adaptation to particular tasks or domains. We propose Low-Rank Adaptation, or LoRA, which freezes the pre-trained model weights and injects trainable rank decomposition matrices into each layer of the Transformer architecture, greatly reducing the number of trainable parameters for downstream tasks.",
    tldr: "Freezes the base model and trains low-rank update matrices instead of full weights. Made parameter-efficient fine-tuning standard practice.",
    tags: ["language-modeling"],
    upvotes: 4120, citations: 12810, comments: 0,
    year: 2021, date: "Jun 17, 2021", venue: "ICLR 2022",
  },
};

function getPaperOrSource(id) {
  return PAPERS.find(p => p.id === id) || SOURCE_PAPERS[id] || STUB_PAPERS[id] || null;
}

// Runtime registry: stubs synthesized from leaderboard rows for papers not in
// PAPERS or SOURCE_PAPERS. Lets every benchmark row open *some* paper view.
const STUB_PAPERS = {};
function registerStubPaper(stub) {
  STUB_PAPERS[stub.id] = stub;
  return stub.id;
}

// Slugify benchmark name → stable id
function benchSlug(name) {
  return name.toLowerCase().replace(/[^\w]+/g, '-').replace(/^-|-$/g, '');
}

// Domain-level explainers, sister tasks, benchmarks for the task detail page.
// Each benchmark also has `leaderboard`: rows of {model, value, paper, paperId?, code, year, date}
const DOMAIN_DETAILS = {
  "language-modeling": {
    parent: "Language",
    explainer: "Language modeling is the task of predicting the next token in a sequence given prior context. It underpins modern generative LLMs and is the dominant pretraining objective for transformer-based systems. Performance is reported as perplexity (lower is better) on held-out text.",
    sisters: [["code-generation", 298], ["agents", 401], ["evaluation", 223]],
    benchmarks: [
      {
        name: "C4 (validation)", metric: "PPL", arrow: "↓", sota: "9.84", sotaModel: "SMoS-13B",
        series: [22.4, 18.2, 15.6, 13.1, 11.8, 10.5, 9.84],
        seriesDates: ["Sep 22","Apr 23","Oct 23","Mar 24","Sep 24","Mar 25","Oct 25"],
        leaderboard: [
          { model: "SMoS-13B",        value: "9.84",  paper: "Shared Mixture-of-States Models",                   paperId: "p13", code: true,  year: 2026, date: "Oct 25" },
          { model: "DenseScale-7B",   value: "10.21", paper: "DenseScale: scaling laws for dense transformers",   paperId: "p07", code: true,  year: 2025, date: "Mar 25" },
          { model: "Mamba-2.8B",      value: "11.78", paper: "Mamba: Linear-Time Sequence Modeling",              paperId: null,  code: true,  year: 2024, date: "Sep 24" },
          { model: "GPT-3 Replication",value:"13.10", paper: "Replicating GPT-3 with open data",                  paperId: null,  code: false, year: 2024, date: "Mar 24" },
          { model: "Chinchilla-70B",  value: "13.95", paper: "Compute-optimal scaling",                            paperId: null,  code: false, year: 2023, date: "Oct 23" },
          { model: "T5-XL",           value: "15.62", paper: "T5: Text-to-Text Transfer Transformer",              paperId: null,  code: true,  year: 2023, date: "Apr 23" },
          { model: "GPT-2 1.5B",      value: "22.40", paper: "Language Models are Unsupervised Multitask Learners",paperId: null, code: true,  year: 2022, date: "Sep 22" },
        ],
      },
      {
        name: "The Pile", metric: "PPL", arrow: "↓", sota: "7.21", sotaModel: "SMoS-13B",
        series: [16.8, 14.1, 12.3, 10.8, 9.4, 8.2, 7.21],
        seriesDates: ["Sep 22","Apr 23","Oct 23","Mar 24","Sep 24","Mar 25","Oct 25"],
        leaderboard: [
          { model: "SMoS-13B",       value: "7.21",  paper: "Shared Mixture-of-States Models",                paperId: "p13", code: true,  year: 2026, date: "Oct 25" },
          { model: "DenseScale-7B",  value: "8.20",  paper: "DenseScale: scaling laws for dense transformers",paperId: "p07", code: true,  year: 2025, date: "Mar 25" },
          { model: "GPT-NeoX-20B",   value: "9.41",  paper: "GPT-NeoX: training a 20B autoregressive LM",     paperId: null,  code: true,  year: 2024, date: "Sep 24" },
          { model: "Pythia-12B",     value: "10.78", paper: "Pythia: a suite for analyzing large LMs",         paperId: null,  code: true,  year: 2024, date: "Mar 24" },
          { model: "OPT-13B",        value: "12.30", paper: "OPT: Open Pre-trained Transformer LMs",           paperId: null,  code: true,  year: 2023, date: "Oct 23" },
        ],
      },
    ],
  },
  "robotics": {
    parent: "Embodied",
    explainer: "Robotics research in AI focuses on learned controllers that map sensor observations to motor actions, often through imitation learning, reinforcement learning, or visuomotor policies. Evaluation is typically per-task success rate on fixed manipulation or locomotion benchmarks.",
    sisters: [["reinforcement-learning", 612], ["3d-reconstruction", 198]],
    benchmarks: [
      {
        name: "RoboBench-22", metric: "Success", arrow: "↑", sota: "78.3%", sotaModel: "DiffPolicy",
        series: [42, 51, 58, 64, 69, 73.5, 78.3],
        seriesDates: ["Sep 22","Apr 23","Oct 23","Mar 24","Sep 24","Mar 25","Oct 25"],
        leaderboard: [
          { model: "DiffPolicy + ACT", value: "78.3%", paper: "Diffusion Policy with action chunking",      paperId: "p10", code: true,  year: 2026, date: "Oct 25" },
          { model: "OpenVLA-7B",       value: "73.5%", paper: "OpenVLA: open vision-language-action model", paperId: null,  code: true,  year: 2025, date: "Mar 25" },
          { model: "RT-2-X",           value: "69.0%", paper: "RT-2-X: cross-embodiment training",          paperId: null,  code: false, year: 2024, date: "Sep 24" },
          { model: "Octo-Base",        value: "64.0%", paper: "Octo: an open generalist robot policy",      paperId: null,  code: true,  year: 2024, date: "Mar 24" },
          { model: "Diffusion Policy", value: "58.0%", paper: "Diffusion Policy: visuomotor policy via diffusion", paperId: null, code: true, year: 2023, date: "Oct 23" },
        ],
      },
      {
        name: "Franka 9-task", metric: "Success", arrow: "↑", sota: "73%", sotaModel: "WMSparse",
        series: [38, 45, 52, 58, 64, 69, 73],
        seriesDates: ["Sep 22","Apr 23","Oct 23","Mar 24","Sep 24","Mar 25","Oct 25"],
        leaderboard: [
          { model: "WMSparse",     value: "73.0%", paper: "Sparse world models for manipulation",  paperId: "p04", code: true,  year: 2026, date: "Oct 25" },
          { model: "ACT-Franka",   value: "69.0%", paper: "Action Chunking Transformer (Franka)",  paperId: null,  code: true,  year: 2025, date: "Mar 25" },
          { model: "RoboCat-1.2B", value: "64.0%", paper: "RoboCat: a self-improving generalist agent", paperId: null, code: false, year: 2024, date: "Sep 24" },
        ],
      },
    ],
  },
  "object-detection": {
    parent: "Computer Vision",
    explainer: "Object detection is the task of identifying and localizing objects in an image with axis-aligned bounding boxes and class labels. It sits between image classification (what is in the image) and instance segmentation (what is in the image, pixel-precise).",
    sisters: [["image-classification", 891], ["3d-reconstruction", 198], ["medical-imaging", 134]],
    benchmarks: [
      {
        name: "COCO val 2017", metric: "mAP", arrow: "↑", sota: "62.1", sotaModel: "SAM 3 (DET)",
        series: [39.4, 46.8, 51.2, 54.5, 57.0, 59.1, 60.8, 62.1],
        seriesDates: ["Sep 18","Aug 20","Apr 22","Apr 23","Oct 23","Mar 24","Jan 25","Feb 26"],
        leaderboard: [
          { model: "SAM 3 (DET)",         value: "62.1", paper: "Segment Anything 3, detection head",       paperId: null,  code: true,  year: 2026, date: "Feb 26" },
          { model: "DINOv3 + Plain-DETR", value: "61.4", paper: "DINOv3",                                   paperId: null,  code: true,  year: 2025, date: "Jan 25" },
          { model: "Co-DETR",             value: "59.1", paper: "DETRs with Collaborative Hybrid Assignments", paperId: null, code: true,  year: 2024, date: "Mar 24" },
          { model: "DINO-DETR (Swin-L)",  value: "57.0", paper: "DINO: DETR with Improved DeNoising",       paperId: null,  code: true,  year: 2023, date: "Oct 23" },
          { model: "Group-DETR v2",       value: "54.5", paper: "Group DETR v2: Strong Object Detector",    paperId: null,  code: false, year: 2023, date: "Apr 23" },
          { model: "DyHead",              value: "51.2", paper: "Dynamic Head: Unifying Object Detection Heads", paperId: null, code: true,  year: 2022, date: "Apr 22" },
          { model: "Cascade R-CNN",       value: "46.8", paper: "Cascade R-CNN",                            paperId: null,  code: true,  year: 2020, date: "Aug 20" },
          { model: "Faster R-CNN",        value: "39.4", paper: "Faster R-CNN",                             paperId: null,  code: true,  year: 2018, date: "Sep 18" },
        ],
      },
      {
        name: "LVIS v1.0", metric: "AP", arrow: "↑", sota: "47.4", sotaModel: "DETR-XL",
        series: [28, 32, 36, 40, 43, 45.5, 47.4],
        seriesDates: ["Sep 22","Apr 23","Oct 23","Mar 24","Sep 24","Mar 25","Oct 25"],
        leaderboard: [
          { model: "DETR-XL",       value: "47.4", paper: "Scaling DETR to extreme sizes", paperId: null, code: true,  year: 2026, date: "Oct 25" },
          { model: "Co-DETR (long)",value: "45.5", paper: "Co-DETR long-tail distillation",paperId: null, code: true,  year: 2025, date: "Mar 25" },
          { model: "ViTDet-H",      value: "43.0", paper: "ViTDet: plain ViT backbone for detection", paperId: null, code: true, year: 2024, date: "Sep 24" },
        ],
      },
    ],
  },
  "diffusion-models": {
    parent: "Multimodal & Generative",
    explainer: "Diffusion models generate samples by iteratively denoising a noise prior, learning to reverse a fixed noising process. They have become the dominant approach for image, video, audio, and 3D generation due to stable training and high sample quality.",
    sisters: [["video-generation", 167], ["3d-reconstruction", 198], ["multimodal", 478]],
    benchmarks: [
      {
        name: "ImageNet 256×256", metric: "FID", arrow: "↓", sota: "1.97", sotaModel: "DiT-XL/2",
        series: [12.4, 8.1, 5.6, 4.2, 3.1, 2.4, 1.97],
        seriesDates: ["Sep 22","Apr 23","Oct 23","Mar 24","Sep 24","Mar 25","Oct 25"],
        leaderboard: [
          { model: "DiT-XL/2 + REPA",  value: "1.97", paper: "REPA: representation-aligned diffusion", paperId: "p11", code: true,  year: 2026, date: "Oct 25" },
          { model: "MDT-G/2",          value: "2.40", paper: "Masked Diffusion Transformer",          paperId: null,  code: true,  year: 2025, date: "Mar 25" },
          { model: "DiT-XL/2",         value: "3.10", paper: "Scalable Diffusion Models with Transformers", paperId: null, code: true, year: 2024, date: "Sep 24" },
          { model: "ADM-G",            value: "4.20", paper: "Diffusion Models Beat GANs on Image Synthesis", paperId: null, code: true, year: 2024, date: "Mar 24" },
          { model: "LDM-8",            value: "5.60", paper: "Latent Diffusion Models",                paperId: null,  code: true,  year: 2023, date: "Oct 23" },
        ],
      },
      {
        name: "GEOM-Drugs", metric: "AMR-MIN", arrow: "↓", sota: "0.247", sotaModel: "EquiDiff",
        series: [0.84, 0.62, 0.48, 0.38, 0.31, 0.27, 0.247],
        seriesDates: ["Sep 22","Apr 23","Oct 23","Mar 24","Sep 24","Mar 25","Oct 25"],
        leaderboard: [
          { model: "EquiDiff-3D",  value: "0.247", paper: "Equivariant diffusion for 3D molecules", paperId: "p12", code: true, year: 2026, date: "Oct 25" },
          { model: "Torsional Diffusion", value: "0.270", paper: "Torsional Diffusion for Molecular Conformer Generation", paperId: null, code: true, year: 2025, date: "Mar 25" },
          { model: "GeoDiff",      value: "0.310", paper: "GeoDiff: a geometric diffusion model",   paperId: null,  code: true, year: 2024, date: "Sep 24" },
        ],
      },
    ],
  },
  "video-generation": {
    parent: "Multimodal & Generative",
    explainer: "Video generation produces temporally coherent video from text, image, or trajectory conditioning. Long-horizon consistency and motion realism remain the central challenges; FVD on UCF-101 is the standard metric.",
    sisters: [["diffusion-models", 543], ["multimodal", 478]],
    benchmarks: [
      {
        name: "UCF-101", metric: "FVD", arrow: "↓", sota: "212.4", sotaModel: "FlowVideo",
        series: [521, 432, 372, 318, 281, 244, 212.4],
        seriesDates: ["Sep 22","Apr 23","Oct 23","Mar 24","Sep 24","Mar 25","Oct 25"],
        leaderboard: [
          { model: "FlowVideo-L",   value: "212.4", paper: "FlowVideo: rectified flow for video",       paperId: null, code: true,  year: 2026, date: "Oct 25" },
          { model: "VideoLDM-XL",   value: "244.0", paper: "Latent video diffusion at scale",            paperId: null, code: true,  year: 2025, date: "Mar 25" },
          { model: "Make-A-Video2", value: "281.0", paper: "Make-A-Video 2",                              paperId: null, code: false, year: 2024, date: "Sep 24" },
        ],
      },
    ],
  },
  "image-classification": {
    parent: "Computer Vision",
    explainer: "Image classification assigns one or more class labels to an entire image. It is the canonical computer-vision benchmark task; ImageNet top-1 accuracy on the ILSVRC-2012 validation set has been the dominant yardstick for backbone architectures for over a decade.",
    sisters: [["object-detection", 267], ["3d-reconstruction", 198], ["medical-imaging", 134]],
    benchmarks: [
      {
        name: "ImageNet-1k", metric: "Top-1 Acc", arrow: "↑", sota: "92.4%", sotaModel: "BEiT-3 huge",
        series: [76.5, 82.1, 86.4, 88.7, 90.1, 91.3, 92.4],
        seriesDates: ["Sep 19","Sep 20","Mar 22","Sep 23","Mar 24","Mar 25","Oct 25"],
        leaderboard: [
          { model: "BEiT-3 huge (RevCol)", value: "92.4%", paper: "BEiT-3: Image as a Foreign Language",  paperId: null, code: true,  year: 2026, date: "Oct 25" },
          { model: "InternImage-H",        value: "91.3%", paper: "InternImage: Exploring Large-Scale Vision Foundation Models", paperId: null, code: true,  year: 2025, date: "Mar 25" },
          { model: "ViT-22B",              value: "90.1%", paper: "Scaling Vision Transformers to 22 Billion Parameters",         paperId: null, code: false, year: 2024, date: "Mar 24" },
          { model: "CoCa-2.1B",            value: "88.7%", paper: "CoCa: Contrastive Captioners are Image-Text Foundation Models",paperId: null, code: true,  year: 2023, date: "Sep 23" },
          { model: "ConvNeXt-XL",          value: "86.4%", paper: "A ConvNet for the 2020s",                                       paperId: null, code: true,  year: 2022, date: "Mar 22" },
          { model: "EfficientNet-L2",      value: "82.1%", paper: "Self-training with Noisy Student improves ImageNet",            paperId: null, code: true,  year: 2020, date: "Sep 20" },
          { model: "ResNeXt-101",          value: "76.5%", paper: "Aggregated Residual Transformations",                           paperId: null, code: true,  year: 2019, date: "Sep 19" },
        ],
      },
      {
        name: "CIFAR-10", metric: "Acc", arrow: "↑", sota: "99.7%", sotaModel: "ViT-H/14 (JFT-3B)",
        series: [96.5, 97.3, 98.5, 99.0, 99.4, 99.7],
        seriesDates: ["Sep 20","Mar 22","Sep 23","Mar 24","Mar 25","Oct 25"],
        leaderboard: [
          { model: "ViT-H/14 (JFT-3B)",   value: "99.7%", paper: "Scaling Vision Transformers", paperId: null, code: true,  year: 2026, date: "Oct 25" },
          { model: "EfficientNet-V2-XL", value: "99.4%", paper: "EfficientNetV2: Smaller Models and Faster Training", paperId: null, code: true,  year: 2025, date: "Mar 25" },
          { model: "BiT-L",              value: "99.0%", paper: "Big Transfer (BiT)", paperId: null, code: true,  year: 2024, date: "Mar 24" },
          { model: "Wide ResNet 28-10",  value: "97.3%", paper: "Wide Residual Networks", paperId: null, code: true,  year: 2022, date: "Mar 22" },
        ],
      },
    ],
  },
  "code-generation": {
    parent: "Language",
    explainer: "Code generation is the task of synthesizing executable source code from natural-language specifications, partial code, or test cases. Pass-rate on hidden unit tests (pass@1) is the dominant evaluation metric.",
    sisters: [["language-modeling", 1284], ["agents", 401], ["evaluation", 223]],
    benchmarks: [
      {
        name: "HumanEval", metric: "pass@1", arrow: "↑", sota: "92.1%", sotaModel: "Claude 4.5 Code",
        series: [33.5, 48.1, 65.8, 78.2, 85.4, 88.9, 92.1],
        seriesDates: ["Jul 21","Mar 23","Mar 24","Sep 24","Mar 25","Sep 25","Mar 26"],
        leaderboard: [
          { model: "Claude 4.5 Code",   value: "92.1%", paper: "Claude 4.5 model card",            paperId: null, code: false, year: 2026, date: "Mar 26" },
          { model: "GPT-5",             value: "88.9%", paper: "GPT-5 system card",               paperId: null, code: false, year: 2025, date: "Sep 25" },
          { model: "DeepSeek-Coder-V3", value: "85.4%", paper: "DeepSeek-Coder-V3",                paperId: null, code: true,  year: 2025, date: "Mar 25" },
          { model: "Code Llama 70B",    value: "78.2%", paper: "Code Llama: Open Foundation Models for Code", paperId: null, code: true,  year: 2024, date: "Sep 24" },
          { model: "WizardCoder",       value: "65.8%", paper: "WizardCoder: Empowering Code LLMs", paperId: null, code: true,  year: 2024, date: "Mar 24" },
        ],
      },
      {
        name: "MBPP", metric: "pass@1", arrow: "↑", sota: "84.7%", sotaModel: "Claude 4.5 Code",
        series: [44.1, 58.3, 71.5, 78.4, 82.0, 84.7],
        seriesDates: ["Mar 23","Mar 24","Sep 24","Mar 25","Sep 25","Mar 26"],
        leaderboard: [
          { model: "Claude 4.5 Code", value: "84.7%", paper: "Claude 4.5 model card", paperId: null, code: false, year: 2026, date: "Mar 26" },
          { model: "GPT-5",           value: "82.0%", paper: "GPT-5 system card",     paperId: null, code: false, year: 2025, date: "Sep 25" },
        ],
      },
    ],
  },
  "reinforcement-learning": {
    parent: "Embodied",
    explainer: "Reinforcement learning trains agents to maximize cumulative reward through environment interaction. Atari, MuJoCo, and procgen suites have served as canonical benchmarks; current frontier work centers on offline RL, world models, and RL from human feedback.",
    sisters: [["robotics", 287], ["agents", 401]],
    benchmarks: [
      {
        name: "Atari 100k", metric: "Median HNS", arrow: "↑", sota: "212%", sotaModel: "EfficientZero V2",
        series: [40, 78, 124, 168, 195, 212],
        seriesDates: ["Sep 22","Mar 23","Sep 23","Mar 24","Mar 25","Oct 25"],
        leaderboard: [
          { model: "EfficientZero V2", value: "212%", paper: "EfficientZero V2", paperId: null, code: true,  year: 2026, date: "Oct 25" },
          { model: "DreamerV3",        value: "168%", paper: "Mastering Diverse Domains through World Models", paperId: null, code: true, year: 2024, date: "Mar 24" },
          { model: "MuZero",           value: "78%",  paper: "MuZero: Mastering Atari, Go, Chess, Shogi", paperId: null, code: true, year: 2023, date: "Mar 23" },
        ],
      },
    ],
  },
  "agents": {
    parent: "Language",
    explainer: "Autonomous agents combine LLM reasoning with tool use, memory, and action loops to complete multi-step tasks. Evaluation typically measures end-to-end success on web, software-engineering, or simulated-OS environments.",
    sisters: [["language-modeling", 1284], ["code-generation", 298], ["evaluation", 223]],
    benchmarks: [
      {
        name: "SWE-bench Verified", metric: "% resolved", arrow: "↑", sota: "67.4%", sotaModel: "Claude 4.5 Sonnet",
        series: [4.8, 12.5, 24.6, 43.2, 55.0, 67.4],
        seriesDates: ["Mar 24","Sep 24","Dec 24","Mar 25","Sep 25","Mar 26"],
        leaderboard: [
          { model: "Claude 4.5 Sonnet + agent", value: "67.4%", paper: "Claude 4.5 model card", paperId: null, code: false, year: 2026, date: "Mar 26" },
          { model: "GPT-5 + agent",             value: "55.0%", paper: "GPT-5 system card",      paperId: null, code: false, year: 2025, date: "Sep 25" },
          { model: "SWE-Agent",                 value: "12.5%", paper: "SWE-Agent: Agent-Computer Interfaces", paperId: null, code: true, year: 2024, date: "Sep 24" },
        ],
      },
      {
        name: "WebArena", metric: "Success", arrow: "↑", sota: "48.1%", sotaModel: "Browser-Use Pro",
        series: [14.4, 23.5, 35.8, 42.0, 48.1],
        seriesDates: ["Sep 23","Mar 24","Sep 24","Mar 25","Oct 25"],
        leaderboard: [
          { model: "Browser-Use Pro", value: "48.1%", paper: "Browser-Use: a generalist web agent", paperId: null, code: true, year: 2026, date: "Oct 25" },
          { model: "WebGPT-4o",       value: "42.0%", paper: "WebGPT-4o", paperId: null, code: false, year: 2025, date: "Mar 25" },
        ],
      },
    ],
  },
  "multimodal": {
    parent: "Multimodal & Generative",
    explainer: "Multimodal models jointly reason over multiple input modalities — typically vision and language — supporting tasks from VQA to image captioning to chart understanding. Evaluation increasingly favors broad benchmark suites (MMMU, MMBench) over single-task scores.",
    sisters: [["language-modeling", 1284], ["diffusion-models", 543], ["video-generation", 167]],
    benchmarks: [
      {
        name: "MMMU", metric: "Acc", arrow: "↑", sota: "78.4%", sotaModel: "GPT-5",
        series: [34.9, 47.0, 56.8, 62.4, 70.5, 78.4],
        seriesDates: ["Mar 24","Sep 24","Dec 24","Mar 25","Sep 25","Mar 26"],
        leaderboard: [
          { model: "GPT-5",             value: "78.4%", paper: "GPT-5 system card",  paperId: null, code: false, year: 2026, date: "Mar 26" },
          { model: "Claude 4.5 Sonnet", value: "70.5%", paper: "Claude 4.5 model card", paperId: null, code: false, year: 2025, date: "Sep 25" },
          { model: "Gemini 2 Ultra",    value: "62.4%", paper: "Gemini 2 technical report", paperId: null, code: false, year: 2025, date: "Mar 25" },
          { model: "GPT-4V",            value: "56.8%", paper: "GPT-4V system card", paperId: null, code: false, year: 2024, date: "Dec 24" },
          { model: "LLaVA-1.6",         value: "47.0%", paper: "LLaVA-1.6: improved visual reasoning", paperId: null, code: true,  year: 2024, date: "Sep 24" },
        ],
      },
      {
        name: "MMBench", metric: "Avg", arrow: "↑", sota: "85.2", sotaModel: "Claude 4.5 Sonnet",
        series: [55.8, 68.4, 74.1, 79.5, 85.2],
        seriesDates: ["Sep 23","Mar 24","Sep 24","Mar 25","Oct 25"],
        leaderboard: [
          { model: "Claude 4.5 Sonnet", value: "85.2", paper: "Claude 4.5 model card", paperId: null, code: false, year: 2026, date: "Oct 25" },
          { model: "Qwen-VL-Plus",      value: "79.5", paper: "Qwen-VL: Versatile Vision-Language Models", paperId: null, code: true,  year: 2025, date: "Mar 25" },
        ],
      },
    ],
  },
  "alignment": {
    parent: "Safety & Alignment",
    explainer: "Alignment research aims to make models behave consistently with human intent, values, and instructions across deployment conditions. Methods span RLHF, DPO, constitutional AI, and reward modeling. Evaluation is fragmented; AlpacaEval and Arena win-rate are common proxies.",
    sisters: [["interpretability", 234], ["evaluation", 223]],
    benchmarks: [
      {
        name: "AlpacaEval 2 LC", metric: "Win rate", arrow: "↑", sota: "65.4%", sotaModel: "Claude 4.5 Sonnet",
        series: [13.6, 23.4, 38.1, 51.0, 60.5, 65.4],
        seriesDates: ["Mar 24","Sep 24","Dec 24","Mar 25","Sep 25","Mar 26"],
        leaderboard: [
          { model: "Claude 4.5 Sonnet", value: "65.4%", paper: "Claude 4.5 model card", paperId: null, code: false, year: 2026, date: "Mar 26" },
          { model: "GPT-5",             value: "60.5%", paper: "GPT-5 system card",     paperId: null, code: false, year: 2025, date: "Sep 25" },
          { model: "Llama-3.1-405B IT", value: "51.0%", paper: "The Llama 3 Herd of Models", paperId: null, code: true,  year: 2025, date: "Mar 25" },
        ],
      },
    ],
  },
};

// Build a flat lookup keyed by `<domainId>::<benchSlug>`
const BENCHMARKS = {};
Object.entries(DOMAIN_DETAILS).forEach(([domainId, d]) => {
  (d.benchmarks || []).forEach(b => {
    const slug = benchSlug(b.name);
    BENCHMARKS[`${domainId}::${slug}`] = { ...b, slug, domainId };
    b.slug = slug; // mutate in place so domain page can link
  });
});

function getDomainDetail(id) { return DOMAIN_DETAILS[id]; }
function getBenchmark(domainId, slug) { return BENCHMARKS[`${domainId}::${slug}`]; }

function resolveLeaderboardPaper(row, bench, tagId) {
  if (row.paperId) return row.paperId;
  const slug = "stub-" + (row.paper || row.model).toLowerCase().replace(/[^\w]+/g, '-').replace(/^-|-$/g, '').slice(0, 60);
  if (STUB_PAPERS[slug]) return slug;
  const stub = {
    id: slug,
    title: row.paper || row.model,
    authors: ["Authors not on record"],
    institution: "—",
    abstract: `${row.paper || row.model} reports ${row.value} on the ${bench.name} benchmark (${bench.metric}). This is a historical or external result tracked by the leaderboard; the full paper record is not in the local database. Click through to arXiv or the project page for details.`,
    tldr: `Reports ${row.value} ${bench.metric} on ${bench.name} (${row.year}).`,
    tags: tagId ? [tagId] : [],
    upvotes: 0,
    citations: 0,
    date: row.date || `${row.year}`,
    year: row.year,
    submitter: "leaderboard",
    github: row.code ? 1 : 0,
    pdfPages: 12,
    isStub: true,
  };
  registerStubPaper(stub);
  return slug;
}

export {
  DOMAINS,
  PAPERS,
  METHODS,
  METHOD_CATEGORIES,
  PAPER_METHODS,
  PAPER_RESULTS,
  SOURCE_PAPERS,
  STUB_PAPERS,
  DOMAIN_DETAILS,
  BENCHMARKS,
  getDomain,
  getMethod,
  getMethodCategory,
  getPapersByTag,
  getPapersByMethod,
  getDomainDetail,
  getBenchmark,
  benchSlug,
  registerStubPaper,
  getPaperOrSource,
  resolveLeaderboardPaper,
};
