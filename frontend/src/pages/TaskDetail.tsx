import Header from "@/components/Header";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useParams, Link } from "react-router-dom";
import { ExternalLink, Github, TrendingUp } from "lucide-react";

// Sample task data - in a real app this would come from an API
const taskData = {
  "object-detection": {
    title: "Object Detection",
    categories: ["Computer Vision", "3D Object Detection"],
    papersWithCode: 1076,
    benchmarks: 27,
    description: "Object detection is the task of detecting instances of objects of a certain class within an image. The state-of-the-art methods can be categorized into two main types: one-stage methods and two stage-methods. One-stage methods prioritize inference speed, and example models include YOLO, SSD and RetinaNet. Two-stage methods prioritize detection accuracy, and example models include Mask R-CNN and Cascade R-CNN.",
    additionalInfo: "The most popular benchmark is the MSCOCO dataset. Models are typically evaluated according to a Mean Average Precision (mAP).",
    imageCredit: "Detectron",
    benchmarkResults: [
      {
        trend: "up",
        dataset: "COCO test-dev",
        bestModel: "Cascade Eff-B7 NAS-FPN (1280, self-training Copy Paste, single-scale)",
        paperTitle: "Simple Copy-Paste is a Strong Data Augmentation Method for Instance Segmentation",
        paperLink: "/paper/simple-copy-paste",
        hasCode: true,
        benchmark: "coco-test-dev"
      },
      {
        trend: "up", 
        dataset: "COCO minival",
        bestModel: "Cascade Eff-B7 NAS-FPN (1280, self-training Copy Paste, single-scale)",
        paperTitle: "Simple Copy-Paste is a Strong Data Augmentation Method for Instance Segmentation",
        paperLink: "/paper/simple-copy-paste",
        hasCode: true,
        benchmark: "coco-minival"
      },
      {
        trend: "up",
        dataset: "PASCAL VOC 2007",
        bestModel: "Cascade Eff-B7 NAS-FPN (Copy Paste pre-training, single-scale)",
        paperTitle: "Simple Copy-Paste is a Strong Data Augmentation Method for Instance Segmentation", 
        paperLink: "/paper/simple-copy-paste",
        hasCode: true,
        benchmark: "pascal-voc-2007"
      },
      {
        trend: "up",
        dataset: "KITTI Cars Easy",
        bestModel: "Patches",
        paperTitle: "Patch Refinement -- Localized 3D Object Detection",
        paperLink: "/paper/patch-refinement",
        hasCode: true,
        benchmark: "kitti-cars-easy"
      },
      {
        trend: "up",
        dataset: "CrowdHuman (full body)",
        bestModel: "IterDet (Faster RCNN, ResNet50, 2 iterations)",
        paperTitle: "IterDet: Iterative Scheme for ObjectDetection in Crowded Environments",
        paperLink: "/paper/iterdet",
        hasCode: true,
        benchmark: "crowdhuman-full-body"
      }
    ]
  },
  "image-classification": {
    title: "Image Classification", 
    categories: ["Computer Vision"],
    papersWithCode: 2341,
    benchmarks: 15,
    description: "Image classification is the task of assigning a label or class to an entire image. The model analyzes the visual content and predicts which category the image belongs to from a predefined set of classes.",
    additionalInfo: "Common benchmarks include ImageNet, CIFAR-10, and CIFAR-100. Models are typically evaluated using top-1 and top-5 accuracy metrics.",
    imageCredit: "ImageNet",
    benchmarkResults: [
      {
        trend: "up",
        dataset: "ImageNet",
        bestModel: "Vision Transformer (ViT-H/14)",
        paperTitle: "An Image is Worth 16x16 Words: Transformers for Image Recognition at Scale",
        paperLink: "/paper/vision-transformer", 
        hasCode: true,
        benchmark: "imagenet"
      }
    ]
  }
};

const TaskDetail = () => {
  const { taskId } = useParams<{ taskId: string }>();
  const task = taskData[taskId as keyof typeof taskData];

  if (!task) {
    return (
      <div className="min-h-screen bg-background">
        <Header />
        <div className="container mx-auto px-4 py-16 text-center">
          <h1 className="text-2xl font-bold mb-4">Task not found</h1>
          <Link to="/tasks">
            <Button>Back to Tasks</Button>
          </Link>
        </div>
      </div>
    );
  }

  const TrendChart = ({ trend }: { trend: string }) => (
    <div className="w-16 h-8 flex items-end space-x-1">
      {[...Array(6)].map((_, i) => (
        <div
          key={i}
          className={`w-1 bg-teal-500 rounded-sm ${
            trend === 'up' 
              ? 'h-' + Math.max(2, (i + 1) * 1.2) 
              : 'h-' + Math.max(2, (6 - i) * 1.2)
          }`}
          style={{ height: `${Math.max(8, (i + 1) * 3)}px` }}
        />
      ))}
    </div>
  );

  return (
    <div className="min-h-screen bg-background">
      <Header />
      
      {/* Hero Section */}
      <div className="container mx-auto px-4 py-8">
        <div className="flex items-start gap-8">
          {/* Task Image Placeholder */}
          <div className="w-48 h-32 bg-gradient-to-br from-blue-100 to-blue-200 rounded-lg flex items-center justify-center">
            <span className="text-4xl">🎯</span>
          </div>
          
          {/* Task Info */}
          <div className="flex-1">
            <div className="flex items-center justify-between mb-4">
              <h1 className="text-4xl font-bold">{task.title}</h1>
              <Button variant="outline" size="sm">
                ✏️ Edit Task
              </Button>
            </div>
            
            <div className="flex items-center gap-2 mb-4 text-teal-600">
              {task.categories.map((category, index) => (
                <span key={category}>
                  {category}
                  {index < task.categories.length - 1 && " • "}
                </span>
              ))}
            </div>
            
            <div className="flex items-center gap-6 text-lg">
              <span><strong>{task.papersWithCode.toLocaleString()}</strong> papers with code</span>
              <span><strong>{task.benchmarks}</strong> benchmarks</span>
            </div>
          </div>
        </div>
      </div>

      {/* About Section */}
      <div className="container mx-auto px-4 py-8">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-2xl font-bold">About</h2>
          <Button variant="ghost" size="sm" className="text-muted-foreground">
            ✏️ Edit
          </Button>
        </div>
        
        <div className="prose max-w-none mb-6">
          <p className="text-muted-foreground leading-relaxed mb-4">
            {task.description}
          </p>
          <p className="text-muted-foreground leading-relaxed mb-4">
            {task.additionalInfo}
          </p>
          <p className="text-sm text-muted-foreground">
            ( Image credit: <span className="text-teal-600">{task.imageCredit}</span> )
          </p>
        </div>
      </div>

      {/* Benchmarks Section */}
      <div className="container mx-auto px-4 py-8">
        <div className="flex items-center justify-between mb-6">
          <div className="bg-blue-600 text-white px-3 py-1 rounded">
            <h2 className="text-xl font-semibold">Benchmarks</h2>
          </div>
          <Button variant="outline" size="sm" className="text-muted-foreground">
            ➕ Add a Result
          </Button>
        </div>

        {/* Benchmarks Table */}
        <Card>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="border-b bg-muted/50">
                  <tr>
                    <th className="text-left p-4 font-medium text-muted-foreground uppercase text-sm">Trend</th>
                    <th className="text-left p-4 font-medium text-muted-foreground uppercase text-sm">Dataset</th>
                    <th className="text-left p-4 font-medium text-muted-foreground uppercase text-sm">Best Model</th>
                    <th className="text-left p-4 font-medium text-muted-foreground uppercase text-sm">Paper Title</th>
                    <th className="text-center p-4 font-medium text-muted-foreground uppercase text-sm">Paper</th>
                    <th className="text-center p-4 font-medium text-muted-foreground uppercase text-sm">Code</th>
                    <th className="text-center p-4 font-medium text-muted-foreground uppercase text-sm">Compare</th>
                  </tr>
                </thead>
                <tbody>
                  {task.benchmarkResults.map((result, index) => (
                    <tr key={index} className="border-b hover:bg-muted/20">
                      <td className="p-4">
                        <TrendChart trend={result.trend} />
                      </td>
                      <td className="p-4">
                        <div className="font-medium">{result.dataset}</div>
                      </td>
                      <td className="p-4">
                        <div className="flex items-center gap-2">
                          <span className="text-yellow-500">🏆</span>
                          <span className="font-medium">{result.bestModel}</span>
                        </div>
                      </td>
                      <td className="p-4">
                        <Link to={result.paperLink} className="text-teal-600 hover:underline">
                          {result.paperTitle}
                        </Link>
                      </td>
                      <td className="p-4 text-center">
                        <Link to={result.paperLink}>
                          <Button variant="ghost" size="icon" className="w-8 h-8 text-teal-600">
                            📄
                          </Button>
                        </Link>
                      </td>
                      <td className="p-4 text-center">
                        {result.hasCode && (
                          <Button variant="ghost" size="icon" className="w-8 h-8 text-blue-600">
                            <Github className="w-4 h-4" />
                          </Button>
                        )}
                      </td>
                      <td className="p-4 text-center">
                        <Link to={`/benchmark/${result.benchmark}`}>
                          <Button size="sm" className="bg-teal-500 hover:bg-teal-600 text-white rounded-full">
                            See all
                          </Button>
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

export default TaskDetail;