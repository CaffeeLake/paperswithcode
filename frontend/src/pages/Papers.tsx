import Header from "@/components/Header";
import { Search, Sparkles, Github } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import PaperCard from "@/components/PaperCard";
import TrendingPaperCard from "@/components/TrendingPaperCard";

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
    date: "Sep 11, 2025",
    upvotes: 52,
    comments: 1,
    category: "Computer Vision",
    isUpvoted: false,
    githubStars: 486,
    tags: ["vision-language-action models", "model compression", "multi-modal learning"],
  },
  {
    id: "2",
    title: "HuMo: Human-Centric Video Generation via Collaborative Multi-Modal Conditioning",
    abstract: "Human-Centric Video Generation (HCVG) methods seek to synthesize human videos from multimodal inputs, including text, image, and audio. Existing methods struggle to effectively coordinate these heterogeneous modalities due to two challenges: the scarcity of training data with paired triplet conditions and the difficulty of collaborating the sub-tasks of subject...",
    authors: [
      { name: "Zhenyu Lu", color: "#3B82F6" },
      { name: "Bingbing Ni", color: "#8B5CF6" },
      { name: "Cheng Deng", color: "#EF4444" },
      { name: "Qixiang Chen", color: "#10B981" },
    ],
    submittedBy: "TianxiangMa",
    date: "Sep 10, 2025",
    upvotes: 85,
    comments: 1,
    category: "Computer Vision",
    isUpvoted: true,
    githubStars: 159,
    tags: ["video generation", "multi-modal conditioning", "human-centric"],
  },
  {
    id: "3",
    title: "AgentScope 1.0: A Developer-Centric Framework for Building Agentic Applications",
    abstract: "Driven by rapid advancements of Large Language Models (LLMs), agents are empowered to combine intrinsic knowledge with dynamic tool use, greatly enhancing their capacity to address real-world tasks. In line with such an evolution, AgentScope introduces major improvements in a new version (1.0), towards comprehensively supporting flexible and efficient...",
    authors: [
      { name: "Haohzhi Li", color: "#3B82F6" },
      { name: "Yunbo Chen", color: "#8B5CF6" },
      { name: "Rutu Han", color: "#EF4444" },
      { name: "Yuhua Zhang", color: "#10B981" },
      { name: "Shaobin Zhan", color: "#F59E0B" },
    ],
    submittedBy: "taesiri",
    date: "Aug 22, 2025",
    upvotes: 36,
    comments: 1,
    category: "Reinforcement Learning",
    isUpvoted: false,
    githubStars: 11100,
    tags: ["reasoning", "multi-agent systems", "large language models"],
  },
  {
    id: "4",
    title: "LlamaFactory: Unified Efficient Fine-tuning of 100+ Language Models",
    abstract: "Efficient fine-tuning is vital for adapting large language models (LLMs) to downstream tasks. It requires non-trivial efforts to implement these methods on different models. We present LlamaFactory, a unified framework that integrates a suite of cutting-edge efficient training methods. It allows users to flexibly customize the fine-tuning of 100+ LLMs without...",
    authors: [
      { name: "Wei Zhang", color: "#3B82F6" },
      { name: "Li Chen", color: "#8B5CF6" },
      { name: "Ming Liu", color: "#EF4444" },
    ],
    submittedBy: "ashlaila",
    date: "Mar 20, 2024",
    upvotes: 137,
    comments: 0,
    category: "Speech Processing",
    isUpvoted: false,
    githubStars: 56000,
    tags: ["fine-tuning", "large language models", "efficient training"],
  },
];

const Papers = () => {
  return (
    <div className="min-h-screen bg-background">
      <Header />
      
      <div className="container mx-auto px-4 py-8 max-w-7xl">
        {/* Header Section */}
        <div className="mb-8">
          <div className="flex items-center justify-between mb-6">
            <div>
              <h1 className="text-4xl font-bold mb-2">Trending Papers</h1>
              <div className="flex items-center text-muted-foreground">
                <span className="mr-2">by</span>
                <div className="flex items-center space-x-1 mr-2">
                  <Avatar className="w-6 h-6">
                    <AvatarFallback className="text-xs bg-blue-500 text-white">AK</AvatarFallback>
                  </Avatar>
                  <Avatar className="w-6 h-6">
                    <AvatarFallback className="text-xs bg-green-500 text-white">HF</AvatarFallback>
                  </Avatar>
                </div>
                <span>AK and the research community</span>
              </div>
            </div>
            <Button variant="outline" size="sm" className="hidden md:flex">
              + Submit a paper
            </Button>
          </div>

          {/* Search Bar */}
          <div className="flex items-center gap-4 mb-6">
            <div className="relative flex-1 max-w-md">
              <Sparkles className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground w-4 h-4" />
              <Input
                className="pl-10 bg-muted/50 border focus-visible:ring-1 focus-visible:ring-primary"
                placeholder="Search any paper with AI"
              />
            </div>
          </div>

          {/* Time Filter Tabs */}
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" className="bg-muted">Daily</Button>
            <Button variant="outline" size="sm">Weekly</Button>
            <Button variant="outline" size="sm">Monthly</Button>
            <div className="ml-auto">
              <Button variant="default" size="sm" className="bg-orange-500 hover:bg-orange-600">
                Trending Papers
              </Button>
            </div>
          </div>
        </div>

        {/* Papers List */}
        <div className="space-y-6">
          {mockPapers.map((paper) => (
            <TrendingPaperCard key={paper.id} {...paper} />
          ))}
        </div>
      </div>
    </div>
  );
};

export default Papers;