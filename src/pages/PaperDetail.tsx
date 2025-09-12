import { ArrowUp, MessageCircle, Calendar, ExternalLink, BookOpen, Database, Zap, Bookmark, Trophy, Edit } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import Header from "@/components/Header";

const PaperDetail = () => {
  const paper = {
    id: "arxiv:2509.08721",
    title: "Sharing is Caring: Efficient LM Post-Training with Collective RL Experience Sharing",
    abstract: `Swarm sAmpling Policy Optimization (SAPO) is a decentralized and asynchronous RL algorithm that enhances post-training language models without supervised fine-tuning, achieving significant reward gains and scalability across diverse hardware.

Post-training language models (LMs) with reinforcement learning (RL) can enhance their complex reasoning capabilities without supervised fine-tuning, as demonstrated by DeepSeek-R1-Zero. However, effectively utilizing RL for LMs requires significant parallelization to scale-up inference, which introduces non-trivial technical challenges (e.g. latency, memory, and reliability) alongside ever-growing financial costs. We present Swarm sAmpling Policy Optimization (SAPO), a fully decentralized and asynchronous RL post-training algorithm. SAPO is designed for decentralized networks of heterogeneous compute nodes, where each node manages its own policy model(s) while "sharing" rollouts with others in the network; no explicit assumptions about latency, model homogeneity, or hardware are required and nodes can operate in silo if desired. As a result, the algorithm avoids common bottlenecks in scaling RL post-training while also allowing (and even encouraging) new possibilities. By sampling rollouts "shared" across the network, it enables "Aha moments" to propagate, thereby bootstrapping the learning process. In this paper we show SAPO achieved cumulative reward gains of up to 94% in controlled experiments. We also share insights from tests on a network with thousands of nodes contributed by Gensyn community members running the algorithm on diverse hardware and models during an open-source demo.`,
    authors: [
      { name: "Jeffrey Amico", color: "#3B82F6" },
      { name: "Gabriel Passamani Andrade", color: "#8B5CF6" },
      { name: "John Donaghy", color: "#EF4444" },
      { name: "Ben Fielding", color: "#10B981" },
      { name: "Tristin Forbius", color: "#F59E0B" },
      { name: "Harry Grieve", color: "#EC4899" },
      { name: "Semih Kara", color: "#06B6D4" },
      { name: "Jari Kolehmainen", color: "#84CC16" },
      { name: "Yihua Lou", color: "#F97316" },
      { name: "Christopher Nies", color: "#8B5CF6" },
      { name: "Edward Phillip Flores Nuño", color: "#EF4444" },
      { name: "Diogo Ortega", color: "#10B981" },
      { name: "Shikhar Rastogi", color: "#F59E0B" },
      { name: "Austin Virts", color: "#EC4899" },
      { name: "Matthew J. Wright", color: "#06B6D4" },
    ],
    submittedBy: "benfielding",
    submittedDate: "Sep 10",
    publishedDate: "Sep 10",
    upvotes: 435,
    badge: "+423",
    category: "Machine Learning",
    paperOfTheDay: true,
  };

  return (
    <div className="min-h-screen bg-background">
      <Header />
      
      <div className="container mx-auto px-4 py-8">
        {/* Breadcrumb */}
        <div className="flex items-center space-x-2 text-sm text-muted-foreground mb-6">
          <button className="hover:text-foreground transition-colors">Papers</button>
          <span>/</span>
          <span className="text-foreground">{paper.id}</span>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-4 gap-8">
          {/* Main Content */}
          <div className="lg:col-span-3">
            {/* Paper Header */}
            <div className="mb-8">
              <div className="flex items-start justify-between mb-4">
                <h1 className="text-3xl font-bold leading-tight pr-8">{paper.title}</h1>
                <div className="flex items-center space-x-2">
                  <Button
                    variant="outline"
                    className="flex items-center space-x-2 bg-primary/5 border-primary/20 hover:bg-primary/10"
                  >
                    <ArrowUp className="w-4 h-4" />
                    <span>Upvote</span>
                    <span className="font-semibold">{paper.upvotes}</span>
                  </Button>
                  <div className="flex items-center space-x-1">
                    {/* Colorful author avatars */}
                    <div className="flex -space-x-1">
                      {[...Array(12)].map((_, i) => (
                        <div
                          key={i}
                          className="w-6 h-6 rounded-full border-2 border-background"
                          style={{ backgroundColor: `hsl(${(i * 30) % 360}, 70%, 60%)` }}
                        />
                      ))}
                    </div>
                    <Badge variant="secondary" className="bg-paper-orange/10 text-paper-orange">
                      {paper.badge}
                    </Badge>
                  </div>
                </div>
              </div>

              {/* Metadata */}
              <div className="flex flex-wrap items-center gap-4 text-sm text-muted-foreground mb-6">
                <div className="flex items-center space-x-1">
                  <span>Published on {paper.publishedDate}</span>
                </div>
                <div className="flex items-center space-x-2">
                  <span>Submitted by</span>
                  <Avatar className="w-5 h-5">
                    <AvatarFallback className="bg-paper-pink text-white text-xs">
                      {paper.submittedBy[0].toUpperCase()}
                    </AvatarFallback>
                  </Avatar>
                  <span className="text-paper-blue font-medium">{paper.submittedBy}</span>
                  <span>on {paper.submittedDate}</span>
                </div>
                {paper.paperOfTheDay && (
                  <Badge className="bg-gradient-primary text-white">
                    #1 Paper of the day
                  </Badge>
                )}
              </div>

              {/* Authors */}
              <div className="mb-6">
                <span className="text-sm font-semibold text-foreground">Authors: </span>
                <span className="text-sm">
                  {paper.authors.map((author, index) => (
                    <span key={index}>
                      <button className="text-paper-blue hover:underline font-medium">
                        {author.name}
                      </button>
                      {index < paper.authors.length - 1 && ", "}
                    </span>
                  ))}
                </span>
              </div>
            </div>

            {/* Abstract */}
            <Card className="mb-8">
              <CardHeader>
                <CardTitle className="flex items-center space-x-2">
                  <BookOpen className="w-5 h-5" />
                  <span>Abstract</span>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="border-l-4 border-primary bg-primary/5 p-4 rounded-r-lg mb-4">
                  <p className="text-sm text-muted-foreground mb-2">
                    <span className="text-primary">✨</span> AI generated summary
                  </p>
                  <p className="text-sm leading-relaxed">
                    {paper.abstract.split('\n\n')[0]}
                  </p>
                </div>
                <div className="prose prose-sm max-w-none">
                  <p className="leading-relaxed">{paper.abstract.split('\n\n')[1]}</p>
                </div>
              </CardContent>
            </Card>

            {/* Actions */}
            <div className="flex items-center space-x-4 mb-12">
              <Button variant="outline" className="flex items-center space-x-2">
                <ExternalLink className="w-4 h-4" />
                <span>View on arXiv</span>
              </Button>
              <Button variant="outline" className="flex items-center space-x-2">
                <BookOpen className="w-4 h-4" />
                <span>PDF</span>
              </Button>
              <Button variant="outline" className="flex items-center space-x-2">
                <ExternalLink className="w-4 h-4" />
                <span>Project page</span>
              </Button>
              <Button variant="outline" className="flex items-center space-x-2">
                <ExternalLink className="w-4 h-4" />
                <span>Github</span>
              </Button>
              <Button variant="outline" className="flex items-center space-x-2">
                <Bookmark className="w-4 h-4" />
                <span>Save</span>
              </Button>
            </div>

            {/* Evaluation Results */}
            <Card className="mb-8">
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="text-xl font-semibold">Evaluation results from the paper</CardTitle>
                  <Button variant="ghost" size="sm" className="flex items-center space-x-1 text-muted-foreground">
                    <Edit className="w-4 h-4" />
                    <span>Edit</span>
                  </Button>
                </div>
              </CardHeader>
              <CardContent>
                {/* SOTA Badge */}
                <div className="bg-muted/30 rounded-lg p-4 mb-6">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-3">
                      <Trophy className="w-5 h-5 text-yellow-600" />
                      <span className="font-semibold">SOTA for </span>
                      <button className="text-primary hover:underline font-semibold">
                        Face Detection on WIDER Face (Easy)
                      </button>
                    </div>
                    <button className="text-primary text-sm hover:underline">
                      →| Get a GitHub badge
                    </button>
                  </div>
                </div>

                {/* Evaluation Table */}
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className="border-b border-border">
                        <th className="text-left py-3 px-4 font-medium text-muted-foreground">Task</th>
                        <th className="text-left py-3 px-4 font-medium text-muted-foreground">Dataset</th>
                        <th className="text-left py-3 px-4 font-medium text-muted-foreground">Model</th>
                        <th className="text-left py-3 px-4 font-medium text-muted-foreground">Metric name</th>
                        <th className="text-left py-3 px-4 font-medium text-muted-foreground">Metric value</th>
                        <th className="text-left py-3 px-4 font-medium text-muted-foreground">Global rank</th>
                        <th className="text-left py-3 px-4 font-medium text-muted-foreground">Compare</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr className="border-b border-border hover:bg-muted/20">
                        <td className="py-4 px-4">Face Detection</td>
                        <td className="py-4 px-4">FDDB</td>
                        <td className="py-4 px-4 font-medium">DSFD</td>
                        <td className="py-4 px-4">AP</td>
                        <td className="py-4 px-4 font-semibold">0.991</td>
                        <td className="py-4 px-4 font-semibold"># 1</td>
                        <td className="py-4 px-4">
                          <Button size="sm" className="bg-emerald-500 hover:bg-emerald-600 text-white rounded-full px-4">
                            See all
                          </Button>
                        </td>
                      </tr>
                      <tr className="border-b border-border hover:bg-muted/20">
                        <td className="py-4 px-4">Face Detection</td>
                        <td className="py-4 px-4">WIDER Face (Easy)</td>
                        <td className="py-4 px-4 font-medium">DSFD</td>
                        <td className="py-4 px-4">AP</td>
                        <td className="py-4 px-4 font-semibold">0.960</td>
                        <td className="py-4 px-4 font-semibold"># 1</td>
                        <td className="py-4 px-4">
                          <Button size="sm" className="bg-emerald-500 hover:bg-emerald-600 text-white rounded-full px-4">
                            See all
                          </Button>
                        </td>
                      </tr>
                      <tr className="border-b border-border hover:bg-muted/20">
                        <td className="py-4 px-4">Face Detection</td>
                        <td className="py-4 px-4">WIDER Face (Hard)</td>
                        <td className="py-4 px-4 font-medium">DSFD</td>
                        <td className="py-4 px-4">AP</td>
                        <td className="py-4 px-4 font-semibold">0.900</td>
                        <td className="py-4 px-4 font-semibold"># 1</td>
                        <td className="py-4 px-4">
                          <Button size="sm" className="bg-emerald-500 hover:bg-emerald-600 text-white rounded-full px-4">
                            See all
                          </Button>
                        </td>
                      </tr>
                      <tr className="hover:bg-muted/20">
                        <td className="py-4 px-4">Face Detection</td>
                        <td className="py-4 px-4">WIDER Face (Medium)</td>
                        <td className="py-4 px-4 font-medium">DSFD</td>
                        <td className="py-4 px-4">AP</td>
                        <td className="py-4 px-4 font-semibold">0.953</td>
                        <td className="py-4 px-4 font-semibold"># 1</td>
                        <td className="py-4 px-4">
                          <Button size="sm" className="bg-emerald-500 hover:bg-emerald-600 text-white rounded-full px-4">
                            See all
                          </Button>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Sidebar */}
          <div className="lg:col-span-1">
            <div className="space-y-6">
              {/* Models citing this paper */}
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base flex items-center space-x-2">
                    <Zap className="w-4 h-4" />
                    <span>Models citing this paper</span>
                    <Badge variant="secondary">0</Badge>
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-sm text-muted-foreground">No model linking this paper</p>
                  <p className="text-xs text-muted-foreground mt-2">
                    Cite arxiv.org/abs/2509.08721 in a model README.md to link it from this page.
                  </p>
                </CardContent>
              </Card>

              {/* Datasets citing this paper */}
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base flex items-center space-x-2">
                    <Database className="w-4 h-4" />
                    <span>Datasets citing this paper</span>
                    <Badge variant="secondary">0</Badge>
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-sm text-muted-foreground">No dataset linking this paper</p>
                  <p className="text-xs text-muted-foreground mt-2">
                    Cite arxiv.org/abs/2509.08721 in a dataset README.md to link it from this page.
                  </p>
                </CardContent>
              </Card>

              {/* Spaces citing this paper */}
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base flex items-center space-x-2">
                    <Zap className="w-4 h-4" />
                    <span>Spaces citing this paper</span>
                    <Badge variant="secondary">0</Badge>
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-sm text-muted-foreground">No Space linking this paper</p>
                  <p className="text-xs text-muted-foreground mt-2">
                    Cite arxiv.org/abs/2509.08721 in a Space README.md to link it from this page.
                  </p>
                </CardContent>
              </Card>

              {/* Collections */}
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base flex items-center space-x-2">
                    <BookOpen className="w-4 h-4" />
                    <span>Collections including this paper</span>
                    <Badge variant="secondary">7</Badge>
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2">
                    <div className="flex items-center space-x-2">
                      <div className="w-2 h-2 bg-paper-blue rounded-full"></div>
                      <button className="text-sm text-paper-blue hover:underline">
                        RL reason model
                      </button>
                      <Badge variant="outline" className="text-xs">Collection</Badge>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default PaperDetail;