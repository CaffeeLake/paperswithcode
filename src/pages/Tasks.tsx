import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import Header from "@/components/Header";
import { BarChart, Layers, Users, FileText, Twitter } from "lucide-react";
import { Link } from "react-router-dom";

const taskCategories = [
  {
    name: "Computer Vision",
    tasks: [
      {
        id: 1,
        name: "Semantic Segmentation", 
        slug: "semantic-segmentation",
        icon: "🎯",
        leaderboards: 59,
        papers: 910
      },
      {
        id: 2,
        name: "Image Classification",
        slug: "image-classification",
        icon: "🖼️", 
        leaderboards: 127,
        papers: 769
      },
      {
        id: 3,
        name: "Object Detection",
        slug: "object-detection",
        icon: "🔍",
        leaderboards: 58, 
        papers: 644
      },
      {
        id: 4,
        name: "Image Generation",
        slug: "image-generation", 
        icon: "🎨",
        leaderboards: 92,
        papers: 318
      },
      {
        id: 5,
        name: "Denoising",
        slug: "denoising",
        icon: "✨",
        leaderboards: 16,
        papers: 300
      }
    ],
    totalTasks: 759
  },
  {
    name: "Natural Language Processing",
    tasks: [
      {
        id: 6,
        name: "Machine Translation",
        slug: "machine-translation",
        icon: "🔄",
        leaderboards: 44,
        papers: 601
      },
      {
        id: 7,
        name: "Language Modelling",
        slug: "language-modelling", 
        icon: "📝",
        leaderboards: 11,
        papers: 562
      },
      {
        id: 8,
        name: "Question Answering",
        slug: "question-answering",
        icon: "❓",
        leaderboards: 51,
        papers: 522
      },
      {
        id: 9,
        name: "Sentiment Analysis",
        slug: "sentiment-analysis",
        icon: "😊",
        leaderboards: 37,
        papers: 372
      },
      {
        id: 10,
        name: "Text Generation",
        slug: "text-generation",
        icon: "📄", 
        leaderboards: 33,
        papers: 225
      }
    ],
    totalTasks: 285
  }
];

const Tasks = () => {
  return (
    <div className="min-h-screen bg-background">
      <Header />
      
      <main className="container mx-auto px-4 py-8">
        {/* Header Section */}
        <div className="mb-8">
          <h1 className="text-4xl font-bold mb-4">Browse State-of-the-Art</h1>
          
          <div className="flex items-center space-x-4 text-muted-foreground mb-4">
            <div className="flex items-center space-x-1">
              <BarChart className="w-4 h-4" />
              <span>2515 leaderboards</span>
            </div>
            <span>•</span>
            <div className="flex items-center space-x-1">
              <Layers className="w-4 h-4" />
              <span>1507 tasks</span>
            </div>
            <span>•</span>
            <div className="flex items-center space-x-1">
              <FileText className="w-4 h-4" />
              <span>2274 datasets</span>
            </div>
            <span>•</span>
            <div className="flex items-center space-x-1">
              <Users className="w-4 h-4" />
              <span>23164 papers with code</span>
            </div>
          </div>

          <div className="flex items-center space-x-2 text-primary">
            <span>Follow on</span>
            <Twitter className="w-4 h-4" />
            <span className="font-medium">Twitter for updates</span>
          </div>
        </div>

        {/* Task Categories */}
        {taskCategories.map((category, categoryIndex) => (
          <div key={category.name} className="mb-12">
            <h2 className="text-2xl font-semibold mb-6">{category.name}</h2>
            
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-6 mb-6">
              {category.tasks.map((task) => (
                <Link key={task.id} to={`/tasks/${task.slug}`}>
                  <Card className="p-6 hover:shadow-md transition-shadow cursor-pointer border bg-card h-full">
                    <div className="flex items-start space-x-3 mb-4">
                      <div className="w-10 h-10 bg-muted rounded-lg flex items-center justify-center text-lg">
                        {task.icon}
                      </div>
                      <div className="flex-1">
                        <h3 className="font-semibold text-base leading-tight">{task.name}</h3>
                      </div>
                    </div>
                    
                    <div className="space-y-2 text-sm text-muted-foreground">
                      <div className="flex items-center space-x-1">
                        <BarChart className="w-3 h-3" />
                        <span>{task.leaderboards} leaderboards</span>
                      </div>
                      <div>{task.papers} papers with code</div>
                    </div>
                  </Card>
                </Link>
              ))}
            </div>

            <div className="text-primary font-medium">
              ▶ See all {category.totalTasks} tasks
            </div>
          </div>
        ))}
      </main>
    </div>
  );
};

export default Tasks;