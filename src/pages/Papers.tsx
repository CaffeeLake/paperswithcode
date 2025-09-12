import Header from "@/components/Header";
import FilterBar from "@/components/FilterBar";
import PaperCard from "@/components/PaperCard";

// Mock data for demonstration
const mockPapers = [
  {
    id: "1",
    title: "VLA-Adapter: An Effective Paradigm for Tiny-Scale Vision-Language-Action Model",
    abstract: "We introduce VLA-Adapter, a novel approach for scaling vision-language-action models to tiny-scale architectures while maintaining performance.",
    authors: [
      { name: "Yihan Wang", color: "#3B82F6" },
      { name: "Pengjing Deng", color: "#8B5CF6" },
      { name: "Lingxiao Li", color: "#EF4444" },
      { name: "Can Cui", color: "#10B981" },
      { name: "Jiali Chen", color: "#F59E0B" },
      { name: "Yile Gu", color: "#EC4899" },
    ],
    submittedBy: "huangziteng",
    date: "Sep 11",
    upvotes: 104,
    comments: 1,
    category: "Computer Vision",
    isUpvoted: false,
  },
  {
    id: "2",
    title: "HuMo: Human-Centric Video Generation via Collaborative Multi-Modal Conditioning",
    abstract: "A novel framework for generating human-centric videos through collaborative multi-modal conditioning mechanisms.",
    authors: [
      { name: "Zhenyu Lu", color: "#3B82F6" },
      { name: "Bingbing Ni", color: "#8B5CF6" },
      { name: "Cheng Deng", color: "#EF4444" },
      { name: "Qixiang Chen", color: "#10B981" },
    ],
    submittedBy: "TianxiangMa",
    date: "Sep 11",
    upvotes: 85,
    comments: 1,
    category: "Computer Vision",
    isUpvoted: true,
  },
  {
    id: "3",
    title: "SimpleVLA-RL: Scaling VLA Training via Reinforcement Learning",
    abstract: "We present SimpleVLA-RL, a method for scaling vision-language-action model training using reinforcement learning techniques.",
    authors: [
      { name: "Haohzhi Li", color: "#3B82F6" },
      { name: "Yunbo Chen", color: "#8B5CF6" },
      { name: "Rutu Han", color: "#EF4444" },
      { name: "Yuhua Zhang", color: "#10B981" },
      { name: "Shaobin Zhan", color: "#F59E0B" },
    ],
    submittedBy: "Haozhzh72",
    date: "Sep 11",
    upvotes: 52,
    comments: 1,
    category: "Reinforcement Learning",
    isUpvoted: false,
  },
  {
    id: "4",
    title: "EchoX: Towards Mitigating Acoustic-Semantic Gap via Echo Training",
    abstract: "EchoX addresses the acoustic-semantic gap in speech processing through innovative echo training methodologies.",
    authors: [
      { name: "Wei Zhang", color: "#3B82F6" },
      { name: "Li Chen", color: "#8B5CF6" },
      { name: "Ming Liu", color: "#EF4444" },
    ],
    submittedBy: "Yoohao",
    date: "Sep 10",
    upvotes: 38,
    comments: 0,
    category: "Speech Processing",
    isUpvoted: false,
  },
  {
    id: "5",
    title: "Kling-Avatar: Grounding Multimodal Instructions for Cascaded Long-Duration Avatar Animation Synthesis",
    abstract: "A comprehensive framework for long-duration avatar animation synthesis using multimodal instruction grounding.",
    authors: [
      { name: "Ling Cao", color: "#3B82F6" },
      { name: "Xiangning Lou", color: "#8B5CF6" },
      { name: "Yingshan Shan", color: "#EF4444" },
      { name: "Hai Liu", color: "#10B981" },
      { name: "Matthew Li", color: "#F59E0B" },
    ],
    submittedBy: "taesiri",
    date: "Sep 10",
    upvotes: 67,
    comments: 2,
    category: "Computer Graphics",
    isUpvoted: false,
  },
  {
    id: "6",
    title: "Harnessing Uncertainty: Entropy-Modulated Policy Gradients for Long-Horizon LLM Agents",
    abstract: "Novel approach to long-horizon planning in language model agents using entropy-modulated policy gradients.",
    authors: [
      { name: "Jiawei Wang", color: "#3B82F6" },
      { name: "Jacqui Liu", color: "#8B5CF6" },
      { name: "Yugen Fu", color: "#EF4444" },
      { name: "Xinye Li", color: "#10B981" },
      { name: "Xintao Wang", color: "#F59E0B" },
      { name: "Yan Liu", color: "#EC4899" },
      { name: "Yu Xian", color: "#06B6D4" },
      { name: "Liu Zhang", color: "#84CC16" },
    ],
    submittedBy: "Jarvis1111",
    date: "Sep 10",
    upvotes: 29,
    comments: 0,
    category: "Natural Language Processing",
    isUpvoted: false,
  },
];

const Papers = () => {
  return (
    <div className="min-h-screen bg-background">
      <Header />
      
      <div className="container mx-auto px-4 py-8">
        <FilterBar />
        
        {/* Papers Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {mockPapers.map((paper) => (
            <PaperCard key={paper.id} {...paper} />
          ))}
        </div>
        
        {/* Load More */}
        <div className="flex justify-center mt-12">
          <button className="px-6 py-2 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors">
            Load more papers...
          </button>
        </div>
      </div>
    </div>
  );
};

export default Papers;